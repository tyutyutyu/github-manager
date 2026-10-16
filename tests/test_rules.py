import json
from pathlib import Path

import pytest

from github_manager.rules import (
    BranchStrategy,
    FileSync,
    Finding,
    RenovatePreset,
    RepoSettings,
    RequiredLines,
)

PRESET = "local>owner/central//renovate/default"


def required_lines(**overrides) -> RequiredLines:
    options = {"id": "gi", "path": ".gitignore", "lines": [".env", ".idea/"], **overrides}
    return RequiredLines.from_options(options, Path())


def renovate(**overrides) -> RenovatePreset:
    options = {"id": "rn", "preset": PRESET, "remove_extends": ["config:recommended"], **overrides}
    return RenovatePreset.from_options(options, Path())


# --- required_lines ----------------------------------------------------------


BEGIN = "# >>> github-manager: gi"
END = "# <<< github-manager: gi"
BLOCK = f"{BEGIN}\n.env\n.idea/\n{END}\n"


def test_required_lines_compliant_file_is_untouched(make_workspace) -> None:
    text = "dist/\n\n" + BLOCK
    workspace = make_workspace({".gitignore": text})
    assert required_lines().apply(workspace) == []
    assert workspace.files == {".gitignore": text}


def test_required_lines_appends_missing_block(make_workspace) -> None:
    workspace = make_workspace({".gitignore": "dist/"})
    findings = required_lines().apply(workspace)
    assert findings == [Finding("gi", ".gitignore: managed block is missing")]
    assert workspace.files[".gitignore"] == "dist/\n\n" + BLOCK


def test_required_lines_creates_missing_file(make_workspace) -> None:
    workspace = make_workspace()
    required_lines().apply(workspace)
    assert workspace.files[".gitignore"] == BLOCK


def test_required_lines_replaces_outdated_block_in_place(make_workspace) -> None:
    workspace = make_workspace({".gitignore": f"a\n{BEGIN}\nold\n{END}\nb\n"})
    findings = required_lines().apply(workspace)
    assert findings == [Finding("gi", ".gitignore: managed block is outdated")]
    assert workspace.files[".gitignore"] == f"a\n{BLOCK}b\n"


def test_required_lines_removes_unwanted_lines(make_workspace) -> None:
    workspace = make_workspace({".gitignore": "x/\n  .claude/\n" + BLOCK + ".claude/\n"})
    findings = required_lines(remove_lines=[".claude/"]).apply(workspace)
    assert findings == [Finding("gi", ".gitignore: unwanted lines: .claude/, .claude/")]
    assert workspace.files[".gitignore"] == "x/\n" + BLOCK


def test_required_lines_custom_comment_and_final_newline(make_workspace) -> None:
    block = "// >>> github-manager: gi\n.env\n.idea/\n// <<< github-manager: gi"
    workspace = make_workspace({"f": block})
    findings = required_lines(path="f", comment="//").apply(workspace)
    assert findings == [Finding("gi", "f: missing final newline")]
    assert workspace.files["f"] == block + "\n"


@pytest.mark.parametrize(
    "text",
    [f"{BEGIN}\n.env\n", f"{END}\n{BEGIN}\n", f"{BEGIN}\n{END}\n{BEGIN}\n{END}\n"],
)
def test_required_lines_reports_malformed_markers(make_workspace, text) -> None:
    workspace = make_workspace({".gitignore": text})
    findings = required_lines().apply(workspace)
    assert findings == [Finding("gi", ".gitignore: malformed managed block markers", fixable=False)]
    assert workspace.files[".gitignore"] == text


