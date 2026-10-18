from pathlib import Path

import pytest

from github_manager.config import Config
from github_manager.engine import Outcome, RemoteWorkspace, process_repo, select_repos
from github_manager.github import GitHubError
from github_manager.rules import (
    BranchStrategy,
    RenovatePreset,
    RepoRuleset,
    RepoSettings,
    RepoVisibility,
    RequiredLines,
    SelfHostedRunners,
)

RULE = RequiredLines.from_options(
    {"id": "gi", "path": ".gitignore", "lines": ".env", "exclude": ["skip-rule"]}, Path()
)
CONFIG = Config(owners=["owner"], rules=[RULE], exclude=["legacy-*"])
SETTINGS_RULE = RepoSettings.from_options(
    {"id": "rs", "settings": {"delete_branch_on_merge": True}}, Path()
)
RULESET_RULE = RepoRuleset.from_options(
    {"id": "dr", "required_status_checks": {"owner/app": ["verify"]}}, Path()
)
RULESET_NAME = "github-manager: dr"
VISIBILITY_RULE = RepoVisibility.from_options(
    {"id": "rv", "visibility": {"owner": "private"}}, Path()
)
RUNNERS_RULE = SelfHostedRunners.from_options(
    {"id": "sh", "allowed_runs_on": [["self-hosted"]]}, Path()
)
UBUNTU_WORKFLOW = "jobs:\n  test:\n    runs-on: ubuntu-latest\n"


def repo_named(api, name):
    return next(repo for repo in api.list_repos("owner") if repo.name == name)


def test_select_repos_filters_and_sorts(fake_github) -> None:
    for name in ("b", "A", "legacy-x"):
        fake_github.add_repo(name, {})
    fake_github.add_repo("archived", {}, archived=True)
    fake_github.add_repo("fork", {}, fork=True)

    assert [repo.name for repo in select_repos(fake_github, CONFIG, [])] == ["A", "b"]
    assert [repo.name for repo in select_repos(fake_github, CONFIG, ["b"])] == ["b"]
    with pytest.raises(GitHubError, match="unknown repository: zzz"):
        select_repos(fake_github, CONFIG, ["zzz"])


def test_select_repos_spans_owners(fake_github) -> None:
    config = Config(owners=["owner", "org"], rules=[RULE], exclude=["org/legacy-*"])
    fake_github.add_repo("app", {})
    fake_github.add_repo("app", {}, owner="org")
    fake_github.add_repo("tool", {}, owner="org")
    fake_github.add_repo("legacy-x", {}, owner="org")
    fake_github.add_repo("stranger", {}, owner="other")

    def names(only, owners=None):
        return [repo.full_name for repo in select_repos(fake_github, config, only, owners)]

    assert names([]) == ["org/app", "org/tool", "owner/app"]
    assert names([], ["ORG"]) == ["org/app", "org/tool"]
    assert names(["tool", "Owner/App"]) == ["org/tool", "owner/app"]
    with pytest.raises(GitHubError, match="ambiguous repository app: org/app, owner/app"):
        names(["app"])
    with pytest.raises(GitHubError, match="owners not in the configuration: other"):
        names([], ["other"])


def test_rule_exclude_matches_full_name() -> None:
    rule = RequiredLines.from_options(
        {"id": "x", "path": "p", "lines": "a", "exclude": ["org/*"]}, Path()
    )
    assert not rule.applies_to("app", "org/app")
    assert rule.applies_to("app", "owner/app")


def test_check_reports_without_writing(fake_github) -> None:
    fake_github.add_repo("app", {".gitignore": "dist/\n"})
    report = process_repo(fake_github, CONFIG, repo_named(fake_github, "app"), fix=False)

    assert report.outcome is Outcome.NEEDS_FIX
    assert "+.env" in report.diffs[0]
    assert not any(call.startswith(("commit", "create", "reset")) for call in fake_github.calls)


