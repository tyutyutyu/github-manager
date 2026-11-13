from pathlib import Path

import pytest

from github_manager.rules import (
    Finding,
    FindingKind,
    RepoRuleset,
    ruleset_matches,
)

# --- repo_ruleset ------------------------------------------------------------

NAME = "github-manager: dr"


def ruleset_rule(**overrides) -> RepoRuleset:
    return RepoRuleset.from_options({"id": "dr", **overrides}, Path())


def rule_types(payload: dict) -> list[str]:
    return [rule["type"] for rule in payload["rules"]]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"required_status_checks": {"a": []}}, "must be a non-empty list"),
        ({"required_status_checks": {"a": [""]}}, "must be a non-empty list"),
        ({"required_status_checks": {"a": "verify"}}, "must be a non-empty list"),
        ({"required_status_checks": {"": ["verify"]}}, "patterns must not be empty"),
        ({"required_status_checks": ["verify"]}, "must be of type dict"),
        ({"strict_required_status_checks": "yes"}, "must be of type bool"),
        ({"required_workflow_check": ""}, "'required_workflow_check' must not be empty"),
        ({"required_workflow_check": ["verify"]}, "must be of type str"),
        ({"strict": True}, "unknown keys: strict"),
    ],
)
def test_ruleset_options_are_validated(options, message) -> None:
    with pytest.raises(ValueError, match=message):
        ruleset_rule(**options)


def test_ruleset_options_defaults() -> None:
    rule = ruleset_rule()
    assert rule.required_status_checks == {}
    assert not rule.strict_required_status_checks
    assert rule.required_workflow_check is None


def test_ruleset_payload_without_checks() -> None:
    payload = ruleset_rule().payload("owner/app")
    assert payload == {
        "name": NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
        ],
    }


def test_ruleset_payload_allows_only_squash_merge() -> None:
    payload = ruleset_rule().payload("owner/app")
    (pull_request,) = [rule for rule in payload["rules"] if rule["type"] == "pull_request"]
    assert pull_request["parameters"]["allowed_merge_methods"] == ["squash"]


def test_ruleset_with_all_merge_methods_is_outdated(with_server_defaults, make_workspace) -> None:
    rule = ruleset_rule()
    server = with_server_defaults(rule.payload("owner/app"), ruleset_id=7)
    server["rules"][2]["parameters"]["allowed_merge_methods"] = ["merge", "squash", "rebase"]
    workspace = make_workspace(rulesets=[server])
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is outdated", kind=FindingKind.DIRECT)
    ]
    assert workspace.ruleset_changes == [(NAME, 7, rule.payload("owner/app"))]


def test_ruleset_checks_are_the_sorted_union_of_matching_globs() -> None:
    rule = ruleset_rule(
        required_status_checks={
            "app": ["verify", "lint"],
            "owner/*": ["verify", "audit"],
            "other/app": ["nope"],
            "ap*": ["zzz"],
            "unrelated": ["nope"],
        },
        strict_required_status_checks=True,
    )
    assert rule.checks_for("owner/app") == ["audit", "lint", "verify", "zzz"]
    payload = rule.payload("owner/app")
    assert rule_types(payload) == [
        "deletion",
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    ]
    assert payload["rules"][3] == {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {"context": "audit"},
                {"context": "lint"},
                {"context": "verify"},
                {"context": "zzz"},
            ],
        },
    }
    assert rule.checks_for("owner/unlisted") == ["audit", "verify"]
    assert rule.checks_for("elsewhere/unlisted") == []
    assert "required_status_checks" not in rule_types(rule.payload("elsewhere/unlisted"))


def test_ruleset_missing(make_workspace) -> None:
    workspace = make_workspace(rulesets=[])
    rule = ruleset_rule()
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is missing", kind=FindingKind.DIRECT)
    ]
    assert workspace.ruleset_changes == [(NAME, None, rule.payload("owner/app"))]


def test_ruleset_up_to_date_with_server_defaults(with_server_defaults, make_workspace) -> None:
    rule = ruleset_rule(required_status_checks={"app": ["verify"]})
    server = with_server_defaults(rule.payload("owner/app"))
    workspace = make_workspace(rulesets=[server])
    assert rule.apply(workspace) == []
    assert workspace.ruleset_changes == []


