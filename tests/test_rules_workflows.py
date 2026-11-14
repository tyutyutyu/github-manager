import re
from pathlib import Path

import pytest

from github_manager.rules import (
    NOT_READABLE,
    RULE_TYPES,
    DefaultBranchPushOnly,
    Finding,
    FindingKind,
    SelfHostedRunners,
)
from github_manager.rules.workflows import NOT_SHOWABLE, TOO_LARGE

SONAR = ".github/workflows/sonarqube.yml"


# --- default_branch_push_only ------------------------------------------------


def push_only(**overrides) -> DefaultBranchPushOnly:
    return DefaultBranchPushOnly.from_options({"id": "po", "path": SONAR, **overrides}, Path())


def push_only_findings(make_workspace, text: str, default_branch: str = "main") -> list[Finding]:
    workspace = make_workspace({SONAR: text}, default_branch=default_branch)
    findings = push_only().apply(workspace)
    assert workspace.files == {SONAR: text}
    assert workspace.settings == {}
    assert workspace.ruleset_changes == []
    return findings


@pytest.mark.parametrize(
    "text",
    [
        "on:\n  push:\n    branches: [main]\njobs: {}\n",
        "on:\n  push:\n    branches: main\n",
        "on:\n  push:\n    branches:\n      - main\n    paths: [src/**]\n",
        "on:\n  push:\n    branches: [main]\n    paths-ignore: [docs/**]\n",
        '"on":\n  push:\n    branches: [main]\n',
    ],
)
def test_default_branch_push_only_accepts_push_to_default_branch(make_workspace, text) -> None:
    assert push_only_findings(make_workspace, text) == []


def test_default_branch_push_only_follows_the_workspace_default_branch(make_workspace) -> None:
    text = "on:\n  push:\n    branches: [master]\n"
    assert push_only_findings(make_workspace, text, default_branch="master") == []
    assert push_only_findings(make_workspace, text) == [
        Finding(
            "po",
            f'{SONAR}: push branches ["master"] must be exactly ["main"] (the default branch)',
            kind=FindingKind.MANUAL,
        )
    ]


def test_default_branch_push_only_missing_file_has_no_finding(make_workspace) -> None:
    workspace = make_workspace({"README.md": "x"})
    assert push_only().apply(workspace) == []
    assert workspace.files == {"README.md": "x"}