def test_compliant_and_excluded_and_empty_repositories(fake_github) -> None:
    fake_github.add_repo(
        "ok", {".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"}
    )
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
    assert (
        fake_github.files_at(name, CONFIG.branch)[".gitignore"]
        == "dist/\n\n# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"
    )

    fake_github.calls.clear()
    second = process_repo(fake_github, CONFIG, repo, fix=True)
    assert second.outcome is Outcome.PR_UP_TO_DATE
    assert "reset github-manager/compliance" not in fake_github.calls

    # The default branch moves on: the branch is rebuilt on top of it.
    fake_github.repos[name].commits["base2"] = ("base", {".gitignore": "build/\n"})
    fake_github.repos[name].branches["develop"] = "base2"
    third = process_repo(fake_github, CONFIG, repo, fix=True)
    assert third.outcome is Outcome.PR_UPDATED
    assert (
        fake_github.files_at(name, CONFIG.branch)[".gitignore"]
        == "build/\n\n# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"
    )

    # Someone fixes the default branch by hand: the pull request becomes obsolete.
    fake_github.repos[name].commits["base3"] = (
        "base2",
        {".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"},
    )
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
    config = Config(owners=["owner"], rules=rules)
    name = fake_github.add_repo("app", {"renovate.json": "{broken"})
    process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)

    _, body, _ = fake_github.pulls[name][1]
    assert "- gi: .gitignore: managed block is missing" in body
    assert "### Needs manual action\n- rn: renovate.json: invalid JSON" in body


def test_api_errors_are_reported_per_repository(fake_github) -> None:
    rule = RequiredLines.from_options({"id": "x", "path": "broken", "lines": "a"}, Path())
    fake_github.add_repo("app", {"broken": ""})
    report = process_repo(
        fake_github,
        Config(owners=["owner"], rules=[rule]),
        repo_named(fake_github, "app"),
        fix=False,
    )
    assert report.outcome is Outcome.ERROR
    assert report.detail == "boom"


def test_branch_strategy_sees_repository_branches(fake_github) -> None:
    rule = BranchStrategy.from_options({"id": "bs"}, Path())
    config = Config(owners=["owner"], rules=[rule])
    name = fake_github.add_repo("app", {}, default_branch="master")
    fake_github.repos[name].branches["develop"] = "base"

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.NEEDS_FIX
    assert [finding.message for finding in report.manual_findings] == [
        "default branch is 'master', expected 'main'",
        "forbidden branch exists: develop",
    ]


def test_check_does_not_change_settings(fake_github) -> None:
    config = Config(owners=["owner"], rules=[SETTINGS_RULE])
    name = fake_github.add_repo("app", {}, settings={"delete_branch_on_merge": False})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.NEEDS_FIX
    assert fake_github.repos[name].settings == {"delete_branch_on_merge": False}


def test_fix_applies_settings_without_pull_request(fake_github) -> None:
    config = Config(owners=["owner"], rules=[SETTINGS_RULE])
    name = fake_github.add_repo("app", {}, settings={"delete_branch_on_merge": False})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert fake_github.repos[name].settings == {"delete_branch_on_merge": True}
    assert fake_github.calls == ["settings ['delete_branch_on_merge']"]

    again = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert again.outcome is Outcome.COMPLIANT


def test_fix_applies_settings_next_to_pull_request(fake_github) -> None:
    config = Config(owners=["owner"], rules=[RULE, SETTINGS_RULE])
    name = fake_github.add_repo("app", {}, settings={"delete_branch_on_merge": False})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.PR_CREATED
    assert fake_github.repos[name].settings == {"delete_branch_on_merge": True}

    _, body, _ = fake_github.pulls[name][1]
    assert "### Fixed\n- gi: .gitignore: managed block is missing\n\n" in body
    assert (
        "### Repository settings (applied directly)\n"
        "- rs: setting delete_branch_on_merge is false, expected true"
    ) in body


SECURITY_RULE = RepoSettings.from_options(
    {
        "id": "rs",
        "security_and_analysis": {
            "secret_scanning": "enabled",
            "secret_scanning_push_protection": "enabled",
        },
    },
    Path(),
)
DISABLED = {
    "visibility": "public",
    "security_and_analysis": {
        "secret_scanning": {"status": "disabled"},
        "secret_scanning_push_protection": {"status": "disabled"},
    },
}