def test_required_lines_skips_excluded_repositories() -> None:
    rule = required_lines(exclude=["legacy-*"])
    assert not rule.applies_to("legacy-app")
    assert rule.applies_to("app")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lines": []}, "'lines' must not be empty"),
        ({"lines": [""]}, "list of non-empty strings"),
        ({"lines": "x"}, "must be of type list"),
        ({"path": ""}, "must not be empty"),
        ({"colour": "red"}, "unknown keys: colour"),
    ],
)
def test_required_lines_rejects_invalid_options(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        required_lines(**overrides)


def test_rule_requires_id() -> None:
    with pytest.raises(ValueError, match="missing required key 'id'"):
        RequiredLines.from_options({"path": "x", "lines": ["y"]}, Path())


# --- renovate_preset ---------------------------------------------------------


def test_renovate_creates_minimal_config(make_workspace) -> None:
    workspace = make_workspace()
    assert renovate().apply(workspace) == [Finding("rn", "renovate.json is missing")]
    assert json.loads(workspace.files["renovate.json"])["extends"] == [PRESET]


def test_renovate_compliant_config_is_untouched(make_workspace) -> None:
    text = json.dumps({"extends": [PRESET, ":semanticCommits"]})
    workspace = make_workspace({".github/renovate.json": text})
    assert renovate().apply(workspace) == []
    assert workspace.files == {".github/renovate.json": text}


def test_renovate_rewrites_only_the_multiline_extends_array(make_workspace) -> None:
    text = (
        "{\n"
        '    "extends": [\n'
        '        "config:recommended",\n'
        '        ":semanticCommits"\n'
        "    ],\n"
        '    "schedule": ["before 6am"]\n'
        "}\n"
    )
    workspace = make_workspace({"renovate.json": text})
    findings = renovate().apply(workspace)
    assert findings[0].fixable
    assert workspace.files["renovate.json"] == text.replace("config:recommended", PRESET)


def test_renovate_keeps_inline_extends_inline(make_workspace) -> None:
    text = '{"extends": ["config:recommended", "a"], "nested": {"extends": "x"}}'
    workspace = make_workspace({"renovate.json": text})
    renovate().apply(workspace)
    assert workspace.files["renovate.json"] == text.replace("config:recommended", PRESET)


def test_renovate_adds_missing_extends_by_reserializing(make_workspace) -> None:
    workspace = make_workspace({"renovate.json": '{\n   "automerge": true\n}'})
    renovate().apply(workspace)
    assert workspace.files["renovate.json"] == (
        '{\n   "automerge": true,\n   "extends": [\n      "' + PRESET + '"\n   ]\n}\n'
    )


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"renovate.json": "{}", ".renovaterc": "{}"}, "multiple Renovate configs"),
        ({"renovate.json": "{nope"}, "invalid JSON"),
        ({"renovate.json": "[]"}, "top level must be an object"),
        ({"renovate.json": '{"extends": "x"}'}, "'extends' must be a list"),
        ({"renovate.json5": "{extends: ['config:base']}"}, "does not extend"),
    ],
)
def test_renovate_reports_unfixable_configs(make_workspace, files, message) -> None:
    workspace = make_workspace(files)
    [finding] = renovate().apply(workspace)
    assert not finding.fixable
    assert message in finding.message
    assert workspace.files == files


def test_renovate_accepts_json5_that_mentions_the_preset(make_workspace) -> None:
    workspace = make_workspace({"renovate.json5": f"{{extends: ['{PRESET}']}}"})
    assert renovate().apply(workspace) == []


# --- file_sync ---------------------------------------------------------------


def test_file_sync_writes_template(tmp_path: Path, make_workspace) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "ec").write_text("root = true\n")
    rule = FileSync.from_options(
        {"id": "ec", "path": ".editorconfig", "source": "templates/ec"}, tmp_path
    )

    workspace = make_workspace()
    assert rule.apply(workspace) == [Finding("ec", ".editorconfig: missing")]
    assert rule.apply(workspace) == []

    workspace.files[".editorconfig"] = "old"
    assert rule.apply(workspace) == [Finding("ec", ".editorconfig: differs from the template")]
    assert workspace.files[".editorconfig"] == "root = true\n"


def test_file_sync_requires_existing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FileSync.from_options({"id": "ec", "path": "x", "source": "missing"}, tmp_path)


# --- branch_strategy ---------------------------------------------------------


def branch_strategy(**overrides) -> BranchStrategy:
    return BranchStrategy.from_options({"id": "bs", **overrides}, Path())


def test_branch_strategy_compliant(make_workspace) -> None:
    workspace = make_workspace(branches={"main", "feature"})
    assert branch_strategy().apply(workspace) == []


def test_branch_strategy_reports_wrong_default_and_forbidden_branch(make_workspace) -> None:
    workspace = make_workspace(default_branch="master", branches={"master", "develop"})
    assert branch_strategy().apply(workspace) == [
        Finding("bs", "default branch is 'master', expected 'main'", fixable=False),
        Finding("bs", "forbidden branch exists: develop", fixable=False),
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
        Finding("rs", "setting delete_branch_on_merge is false, expected true", setting=True)
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
            fixable=False,
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
            setting=True,
        ),
        Finding(
            "rs",
            "setting security_and_analysis.secret_scanning_push_protection "
            'is "disabled", expected "enabled"',
            setting=True,
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
            fixable=False,
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
            fixable=False,
        )
    ]