NO_FILTER = "without a push branches filter it runs on every branch"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("on: push\n", f"'on' is \"push\", not a mapping: {NO_FILTER}"),
        ("on: [push]\n", f"'on' is [\"push\"], not a mapping: {NO_FILTER}"),
        ("on: !custom push\n", f"'on' is push, not a mapping: {NO_FILTER}"),
        ("on: 1\n", f"'on' is 1, not a mapping: {NO_FILTER}"),
        ("on:\n", f"'on' is empty, not a mapping: {NO_FILTER}"),
        ("on: &a [*a]\n", f"'on' is a list with non-string items, not a mapping: {NO_FILTER}"),
        (
            "on:\n  push:\n    branches: [main]\n  pull_request:\n",
            "other triggers: pull_request (only push to main is allowed)",
        ),
        (
            "on:\n  workflow_dispatch:\n  push:\n    branches: [main]\n  pull_request:\n",
            "other triggers: pull_request, workflow_dispatch (only push to main is allowed)",
        ),
        (
            "on:\n  push:\n    branches: [main]\n  schedule:\n    - cron: '0 0 * * *'\n",
            "other triggers: schedule (only push to main is allowed)",
        ),
        (
            "on:\n  push:\n    branches: [main]\n  pull_request_target:\n  workflow_call:\n",
            "other triggers: pull_request_target, workflow_call (only push to main is allowed)",
        ),
        (
            "on:\n  workflow_dispatch:\n",
            "other triggers: workflow_dispatch (only push to main is allowed)",
        ),
        ("on: {}\n", "no push trigger"),
        ("on:\n  push:\n", "push has no branches filter (it runs on every branch)"),
        (
            "on:\n  push:\n    paths: [src/**]\n",
            "push has no branches filter (it runs on every branch)",
        ),
        (
            'on:\n  push:\n    branches: ["main", "renovate/**"]\n',
            'push branches ["main", "renovate/**"] must be exactly ["main"] (the default branch)',
        ),
        (
            'on:\n  push:\n    branches: ["*"]\n',
            'push branches ["*"] must be exactly ["main"] (the default branch)',
        ),
        (
            'on:\n  push:\n    branches: ["!main"]\n',
            'push branches ["!main"] must be exactly ["main"] (the default branch)',
        ),
        (
            "on:\n  push:\n    branches: []\n",
            'push branches [] must be exactly ["main"] (the default branch)',
        ),
        ("on:\n  push:\n    branches: [{a: 1}]\n", "push branches cannot be read"),
        (
            "on:\n  push:\n    branches: [main]\n    branches-ignore: [renovate/**]\n",
            "push has branches-ignore (only branches, paths and paths-ignore are allowed)",
        ),
        (
            "on:\n  push:\n    branches: [main]\n    tags: [v*]\n",
            "push has tags (only branches, paths and paths-ignore are allowed)",
        ),
        (
            "on:\n  push:\n    branches: [main]\n    tags-ignore: [v*]\n    tags: [x]\n",
            "push has tags, tags-ignore (only branches, paths and paths-ignore are allowed)",
        ),
        ("jobs: {}\n", "no 'on' trigger"),
        ("on: [\n", "invalid YAML (expected the node content, but found '<stream end>')"),
        ("a: 1\n---\nb: 2\n", "invalid YAML (but found another document)"),
        ("- on\n", "invalid YAML (the root is not a mapping)"),
        ("", "invalid YAML (the root is not a mapping)"),
    ],
)
def test_default_branch_push_only_reports_the_reason(make_workspace, text, problem) -> None:
    assert push_only_findings(make_workspace, text) == [
        Finding("po", f"{SONAR}: {problem}", kind=FindingKind.MANUAL)
    ]


def test_default_branch_push_only_registers_its_type() -> None:
    assert RULE_TYPES["default_branch_push_only"] is DefaultBranchPushOnly


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"path": None}, "missing required key 'path'"),
        ({"path": ""}, "'path' must not be empty"),
        ({"path": 1}, "'path' must be of type str"),
        ({"path": "sonarqube.yml"}, None),
        ({"path": ".github/sonarqube.yml"}, None),
        ({"path": ".github/workflows/sub/sonarqube.yml"}, None),
        ({"path": ".github/workflows/sonarqube.json"}, None),
        ({"path": ".github/workflows/.yml"}, None),
        ({"path": ".github/workflows/"}, None),
        ({"path": SONAR, "typo": 1}, "unknown keys: typo"),
    ],
)
def test_default_branch_push_only_rejects_invalid_options(options, message) -> None:
    raw = {"id": "po", **{key: value for key, value in options.items() if value is not None}}
    expected = message or (
        f"'path' {options['path']!r} must be a .yml or .yaml file directly in .github/workflows/"
    )
    with pytest.raises(ValueError, match=re.escape(expected)):
        DefaultBranchPushOnly.from_options(raw, Path())


def test_default_branch_push_only_accepts_yaml_extension() -> None:
    rule = DefaultBranchPushOnly.from_options(
        {"id": "po", "path": ".github/workflows/sonar.yaml"}, Path()
    )
    assert rule.path == ".github/workflows/sonar.yaml"


# --- self_hosted_runners -----------------------------------------------------

WORKFLOW = ".github/workflows/ci.yml"


def runners_rule(allowed=(("self-hosted",),), **options) -> SelfHostedRunners:
    raw = {
        "id": "sh",
        "allowed_runs_on": [list(labels) for labels in allowed],
        "runs_on": ["self-hosted"],
        **options,
    }
    return SelfHostedRunners.from_options(raw, Path())


def job_workspace(make_workspace, jobs: str, *, visibility="private", path=WORKFLOW, **options):
    text = f"name: ci\non: push\njobs:\n{jobs}"
    return make_workspace(files={path: text}, settings={"visibility": visibility}, **options)


