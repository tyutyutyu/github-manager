from pathlib import Path

import pytest

from github_manager.config import Config
from github_manager.engine import Outcome, process_repo, select_repos
from github_manager.github import GitHubError
from github_manager.rules import RenovatePreset, RequiredLines

RULE = RequiredLines.from_options(
    {"id": "gi", "path": ".gitignore", "lines": [".env"], "exclude": ["skip-rule"]}, Path()
)
CONFIG = Config(owner="owner", rules=[RULE], exclude=["legacy-*"])


def repo_named(api, name):
    return next(repo for repo in api.list_repos("owner") if repo.name == name)


def test_select_repos_filters_and_sorts(fake_github) -> None:
    for name in ("b", "A", "legacy-x"):
        fake_github.add_repo(name, {})
    fake_github.add_repo("archived", {}, archived=True)
    fake_github.add_repo("fork", {}, fork=True)

    assert [repo.name for repo in select_repos(fake_github, CONFIG, [])] == ["A", "b"]
    assert [repo.name for repo in select_repos(fake_github, CONFIG, ["b"])] == ["b"]
    with pytest.raises(GitHubError, match="unknown repositories for owner: zzz"):
        select_repos(fake_github, CONFIG, ["zzz"])


def test_check_reports_without_writing(fake_github) -> None:
    fake_github.add_repo("app", {".gitignore": "dist/\n"})
    report = process_repo(fake_github, CONFIG, repo_named(fake_github, "app"), fix=False)

    assert report.outcome is Outcome.NEEDS_FIX
    assert "+.env" in report.diffs[0]
    assert not any(call.startswith(("commit", "create", "reset")) for call in fake_github.calls)


def test_compliant_and_excluded_and_empty_repositories(fake_github) -> None:
    fake_github.add_repo("ok", {".gitignore": ".env\n"})
    fake_github.add_repo("skip-rule", {})
    fake_github.add_repo("empty", None)

    outcomes = [
        process_repo(fake_github, CONFIG, repo_named(fake_github, name), fix=True).outcome
        for name in ("ok", "skip-rule", "empty")
    ]
    assert outcomes == [Outcome.COMPLIANT, Outcome.COMPLIANT, Outcome.SKIPPED]


def test_fix_lifecycle(fake_github) -> None:
    name = fake_github.add_repo("app", {".gitignore": "dist/\n"}, default_branch="develop")
    repo = repo_named(fake_github, "app")

    first = process_repo(fake_github, CONFIG, repo, fix=True)
    assert first.outcome is Outcome.PR_CREATED
    assert fake_github.files_at(name, CONFIG.branch)[".gitignore"] == "dist/\n\n.env\n"

    fake_github.calls.clear()
    second = process_repo(fake_github, CONFIG, repo, fix=True)
    assert second.outcome is Outcome.PR_UP_TO_DATE
    assert "reset github-manager/compliance" not in fake_github.calls

    # The default branch moves on: the branch is rebuilt on top of it.
    fake_github.repos[name].commits["base2"] = ("base", {".gitignore": "build/\n"})
    fake_github.repos[name].branches["develop"] = "base2"
    third = process_repo(fake_github, CONFIG, repo, fix=True)
    assert third.outcome is Outcome.PR_UPDATED
    assert fake_github.files_at(name, CONFIG.branch)[".gitignore"] == "build/\n\n.env\n"

    # Someone fixes the default branch by hand: the pull request becomes obsolete.
    fake_github.repos[name].commits["base3"] = ("base2", {".gitignore": ".env\n"})
    fake_github.repos[name].branches["develop"] = "base3"
    fourth = process_repo(fake_github, CONFIG, repo, fix=True)
    assert fourth.outcome is Outcome.PR_CLOSED
    assert CONFIG.branch not in fake_github.repos[name].branches
    assert fake_github.find_open_pr(name, CONFIG.branch) is None


def test_stale_branch_without_pull_request_is_reused(fake_github) -> None:
    name = fake_github.add_repo("app", {})
    fake_github.repos[name].branches[CONFIG.branch] = "base"
    report = process_repo(fake_github, CONFIG, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.PR_CREATED


def test_pull_request_body_lists_manual_findings(fake_github) -> None:
    rules = [RULE, RenovatePreset.from_options({"id": "rn", "preset": "local>o/c"}, Path())]
    config = Config(owner="owner", rules=rules)
    name = fake_github.add_repo("app", {"renovate.json": "{broken"})
    process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)

    _, body, _ = fake_github.pulls[name][1]
    assert "- gi: .gitignore: missing lines: .env" in body
    assert "### Needs manual action\n- rn: renovate.json: invalid JSON" in body


def test_api_errors_are_reported_per_repository(fake_github) -> None:
    rule = RequiredLines.from_options({"id": "x", "path": "broken", "lines": ["a"]}, Path())
    fake_github.add_repo("app", {"broken": ""})
    report = process_repo(
        fake_github, Config(owner="owner", rules=[rule]), repo_named(fake_github, "app"), fix=False
    )
    assert report.outcome is Outcome.ERROR
    assert report.detail == "boom"
