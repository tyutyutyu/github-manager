import json
from pathlib import Path

import pytest

from github_manager.rules import FileSync, Finding, RenovatePreset, RequiredLines

PRESET = "local>owner/central//renovate/default"


def required_lines(**overrides) -> RequiredLines:
    options = {"id": "gi", "path": ".gitignore", "lines": [".env", ".idea/"], **overrides}
    return RequiredLines.from_options(options, Path())


def renovate(**overrides) -> RenovatePreset:
    options = {"id": "rn", "preset": PRESET, "remove_extends": ["config:recommended"], **overrides}
    return RenovatePreset.from_options(options, Path())


# --- required_lines ----------------------------------------------------------


def test_required_lines_compliant_file_is_untouched(make_workspace) -> None:
    workspace = make_workspace({".gitignore": "  .env\n.idea/\n"})
    assert required_lines().apply(workspace) == []
    assert workspace.files == {".gitignore": "  .env\n.idea/\n"}


def test_required_lines_appends_missing_lines_with_header(make_workspace) -> None:
    workspace = make_workspace({".gitignore": "dist/"})
    findings = required_lines(header="# managed").apply(workspace)
    assert findings == [Finding("gi", ".gitignore: missing lines: .env, .idea/")]
    assert workspace.files[".gitignore"] == "dist/\n\n# managed\n.env\n.idea/\n"


def test_required_lines_creates_missing_file(make_workspace) -> None:
    workspace = make_workspace()
    required_lines(header="# managed").apply(workspace)
    assert workspace.files[".gitignore"] == "# managed\n.env\n.idea/\n"


def test_required_lines_does_not_repeat_existing_header(make_workspace) -> None:
    workspace = make_workspace({".gitignore": "# managed\n.env\n"})
    required_lines(header="# managed").apply(workspace)
    assert workspace.files[".gitignore"] == "# managed\n.env\n\n.idea/\n"


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