def manual(message: str) -> Finding:
    return Finding("sh", message, kind=FindingKind.MANUAL)


@pytest.mark.parametrize("visibility", ["private", "internal"])
@pytest.mark.parametrize(
    "runs_on",
    ["self-hosted", "[self-hosted]", "Self-Hosted", "[SELF-HOSTED, self-hosted]", "'self-hosted'"],
)
def test_self_hosted_runners_accept_exact_label_set(make_workspace, visibility, runs_on) -> None:
    workspace = job_workspace(
        make_workspace, f"  test:\n    runs-on: {runs_on}\n", visibility=visibility
    )
    assert runners_rule().apply(workspace) == []


def test_self_hosted_runners_compare_as_sets_against_every_allowed_set(make_workspace) -> None:
    rule = runners_rule(allowed=[("self-hosted",), ("self-hosted", "GPU")])
    workspace = job_workspace(
        make_workspace, "  a:\n    runs-on: [gpu, Self-Hosted]\n  b:\n    runs-on: self-hosted\n"
    )
    assert rule.apply(workspace) == []


@pytest.mark.parametrize(
    ("runs_on", "actual"),
    [
        ("windows-latest", '["windows-latest"]'),
        ("macos-latest", '["macos-latest"]'),
        ("linux", '["linux"]'),
        ("[Linux, X64]", '["Linux", "X64"]'),
        ("[ubuntu-latest, ubuntu-22.04]", '["ubuntu-latest", "ubuntu-22.04"]'),
        ("[ubuntu-latest, windows-latest]", '["ubuntu-latest", "windows-latest"]'),
        ("[]", "[]"),
    ],
)
def test_self_hosted_runners_report_other_label_sets(make_workspace, runs_on, actual) -> None:
    workspace = job_workspace(make_workspace, f"  test:\n    runs-on: {runs_on}\n")
    assert runners_rule().apply(workspace) == [
        manual(
            f"{WORKFLOW}: job test: runs-on {actual} is not an allowed self-hosted runner "
            '(allowed: ["self-hosted"])'
        )
    ]


def test_self_hosted_runners_message_lists_every_allowed_set(make_workspace) -> None:
    rule = runners_rule(allowed=[("self-hosted",), ("self-hosted", "gpu")])
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: windows-latest\n")
    assert rule.apply(workspace)[0].message.endswith(
        '(allowed: ["self-hosted"] or ["self-hosted", "gpu"])'
    )


def test_self_hosted_runners_report_each_bad_job_once(make_workspace) -> None:
    jobs = (
        "  a:\n    runs-on: windows-latest\n"
        "  b:\n    runs-on: self-hosted\n"
        "  c:\n    runs-on: macos-latest\n"
    )
    findings = runners_rule().apply(job_workspace(make_workspace, jobs))
    assert [finding.message.split(":")[1] for finding in findings] == [" job a", " job c"]
    assert not any(finding.kind is not FindingKind.MANUAL for finding in findings)


@pytest.mark.parametrize(
    ("job", "problem"),
    [
        (
            "runs-on: ${{ matrix.os }}",
            'runs-on ["${{ matrix.os }}"] contains an expression'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on: [self-hosted, '${{ x }}']",
            'runs-on ["self-hosted", "${{ x }}"] contains an expression'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on:\n      group: big",
            'runs-on {"group": "big"} must be a string or a list of strings'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on:\n      labels: [self-hosted]",
            'runs-on {"labels": ["self-hosted"]} must be a string or a list of strings'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on: [self-hosted, {a: b}]",
            'runs-on ["self-hosted", {"a": "b"}] has a list item that is not a string'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on: [self-hosted, 3]",
            'runs-on ["self-hosted", 3] has a list item that is not a string'
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on: 3",
            "runs-on 3 must be a string or a list of strings"
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "runs-on:",
            "runs-on null must be a string or a list of strings"
            ' (check manually; allowed: ["self-hosted"])',
        ),
        (
            "uses: owner/repo/.github/workflows/x.yml@main",
            "calls \"owner/repo/.github/workflows/x.yml@main\" without 'runs-on'",
        ),
        ("name: nothing", "has neither 'runs-on' nor 'uses'"),
        ("uses:", "has neither 'runs-on' nor 'uses'"),
    ],
)
def test_self_hosted_runners_report_undecidable_jobs(make_workspace, job, problem) -> None:
    workspace = job_workspace(make_workspace, f"  test:\n    {job}\n")
    findings = runners_rule().apply(workspace)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.MANUAL
    assert findings[0].message.startswith(f"{WORKFLOW}: job test: ")
    assert problem in findings[0].message


