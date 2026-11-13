"""Compliance pull request lifecycle against the real GitHub API, on a dedicated sandbox repository.

Opt-in: set GITHUB_MANAGER_SANDBOX_REPO=OWNER/NAME and run `task dev:test-integration`.
Without the variable the test is skipped before any network call.
"""

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from github_manager.config import Config, parse_config
from github_manager.engine import MERGEABLE_NOW, STAGING_SUFFIX, Outcome, process_repo
from github_manager.github import GitHub, GitHubError, PullRequest, Repo, resolve_token

pytestmark = pytest.mark.integration

SANDBOX_ENV = "GITHUB_MANAGER_SANDBOX_REPO"
SANDBOX_MARKER = "sandbox"
BRANCH = "github-manager/integration-test"
MANAGED_PATH = ".github-manager-sandbox"
NONCOMPLIANT_CONTENT = "not managed yet\n"
TOUCH_PATH = ".github-manager-sandbox-touch"
# GitHub answers a missing ref with 404 or 422.
MISSING_REF = (404, 422)
# GitHub computes the merge state asynchronously after the pull request is opened.
MERGE_STATE_ATTEMPTS = 5
MERGE_STATE_PAUSE_SECONDS = 2


def _sandbox_repo() -> str:
    """The sandbox repository from the environment; refuses anything not named as a sandbox."""
    full_name = os.environ.get(SANDBOX_ENV, "").strip()
    if not full_name:
        pytest.skip(f"{SANDBOX_ENV} is not set")
    owner, _, name = full_name.partition("/")
    if not owner or not name or "/" in name:
        pytest.fail(f"{SANDBOX_ENV} must be OWNER/NAME, got {full_name!r}")
    if SANDBOX_MARKER not in name.lower():
        pytest.fail(
            f"refusing to run: repository name {name!r} does not contain {SANDBOX_MARKER!r}"
        )
    return full_name


def _config(owner: str) -> Config:
    """Synthetic configuration; the real github-manager.toml is never loaded."""
    raw = {
        "owners": [owner],
        "branch": BRANCH,
        "auto_merge": False,
        "rules": [
            {
                "id": "sandbox",
                "type": "required_lines",
                "path": MANAGED_PATH,
                "lines": "integration-test\n",
            }
        ],
    }
    return parse_config(raw, Path())


def _repo(api: GitHub, full_name: str) -> Repo:
    raw = api.call("GET", f"/repos/{full_name}")
    return Repo(
        name=raw["name"],
        full_name=raw["full_name"],
        default_branch=raw["default_branch"],
        archived=raw["archived"],
        fork=raw["fork"],
    )


def _commit_to_default(api: GitHub, repo: Repo, files: dict[str, str], message: str) -> None:
    head = api.branch_sha(repo.full_name, repo.default_branch)
    assert head is not None
    api.commit_files(repo.full_name, repo.default_branch, head, message, files)


def _clean_up(api: GitHub, repo: str) -> None:
    """Close the test's pull request and delete its branches; missing ones are fine."""
    pull = api.find_open_pr(repo, BRANCH)
    if pull is not None:
        api.close_pr(repo, pull.number, "Closed by the github-manager integration test.")
    for branch in (BRANCH, f"{BRANCH}{STAGING_SUFFIX}"):
        try:
            api.delete_branch(repo, branch)
        except GitHubError as exc:
            if exc.status not in MISSING_REF:
                raise


@pytest.fixture
def sandbox() -> Iterator[tuple[GitHub, Repo]]:
    full_name = _sandbox_repo()
    api = GitHub(resolve_token())
    repo = _repo(api, full_name)
    _clean_up(api, repo.full_name)
    try:
        yield api, repo
    finally:
        _clean_up(api, repo.full_name)


def _wait_for_merge_state(api: GitHub, repo: str, pull: PullRequest) -> list[str]:
    """Poll the merge state until it is `CLEAN` or the attempts run out; all observed states."""
    states: list[str] = []
    for attempt in range(MERGE_STATE_ATTEMPTS):
        if attempt:
            time.sleep(MERGE_STATE_PAUSE_SECONDS)
        states.append(api.merge_state(repo, pull))
        if states[-1] == MERGEABLE_NOW:
            break
    return states


def test_compliance_pull_request_lifecycle(sandbox: tuple[GitHub, Repo]) -> None:
    api, repo = sandbox
    config = _config(repo.full_name.split("/", 1)[0])
    stamp = datetime.now(UTC).isoformat()

    # a. the managed file is not compliant on the default branch
    _commit_to_default(
        api, repo, {MANAGED_PATH: NONCOMPLIANT_CONTENT}, "test: reset integration sandbox"
    )

    # b. the first run opens the pull request
    report = process_repo(api, config, repo, fix=True)
    assert report.outcome is Outcome.PR_CREATED, report.detail
    pull = api.find_open_pr(repo.full_name, BRANCH)
    assert pull is not None

    # b2. without required checks the pull request is mergeable now, so auto-merge is refused
    states = _wait_for_merge_state(api, repo.full_name, pull)
    print(f"observed merge states: {states}")
    assert states[-1] == MERGEABLE_NOW, states
    with pytest.raises(GitHubError) as refused:
        api.enable_auto_merge(repo.full_name, pull)
    print(f"auto-merge refused with: {refused.value}")

    # c. the default branch moves on with an unrelated commit
    _commit_to_default(api, repo, {TOUCH_PATH: f"{stamp}\n"}, "test: move integration sandbox")

    # d. the same open pull request is updated, not closed by the branch reset
    report = process_repo(api, config, repo, fix=True)
    assert report.outcome is Outcome.PR_UPDATED, report.detail
    updated = api.find_open_pr(repo.full_name, BRANCH)
    assert updated is not None
    assert updated.number == pull.number

    # e. nothing changed since: the pull request is up to date
    report = process_repo(api, config, repo, fix=True)
    assert report.outcome is Outcome.PR_UP_TO_DATE, report.detail

    # f. the default branch becomes compliant: the pull request is closed and its branch deleted
    compliant = api.read_file(repo.full_name, MANAGED_PATH, BRANCH)
    assert compliant is not None
    _commit_to_default(
        api, repo, {MANAGED_PATH: compliant}, "test: make integration sandbox compliant"
    )
    report = process_repo(api, config, repo, fix=True)
    assert report.outcome is Outcome.PR_CLOSED, report.detail
    assert api.find_open_pr(repo.full_name, BRANCH) is None
    assert api.branch_sha(repo.full_name, BRANCH) is None
