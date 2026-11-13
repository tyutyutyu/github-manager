import base64
import io
import json
import logging
import subprocess
import urllib.error
import urllib.request
from email.message import Message
from http.client import IncompleteRead

import pytest

from github_manager import github
from github_manager.github import GitHub, GitHubError, resolve_token

API = "https://api.github.com"


class FakeResponse(io.BytesIO):
    def __init__(self, raw: bytes, headers: Message) -> None:
        super().__init__(raw)
        self.headers = headers


class FakeHttp:
    """Records requests and replays queued responses or network errors."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object]] = []
        self.responses: list[tuple[int, object, str, dict[str, str]] | BaseException] = []

    def queue(
        self,
        body: object = None,
        status: int = 200,
        link: str = "",
        headers: dict[str, str] | None = None,
    ) -> FakeHttp:
        self.responses.append((status, body, link, headers or {}))
        return self

    def queue_error(self, exc: BaseException) -> FakeHttp:
        self.responses.append(exc)
        return self

    def __call__(self, request: urllib.request.Request):
        data = request.data
        body = json.loads(data) if isinstance(data, bytes) else None
        self.requests.append((request.get_method(), request.full_url, body))
        assert request.get_header("Authorization") == "Bearer secret"
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        status, payload, link, extra = response
        raw = b"" if payload is None else json.dumps(payload).encode()
        headers = Message()
        if link:
            headers["Link"] = link
        for name, value in extra.items():
            headers[name] = value
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", headers, io.BytesIO(raw))
        return FakeResponse(raw, headers)


@pytest.fixture
def http() -> FakeHttp:
    return FakeHttp()


class FakeTime:
    """Records sleeps instead of waiting; `now` is the clock value."""

    def __init__(self) -> None:
        self.now = 1_000_000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def clock(self) -> float:
        return self.now


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def client(http: FakeHttp, fake_time: FakeTime) -> GitHub:
    return GitHub("secret", opener=http, sleep=fake_time.sleep, clock=fake_time.clock)


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
        GitHub("secret", opener=offline, sleep=lambda _: None).call("GET", "/user")


def test_branch_sha(http: FakeHttp, client: GitHub) -> None:
    http.queue({"object": {"sha": "abc"}})
    http.queue({"message": "Git Repository is empty."}, status=409)
    for _ in range(github.MAX_ATTEMPTS):
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
    for _ in range(github.MAX_ATTEMPTS):
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
    pull = {"number": 7, "html_url": "https://github.com/me/a/pull/7", "node_id": "PR_7"}
    http.queue([pull]).queue([]).queue(pull).queue({}).queue({}).queue({})

    assert client.find_open_pr("me/a", "fix") == github.PullRequest(7, pull["html_url"], "PR_7")
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


def test_pull_request_reports_auto_merge_state(http: FakeHttp, client: GitHub) -> None:
    pull = {
        "number": 7,
        "html_url": "u",
        "node_id": "PR_7",
        "auto_merge": {"merge_method": "squash"},
    }
    http.queue([pull]).queue([{**pull, "auto_merge": None}])

    assert client.find_open_pr("me/a", "fix") == github.PullRequest(7, "u", "PR_7", auto_merge=True)
    assert client.find_open_pr("me/a", "fix") == github.PullRequest(7, "u", "PR_7")


def test_enable_auto_merge_sends_squash_mutation(http: FakeHttp, client: GitHub) -> None:
    http.queue({"data": {"enablePullRequestAutoMerge": {"pullRequest": {"number": 7}}}})
    client.enable_auto_merge("me/a", github.PullRequest(7, "u", "PR_7"))

    method, url, body = http.requests[0]
    assert (method, url) == ("POST", f"{API}/graphql")
    assert isinstance(body, dict)
    assert "enablePullRequestAutoMerge" in body["query"]
    assert "mergeMethod: SQUASH" in body["query"]
    assert body["variables"] == {"pullRequestId": "PR_7"}


def test_enable_auto_merge_raises_graphql_errors(http: FakeHttp, client: GitHub) -> None:
    http.queue({"errors": [{"message": "Pull request is in clean status"}]})
    with pytest.raises(GitHubError, match="clean status"):
        client.enable_auto_merge("me/a", github.PullRequest(7, "u", "PR_7"))


def test_merge_pr_squash_merges_through_rest(http: FakeHttp, client: GitHub) -> None:
    http.queue({"merged": True})
    client.merge_pr("me/a", 7)

    assert http.requests == [("PUT", f"{API}/repos/me/a/pulls/7/merge", {"merge_method": "squash"})]


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


def test_repo_settings_reads_the_repository(http: FakeHttp, client: GitHub) -> None:
    http.queue({"full_name": "o/r", "delete_branch_on_merge": False})
    assert client.repo_settings("o/r") == {"full_name": "o/r", "delete_branch_on_merge": False}
    assert http.requests == [("GET", f"{API}/repos/o/r", None)]


def test_update_repo_settings_sends_one_patch(http: FakeHttp, client: GitHub) -> None:
    http.queue({"full_name": "o/r"})
    client.update_repo_settings("o/r", {"delete_branch_on_merge": True})
    assert http.requests == [("PATCH", f"{API}/repos/o/r", {"delete_branch_on_merge": True})]


def test_update_repo_settings_passes_security_and_analysis(http: FakeHttp, client: GitHub) -> None:
    payload = {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }
    http.queue({"full_name": "o/r"})
    client.update_repo_settings("o/r", {"security_and_analysis": payload})
    assert http.requests == [("PATCH", f"{API}/repos/o/r", {"security_and_analysis": payload})]


def test_repo_settings_errors_carry_the_status(http: FakeHttp, client: GitHub) -> None:
    error = {"message": "Resource not accessible"}
    http.queue(error, status=403).queue(error, status=403)
    with pytest.raises(GitHubError, match="Resource not accessible") as read:
        client.repo_settings("o/r")
    with pytest.raises(GitHubError, match="Resource not accessible") as write:
        client.update_repo_settings("o/r", {"delete_branch_on_merge": True})
    assert read.value.status == 403
    assert write.value.status == 403


def test_list_rulesets_paginates_repository_level_only(http: FakeHttp, client: GitHub) -> None:
    next_url = f"{API}/repositories/1/rulesets?includes_parents=false&per_page=100&page=2"
    http.queue([{"id": 1}], link=f'<{next_url}>; rel="next"').queue([{"id": 2}])
    assert client.list_rulesets("o/r") == [{"id": 1}, {"id": 2}]
    assert http.requests == [
        ("GET", f"{API}/repos/o/r/rulesets?includes_parents=false&per_page=100", None),
        ("GET", next_url, None),
    ]


def test_list_rulesets_on_free_plan_is_none(http: FakeHttp, client: GitHub) -> None:
    message = "Upgrade to GitHub Pro or make this repository public to enable this feature."
    http.queue({"message": message}, status=403)
    assert client.list_rulesets("o/r") is None


@pytest.mark.parametrize("status", [403, 404, 500])
def test_list_rulesets_other_errors_are_raised(http: FakeHttp, client: GitHub, status) -> None:
    attempts = github.MAX_ATTEMPTS if status in github.TRANSIENT_STATUSES else 1
    for _ in range(attempts):
        http.queue({"message": "Resource not accessible by personal access token"}, status=status)
    with pytest.raises(GitHubError, match=f"HTTP {status}") as info:
        client.list_rulesets("o/r")
    assert info.value.status == status


def test_ruleset_reads_and_writes(http: FakeHttp, client: GitHub) -> None:
    payload = {"name": "github-manager: x"}
    http.queue({"id": 5}).queue({"id": 5}).queue({"id": 5, "name": "github-manager: x"})
    assert client.create_ruleset("o/r", payload) == {"id": 5}
    assert client.update_ruleset("o/r", 5, payload) == {"id": 5}
    assert client.get_ruleset("o/r", 5)["name"] == "github-manager: x"
    assert http.requests == [
        ("POST", f"{API}/repos/o/r/rulesets", payload),
        ("PUT", f"{API}/repos/o/r/rulesets/5", payload),
        ("GET", f"{API}/repos/o/r/rulesets/5?includes_parents=false", None),
    ]


# --- retries and rate limits ----------------------------------------------

WRITE_METHODS = ["POST", "PATCH", "PUT", "DELETE"]
NETWORK_ERRORS = [
    urllib.error.URLError("no route"),
    TimeoutError("timed out"),
    ConnectionResetError("connection reset"),
    IncompleteRead(b"x"),
]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_get_retries_transient_status_then_succeeds(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, status: int
) -> None:
    http.queue({"message": "boom"}, status=status).queue({"message": "boom"}, status=status)
    http.queue({"ok": True})
    assert client.call("GET", "/user") == {"ok": True}
    assert len(http.requests) == 3
    assert fake_time.sleeps == [1, 2]


@pytest.mark.parametrize("exc", NETWORK_ERRORS)
def test_get_retries_network_errors_then_succeeds(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, exc: BaseException
) -> None:
    http.queue_error(exc).queue({"ok": True})
    assert client.call("GET", "/user") == {"ok": True}
    assert len(http.requests) == 2
    assert fake_time.sleeps == [1]


def test_get_exhausted_transient_keeps_message_and_status(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, caplog: pytest.LogCaptureFixture
) -> None:
    for _ in range(github.MAX_ATTEMPTS):
        http.queue({"message": "Bad Gateway"}, status=502)
    with (
        caplog.at_level(logging.WARNING, logger="github_manager.github"),
        pytest.raises(GitHubError) as info,
    ):
        client.call("GET", "/user")
    assert str(info.value) == f"GET {API}/user: HTTP 502: Bad Gateway"
    assert info.value.status == 502
    assert len(http.requests) == github.MAX_ATTEMPTS
    assert fake_time.sleeps == [1, 2]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all("HTTP 502" in r.getMessage() and "secret" not in r.getMessage() for r in warnings)


@pytest.mark.parametrize("exc", NETWORK_ERRORS)
def test_get_exhausted_network_error_is_github_error(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, exc: BaseException
) -> None:
    for _ in range(github.MAX_ATTEMPTS):
        http.queue_error(exc)
    with pytest.raises(GitHubError, match=f"^GET {API}/user: ") as info:
        client.call("GET", "/user")
    assert info.value.status is None
    assert len(http.requests) == github.MAX_ATTEMPTS
    assert fake_time.sleeps == [1, 2]


def test_url_error_message_keeps_reason(http: FakeHttp, client: GitHub) -> None:
    for _ in range(github.MAX_ATTEMPTS):
        http.queue_error(urllib.error.URLError("no route"))
    with pytest.raises(GitHubError) as info:
        client.call("GET", "/user")
    assert str(info.value) == f"GET {API}/user: no route"


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_write_is_not_retried_after_transient_status(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, method: str, status: int
) -> None:
    http.queue({"message": "boom"}, status=status)
    with pytest.raises(GitHubError, match=f"HTTP {status}") as info:
        client.call(method, "/x", {"a": 1})
    assert info.value.status == status
    assert len(http.requests) == 1
    assert fake_time.sleeps == []


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("exc", NETWORK_ERRORS)
def test_write_is_not_retried_after_network_error(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, method: str, exc: BaseException
) -> None:
    http.queue_error(exc)
    with pytest.raises(GitHubError, match=f"^{method} {API}/x: "):
        client.call(method, "/x", {"a": 1})
    assert len(http.requests) == 1
    assert fake_time.sleeps == []


class BrokenBody(io.BytesIO):
    """An error response body whose read fails mid-transfer."""

    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self.exc = exc

    def read(self, size: int | None = -1) -> bytes:
        raise self.exc


def broken_body_error(status: int, exc: BaseException) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(f"{API}/x", status, "err", Message(), BrokenBody(exc))


@pytest.mark.parametrize("exc", NETWORK_ERRORS[1:])
def test_get_retries_when_error_body_read_fails(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, exc: BaseException
) -> None:
    http.queue_error(broken_body_error(502, exc)).queue({"ok": True})
    assert client.call("GET", "/x") == {"ok": True}
    assert len(http.requests) == 2
    assert fake_time.sleeps == [1]


@pytest.mark.parametrize("exc", NETWORK_ERRORS[1:])
def test_get_exhausted_with_broken_error_body_keeps_status(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, exc: BaseException
) -> None:
    for _ in range(github.MAX_ATTEMPTS):
        http.queue_error(broken_body_error(502, exc))
    with pytest.raises(GitHubError) as info:
        client.call("GET", "/x")
    assert str(info.value) == f"GET {API}/x: HTTP 502: err"
    assert info.value.status == 502
    assert len(http.requests) == github.MAX_ATTEMPTS
    assert fake_time.sleeps == [1, 2]


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("exc", NETWORK_ERRORS[1:])
def test_write_with_broken_error_body_is_not_retried(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, method: str, exc: BaseException
) -> None:
    http.queue_error(broken_body_error(502, exc))
    with pytest.raises(GitHubError) as info:
        client.call(method, "/x", {"a": 1})
    assert str(info.value) == f"{method} {API}/x: HTTP 502: err"
    assert info.value.status == 502
    assert len(http.requests) == 1
    assert fake_time.sleeps == []


@pytest.mark.parametrize("method", ["GET", *WRITE_METHODS])
@pytest.mark.parametrize(
    ("status", "headers", "wait"),
    [
        (429, {"Retry-After": "7"}, 7),
        (403, {"Retry-After": "5"}, 5),
        (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000030"}, 31),
        (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "999000"}, 1),
        (429, {}, 60),
        (403, {"Retry-After": "soon"}, 60),
    ],
)
def test_rate_limit_waits_and_retries_any_method(
    http: FakeHttp,
    client: GitHub,
    fake_time: FakeTime,
    caplog: pytest.LogCaptureFixture,
    method: str,
    status: int,
    headers: dict[str, str],
    wait: float,
) -> None:
    http.queue({"message": "rate limited"}, status=status, headers=headers).queue({"ok": True})
    with caplog.at_level(logging.WARNING, logger="github_manager.github"):
        assert client.call(method, "/x") == {"ok": True}
    assert len(http.requests) == 2
    assert fake_time.sleeps == [wait]
    assert len(caplog.records) == 1
    assert "secret" not in caplog.records[0].getMessage()


def test_rate_limit_exhausted_keeps_status(
    http: FakeHttp, client: GitHub, fake_time: FakeTime
) -> None:
    for _ in range(github.MAX_ATTEMPTS):
        http.queue({"message": "slow down"}, status=429, headers={"Retry-After": "3"})
    with pytest.raises(GitHubError) as info:
        client.call("POST", "/x", {"a": 1})
    assert str(info.value) == f"POST {API}/x: HTTP 429: slow down"
    assert info.value.status == 429
    assert len(http.requests) == github.MAX_ATTEMPTS
    assert fake_time.sleeps == [3, 3]


@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "121"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000300"},
    ],
)
def test_rate_limit_too_long_fails_without_waiting(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, headers: dict[str, str]
) -> None:
    http.queue({"message": "API rate limit exceeded"}, status=403, headers=headers)
    with pytest.raises(GitHubError, match=r"rate limit.*resets in \d+ s") as info:
        client.call("GET", "/x")
    assert str(info.value).startswith(f"GET {API}/x: HTTP 403: API rate limit exceeded")
    assert info.value.status == 403
    assert len(http.requests) == 1
    assert fake_time.sleeps == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_other_client_errors_are_not_retried(
    http: FakeHttp, client: GitHub, fake_time: FakeTime, status: int
) -> None:
    http.queue({"message": "nope"}, status=status, headers={"X-RateLimit-Remaining": "42"})
    with pytest.raises(GitHubError) as info:
        client.call("GET", "/x")
    assert str(info.value) == f"GET {API}/x: HTTP {status}: nope"
    assert info.value.status == status
    assert len(http.requests) == 1
    assert fake_time.sleeps == []