def alias_bomb_definitions(levels: int) -> str:
    """Top-level keys whose anchors nest 9 aliases per level: `*a<levels>` expands to 9**levels."""
    lines = ["d0: &a0 [x, y]"]
    for level in range(1, levels + 1):
        lines.append(f"d{level}: &a{level} [{', '.join([f'*a{level - 1}'] * 9)}]")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("runs_on", "shown"),
    [
        ("{x: *a6}", TOO_LARGE),
        ("!foo bar", NOT_SHOWABLE),
        ("[!foo bar]", NOT_SHOWABLE),
        ("!!int nope", NOT_SHOWABLE),
        ("[!!int nope]", NOT_SHOWABLE),
        ("!!float nope", NOT_SHOWABLE),
        ("!!timestamp nope", NOT_SHOWABLE),
        ("{2026-11-14: big}", NOT_SHOWABLE),
        ("&r {x: *r}", None),
    ],
)
def test_self_hosted_runners_show_unrenderable_runs_on_as_manual(
    make_workspace, runs_on, shown
) -> None:
    text = (
        f"name: ci\non: push\n{alias_bomb_definitions(6)}"
        f"jobs:\n  a:\n    runs-on: {runs_on}\n  b:\n    runs-on: windows-latest\n"
    )
    workspace = make_workspace(files={WORKFLOW: text}, settings={"visibility": "private"})

    findings = runners_rule().apply(workspace)

    assert [finding.kind for finding in findings] == [FindingKind.MANUAL] * 2
    assert findings[0].message.startswith(f"{WORKFLOW}: job a: runs-on ")
    assert len(findings[0].message) < 300
    if shown is not None:
        assert shown in findings[0].message
    assert f"{WORKFLOW}: job b: " in findings[1].message


def test_self_hosted_runners_allow_local_reusable_workflow(make_workspace) -> None:
    jobs = "  call:\n    uses: ./.github/workflows/ci.yml\n"
    assert runners_rule().apply(job_workspace(make_workspace, jobs)) == []


def test_self_hosted_runners_report_job_that_is_not_a_mapping(make_workspace) -> None:
    findings = runners_rule().apply(job_workspace(make_workspace, "  test: nope\n"))
    assert [finding.message for finding in findings] == [f"{WORKFLOW}: job test: is not a mapping"]


def test_self_hosted_runners_check_yaml_extension_and_ignore_other_files(make_workspace) -> None:
    jobs = "  test:\n    runs-on: ubuntu-latest\n"
    text = f"jobs:\n{jobs}"
    workspace = make_workspace(
        files={
            ".github/workflows/deploy.yaml": text,
            ".github/workflows/sub/nested.yml": text,
            ".github/workflows/README.md": text,
            ".github/workflows/notes.txt": text,
            ".github/actions/x/action.yml": text,
            "ci.yml": text,
        },
        settings={"visibility": "private"},
    )
    findings = runners_rule().apply(workspace)
    assert [finding.message.split(":")[0] for finding in findings] == [
        ".github/workflows/deploy.yaml"
    ]


def test_self_hosted_runners_inspect_workflows_in_sorted_order(make_workspace) -> None:
    text = "jobs:\n  test:\n    runs-on: ubuntu-latest\n"
    workspace = make_workspace(
        files={".github/workflows/b.yml": text, ".github/workflows/a.yml": text},
        settings={"visibility": "internal"},
    )
    names = [finding.message.split(":")[0] for finding in runners_rule().apply(workspace)]
    assert names == [".github/workflows/a.yml", ".github/workflows/b.yml"]


