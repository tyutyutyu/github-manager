import json
from pathlib import Path

import pytest

from github_manager.rules import (
    Finding,
    FindingKind,
    RenovatePreset,
)

PRESET = "local>owner/central//renovate/default"


def renovate(**overrides) -> RenovatePreset:
    options = {"id": "rn", "preset": PRESET, "remove_extends": ["config:recommended"], **overrides}
    return RenovatePreset.from_options(options, Path())


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
    assert findings[0].kind is not FindingKind.MANUAL
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


def assert_no_bare_lf(text: str) -> None:
    assert "\n" not in text.replace("\r\n", "")


def test_renovate_multiline_extends_keeps_crlf(make_workspace) -> None:
    text = '{\r\n  "extends": [\r\n    "config:recommended",\r\n    "a"\r\n  ]\r\n}\r\n'
    workspace = make_workspace({"renovate.json": text})
    renovate().apply(workspace)
    after = workspace.files["renovate.json"]
    assert after == text.replace("config:recommended", PRESET)
    assert_no_bare_lf(after)


def test_renovate_inline_extends_keeps_crlf(make_workspace) -> None:
    text = '{\r\n  "extends": ["config:recommended"]\r\n}\r\n'
    workspace = make_workspace({"renovate.json": text})
    renovate().apply(workspace)
    after = workspace.files["renovate.json"]
    assert after == text.replace("config:recommended", PRESET)
    assert_no_bare_lf(after)


def test_renovate_reserializing_keeps_crlf(make_workspace) -> None:
    workspace = make_workspace({"renovate.json": '{\r\n  "automerge": true\r\n}\r\n'})
    renovate().apply(workspace)
    after = workspace.files["renovate.json"]
    assert json.loads(after) == {"automerge": True, "extends": [PRESET]}
    assert "\r\n" in after
    assert_no_bare_lf(after)


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
def test_renovate_reports_manual_configs(make_workspace, files, message) -> None:
    workspace = make_workspace(files)
    [finding] = renovate().apply(workspace)
    assert finding.kind is FindingKind.MANUAL
    assert message in finding.message
    assert workspace.files == files


@pytest.mark.parametrize(
    "text",
    [
        f"{{extends: ['{PRESET}']}}",
        f'{{"extends": ["{PRESET}"]}}',
        f"{{'extends': ['{PRESET}']}}",
        f"{{\n  extends: [\n    'config:base',\n    '{PRESET}',\n  ],\n}}\n",
        f"{{extends: [/* a */ 'config:base', // b\n '{PRESET}']}}",
    ],
)
def test_renovate_accepts_json5_that_extends_the_preset(make_workspace, text) -> None:
    workspace = make_workspace({"renovate.json5": text})
    assert renovate().apply(workspace) == []


@pytest.mark.parametrize(
    "text",
    [
        f"{{ // TODO extend {PRESET}\n}}",
        f"{{ /* {PRESET} */ extends: ['config:base'] }}",
        f"{{ description: 'see {PRESET}', extends: [] }}",
        f"{{ extends: ['{PRESET}-other'] }}",
        "{ description: 'x' }",
        "{ extends: [] }",
        f"{{ extends: ['config:base'] }} // {PRESET}",
    ],
)
def test_renovate_reports_json5_that_does_not_extend_the_preset(make_workspace, text) -> None:
    files = {"renovate.json5": text}
    workspace = make_workspace(files)
    assert renovate().apply(workspace) == [
        Finding("rn", f"renovate.json5: does not extend {PRESET}", kind=FindingKind.MANUAL)
    ]
    assert workspace.files == files