def test_ruleset_rule_order_does_not_matter(with_server_defaults, make_workspace) -> None:
    rule = ruleset_rule()
    server = with_server_defaults(rule.payload("owner/app"))
    server["rules"].reverse()
    assert rule.apply(make_workspace(rulesets=[server])) == []


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(enforcement="evaluate"),
        lambda p: p.update(bypass_actors=[{"actor_id": 1, "actor_type": "Team"}]),
        lambda p: p["conditions"]["ref_name"].update(include=["refs/heads/main"]),
        lambda p: p["rules"].pop(0),
        lambda p: p["rules"].append({"type": "creation"}),
        lambda p: p["rules"][2]["parameters"].update(required_approving_review_count=1),
        lambda p: p["rules"][2]["parameters"].update(allowed_merge_methods=["merge"]),
    ],
    ids=[
        "enforcement",
        "bypass",
        "condition",
        "rule-removed",
        "rule-added",
        "approvals",
        "merge-methods",
    ],
)
def test_ruleset_outdated(with_server_defaults, make_workspace, change) -> None:
    rule = ruleset_rule()
    server = with_server_defaults(rule.payload("owner/app"), ruleset_id=7)
    change(server)
    workspace = make_workspace(rulesets=[server])
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is outdated", kind=FindingKind.DIRECT)
    ]
    assert workspace.ruleset_changes == [(NAME, 7, rule.payload("owner/app"))]


def test_ruleset_outdated_when_checks_change(with_server_defaults, make_workspace) -> None:
    server = with_server_defaults(ruleset_rule().payload("owner/app"))
    rule = ruleset_rule(required_status_checks={"app": ["verify"]})
    workspace = make_workspace(rulesets=[server])
    assert [f.message for f in rule.apply(workspace)] == [f"ruleset {NAME} is outdated"]


def test_ruleset_ignores_manual_and_inherited_rulesets(
    with_server_defaults, make_workspace
) -> None:
    rule = ruleset_rule()
    payload = rule.payload("owner/app")
    manual = {**with_server_defaults(payload, 1), "name": "Protect main"}
    inherited = with_server_defaults(payload, 2, source_type="Organization")
    workspace = make_workspace(rulesets=[manual, inherited])
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is missing", kind=FindingKind.DIRECT)
    ]
    assert workspace.ruleset_changes == [(NAME, None, payload)]


def test_ruleset_duplicate_managed_name_is_manual(with_server_defaults, make_workspace) -> None:
    rule = ruleset_rule()
    payload = rule.payload("owner/app")
    workspace = make_workspace(
        rulesets=[with_server_defaults(payload, 1), with_server_defaults(payload, 2)]
    )
    assert rule.apply(workspace) == [
        Finding("dr", f"multiple rulesets named {NAME}", kind=FindingKind.MANUAL)
    ]
    assert workspace.ruleset_changes == []


def test_ruleset_unavailable_on_free_plan_is_manual(make_workspace) -> None:
    workspace = make_workspace(rulesets_available=False)
    [finding] = ruleset_rule().apply(workspace)
    assert finding.kind is FindingKind.MANUAL
    assert finding.kind is not FindingKind.DIRECT
    assert "GitHub Free" in finding.message
    assert workspace.ruleset_changes == []


def test_ruleset_matches_compares_only_requested_keys() -> None:
    assert ruleset_matches({"a": 1, "b": 2}, {"a": 1})
    assert not ruleset_matches({"a": 1}, {"b": 1})
    assert not ruleset_matches({"a": 1}, {"a": 2})
    assert not ruleset_matches(1, {"a": 1})
    assert ruleset_matches([{"x": 1, "y": 2}, {"x": 3}], [{"x": 3}, {"x": 1}])
    assert not ruleset_matches([{"x": 1}], [{"x": 1}, {"x": 1}])
    assert not ruleset_matches([{"x": 1}, {"x": 1}], [{"x": 1}])
    assert not ruleset_matches({"x": 1}, [{"x": 1}])
    assert not ruleset_matches([{"x": 1}, {"x": 2}], [{"x": 1}, {"x": 1}])
    assert not ruleset_matches(0, False)


# --- repo_ruleset: required_workflow_check -----------------------------------

VERIFY_PATH = ".github/workflows/verify.yml"
NO_VERIFY_JOB = (
    f"{VERIFY_PATH}: no job reports the check 'verify' (its name, or its id without a name)"
)
SIMPLE_VERIFY = """\
name: CI
on: pull_request
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: true
"""


def verify_rule(**overrides) -> RepoRuleset:
    return ruleset_rule(required_workflow_check="verify", **overrides)


def workflow(on: str = "on: pull_request", job: str = "  verify:\n    runs-on: x") -> str:
    return f"name: CI\n{on}\njobs:\n{job}\n"