def test_self_hosted_runners_skip_public_repository_without_reading(make_workspace) -> None:
    workspace = job_workspace(
        make_workspace, "  test:\n    runs-on: ubuntu-latest\n", visibility="public"
    )
    workspace.read = lambda path: pytest.fail("public repositories must not be read")
    workspace.paths = lambda prefix: pytest.fail("public repositories must not be listed")
    assert runners_rule().apply(workspace) == []


def test_self_hosted_runners_unreadable_visibility_is_manual(make_workspace) -> None:
    workspace = make_workspace(files={WORKFLOW: "jobs: {}"})
    assert runners_rule().apply(workspace) == [manual(f"setting visibility {NOT_READABLE}")]


def test_self_hosted_runners_unlistable_tree_is_manual(make_workspace) -> None:
    workspace = make_workspace(settings={"visibility": "private"}, listable=False)
    assert runners_rule().apply(workspace) == [
        manual(".github/workflows/: the workflow files cannot be listed")
    ]


def test_self_hosted_runners_no_workflows_is_compliant(make_workspace) -> None:
    workspace = make_workspace(files={"README.md": "x"}, settings={"visibility": "private"})
    assert runners_rule().apply(workspace) == []


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("jobs: [unclosed", "invalid YAML ("),
        ("a: 1\n---\nb: 2\n", "invalid YAML ("),
        ("", "no 'jobs' mapping"),
        ("- a\n- b\n", "no 'jobs' mapping"),
        ("name: ci\n", "no 'jobs' mapping"),
        ("jobs: [a, b]\n", "no 'jobs' mapping"),
        ("jobs:\n", "no 'jobs' mapping"),
    ],
)
def test_self_hosted_runners_report_unusable_workflow_files(make_workspace, text, problem) -> None:
    workspace = make_workspace(files={WORKFLOW: text}, settings={"visibility": "private"})
    findings = runners_rule().apply(workspace)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.MANUAL
    assert findings[0].message.startswith(f"{WORKFLOW}: {problem}")


def test_self_hosted_runners_report_unreadable_file(make_workspace) -> None:
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: self-hosted\n")
    workspace.read = lambda path: None
    assert runners_rule().apply(workspace) == [manual(f"{WORKFLOW}: the file is not readable")]


def test_self_hosted_runners_write_only_workflow_files(make_workspace) -> None:
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: ubuntu-latest\n")
    workspace.change_setting = lambda *args: pytest.fail("the rule must not change settings")
    workspace.change_ruleset = lambda *args: pytest.fail("the rule must not change rulesets")
    assert [
        finding.kind is not FindingKind.MANUAL for finding in runners_rule().apply(workspace)
    ] == [True]
    assert list(workspace.files) == [WORKFLOW]


def test_self_hosted_runners_never_write_manual_jobs(make_workspace) -> None:
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: windows-latest\n")
    workspace.write = lambda *args: pytest.fail("the rule must not write")
    workspace.change_setting = lambda *args: pytest.fail("the rule must not change settings")
    workspace.change_ruleset = lambda *args: pytest.fail("the rule must not change rulesets")
    assert len(runners_rule().apply(workspace)) == 1


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"runs_on": ["self-hosted"]}, "missing required key 'allowed_runs_on'"),
        ({"allowed_runs_on": []}, "'allowed_runs_on' must not be empty"),
        ({"allowed_runs_on": "self-hosted"}, "'allowed_runs_on' must be of type list"),
        ({"allowed_runs_on": ["self-hosted"]}, "must be a list of non-empty lists"),
        ({"allowed_runs_on": [[]]}, "must be a list of non-empty lists"),
        ({"allowed_runs_on": [[""]]}, "must be a list of non-empty lists"),
        ({"allowed_runs_on": [["self-hosted", 1]]}, "must be a list of non-empty lists"),
        ({"allowed_runs_on": [["linux"]]}, "must contain 'self-hosted'"),
        (
            {"allowed_runs_on": [["self-hosted", "A"], ["a", "Self-Hosted"]]},
            r"duplicate 'allowed_runs_on' set: \[\"a\", \"Self-Hosted\"\]",
        ),
        ({"allowed_runs_on": [["self-hosted"]]}, "missing required key 'runs_on'"),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": "self-hosted"},
            "'runs_on' must be of type list",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": []},
            "'runs_on' must not be empty",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": [""]},
            "'runs_on' must be a list of non-empty strings",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": ["self-hosted", 1]},
            "'runs_on' must be a list of non-empty strings",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": ["ubuntu-latest"]},
            r"'runs_on' \[\"ubuntu-latest\"\] must equal one of the 'allowed_runs_on' sets",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": ["self-hosted", "gpu"]},
            "must equal one of the 'allowed_runs_on' sets",
        ),
        (
            {"allowed_runs_on": [["self-hosted"]], "runs_on": ["self-hosted"], "typo": 1},
            "unknown keys: typo",
        ),
    ],
)
def test_self_hosted_runners_reject_invalid_options(options, message) -> None:
    with pytest.raises(ValueError, match=message):
        SelfHostedRunners.from_options({"id": "sh", **options}, Path())


