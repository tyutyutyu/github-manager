import base64
import io
import json
import subprocess
import urllib.error
import urllib.request
from email.message import Message

import pytest
from github import GithubException

from github_manager import github
from github_manager.github import GitHub, GitHubError, resolve_token

API = "https://api.github.com"


class FakeResponse(io.BytesIO):
    def __init__(self, raw: bytes, headers: Message) -> None:
        super().__init__(raw)
        self.headers = headers


class FakeHttp:
    """Records requests and replays queued responses: (status, body, link)."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object]] = []
        self.responses: list[tuple[int, object, str]] = []

    def queue(self, body: object = None, status: int = 200, link: str = "") -> FakeHttp:
        self.responses.append((status, body, link))
        return self

    def __call__(self, request: urllib.request.Request):
        data = request.data
        body = json.loads(data) if isinstance(data, bytes) else None
        self.requests.append((request.get_method(), request.full_url, body))
        assert request.get_header("Authorization") == "Bearer secret"
        status, payload, link = self.responses.pop(0)
        raw = b"" if payload is None else json.dumps(payload).encode()
        headers = Message()
        if link:
            headers["Link"] = link
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", headers, io.BytesIO(raw))
        return FakeResponse(raw, headers)


@pytest.fixture
def http() -> FakeHttp:
    return FakeHttp()


@pytest.fixture
def client(http: FakeHttp) -> GitHub:
    return GitHub("secret", opener=http)


def encoded(text: str) -> dict[str, str]:
    return {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(text.encode()).decode(),
    }


def test_list_repos_for_user_follows_pagination(http: FakeHttp, client: GitHub) -> None:
    repo = {"name": "a", "full_name": "me/a", "default_branch": "main", "archived": False}
    http.queue({"login": "Me"})
    http.queue([{**repo, "fork": False}], link=f'<{API}/user/repos?page=2>; rel="next"')
    http.queue([{**repo, "name": "b", "fork": True}])

    repos = client.list_repos("me")

    assert [r.name for r in repos] == ["a", "b"]
    assert http.requests[1][1] == f"{API}/user/repos?affiliation=owner&per_page=100"
    assert http.requests[2][1] == f"{API}/user/repos?page=2"


def test_list_repos_for_organization(http: FakeHttp, client: GitHub) -> None:
    http.queue({"login": "me"}).queue([])
    assert client.list_repos("org") == []
    assert http.requests[1][1] == f"{API}/orgs/org/repos?type=all&per_page=100"


def test_pagination_never_sends_the_token_elsewhere(http: FakeHttp, client: GitHub) -> None:
    http.queue([], link='<https://evil.example/x>; rel="next"')
    with pytest.raises(GitHubError, match="refusing"):
        client.paginate("/user/repos")


def test_api_url_must_be_https() -> None:
    with pytest.raises(GitHubError, match="https"):
        GitHub("secret", api_url="http://api.github.com")


def test_read_file(http: FakeHttp, client: GitHub) -> None:
    http.queue(encoded("árvíztűrő\n"))
    assert client.read_file("me/a", "dir/.gitignore", "abc") == "árvíztűrő\n"
    assert http.requests[0][1] == f"{API}/repos/me/a/contents/dir/.gitignore?ref=abc"

    http.queue({"message": "Not Found"}, status=404)
    assert client.read_file("me/a", "x", "abc") is None


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "not a regular file"),
        ({"type": "file", "encoding": "none", "content": ""}, "too large"),
        ({"type": "file", "encoding": "base64", "content": "/w=="}, "not valid UTF-8"),
    ],
)
def test_read_file_rejects_unusable_content(http: FakeHttp, client: GitHub, payload, message):
    http.queue(payload)
    with pytest.raises(GitHubError, match=message):
        client.read_file("me/a", "x", "abc")


def test_http_errors_carry_status_and_message(http: FakeHttp, client: GitHub) -> None:
    http.queue({"message": "Bad credentials"}, status=401)
    with pytest.raises(GitHubError, match="HTTP 401: Bad credentials") as info:
        client.read_file("me/a", "x", "abc")
    assert info.value.status == 401


def test_network_errors_are_wrapped() -> None:
    def offline(request):
        raise urllib.error.URLError("no route")

    with pytest.raises(GitHubError, match="no route"):
        GitHub("secret", opener=offline).call("GET", "/user")


def test_branch_sha(http: FakeHttp, client: GitHub) -> None:
    http.queue({"object": {"sha": "abc"}})
    http.queue({"message": "Git Repository is empty."}, status=409)
    http.queue({"message": "Server Error"}, status=500)
    assert client.branch_sha("me/a", "github-manager/compliance") == "abc"
    assert http.requests[0][1] == f"{API}/repos/me/a/git/ref/heads/github-manager/compliance"
    assert client.branch_sha("me/a", "main") is None
    with pytest.raises(GitHubError):
        client.branch_sha("me/a", "main")


def test_tree_paths(http: FakeHttp, client: GitHub) -> None:
    tree = [{"path": "a", "type": "blob"}, {"path": "d", "type": "tree"}]
    http.queue({"truncated": False, "tree": tree})
    http.queue({"truncated": True, "tree": []})
    http.queue({"message": "Not Found"}, status=404)
    http.queue({"message": "Server Error"}, status=500)
    assert client.tree_paths("me/a", "s") == {"a"}
    assert client.tree_paths("me/a", "s") is None
    assert client.tree_paths("me/a", "s") is None
    with pytest.raises(GitHubError):
        client.tree_paths("me/a", "s")


def test_compare(http: FakeHttp, client: GitHub) -> None:
    http.queue({"ahead_by": 1, "behind_by": 0, "files": [{"filename": ".gitignore"}]})
    assert client.compare("me/a", "b", "h") == (1, 0, {".gitignore"})


def test_branch_management(http: FakeHttp, client: GitHub) -> None:
    http.queue({}).queue({}).queue()
    client.reset_branch("me/a", "fix", "s1", exists=True)
    client.reset_branch("me/a", "fix", "s1", exists=False)
    client.delete_branch("me/a", "fix")
    assert http.requests == [
        ("PATCH", f"{API}/repos/me/a/git/refs/heads/fix", {"sha": "s1", "force": True}),
        ("POST", f"{API}/repos/me/a/git/refs", {"ref": "refs/heads/fix", "sha": "s1"}),
        ("DELETE", f"{API}/repos/me/a/git/refs/heads/fix", None),
    ]


def test_commit_files_uses_graphql(http: FakeHttp, client: GitHub) -> None:
    http.queue({"data": {"createCommitOnBranch": {"commit": {"oid": "new"}}}})
    sha = client.commit_files("me/a", "fix", "s1", "title\n\n- detail", {"b": "2", "a": "1"})

    assert sha == "new"
    payload = http.requests[0][2]
    assert isinstance(payload, dict)
    commit = payload["variables"]["input"]
    assert commit["expectedHeadOid"] == "s1"
    assert commit["message"] == {"headline": "title", "body": "- detail"}
    assert [item["path"] for item in commit["fileChanges"]["additions"]] == ["a", "b"]


def test_graphql_errors_raise(http: FakeHttp, client: GitHub) -> None:
    http.queue({"errors": [{"message": "Expected head mismatch"}]})
    with pytest.raises(GitHubError, match="Expected head mismatch"):
        client.commit_files("me/a", "fix", "s1", "t", {"a": "1"})


def test_pull_requests(http: FakeHttp, client: GitHub) -> None:
    pull = {"number": 7, "html_url": "https://github.com/me/a/pull/7"}
    http.queue([pull]).queue([]).queue(pull).queue({}).queue({}).queue({})

    assert client.find_open_pr("me/a", "fix") == github.PullRequest(7, pull["html_url"])
    assert http.requests[0][1] == f"{API}/repos/me/a/pulls?state=open&head=me%3Afix"
    assert client.find_open_pr("me/a", "fix") is None
    assert client.create_pr("me/a", "main", "fix", "t", "b").number == 7
    client.update_pr("me/a", 7, "t", "b2")
    client.close_pr("me/a", 7, "bye")
    assert [request[:2] for request in http.requests[3:]] == [
        ("PATCH", f"{API}/repos/me/a/pulls/7"),
        ("POST", f"{API}/repos/me/a/issues/7/comments"),
        ("PATCH", f"{API}/repos/me/a/pulls/7"),
    ]


def test_resolve_token_prefers_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", " env-token ")
    assert resolve_token() == "env-token"


def test_resolve_token_falls_back_to_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github.shutil, "which", lambda name: "/usr/bin/gh")
    completed = subprocess.CompletedProcess(["gh"], 0, stdout="gh-token\n")
    monkeypatch.setattr(github.subprocess, "run", lambda *args, **kwargs: completed)
    assert resolve_token() == "gh-token"

    monkeypatch.setattr(github.shutil, "which", lambda name: None)
    with pytest.raises(GitHubError, match="no GitHub token"):
        resolve_token()


class FakeRepository:
    def __init__(self, raw_data: dict[str, object]) -> None:
        self.raw_data = raw_data
        self.edits: list[dict[str, object]] = []

    def edit(self, **settings: object) -> None:
        self.edits.append(settings)


def test_repo_settings_use_pygithub(monkeypatch: pytest.MonkeyPatch, client: GitHub) -> None:
    repository = FakeRepository({"full_name": "o/r", "delete_branch_on_merge": False})
    requested: list[str] = []

    def get_repo(name: str) -> FakeRepository:
        requested.append(name)
        return repository

    monkeypatch.setattr(client._client, "get_repo", get_repo)
    assert client.repo_settings("o/r")["delete_branch_on_merge"] is False
    client.update_repo_settings("o/r", {"delete_branch_on_merge": True})
    assert repository.edits == [{"delete_branch_on_merge": True}]
    assert requested == ["o/r", "o/r"]


def test_update_repo_settings_passes_security_and_analysis(
    monkeypatch: pytest.MonkeyPatch, client: GitHub
) -> None:
    repository = FakeRepository({"full_name": "o/r"})
    monkeypatch.setattr(client._client, "get_repo", lambda name: repository)
    payload = {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }
    client.update_repo_settings("o/r", {"security_and_analysis": payload})
    assert repository.edits == [{"security_and_analysis": payload}]


@pytest.mark.parametrize(
    "data", [{"message": "Resource not accessible"}, "Resource not accessible"]
)
def test_repo_settings_errors_are_wrapped(
    monkeypatch: pytest.MonkeyPatch, client: GitHub, data: object
) -> None:
    def get_repo(name: str) -> FakeRepository:
        raise GithubException(403, data)

    monkeypatch.setattr(client._client, "get_repo", get_repo)
    with pytest.raises(GitHubError, match="GET /repos/o/r: HTTP 403: Resource not accessible"):
        client.repo_settings("o/r")
    with pytest.raises(GitHubError, match="PATCH /repos/o/r: HTTP 403") as info:
        client.update_repo_settings("o/r", {"delete_branch_on_merge": True})
    assert info.value.status == 403