def verify_problem(make_workspace, text: str, **workspace) -> str | None:
    files = {VERIFY_PATH: text}
    return verify_rule().workflow_check_problem(make_workspace(files, **workspace))


def checked(payload: dict) -> list[str]:
    return [
        item["context"]
        for rule in payload["rules"]
        if rule["type"] == "required_status_checks"
        for item in rule["parameters"]["required_status_checks"]
    ]


@pytest.mark.parametrize(
    "text",
    [
        SIMPLE_VERIFY,
        workflow(job="  notes: text\n  verify:\n    runs-on: x"),
        workflow(job="  build:\n    name: verify\n    runs-on: x"),
        workflow(job="  verify:\n    name: verify\n    runs-on: x\n    if: false"),
        workflow(on="on: [push, pull_request]"),
        workflow(on="on:\n  push:\n  pull_request:"),
        workflow(on="on:\n  pull_request:\n    branches: [main, 'release/*']"),
        workflow(on="on:\n  pull_request:\n    branches: main"),
        workflow(on="on:\n  pull_request:\n    branches: ['**', '!main', 'main']"),
        workflow(on="on:\n  pull_request:\n    branches-ignore: [dev]"),
        workflow(on='"on":\n  pull_request:\n    types: [opened, synchronize, reopened]'),
        workflow(on="on:\n  pull_request:\n    types: [opened, synchronize, reopened, closed]"),
        workflow(job="  verify:\n    strategy:\n      fail-fast: false\n    runs-on: x"),
    ],
)
def test_verify_check_is_valid(make_workspace, text) -> None:
    assert verify_problem(make_workspace, text) is None
    assert verify_rule().requires_workflow_check(make_workspace({VERIFY_PATH: text}))


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (
            workflow(job="  Verify:\n    runs-on: x"),
            NO_VERIFY_JOB,
        ),
        (
            workflow(job="  verify:\n    name: Verify\n    runs-on: x"),
            NO_VERIFY_JOB,
        ),
        (
            workflow(
                job="  verify:\n    strategy:\n      matrix:\n        os: [a]\n    runs-on: x"
            ),
            f"{VERIFY_PATH}: job verify has a matrix (its check is 'verify (<value>)')",
        ),
        (
            workflow(job="  verify:\n    strategy: ${{ fromJson(x) }}\n    runs-on: x"),
            f"{VERIFY_PATH}: job verify has a matrix (its check is 'verify (<value>)')",
        ),
        (
            workflow(job="  verify:\n    uses: o/r/.github/workflows/w.yml@v1"),
            f"{VERIFY_PATH}: job verify calls a reusable workflow (its check is 'verify / <job>')",
        ),
        (
            workflow(job="  verify:\n    name: verify ${{ matrix.os }}\n    runs-on: x"),
            f"{VERIFY_PATH}: job verify: the name contains an expression",
        ),
        (workflow(on="on: push"), f"{VERIFY_PATH}: no pull_request trigger"),
        (workflow(on="on: [push]"), f"{VERIFY_PATH}: no pull_request trigger"),
        (workflow(on="on:\n  pull_request_target:"), f"{VERIFY_PATH}: no pull_request trigger"),
        (workflow(on="name2: x"), f"{VERIFY_PATH}: no pull_request trigger"),
        (
            workflow(on="on:\n  pull_request:\n    paths: ['src/**']"),
            f"{VERIFY_PATH}: pull_request has paths: the check stays pending on a pull request "
            "that touches no matching file",
        ),
        (
            workflow(on="on:\n  pull_request:\n    paths-ignore: ['docs/**']"),
            f"{VERIFY_PATH}: pull_request has paths-ignore: the check stays pending on a pull "
            "request that touches no matching file",
        ),
        (
            workflow(on="on:\n  pull_request:\n    branches: [dev]"),
            f"{VERIFY_PATH}: pull_request branches does not run on the default branch main",
        ),
        (
            workflow(on="on:\n  pull_request:\n    branches: ['**', '!main']"),
            f"{VERIFY_PATH}: pull_request branches does not run on the default branch main",
        ),
        (
            workflow(on="on:\n  pull_request:\n    branches-ignore: ['m*']"),
            f"{VERIFY_PATH}: pull_request branches-ignore does not run on the default branch main",
        ),
        (
            workflow(on="on:\n  pull_request:\n    branches: {a: b}"),
            f"{VERIFY_PATH}: pull_request branches cannot be read",
        ),
        (
            workflow(on="on:\n  pull_request:\n    types: [closed]"),
            f"{VERIFY_PATH}: pull_request types ['closed'] do not cover "
            "opened, reopened, synchronize",
        ),
        (
            workflow(on="on:\n  pull_request:\n    types: opened"),
            f"{VERIFY_PATH}: pull_request types ['opened'] do not cover "
            "opened, reopened, synchronize",
        ),
        (
            workflow(on="on:\n  pull_request:\n    types: {a: b}"),
            f"{VERIFY_PATH}: pull_request types cannot be read",
        ),
        (
            "on: [",
            f"{VERIFY_PATH}: invalid YAML (expected the node content, but found '<stream end>')",
        ),
        (
            "a: 1\n---\nb: 2\n",
            f"{VERIFY_PATH}: invalid YAML (but found another document)",
        ),
        ("name: CI\non: pull_request\n", f"{VERIFY_PATH}: no 'jobs' mapping"),
        ("", f"{VERIFY_PATH}: no 'jobs' mapping"),
        (workflow(job="  - verify"), f"{VERIFY_PATH}: no 'jobs' mapping"),
    ],
)
def test_verify_check_problem_is_named(make_workspace, text, problem) -> None:
    assert verify_problem(make_workspace, text) == problem
    assert not verify_rule().requires_workflow_check(make_workspace({VERIFY_PATH: text}))