def test_self_hosted_runners_accept_runs_on_matching_any_allowed_set_case_insensitively() -> None:
    rule = runners_rule(
        allowed=[("self-hosted",), ("self-hosted", "GPU")], runs_on=["gpu", "SELF-HOSTED"]
    )
    assert rule.runs_on == ["gpu", "SELF-HOSTED"]


# --- self_hosted_runners: rewriting ------------------------------------------


def fixed(finding_text: str) -> Finding:
    return Finding("sh", finding_text)


def rewritten(make_workspace, jobs: str, rule=None, **options):
    workspace = job_workspace(make_workspace, jobs, **options)
    findings = (rule or runners_rule()).apply(workspace)
    return workspace.files[WORKFLOW], findings


@pytest.mark.parametrize("visibility", ["private", "internal"])
@pytest.mark.parametrize(
    ("runs_on", "expected", "actual"),
    [
        ("ubuntu-latest", "self-hosted", '["ubuntu-latest"]'),
        ("Ubuntu-22.04", "self-hosted", '["Ubuntu-22.04"]'),
        ("[ubuntu-22.04]", "self-hosted", '["ubuntu-22.04"]'),
        ('"ubuntu-latest"', "self-hosted", '["ubuntu-latest"]'),
        ("'ubuntu-latest'", "self-hosted", '["ubuntu-latest"]'),
        ("[ubuntu-latest, UBUNTU-latest]", "self-hosted", '["ubuntu-latest", "UBUNTU-latest"]'),
        (
            "[self-hosted, Linux, X64, zhukov]",
            "self-hosted",
            '["self-hosted", "Linux", "X64", "zhukov"]',
        ),
        ("[Linux, self-hosted]", "self-hosted", '["Linux", "self-hosted"]'),
        ("[ubuntu-latest, self-hosted]", "self-hosted", '["ubuntu-latest", "self-hosted"]'),
    ],
)
def test_self_hosted_runners_rewrite_replaceable_values(
    make_workspace, visibility, runs_on, expected, actual
) -> None:
    text, findings = rewritten(
        make_workspace, f"  test:\n    runs-on: {runs_on}\n", visibility=visibility
    )
    assert text == f"name: ci\non: push\njobs:\n  test:\n    runs-on: {expected}\n"
    assert findings == [
        fixed(
            f"{WORKFLOW}: job test: runs-on {actual} is not an allowed self-hosted runner "
            '(allowed: ["self-hosted"]); set runs-on to ["self-hosted"]'
        )
    ]