def disabled_security() -> dict:
    return {
        "visibility": "public",
        "security_and_analysis": {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        },
    }


def test_check_does_not_change_security_settings(fake_github) -> None:
    config = Config(owners=["owner"], rules=[SECURITY_RULE])
    name = fake_github.add_repo("app", {}, settings=DISABLED)

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.NEEDS_FIX
    assert len(report.findings) == 2
    assert fake_github.repos[name].settings == DISABLED
    assert fake_github.calls == []


def test_fix_updates_security_settings_in_one_call(fake_github) -> None:
    config = Config(owners=["owner"], rules=[SECURITY_RULE])
    name = fake_github.add_repo("app", {}, settings=DISABLED)

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert fake_github.calls == ["settings ['security_and_analysis']"]
    assert fake_github.repos[name].settings["security_and_analysis"] == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }

    again = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert again.outcome is Outcome.COMPLIANT
    assert fake_github.calls == ["settings ['security_and_analysis']"]


def test_fix_merges_security_settings_of_several_rules(fake_github) -> None:
    rules = [
        RepoSettings.from_options(
            {"id": rule_id, "security_and_analysis": {key: "enabled"}}, Path()
        )
        for rule_id, key in [
            ("rs1", "secret_scanning"),
            ("rs2", "secret_scanning_push_protection"),
        ]
    ]
    config = Config(owners=["owner"], rules=rules)
    name = fake_github.add_repo("app", {}, settings=disabled_security())

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert all(finding.setting for finding in report.findings)
    assert len(report.findings) == 2
    assert fake_github.calls == ["settings ['security_and_analysis']"]
    assert fake_github.repos[name].settings["security_and_analysis"] == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }

    again = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert again.outcome is Outcome.COMPLIANT
    assert fake_github.calls == ["settings ['security_and_analysis']"]


def test_fix_leaves_private_repository_security_alone(fake_github) -> None:
    config = Config(owners=["owner"], rules=[SECURITY_RULE])
    fake_github.add_repo("app", {}, settings={"visibility": "private"})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.COMPLIANT
    assert fake_github.calls == []


# --- repo_ruleset ------------------------------------------------------------


def ruleset_config(*rules) -> Config:
    return Config(owners=["owner"], rules=list(rules) or [RULESET_RULE])