def test_verify_check_name_is_matched_case_sensitively(make_workspace) -> None:
    rule = ruleset_rule(required_workflow_check="Verify")
    assert rule.workflow_check_problem(make_workspace({VERIFY_PATH: SIMPLE_VERIFY})) is not None


def test_verify_check_branch_filter_follows_the_default_branch(make_workspace) -> None:
    text = workflow(on="on:\n  pull_request:\n    branches: [trunk]")
    assert verify_problem(make_workspace, text, default_branch="trunk") is None
    assert verify_problem(make_workspace, text) is not None


def test_verify_check_without_workflows_is_missing(make_workspace) -> None:
    rule = verify_rule()
    assert rule.workflow_check_problem(make_workspace({"README.md": "x"})) == (
        ".github/workflows/: no workflow file (.yml or .yaml)"
    )
    only_nested = make_workspace({".github/workflows/sub/verify.yml": SIMPLE_VERIFY})
    assert rule.workflow_check_problem(only_nested) is not None


def test_verify_check_with_unlistable_tree_is_a_problem(make_workspace) -> None:
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, listable=False)
    assert verify_rule().workflow_check_problem(workspace) == (
        ".github/workflows/: the workflow files cannot be listed"
    )
    assert not verify_rule().requires_workflow_check(workspace)


def test_verify_check_unreadable_file_is_a_problem(make_workspace) -> None:
    class Unreadable(make_workspace):
        def original(self, path: str) -> str | None:
            return None

    workspace = Unreadable({VERIFY_PATH: SIMPLE_VERIFY})
    assert verify_rule().workflow_check_problem(workspace) == (
        f"{VERIFY_PATH}: the file is not readable"
    )


def test_verify_check_one_valid_file_is_enough(make_workspace) -> None:
    files = {
        ".github/workflows/a.yaml": "on: [",
        ".github/workflows/b.yml": workflow(on="on: push"),
        ".github/workflows/c.yml": SIMPLE_VERIFY,
        ".github/workflows/notes.txt": "x",
    }
    assert verify_rule().workflow_check_problem(make_workspace(files)) is None


def test_verify_check_reports_the_problem_closest_to_valid(make_workspace) -> None:
    files = {
        ".github/workflows/a.yml": "on: [",
        ".github/workflows/b.yml": workflow(job="  other:\n    runs-on: x"),
        ".github/workflows/c.yml": workflow(on="on:\n  pull_request:\n    paths: [a]"),
        ".github/workflows/d.yml": workflow(on="on: push"),
    }
    assert verify_rule().workflow_check_problem(make_workspace(files)) == (
        ".github/workflows/c.yml: pull_request has paths: the check stays pending on a pull "
        "request that touches no matching file"
    )


def test_verify_check_ignores_files_written_by_earlier_rules(make_workspace) -> None:
    workspace = make_workspace({VERIFY_PATH: workflow(on="on: push")}, rulesets=[])
    workspace.write(VERIFY_PATH, SIMPLE_VERIFY)
    workspace.write(".github/workflows/new.yml", SIMPLE_VERIFY)
    assert verify_rule().workflow_check_problem(workspace) == (
        f"{VERIFY_PATH}: no pull_request trigger"
    )
    assert not verify_rule().requires_workflow_check(workspace)


