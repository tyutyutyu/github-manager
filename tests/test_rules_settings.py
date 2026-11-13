from pathlib import Path

import pytest

from github_manager.rules import (
    NOT_READABLE,
    BranchStrategy,
    Finding,
    FindingKind,
    RepoSettings,
    RepoVisibility,
)

# --- branch_strategy ---------------------------------------------------------


def branch_strategy(**overrides) -> BranchStrategy:
    return BranchStrategy.from_options({"id": "bs", **overrides}, Path())


def test_branch_strategy_compliant(make_workspace) -> None:
    workspace = make_workspace(branches={"main", "feature"})
    assert branch_strategy().apply(workspace) == []


def test_branch_strategy_reports_wrong_default_and_forbidden_branch(make_workspace) -> None:
    workspace = make_workspace(default_branch="master", branches={"master", "develop"})
    assert branch_strategy().apply(workspace) == [
        Finding("bs", "default branch is 'master', expected 'main'", kind=FindingKind.MANUAL),
        Finding("bs", "forbidden branch exists: develop", kind=FindingKind.MANUAL),
    ]
    assert workspace.files == {}


def test_branch_strategy_custom_options(make_workspace) -> None:
    rule = branch_strategy(default_branch="trunk", forbidden_branches=["main"])
    workspace = make_workspace(default_branch="trunk", branches={"trunk", "develop"})
    assert rule.apply(workspace) == []


# --- repo_settings -----------------------------------------------------------


def repo_settings(**settings) -> RepoSettings:
    return RepoSettings.from_options({"id": "rs", "settings": settings}, Path())


def test_repo_settings_compliant(make_workspace) -> None:
    workspace = make_workspace(settings={"delete_branch_on_merge": True})
    assert repo_settings(delete_branch_on_merge=True).apply(workspace) == []


def test_repo_settings_changes_differing_values(make_workspace) -> None:
    workspace = make_workspace(settings={"delete_branch_on_merge": False, "has_wiki": False})
    rule = repo_settings(delete_branch_on_merge=True, has_wiki=False)
    assert rule.apply(workspace) == [
        Finding(
            "rs",
            "setting delete_branch_on_merge is false, expected true",
            kind=FindingKind.DIRECT,
        )
    ]
    assert workspace.settings == {"delete_branch_on_merge": True, "has_wiki": False}
    assert workspace.files == {}


def test_repo_settings_reports_unreadable_setting(make_workspace) -> None:
    workspace = make_workspace()
    assert repo_settings(delete_branch_on_merge=True).apply(workspace) == [
        Finding(
            "rs",
            "setting delete_branch_on_merge is not readable "
            "(the token needs Administration access)",
            kind=FindingKind.MANUAL,
        )
    ]
    assert workspace.settings == {}


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "missing required key 'settings'"),
        ({"settings": {}}, "'settings' must not be empty"),
        ({"settings": "x"}, "must be of type dict"),
        ({"settings": {"colour": True}}, "unknown settings: colour"),
        ({"settings": {"has_wiki": "yes"}}, "must be true or false: has_wiki"),
        ({"security_and_analysis": {}}, "'settings' must not be empty"),
        ({"settings": {}, "security_and_analysis": {}}, "'settings' must not be empty"),
        ({"security_and_analysis": "x"}, "must be of type dict"),
        (
            {"security_and_analysis": {"dependabot_security_updates": "enabled"}},
            "unknown security_and_analysis settings: dependabot_security_updates",
        ),
        (
            {"security_and_analysis": {"secret_scanning": "on"}},
            "values must be enabled or disabled: secret_scanning",
        ),
        (
            {"security_and_analysis": {"secret_scanning": True}},
            "values must be enabled or disabled: secret_scanning",
        ),
    ],
)
def test_repo_settings_rejects_invalid_options(options, message) -> None:
    with pytest.raises(ValueError, match=message):
        RepoSettings.from_options({"id": "rs", **options}, Path())


def security_rule(**security) -> RepoSettings:
    return RepoSettings.from_options({"id": "rs", "security_and_analysis": security}, Path())


WANTED_SECURITY = {"secret_scanning": "enabled", "secret_scanning_push_protection": "enabled"}


def security_state(scanning: str, protection: str) -> dict:
    return {
        "secret_scanning": {"status": scanning},
        "secret_scanning_push_protection": {"status": protection},
    }


def test_repo_settings_accepts_security_only_or_together() -> None:
    rule = security_rule(**WANTED_SECURITY)
    assert rule.settings == {}
    assert rule.security_and_analysis == WANTED_SECURITY
    both = RepoSettings.from_options(
        {"id": "rs", "settings": {"has_wiki": False}, "security_and_analysis": WANTED_SECURITY},
        Path(),
    )
    assert both.settings == {"has_wiki": False}


def test_security_public_mismatch_is_one_change(make_workspace) -> None:
    workspace = make_workspace(
        settings={
            "visibility": "public",
            "security_and_analysis": security_state("disabled", "disabled"),
        }
    )
    assert security_rule(**WANTED_SECURITY).apply(workspace) == [
        Finding(
            "rs",
            'setting security_and_analysis.secret_scanning is "disabled", expected "enabled"',
            kind=FindingKind.DIRECT,
        ),
        Finding(
            "rs",
            "setting security_and_analysis.secret_scanning_push_protection "
            'is "disabled", expected "enabled"',
            kind=FindingKind.DIRECT,
        ),
    ]
    assert workspace.settings["security_and_analysis"] == {
        "secret_scanning": {"status": "enabled"},
        "secret_scanning_push_protection": {"status": "enabled"},
    }