def test_check_does_not_write_rulesets(fake_github) -> None:
    name = fake_github.add_repo("app", {})

    report = process_repo(fake_github, ruleset_config(), repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.NEEDS_FIX
    assert [(f.message, f.fixable) for f in report.findings] == [
        (f"ruleset {RULESET_NAME} is missing", True)
    ]
    assert fake_github.repos[name].rulesets == {}
    assert fake_github.calls == []


def test_fix_creates_ruleset_then_second_run_is_compliant(fake_github) -> None:
    config = ruleset_config()
    name = fake_github.add_repo("app", {})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert fake_github.calls == [f"create ruleset {RULESET_NAME}"]
    [ruleset] = fake_github.repos[name].rulesets.values()
    assert ruleset["name"] == RULESET_NAME
    assert ruleset["bypass_actors"] == []
    assert [rule["type"] for rule in ruleset["rules"]] == [
        "deletion",
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    ]

    again = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert again.outcome is Outcome.COMPLIANT
    assert again.findings == []
    assert fake_github.calls == [f"create ruleset {RULESET_NAME}"]


def test_fix_updates_outdated_ruleset_and_keeps_manual_ones(fake_github) -> None:
    config = ruleset_config()
    name = fake_github.add_repo("app", {})
    payload = RULESET_RULE.payload(name)
    manual = fake_github.add_ruleset(name, {**payload, "name": "Protect main"})
    manual_before = fake_github.get_ruleset(name, manual)
    outdated = fake_github.add_ruleset(name, {**payload, "enforcement": "disabled"})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert [f.message for f in report.findings] == [f"ruleset {RULESET_NAME} is outdated"]
    assert fake_github.calls == [f"update ruleset {outdated}"]
    assert fake_github.repos[name].rulesets[outdated]["enforcement"] == "active"
    assert fake_github.get_ruleset(name, manual) == manual_before

    again = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert again.outcome is Outcome.COMPLIANT


def test_ruleset_with_server_defaults_is_compliant(fake_github) -> None:
    name = fake_github.add_repo("app", {})
    fake_github.add_ruleset(name, RULESET_RULE.payload(name))

    report = process_repo(fake_github, ruleset_config(), repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.COMPLIANT
    assert fake_github.calls == []


def test_ruleset_unavailable_and_duplicate_are_manual_not_errors(fake_github) -> None:
    free = fake_github.add_repo("free", {}, rulesets_available=False)
    twice = fake_github.add_repo("twice", {})
    payload = RULESET_RULE.payload(twice)
    fake_github.add_ruleset(twice, payload)
    fake_github.add_ruleset(twice, payload)

    for name in ("free", "twice"):
        report = process_repo(
            fake_github, ruleset_config(), repo_named(fake_github, name), fix=True
        )
        assert report.outcome is Outcome.NEEDS_FIX
        assert [f.fixable for f in report.findings] == [False]
    assert fake_github.calls == []
    assert fake_github.repos[free].rulesets == {}


def test_ruleset_write_is_verified_by_reading_back(fake_github) -> None:
    name = fake_github.add_repo("app", {})
    fake_github.add_ruleset(name, {**RULESET_RULE.payload(name), "enforcement": "disabled"})
    fake_github.repos[name].drop_ruleset_writes = True

    report = process_repo(fake_github, ruleset_config(), repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.ERROR
    assert "differs from the request after saving" in report.detail


def test_ruleset_api_errors_are_reported(fake_github) -> None:
    fake_github.add_repo("app", {})

    def forbidden(repo):
        raise GitHubError("GET rulesets: HTTP 403: Resource not accessible", 403)

    fake_github.list_rulesets = forbidden
    report = process_repo(fake_github, ruleset_config(), repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.ERROR


def test_ruleset_change_goes_to_settings_section_not_commit(fake_github) -> None:
    config = ruleset_config(RULE, RULESET_RULE)
    name = fake_github.add_repo("app", {})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.PR_CREATED
    assert f"create ruleset {RULESET_NAME}" in fake_github.calls
    assert "commit ['.gitignore']" in fake_github.calls
    _, body, _ = fake_github.pulls[name][1]
    assert "### Fixed\n- gi: .gitignore: managed block is missing\n\n" in body
    assert (
        f"### Repository settings (applied directly)\n- dr: ruleset {RULESET_NAME} is missing"
        in body
    )
    assert "ruleset" not in body.split("### Repository settings")[0]


def test_ruleset_and_settings_together_do_not_open_a_pull_request(fake_github) -> None:
    config = ruleset_config(SETTINGS_RULE, RULESET_RULE)
    name = fake_github.add_repo("app", {}, settings={"delete_branch_on_merge": False})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert fake_github.pulls[name] == {}
    assert fake_github.calls == [
        "settings ['delete_branch_on_merge']",
        f"create ruleset {RULESET_NAME}",
    ]


def test_several_ruleset_rules_share_one_listing(fake_github) -> None:
    second = RepoRuleset.from_options({"id": "other"}, Path())
    name = fake_github.add_repo("app", {})
    listed: list[str] = []
    original = fake_github.list_rulesets
    fake_github.list_rulesets = lambda repo: listed.append(repo) or original(repo)

    config = ruleset_config(second, RULESET_RULE)
    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.SETTINGS_UPDATED
    assert listed == [name]
    assert fake_github.calls == [
        "create ruleset github-manager: dr",
        "create ruleset github-manager: other",
    ]


def test_visibility_mismatch_is_reported_and_never_fixed(fake_github) -> None:
    config = Config(owners=["owner"], rules=[VISIBILITY_RULE])
    name = fake_github.add_repo("pub", {}, settings={"visibility": "public"})
    fake_github.add_repo("priv", {}, settings={"visibility": "private"})

    for fix in (False, True):
        report = process_repo(fake_github, config, repo_named(fake_github, "pub"), fix=fix)
        assert report.outcome is Outcome.NEEDS_FIX
        assert [finding.message for finding in report.manual_findings] == [
            'visibility is "public", expected "private" for owner owner '
            "(change it or transfer the repository)"
        ]
    ok = process_repo(fake_github, config, repo_named(fake_github, "priv"), fix=True)
    assert ok.outcome is Outcome.COMPLIANT
    assert fake_github.repos[name].settings == {"visibility": "public"}
    assert not [call for call in fake_github.calls if call.startswith("settings")]
    assert fake_github.pulls[name] == {}


def test_visibility_finding_goes_to_manual_section_of_pull_request(fake_github) -> None:
    config = Config(owners=["owner"], rules=[RULE, VISIBILITY_RULE])
    name = fake_github.add_repo("app", {}, settings={"visibility": "public"})

    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=True)
    assert report.outcome is Outcome.PR_CREATED
    _, body, _ = fake_github.pulls[name][1]
    assert '### Needs manual action\n- rv: visibility is "public", expected "private"' in body
    assert fake_github.repos[name].settings == {"visibility": "public"}


def test_self_hosted_runners_are_reported_and_never_fixed(fake_github) -> None:
    config = Config(owners=["owner"], rules=[RUNNERS_RULE])
    name = fake_github.add_repo(
        "app",
        {".github/workflows/ci.yml": UBUNTU_WORKFLOW},
        settings={"visibility": "private"},
    )

    for fix in (False, True):
        report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=fix)
        assert report.outcome is Outcome.NEEDS_FIX
        assert [finding.message for finding in report.manual_findings] == [
            '.github/workflows/ci.yml: job test: runs-on ["ubuntu-latest"] is not an allowed '
            'self-hosted runner (allowed: ["self-hosted"])'
        ]
    assert not [call for call in fake_github.calls if call.startswith(("commit", "create"))]
    assert not [call for call in fake_github.calls if call.startswith("settings")]
    assert fake_github.pulls[name] == {}
    assert fake_github.files_at(name, "main") == {".github/workflows/ci.yml": UBUNTU_WORKFLOW}


def test_self_hosted_runners_skip_public_repository(fake_github) -> None:
    config = Config(owners=["owner"], rules=[RUNNERS_RULE])
    fake_github.add_repo(
        "app", {".github/workflows/ci.yml": UBUNTU_WORKFLOW}, settings={"visibility": "public"}
    )
    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.COMPLIANT


def test_self_hosted_runners_unlistable_tree_is_manual(fake_github) -> None:
    config = Config(owners=["owner"], rules=[RUNNERS_RULE])
    fake_github.add_repo(
        "app",
        {".github/workflows/ci.yml": UBUNTU_WORKFLOW},
        settings={"visibility": "private"},
        tree_listable=False,
    )
    report = process_repo(fake_github, config, repo_named(fake_github, "app"), fix=False)
    assert report.outcome is Outcome.NEEDS_FIX
    assert [finding.message for finding in report.manual_findings] == [
        ".github/workflows/: the workflow files cannot be listed"
    ]


def test_remote_workspace_paths_include_files_written_by_rules(fake_github) -> None:
    name = fake_github.add_repo(
        "app", {".github/workflows/b.yml": "x", "README.md": "y"}, settings={}
    )
    workspace = RemoteWorkspace(fake_github, name, "base", "main")
    workspace.write(".github/workflows/a.yml", "z")
    workspace.write("other.txt", "z")
    assert workspace.paths(".github/workflows/") == [
        ".github/workflows/a.yml",
        ".github/workflows/b.yml",
    ]


def test_remote_workspace_paths_are_none_when_tree_is_not_listable(fake_github) -> None:
    name = fake_github.add_repo("app", {"a": "x"}, tree_listable=False)
    workspace = RemoteWorkspace(fake_github, name, "base", "main")
    workspace.write("b", "z")
    assert workspace.paths("") is None