def test_self_hosted_runners_rewrite_keeps_everything_else_byte_for_byte(make_workspace) -> None:
    before = (
        "# header   \n"
        "name: ci\n"
        "on:   push\n"
        "jobs:\n"
        "    test:   # the job\n"
        "        name: Test\n"
        "        runs-on:    ubuntu-latest   # trailing comment  \n"
        "        steps:\n"
        "            - run: echo runs-on ubuntu-latest\n"
        "\n"
    )
    workspace = make_workspace(files={WORKFLOW: before}, settings={"visibility": "private"})
    runners_rule().apply(workspace)
    assert workspace.files[WORKFLOW] == before.replace(
        "runs-on:    ubuntu-latest   #", "runs-on:    self-hosted   #"
    )


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize("final_newline", [True, False])
def test_self_hosted_runners_rewrite_keeps_line_endings(
    make_workspace, ending, final_newline
) -> None:
    lines = [
        "name: ci",
        "on: push",
        "jobs:",
        "  a:",
        "    runs-on: [self-hosted, Linux]  # c",
        "  b:",
        "    runs-on: ubuntu-latest",
    ]
    before = ending.join(lines) + (ending if final_newline else "")
    workspace = make_workspace(files={WORKFLOW: before}, settings={"visibility": "private"})
    findings = runners_rule().apply(workspace)
    assert len(findings) == 2
    after = workspace.files[WORKFLOW]
    expected = before.replace("[self-hosted, Linux]", "self-hosted").replace(
        "runs-on: ubuntu-latest", "runs-on: self-hosted"
    )
    assert after == expected
    assert after.endswith(ending) is final_newline


def test_self_hosted_runners_rewrite_several_jobs_in_one_write(make_workspace) -> None:
    jobs = (
        "  a:\n    runs-on: ubuntu-latest\n"
        "  b:\n    runs-on: self-hosted\n"
        "  c:\n    runs-on: [self-hosted, Linux, X64, zhukov]\n"
    )
    workspace = job_workspace(make_workspace, jobs)
    writes = []
    original = workspace.write
    workspace.write = lambda path, content: (writes.append(path), original(path, content))
    findings = runners_rule().apply(workspace)
    assert writes == [WORKFLOW]
    assert [finding.kind is not FindingKind.MANUAL for finding in findings] == [True, True]
    assert [finding.message.split(": ")[1] for finding in findings] == ["job a", "job c"]
    assert workspace.files[WORKFLOW].count("runs-on: self-hosted") == 3
    assert runners_rule().apply(workspace) == []


def test_self_hosted_runners_rewrite_to_flow_list_for_several_labels(make_workspace) -> None:
    rule = runners_rule(
        allowed=[("self-hosted",), ("self-hosted", "gpu")], runs_on=["self-hosted", "gpu"]
    )
    text, findings = rewritten(make_workspace, "  test:\n    runs-on: ubuntu-latest\n", rule)
    assert text.endswith("    runs-on: [self-hosted, gpu]\n")
    assert [finding.kind is not FindingKind.MANUAL for finding in findings] == [True]
    assert (
        rule.apply(make_workspace(files={WORKFLOW: text}, settings={"visibility": "private"})) == []
    )


def test_self_hosted_runners_rewrite_flow_style_job(make_workspace) -> None:
    jobs = "  test: {runs-on: ubuntu-latest, steps: []}\n"
    text, findings = rewritten(make_workspace, jobs)
    assert text.endswith("  test: {runs-on: self-hosted, steps: []}\n")
    assert [finding.kind is not FindingKind.MANUAL for finding in findings] == [True]


def test_self_hosted_runners_rewrite_files_independently(make_workspace) -> None:
    other = ".github/workflows/other.yaml"
    bad = "name: x\njobs:\n  t:\n    runs-on: windows-latest\n"
    good = "name: y\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
    workspace = make_workspace(
        files={WORKFLOW: good, other: bad}, settings={"visibility": "private"}
    )
    findings = runners_rule().apply(workspace)
    assert [
        (finding.kind is not FindingKind.MANUAL, finding.message.split(":")[0])
        for finding in findings
    ] == [
        (True, WORKFLOW),
        (False, other),
    ]
    assert workspace.files[WORKFLOW].endswith("runs-on: self-hosted\n")
    assert workspace.files[other] == bad


