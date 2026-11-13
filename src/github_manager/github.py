"""Minimal GitHub REST/GraphQL client built on the standard library."""

import base64
import contextlib
import http.client
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

API_URL = "https://api.github.com"
TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1  # wait after the k-th failed attempt: BACKOFF_SECONDS * 2 ** (k - 1)
SECONDARY_LIMIT_WAIT_SECONDS = 60
MAX_RATE_LIMIT_WAIT_SECONDS = 120
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})

logger = logging.getLogger(__name__)
# The 403 message of a private repository on the Free plan, observed in full as
# "Upgrade to GitHub Pro or make this repository public to enable this feature.".
# The response carries no structured code (only `message`, `documentation_url` and
# `status`), so a case-insensitive text match is the only signal. If GitHub rewords it,
# the repository gets an `error` result with the 403 message instead of being skipped.
RULESETS_UPGRADE = "Upgrade to GitHub Pro"

COMMIT_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) { commit { oid } }
}
"""

AUTO_MERGE_MUTATION = """
mutation($pullRequestId: ID!) {
  enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: SQUASH}) {
    pullRequest { number }
  }
}
"""

MERGE_STATE_QUERY = """
query($id: ID!) {
  node(id: $id) { ... on PullRequest { mergeStateStatus } }
}
"""
UNKNOWN_MERGE_STATE = "UNKNOWN"


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
    node_id: str = ""  # GraphQL id, needed to enable auto-merge
    auto_merge: bool = False  # auto-merge is on, as of when the pull request was read


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


class _Retry(Exception):
    """One failed attempt that may be retried after `wait` seconds."""

    def __init__(self, error: GitHubError, reason: str, wait: float) -> None:
        super().__init__(str(error))
        self.error = error
        self.reason = reason
        self.wait = wait


def _rate_limit_wait(exc: urllib.error.HTTPError, now: float) -> float | None:
    """Seconds to wait when the response is a rate limit, otherwise None."""
    headers = exc.headers
    retry_after = headers.get("Retry-After") if headers else None
    exhausted = bool(headers) and headers.get("X-RateLimit-Remaining") == "0"
    if exc.code != 429 and not (exc.code == 403 and (retry_after is not None or exhausted)):
        return None
    if retry_after is not None:
        with contextlib.suppress(ValueError):
            return float(int(retry_after.strip()))
    reset = headers.get("X-RateLimit-Reset") if exhausted else None
    if reset is not None:
        with contextlib.suppress(ValueError):
            return max(1.0, float(reset) - now + 1)
    return float(SECONDARY_LIMIT_WAIT_SECONDS)


class GitHub:
    def __init__(
        self,
        token: str,
        api_url: str = API_URL,
        opener: Opener = _default_opener,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ):
        if not api_url.startswith("https://"):
            raise GitHubError(f"API URL must use https: {api_url}")
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._open = opener
        self._sleep = sleep
        self._clock = clock

    # --- transport ---------------------------------------------------------

    def _request(self, method: str, url: str, body: Any = None) -> tuple[Any, str]:
        # Absolute URLs come from pagination links; the token never leaves the API root.
        if url.startswith("/"):
            url = self._api_url + url
        elif not url.startswith(self._api_url + "/"):
            raise GitHubError(f"refusing to call a URL outside {self._api_url}: {url}")
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._attempt(method, url, data, attempt)
            except _Retry as retry:
                if attempt == MAX_ATTEMPTS:
                    raise retry.error from retry.error.__cause__
                logger.warning(
                    "%s %s: %s; retrying in %s s (attempt %d of %d failed)",
                    method,
                    url,
                    retry.reason,
                    retry.wait,
                    attempt,
                    MAX_ATTEMPTS,
                )
                self._sleep(retry.wait)
        raise AssertionError("unreachable")  # pragma: no cover

    def _attempt(self, method: str, url: str, data: bytes | None, attempt: int) -> tuple[Any, str]:
        """Send the request once; raise _Retry when another attempt is allowed."""
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        backoff = BACKOFF_SECONDS * 2 ** (attempt - 1)
        try:
            with self._open(request) as response:
                payload = response.read()
                link = response.headers.get("Link", "") or ""
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode(errors="replace")
            except OSError, http.client.HTTPException:
                # The error body itself was cut off; the status is still known.
                detail = exc.reason
            with contextlib.suppress(json.JSONDecodeError, AttributeError):
                detail = json.loads(detail).get("message", detail)
            message = f"{method} {url}: HTTP {exc.code}: {detail}"
            wait = _rate_limit_wait(exc, self._clock())
            if wait is not None:
                if wait > MAX_RATE_LIMIT_WAIT_SECONDS:
                    raise GitHubError(
                        f"{message} (rate limited; resets in {wait:.0f} s)", exc.code
                    ) from exc
                error = GitHubError(message, exc.code)
                error.__cause__ = exc
                raise _Retry(error, f"HTTP {exc.code} (rate limited)", wait) from exc
            error = GitHubError(message, exc.code)
            if exc.code in TRANSIENT_STATUSES and method == "GET":
                error.__cause__ = exc
                raise _Retry(error, f"HTTP {exc.code}", backoff) from exc
            raise error from exc
        except (OSError, http.client.HTTPException) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            error = GitHubError(f"{method} {url}: {reason}")
            if method == "GET":
                error.__cause__ = exc
                raise _Retry(error, str(reason) or type(exc).__name__, backoff) from exc
            raise error from exc
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
        return _pull_request(pulls[0]) if pulls else None

    def create_pr(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequest:
        pull = self.call(
            "POST",
            f"/repos/{repo}/pulls",
            {"title": title, "head": head, "base": base, "body": body},
        )
        return _pull_request(pull)

    def update_pr(self, repo: str, number: int, title: str, body: str) -> None:
        self.call("PATCH", f"/repos/{repo}/pulls/{number}", {"title": title, "body": body})

    def close_pr(self, repo: str, number: int, comment: str) -> None:
        self.call("POST", f"/repos/{repo}/issues/{number}/comments", {"body": comment})
        self.call("PATCH", f"/repos/{repo}/pulls/{number}", {"state": "closed"})

    def enable_auto_merge(self, repo: str, pull: PullRequest) -> None:
        """Squash auto-merge; GitHub refuses it when the pull request can already be merged."""
        self.graphql(AUTO_MERGE_MUTATION, {"pullRequestId": pull.node_id})

    def merge_state(self, repo: str, pull: PullRequest) -> str:
        """The `mergeStateStatus` of the pull request, `UNKNOWN` when GitHub returns none."""
        data = self.graphql(MERGE_STATE_QUERY, {"id": pull.node_id})
        node = data.get("node") if isinstance(data, dict) else None
        state = node.get("mergeStateStatus") if isinstance(node, dict) else None
        return state if isinstance(state, str) else UNKNOWN_MERGE_STATE

    def merge_pr(self, repo: str, number: int) -> None:
        self.call("PUT", f"/repos/{repo}/pulls/{number}/merge", {"merge_method": "squash"})

    # --- repository rulesets -------------------------------------------------

    def list_rulesets(self, repo: str) -> list[dict[str, Any]] | None:
        """Repository-level rulesets, or None when the plan does not offer them."""
        try:
            return self.paginate(f"/repos/{repo}/rulesets?includes_parents=false&per_page=100")
        except GitHubError as exc:
            if exc.status == 403 and RULESETS_UPGRADE.lower() in str(exc).lower():
                return None
            raise

    def get_ruleset(self, repo: str, ruleset_id: int) -> dict[str, Any]:
        return self.call("GET", f"/repos/{repo}/rulesets/{ruleset_id}?includes_parents=false")

    def create_ruleset(self, repo: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.call("POST", f"/repos/{repo}/rulesets", payload)

    def update_ruleset(self, repo: str, ruleset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.call("PUT", f"/repos/{repo}/rulesets/{ruleset_id}", payload)

    # --- repository settings -------------------------------------------------

    def repo_settings(self, repo: str) -> dict[str, Any]:
        """The repository as GitHub returns it; settings the token may not read are absent."""
        return dict(self.call("GET", f"/repos/{repo}"))

    def update_repo_settings(self, repo: str, settings: dict[str, Any]) -> None:
        self.call("PATCH", f"/repos/{repo}", settings)


def _pull_request(raw: dict[str, Any]) -> PullRequest:
    return PullRequest(
        raw["number"], raw["html_url"], raw["node_id"], raw.get("auto_merge") is not None
    )


def _q(value: str) -> str:
    return urllib.parse.quote(value, safe="/")
