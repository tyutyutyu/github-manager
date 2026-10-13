"""Minimal GitHub REST/GraphQL client built on the standard library."""

import base64
import contextlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API_URL = "https://api.github.com"
TIMEOUT_SECONDS = 30

COMMIT_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) { commit { oid } }
}
"""


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Repo:
    name: str
    full_name: str
    default_branch: str
    archived: bool
    fork: bool


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str


type Opener = Callable[[urllib.request.Request], Any]


def _default_opener(request: urllib.request.Request) -> Any:
    # The URL is always under the https API root; see GitHub._request.
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)  # noqa: S310


def resolve_token() -> str:
    """Token from GH_TOKEN / GITHUB_TOKEN, falling back to the logged-in gh CLI."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if token := os.environ.get(name, "").strip():
            return token
    gh = shutil.which("gh")
    if gh:
        result = subprocess.run(  # noqa: S603 - absolute path, fixed arguments
            [gh, "auth", "token"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise GitHubError("no GitHub token: set GH_TOKEN or log in with `gh auth login`")


class GitHub:
    def __init__(self, token: str, api_url: str = API_URL, opener: Opener = _default_opener):
        if not api_url.startswith("https://"):
            raise GitHubError(f"API URL must use https: {api_url}")
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._open = opener

    # --- transport ---------------------------------------------------------

    def _request(self, method: str, url: str, body: Any = None) -> tuple[Any, str]:
        # Absolute URLs come from pagination links; the token never leaves the API root.
        if url.startswith("/"):
            url = self._api_url + url
        elif not url.startswith(self._api_url + "/"):
            raise GitHubError(f"refusing to call a URL outside {self._api_url}: {url}")
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._open(request) as response:
                payload = response.read()
                link = response.headers.get("Link", "") or ""
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            with contextlib.suppress(json.JSONDecodeError, AttributeError):
                detail = json.loads(detail).get("message", detail)
            raise GitHubError(f"{method} {url}: HTTP {exc.code}: {detail}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"{method} {url}: {exc.reason}") from exc
        return (json.loads(payload) if payload else None), link

    def call(self, method: str, path: str, body: Any = None) -> Any:
        return self._request(method, path, body)[0]

    def paginate(self, path: str) -> list[Any]:
        items: list[Any] = []
        url: str | None = path
        while url:
            page, link = self._request("GET", url)
            items.extend(page)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return items

    def graphql(self, query: str, variables: dict[str, Any]) -> Any:
        result = self.call("POST", "/graphql", {"query": query, "variables": variables})
        if result.get("errors"):
            messages = "; ".join(error.get("message", "?") for error in result["errors"])
            raise GitHubError(f"GraphQL: {messages}")
        return result["data"]

    # --- repositories ------------------------------------------------------

    def list_repos(self, owner: str) -> list[Repo]:
        login = self.call("GET", "/user")["login"]
        if login.lower() == owner.lower():
            raw = self.paginate("/user/repos?affiliation=owner&per_page=100")
        else:
            raw = self.paginate(f"/orgs/{_q(owner)}/repos?type=all&per_page=100")
        return [
            Repo(
                name=item["name"],
                full_name=item["full_name"],
                default_branch=item["default_branch"],
                archived=item["archived"],
                fork=item["fork"],
            )
            for item in raw
        ]

    def branch_sha(self, repo: str, branch: str) -> str | None:
        try:
            ref = self.call("GET", f"/repos/{repo}/git/ref/heads/{_q(branch)}")
        except GitHubError as exc:
            if exc.status in (404, 409):  # 409: empty repository
                return None
            raise
        return ref["object"]["sha"]

    def compare(self, repo: str, base: str, head: str) -> tuple[int, int, set[str]]:
        """Commits `head` is ahead of / behind `base`, and the paths it changes."""
        result = self.call("GET", f"/repos/{repo}/compare/{base}...{head}")
        paths = {item["filename"] for item in result.get("files", [])}
        return result["ahead_by"], result["behind_by"], paths

    def tree_paths(self, repo: str, sha: str) -> set[str] | None:
        """All blob paths at `sha`, or None when the listing is unavailable or truncated."""
        try:
            tree = self.call("GET", f"/repos/{repo}/git/trees/{sha}?recursive=1")
        except GitHubError as exc:
            if exc.status == 404:  # e.g. a commit with the empty tree
                return None
            raise
        if tree.get("truncated"):
            return None
        return {entry["path"] for entry in tree["tree"] if entry["type"] == "blob"}

    def read_file(self, repo: str, path: str, ref: str) -> str | None:
        try:
            item = self.call("GET", f"/repos/{repo}/contents/{_q(path)}?ref={_q(ref)}")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise
        if not isinstance(item, dict) or item.get("type") != "file":
            raise GitHubError(f"{repo}:{path} is not a regular file")
        if item.get("encoding") != "base64":
            raise GitHubError(f"{repo}:{path} is too large to read through the contents API")
        try:
            return base64.b64decode(item["content"]).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitHubError(f"{repo}:{path} is not valid UTF-8") from exc

    # --- branches and commits ----------------------------------------------

    def reset_branch(self, repo: str, branch: str, sha: str, *, exists: bool) -> None:
        if exists:
            self.call(
                "PATCH", f"/repos/{repo}/git/refs/heads/{_q(branch)}", {"sha": sha, "force": True}
            )
        else:
            self.call(
                "POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha}
            )

    def delete_branch(self, repo: str, branch: str) -> None:
        self.call("DELETE", f"/repos/{repo}/git/refs/heads/{_q(branch)}")

    def commit_files(
        self, repo: str, branch: str, head_sha: str, message: str, files: dict[str, str]
    ) -> str:
        """One commit with all file changes; GitHub signs it, so it shows as verified."""
        headline, _, body = message.partition("\n")
        additions = [
            {"path": path, "contents": base64.b64encode(content.encode()).decode()}
            for path, content in sorted(files.items())
        ]
        data = self.graphql(
            COMMIT_MUTATION,
            {
                "input": {
                    "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
                    "expectedHeadOid": head_sha,
                    "message": {"headline": headline, "body": body.strip()},
                    "fileChanges": {"additions": additions},
                }
            },
        )
        return data["createCommitOnBranch"]["commit"]["oid"]

    # --- pull requests -----------------------------------------------------

    def find_open_pr(self, repo: str, branch: str) -> PullRequest | None:
        owner = repo.split("/", 1)[0]
        head = _q(f"{owner}:{branch}")
        pulls = self.call("GET", f"/repos/{repo}/pulls?state=open&head={head}")
        return PullRequest(pulls[0]["number"], pulls[0]["html_url"]) if pulls else None

    def create_pr(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequest:
        pull = self.call(
            "POST",
            f"/repos/{repo}/pulls",
            {"title": title, "head": head, "base": base, "body": body},
        )
        return PullRequest(pull["number"], pull["html_url"])

    def update_pr(self, repo: str, number: int, title: str, body: str) -> None:
        self.call("PATCH", f"/repos/{repo}/pulls/{number}", {"title": title, "body": body})

    def close_pr(self, repo: str, number: int, comment: str) -> None:
        self.call("POST", f"/repos/{repo}/issues/{number}/comments", {"body": comment})
        self.call("PATCH", f"/repos/{repo}/pulls/{number}", {"state": "closed"})


def _q(value: str) -> str:
    return urllib.parse.quote(value, safe="/")