def test_verify_check_is_not_required_without_rulesets(make_workspace) -> None:
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, rulesets_available=False)
    assert verify_rule().workflow_check_problem(workspace) is None
    assert not verify_rule().requires_workflow_check(workspace)


def test_workflow_check_is_not_required_without_the_option(make_workspace) -> None:
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY})
    rule = ruleset_rule()
    assert rule.workflow_check_problem(workspace) is None
    assert not rule.requires_workflow_check(workspace)


def test_ruleset_adds_valid_workflow_check_to_the_glob_union(
    with_server_defaults, make_workspace
) -> None:
    rule = verify_rule(required_status_checks={"app": ["verify", "lint"], "owner/*": ["audit"]})
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, rulesets=[])
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is missing", kind=FindingKind.DIRECT)
    ]
    ((_, _, payload),) = workspace.ruleset_changes
    assert checked(payload) == ["audit", "lint", "verify"]
    up_to_date = make_workspace(
        {VERIFY_PATH: SIMPLE_VERIFY}, rulesets=[with_server_defaults(payload)]
    )
    assert rule.apply(up_to_date) == []


def test_ruleset_adds_workflow_check_without_globs(make_workspace) -> None:
    rule = verify_rule()
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, rulesets=[])
    rule.apply(workspace)
    ((_, _, payload),) = workspace.ruleset_changes
    assert checked(payload) == ["verify"]


def test_ruleset_without_the_option_has_an_unchanged_payload(make_workspace) -> None:
    rule = ruleset_rule(required_status_checks={"app": ["lint"]})
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, rulesets=[])
    rule.apply(workspace)
    assert workspace.ruleset_changes == [(NAME, None, rule.payload("owner/app"))]
    assert checked(rule.payload("owner/app")) == ["lint"]


def test_ruleset_skips_invalid_workflow_check_but_fixes_the_rest(make_workspace) -> None:
    rule = verify_rule(required_status_checks={"app": ["lint"]})
    text = workflow(on="on: push")
    workspace = make_workspace({VERIFY_PATH: text}, rulesets=[])
    assert rule.apply(workspace) == [
        Finding("dr", f"ruleset {NAME} is missing", kind=FindingKind.DIRECT),
        Finding(
            "dr",
            f"required check verify is not added: {VERIFY_PATH}: no pull_request trigger",
            kind=FindingKind.MANUAL,
        ),
    ]
    ((_, _, payload),) = workspace.ruleset_changes
    assert checked(payload) == ["lint"]


def test_ruleset_without_workflows_adds_no_check_and_no_status_rule(make_workspace) -> None:
    workspace = make_workspace({}, rulesets=[])
    findings = verify_rule().apply(workspace)
    assert [f.kind is not FindingKind.MANUAL for f in findings] == [True, False]
    assert findings[1].message == (
        "required check verify is not added: .github/workflows/: no workflow file (.yml or .yaml)"
    )
    ((_, _, payload),) = workspace.ruleset_changes
    assert "required_status_checks" not in rule_types(payload)


def test_ruleset_with_an_unlistable_tree_reports_the_missing_check(make_workspace) -> None:
    workspace = make_workspace({VERIFY_PATH: SIMPLE_VERIFY}, rulesets=[], listable=False)
    findings = verify_rule().apply(workspace)
    assert findings[1] == Finding(
        "dr",
        "required check verify is not added: .github/workflows/: the workflow files "
        "cannot be listed",
        kind=FindingKind.MANUAL,
    )


def test_ruleset_unavailable_still_reports_the_missing_check(make_workspace) -> None:
    workspace = make_workspace({}, rulesets_available=False)
    findings = verify_rule().apply(workspace)
    assert [f.kind is not FindingKind.MANUAL for f in findings] == [False, False]
    assert findings[0].message.startswith("rulesets are not available")


def test_ruleset_drops_a_stale_workflow_check_when_the_workflow_goes_away(
    with_server_defaults, make_workspace
) -> None:
    rule = verify_rule()
    stale = with_server_defaults(rule.payload("owner/app", ["verify"]))
    workspace = make_workspace({}, rulesets=[stale])
    findings = rule.apply(workspace)
    assert findings[0] == Finding("dr", f"ruleset {NAME} is outdated", kind=FindingKind.DIRECT)
    ((_, ruleset_id, payload),) = workspace.ruleset_changes
    assert ruleset_id == 7
    assert "required_status_checks" not in rule_types(payload)