@pytest.mark.parametrize(
    "jobs",
    [
        "  test:\n    runs-on:\n      - ubuntu-latest\n",
        "  test:\n    runs-on:\n      - self-hosted\n      - Linux\n",
        "  test:\n    runs-on: [ubuntu-latest,\n      ]\n",
        "  test:\n    runs-on:\n      ubuntu-latest\n",
        "  test:\n    runs-on: >-\n      ubuntu-latest\n",
        "  a:\n    runs-on: &r ubuntu-latest\n  b:\n    runs-on: *r\n",
        "  test:\n    runs-on: &r [ubuntu-latest]\n",
        "  test:\n    runs-on: !!str ubuntu-latest\n",
        "  test:\n    env:\n      X: &runner ubuntu-latest\n    runs-on: [*runner]\n",
        "  a:\n    runs-on: [&r ubuntu-latest]\n  b:\n    runs-on: [*r]\n",
        "  test:\n    runs-on: [!!str ubuntu-latest]\n",
        "  a: &job\n    runs-on: ubuntu-latest    # keep\n  b: *job\n",
    ],
)
def test_self_hosted_runners_do_not_rewrite_unsafe_values(make_workspace, jobs) -> None:
    before = f"name: ci\non: push\njobs:\n{jobs}"
    workspace = make_workspace(files={WORKFLOW: before}, settings={"visibility": "private"})
    workspace.write = lambda *args: pytest.fail("an unsafe value must not be rewritten")
    findings = runners_rule().apply(workspace)
    assert findings
    assert not any(finding.kind is not FindingKind.MANUAL for finding in findings)
    assert all(finding.message.endswith("; cannot rewrite safely") for finding in findings)
    assert workspace.files[WORKFLOW] == before


def test_self_hosted_runners_report_alias_users_without_touching_them(make_workspace) -> None:
    jobs = "  a:\n    runs-on: &r ubuntu-latest\n  b:\n    runs-on: *r\n"
    _, findings = rewritten(make_workspace, jobs)
    assert [finding.message.split(":")[1] for finding in findings] == [" job a", " job b"]


@pytest.mark.parametrize(
    "job",
    [
        "runs-on: windows-latest",
        "runs-on: macos-14",
        "runs-on: [self-hosted, '${{ matrix.os }}']",
        "runs-on: ${{ matrix.os }}",
        "runs-on: {group: g}",
        "runs-on: [ubuntu-latest, {a: b}]",
        "runs-on: [ubuntu-latest, windows-latest]",
        "uses: org/repo/.github/workflows/w.yml@main",
    ],
)
def test_self_hosted_runners_leave_other_jobs_manual_without_writing(make_workspace, job) -> None:
    before = f"name: ci\non: push\njobs:\n  test:\n    {job}\n"
    workspace = make_workspace(files={WORKFLOW: before}, settings={"visibility": "private"})
    workspace.write = lambda *args: pytest.fail("the rule must not write")
    findings = runners_rule().apply(workspace)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.MANUAL
    assert not findings[0].message.endswith("cannot rewrite safely")


def test_self_hosted_runners_mixed_file_rewrites_pull_request_and_reports_rest(
    make_workspace,
) -> None:
    jobs = "  a:\n    runs-on: ubuntu-latest\n  b:\n    runs-on: windows-latest\n"
    text, findings = rewritten(make_workspace, jobs)
    assert text.endswith("  a:\n    runs-on: self-hosted\n  b:\n    runs-on: windows-latest\n")
    assert [finding.kind is not FindingKind.MANUAL for finding in findings] == [False, True]


def test_self_hosted_runners_do_not_write_when_the_check_after_rewriting_fails(
    make_workspace,
) -> None:
    # `runs_on` is allowed, but a bare `true` loads as a boolean, so the rewritten job
    # would still be undecidable: the file must stay as it is.
    rule = runners_rule(allowed=[("self-hosted", "true")], runs_on=["self-hosted", "true"])
    before = "name: ci\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
    workspace = make_workspace(files={WORKFLOW: before}, settings={"visibility": "private"})
    workspace.write = lambda *args: pytest.fail("a failed check must not write")
    findings = rule.apply(workspace)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.MANUAL
    assert findings[0].message.endswith("; cannot rewrite safely")
    assert workspace.files[WORKFLOW] == before
