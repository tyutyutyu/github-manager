import re
from pathlib import Path

import pytest

from github_manager.rules import (
    FileSync,
    Finding,
    FindingKind,
    RequiredFiles,
    RequiredLines,
)


def required_lines(**overrides) -> RequiredLines:
    options = {"id": "gi", "path": ".gitignore", "lines": ".env\n.idea/\n", **overrides}
    return RequiredLines.from_options(options, Path())


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
    assert findings == [
        Finding("gi", ".gitignore: malformed managed block markers", kind=FindingKind.MANUAL)
    ]
    assert workspace.files[".gitignore"] == text


def test_required_lines_parses_multi_line_string(make_workspace) -> None:
    lines = "\n\n# macOS\n.DS_Store  \n\n\\#notes\n!.claude/skills/\t\n\n"
    rule = required_lines(lines=lines)
    assert rule.lines == ["# macOS", ".DS_Store", "", "\\#notes", "!.claude/skills/"]
    workspace = make_workspace()
    rule.apply(workspace)
    expected = f"{BEGIN}\n# macOS\n.DS_Store\n\n\\#notes\n!.claude/skills/\n{END}\n"
    assert workspace.files[".gitignore"] == expected
    assert rule.apply(workspace) == []


def test_required_lines_skips_excluded_repositories() -> None:
    rule = required_lines(exclude=["legacy-*"])
    assert not rule.applies_to("legacy-app")
    assert rule.applies_to("app")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lines": ""}, "'lines' must not be empty"),
        ({"lines": "\n  \n\t\n"}, "'lines' must not be empty"),
        ({"lines": [".env"]}, "must be of type str"),
        ({"lines": ".env\n  .idea/"}, "'lines' line 2 must not be indented: '  .idea/'"),
        ({"lines": "\t.env"}, "'lines' line 1 must not be indented"),
        ({"remove_lines": [""]}, "list of non-empty strings"),
        ({"path": ""}, "must not be empty"),
        ({"colour": "red"}, "unknown keys: colour"),
    ],
)
def test_required_lines_rejects_invalid_options(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        required_lines(**overrides)


def test_rule_requires_id() -> None:
    with pytest.raises(ValueError, match="missing required key 'id'"):
        RequiredLines.from_options({"path": "x", "lines": "y"}, Path())


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


# --- required_files ----------------------------------------------------------

SONAR = ".github/workflows/sonarqube.yml"


def required_files(*paths: str) -> RequiredFiles:
    return RequiredFiles.from_options({"id": "rf", "paths": list(paths) or [SONAR]}, Path())


def test_required_files_existing_file_has_no_finding(make_workspace) -> None:
    workspace = make_workspace({SONAR: "on: push\n"})
    assert required_files().apply(workspace) == []
    assert workspace.files == {SONAR: "on: push\n"}


def test_required_files_empty_existing_file_counts_as_present(make_workspace) -> None:
    assert required_files().apply(make_workspace({SONAR: ""})) == []


def test_required_files_missing_file_is_manual_and_nothing_is_written(make_workspace) -> None:
    workspace = make_workspace({"README.md": "x"})
    assert required_files().apply(workspace) == [
        Finding("rf", f"{SONAR}: missing", kind=FindingKind.MANUAL)
    ]
    assert workspace.files == {"README.md": "x"}
    assert workspace.settings == {}
    assert workspace.ruleset_changes == []


def test_required_files_reports_every_missing_file_in_order(make_workspace) -> None:
    workspace = make_workspace({"b.txt": "b"})
    assert required_files("c.txt", "b.txt", "a/d.txt").apply(workspace) == [
        Finding("rf", "c.txt: missing", kind=FindingKind.MANUAL),
        Finding("rf", "a/d.txt: missing", kind=FindingKind.MANUAL),
    ]


def test_required_files_sees_pending_writes_of_earlier_rules(make_workspace) -> None:
    workspace = make_workspace()
    workspace.write(SONAR, "on: push\n")
    assert required_files().apply(workspace) == []


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "missing required key 'paths'"),
        ({"paths": []}, "'paths' must not be empty"),
        ({"paths": "a.txt"}, "'paths' must be of type list"),
        ({"paths": [""]}, "'paths' must be a list of non-empty strings"),
        ({"paths": [1]}, "'paths' must be a list of non-empty strings"),
        ({"paths": ["/a.txt"]}, "'paths' item '/a.txt' must not start or end with '/'"),
        ({"paths": ["dir/"]}, "'paths' item 'dir/' must not start or end with '/'"),
        ({"paths": ["../a.txt"]}, "'paths' item '../a.txt' must not contain a '..' segment"),
        ({"paths": ["a/../b"]}, "'paths' item 'a/../b' must not contain a '..' segment"),
        ({"paths": ["a.txt", "b", "a.txt"]}, "duplicate 'paths' items: a.txt"),
        ({"paths": ["a.txt"], "typo": 1}, "unknown keys: typo"),
    ],
)
def test_required_files_rejects_invalid_options(options, message) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        RequiredFiles.from_options({"id": "rf", **options}, Path())


def test_required_files_accepts_dotted_names() -> None:
    rule = RequiredFiles.from_options({"id": "rf", "paths": ["..hidden", "a/.b"]}, Path())
    assert rule.paths == ["..hidden", "a/.b"]