def test_security_public_only_differing_key_is_written(make_workspace) -> None:
    workspace = make_workspace(
        settings={
            "visibility": "public",
            "security_and_analysis": security_state("enabled", "disabled"),
        }
    )
    findings = security_rule(**WANTED_SECURITY).apply(workspace)
    assert len(findings) == 1
    assert workspace.settings["security_and_analysis"] == {
        "secret_scanning_push_protection": {"status": "enabled"}
    }


def test_security_public_compliant(make_workspace) -> None:
    workspace = make_workspace(
        settings={
            "visibility": "public",
            "security_and_analysis": security_state("enabled", "enabled"),
        }
    )
    assert security_rule(**WANTED_SECURITY).apply(workspace) == []
    assert workspace.settings["security_and_analysis"] == security_state("enabled", "enabled")


@pytest.mark.parametrize("visibility", ["private", "internal"])
def test_security_skips_non_public_repositories(make_workspace, visibility) -> None:
    workspace = make_workspace(settings={"visibility": visibility})
    assert security_rule(**WANTED_SECURITY).apply(workspace) == []
    assert workspace.settings == {"visibility": visibility}


def test_security_reports_unreadable_field(make_workspace) -> None:
    workspace = make_workspace(settings={"visibility": "public"})
    assert security_rule(**WANTED_SECURITY).apply(workspace) == [
        Finding(
            "rs",
            "setting security_and_analysis is not readable (the token needs Administration access)",
            kind=FindingKind.MANUAL,
        )
    ]
    assert workspace.settings == {"visibility": "public"}


def test_security_reports_unreadable_key(make_workspace) -> None:
    workspace = make_workspace(
        settings={
            "visibility": "public",
            "security_and_analysis": {"secret_scanning": {"status": "enabled"}},
        }
    )
    assert security_rule(**WANTED_SECURITY).apply(workspace) == [
        Finding(
            "rs",
            "setting security_and_analysis.secret_scanning_push_protection is not readable "
            "(the token needs Administration access)",
            kind=FindingKind.MANUAL,
        )
    ]


# --- repo_visibility ---------------------------------------------------------


def visibility_rule(**table) -> RepoVisibility:
    table = table or {"tyutyutyu": "public", "tyutyutyu-org": "private"}
    return RepoVisibility.from_options({"id": "rv", "visibility": table}, Path())


@pytest.mark.parametrize(
    ("full_name", "current"),
    [("tyutyutyu/x", "public"), ("tyutyutyu-org/y", "private"), ("Tyutyutyu/x", "public")],
)
def test_repo_visibility_compliant(make_workspace, full_name, current) -> None:
    workspace = make_workspace(settings={"visibility": current}, full_name=full_name)
    assert visibility_rule().apply(workspace) == []


@pytest.mark.parametrize(
    ("full_name", "current", "wanted", "owner"),
    [
        ("tyutyutyu/x", "private", "public", "tyutyutyu"),
        ("tyutyutyu-org/y", "public", "private", "tyutyutyu-org"),
        ("tyutyutyu/z", "internal", "public", "tyutyutyu"),
        ("Tyutyutyu-Org/y", "public", "private", "Tyutyutyu-Org"),
    ],
)
def test_repo_visibility_reports_mismatch_as_manual(
    make_workspace, full_name, current, wanted, owner
) -> None:
    workspace = make_workspace(settings={"visibility": current}, full_name=full_name)
    message = (
        f'visibility is "{current}", expected "{wanted}" for owner {owner} '
        "(change it or transfer the repository)"
    )
    assert visibility_rule().apply(workspace) == [Finding("rv", message, kind=FindingKind.MANUAL)]
    assert workspace.settings == {"visibility": current}
    assert workspace.files == {}


def test_repo_visibility_ignores_owner_missing_from_table(make_workspace) -> None:
    workspace = make_workspace(settings={"visibility": "public"}, full_name="other/x")
    assert visibility_rule(tyutyutyu="private").apply(workspace) == []


def test_repo_visibility_does_not_read_setting_for_unlisted_owner(make_workspace) -> None:
    workspace = make_workspace(full_name="other/x")
    workspace.setting = lambda name: pytest.fail("visibility must not be read")
    assert visibility_rule().apply(workspace) == []


def test_repo_visibility_unreadable_is_manual(make_workspace) -> None:
    workspace = make_workspace(full_name="tyutyutyu/x")
    assert visibility_rule().apply(workspace) == [
        Finding("rv", f"setting visibility {NOT_READABLE}", kind=FindingKind.MANUAL)
    ]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "missing required key 'visibility'"),
        ({"visibility": {}}, "'visibility' must not be empty"),
        ({"visibility": {"a": "public", "b": "internal"}}, "must be public or private: b"),
        ({"visibility": {"a": True}}, "must be public or private: a"),
        ({"visibility": {"a": "public", "A": "private"}}, "duplicate visibility owners: a"),
        ({"visibility": {"a": "public"}, "typo": 1}, "unknown keys: typo"),
        ({"visibility": ["a"]}, "'visibility' must be of type dict"),
    ],
)
def test_repo_visibility_rejects_invalid_options(options, message) -> None:
    with pytest.raises(ValueError, match=message):
        RepoVisibility.from_options({"id": "rv", **options}, Path())
