from pathlib import Path

import pytest
import yaml
from tests.conftest import MemoryWorkspace

from github_manager.rules import RULE_TYPES, Finding, FindingKind, WorkspaceMembers


def members_rule(**overrides) -> WorkspaceMembers:
    return WorkspaceMembers.from_options({"id": "members", **overrides}, Path())


def manifest(*items: str) -> str:
    return "kind: easy-github-workspace\nrepositories:\n" + "".join(items)


def item(name: str, origin: str) -> str:
    return f"  - name: {name}\n    origin: {origin}\n"


def manual(message: str) -> Finding:
    return Finding("members", message, kind=FindingKind.MANUAL)


def test_rule_type_is_registered() -> None:
    assert RULE_TYPES["workspace_members"] is WorkspaceMembers


def test_all_members_exist_gives_no_finding() -> None:
    files = {"workspace.yaml": manifest(item("a", "git@github.com:org/a.git"))}
    workspace = MemoryWorkspace(files, other_repos={"org/a": {}})

    assert members_rule().apply(workspace) == []


@pytest.mark.parametrize(
    "origin",
    [
        "git@github.com:org/a.git",
        "git@github.com:org/a",
        "https://github.com/org/a.git",
        "https://github.com/org/a",
    ],
)
def test_origin_formats_are_recognised(origin: str) -> None:
    workspace = MemoryWorkspace(
        {"workspace.yaml": manifest(item("a", origin))}, other_repos={"org/a": {}}
    )

    assert members_rule().apply(workspace) == []


def test_missing_member_is_reported_with_its_name_in_manifest_order() -> None:
    files = {
        "workspace.yaml": manifest(
            item("a", "git@github.com:org/a.git"),
            item("b", "git@github.com:org/b.git"),
            item("c", "https://github.com/org/c"),
        )
    }
    workspace = MemoryWorkspace(files, other_repos={"org/a": {}})

    findings = members_rule().apply(workspace)

    assert [f.kind for f in findings] == [FindingKind.MANUAL] * 2
    assert "workspace.yaml: b: repository org/b does not exist or is not readable" in (
        findings[0].message
    )
    assert "c: repository org/c" in findings[1].message


def test_missing_manifest_is_reported() -> None:
    assert members_rule().apply(MemoryWorkspace({})) == [manual("workspace.yaml: missing")]


def test_custom_path_is_named_in_the_message() -> None:
    findings = members_rule(path="ws/members.yaml").apply(MemoryWorkspace({}))

    assert findings == [manual("ws/members.yaml: missing")]


def test_invalid_yaml_is_reported() -> None:
    workspace = MemoryWorkspace({"workspace.yaml": "repositories: [a\n"})

    assert members_rule().apply(workspace) == [manual("workspace.yaml: is not valid YAML")]


@pytest.mark.parametrize("content", ["kind: x\n", "- a\n", "repositories: nope\n", ""])
def test_missing_repositories_list_is_reported(content: str) -> None:
    workspace = MemoryWorkspace({"workspace.yaml": content})

    assert members_rule().apply(workspace) == [manual("workspace.yaml: has no 'repositories' list")]


@pytest.mark.parametrize(
    "entry",
    ["  - name: a\n", "  - origin: git@github.com:org/a.git\n", "  - just-text\n"],
)
def test_item_without_name_or_origin_is_reported(entry: str) -> None:
    workspace = MemoryWorkspace({"workspace.yaml": manifest(entry)})

    [finding] = members_rule().apply(workspace)

    assert finding.kind is FindingKind.MANUAL
    assert "workspace.yaml:" in finding.message
    assert "'name' or 'origin' is missing" in finding.message


def test_item_without_origin_names_the_member() -> None:
    workspace = MemoryWorkspace({"workspace.yaml": manifest("  - name: a\n")})

    assert members_rule().apply(workspace) == [
        manual("workspace.yaml: a: 'name' or 'origin' is missing")
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "git@gitlab.com:org/a.git",
        "http://github.com/org/a",
        "https://github.com/org",
        "https://github.com/org/a/b",
        "ssh://git@github.com/org/a.git",
        "'https://github.com/org/a#readme'",
        "'https://github.com/org/a?x=1'",
        "'https://github.com/org/a\\n'",
        "'git@github.com:us@er/a.git'",
        "'https://github.com/org/..'",
    ],
)
def test_unsupported_origin_is_reported(origin: str) -> None:
    workspace = MemoryWorkspace(
        {"workspace.yaml": manifest(item("a", origin))}, other_repos={"org/a": {}}
    )

    assert members_rule().apply(workspace) == [
        manual(f"workspace.yaml: a: unsupported origin {yaml.safe_load(origin)!r}")
    ]


def test_invalid_yaml_value_is_reported() -> None:
    workspace = MemoryWorkspace({"workspace.yaml": "created: 2026-02-30\nrepositories: []\n"})

    assert members_rule().apply(workspace) == [manual("workspace.yaml: is not valid YAML")]


def test_item_without_name_is_labelled_with_its_origin() -> None:
    workspace = MemoryWorkspace(
        {"workspace.yaml": manifest("  - origin: git@github.com:org/a.git\n")}
    )

    # Origin is present but name is missing: the message names the origin.
    assert members_rule().apply(workspace) == [
        manual(
            "workspace.yaml: repositories item 1 (git@github.com:org/a.git): "
            "'name' or 'origin' is missing"
        )
    ]


def test_nothing_is_written() -> None:
    files = {"workspace.yaml": manifest(item("a", "git@github.com:org/a.git"))}
    workspace = MemoryWorkspace(files)

    members_rule().apply(workspace)

    assert workspace.files == files


def test_unknown_key_is_a_config_error() -> None:
    with pytest.raises(ValueError, match="unknown keys: bogus"):
        members_rule(bogus=1)


@pytest.mark.parametrize("path", ["/workspace.yaml", "dir/", "a/../b.yaml", ""])
def test_invalid_path_is_a_config_error(path: str) -> None:
    with pytest.raises(ValueError, match=r"path|empty"):
        members_rule(path=path)
