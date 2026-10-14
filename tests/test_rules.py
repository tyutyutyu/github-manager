import json
from pathlib import Path

import pytest

from github_manager.rules import BranchStrategy, FileSync, Finding, RenovatePreset, RequiredLines

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
