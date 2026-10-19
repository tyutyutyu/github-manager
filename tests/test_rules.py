import json
from pathlib import Path

import pytest

from github_manager.rules import (
    NOT_READABLE,
    BranchStrategy,
    FileSync,
    Finding,
    RenovatePreset,
    RepoRuleset,
    RepoSettings,
    RepoVisibility,
    RequiredLines,
    SelfHostedRunners,
    ruleset_matches,
)

PRESET = "local>owner/central//renovate/default"


def required_lines(**overrides) -> RequiredLines:
    options = {"id": "gi", "path": ".gitignore", "lines": ".env\n.idea/\n", **overrides}
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
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                },
            },
        ],
    }


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
    assert rule.apply(workspace) == [Finding("dr", f"ruleset {NAME} is missing", setting=True)]
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
    assert rule.apply(workspace) == [Finding("dr", f"ruleset {NAME} is outdated", setting=True)]
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
    assert rule.apply(workspace) == [Finding("dr", f"ruleset {NAME} is missing", setting=True)]
    assert workspace.ruleset_changes == [(NAME, None, payload)]


def test_ruleset_duplicate_managed_name_is_manual(with_server_defaults, make_workspace) -> None:
    rule = ruleset_rule()
    payload = rule.payload("owner/app")
    workspace = make_workspace(
        rulesets=[with_server_defaults(payload, 1), with_server_defaults(payload, 2)]
    )
    assert rule.apply(workspace) == [
        Finding("dr", f"multiple rulesets named {NAME}", fixable=False)
    ]
    assert workspace.ruleset_changes == []


def test_ruleset_unavailable_on_free_plan_is_manual(make_workspace) -> None:
    workspace = make_workspace(rulesets_available=False)
    [finding] = ruleset_rule().apply(workspace)
    assert not finding.fixable
    assert not finding.setting
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
    assert visibility_rule().apply(workspace) == [Finding("rv", message, fixable=False)]
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
        Finding("rv", f"setting visibility {NOT_READABLE}", fixable=False)
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
    return Finding("sh", message, fixable=False)


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
    assert not any(finding.fixable for finding in findings)


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
    assert not findings[0].fixable
    assert findings[0].message.startswith(f"{WORKFLOW}: job test: ")
    assert problem in findings[0].message


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
    assert not findings[0].fixable
    assert findings[0].message.startswith(f"{WORKFLOW}: {problem}")


def test_self_hosted_runners_report_unreadable_file(make_workspace) -> None:
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: self-hosted\n")
    workspace.read = lambda path: None
    assert runners_rule().apply(workspace) == [manual(f"{WORKFLOW}: the file is not readable")]


def test_self_hosted_runners_write_only_workflow_files(make_workspace) -> None:
    workspace = job_workspace(make_workspace, "  test:\n    runs-on: ubuntu-latest\n")
    workspace.change_setting = lambda *args: pytest.fail("the rule must not change settings")
    workspace.change_ruleset = lambda *args: pytest.fail("the rule must not change rulesets")
    assert [finding.fixable for finding in runners_rule().apply(workspace)] == [True]
    assert list(workspace.files) == [WORKFLOW]


def test_self_hosted_runners_never_write_unfixable_jobs(make_workspace) -> None:
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
    assert [finding.fixable for finding in findings] == [True, True]
    assert [finding.message.split(": ")[1] for finding in findings] == ["job a", "job c"]
    assert workspace.files[WORKFLOW].count("runs-on: self-hosted") == 3
    assert runners_rule().apply(workspace) == []


def test_self_hosted_runners_rewrite_to_flow_list_for_several_labels(make_workspace) -> None:
    rule = runners_rule(
        allowed=[("self-hosted",), ("self-hosted", "gpu")], runs_on=["self-hosted", "gpu"]
    )
    text, findings = rewritten(make_workspace, "  test:\n    runs-on: ubuntu-latest\n", rule)
    assert text.endswith("    runs-on: [self-hosted, gpu]\n")
    assert [finding.fixable for finding in findings] == [True]
    assert (
        rule.apply(make_workspace(files={WORKFLOW: text}, settings={"visibility": "private"})) == []
    )


def test_self_hosted_runners_rewrite_flow_style_job(make_workspace) -> None:
    jobs = "  test: {runs-on: ubuntu-latest, steps: []}\n"
    text, findings = rewritten(make_workspace, jobs)
    assert text.endswith("  test: {runs-on: self-hosted, steps: []}\n")
    assert [finding.fixable for finding in findings] == [True]


def test_self_hosted_runners_rewrite_files_independently(make_workspace) -> None:
    other = ".github/workflows/other.yaml"
    bad = "name: x\njobs:\n  t:\n    runs-on: windows-latest\n"
    good = "name: y\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
    workspace = make_workspace(
        files={WORKFLOW: good, other: bad}, settings={"visibility": "private"}
    )
    findings = runners_rule().apply(workspace)
    assert [(finding.fixable, finding.message.split(":")[0]) for finding in findings] == [
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
    assert not any(finding.fixable for finding in findings)
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
    assert not findings[0].fixable
    assert not findings[0].message.endswith("cannot rewrite safely")


def test_self_hosted_runners_mixed_file_rewrites_fixable_and_reports_rest(make_workspace) -> None:
    jobs = "  a:\n    runs-on: ubuntu-latest\n  b:\n    runs-on: windows-latest\n"
    text, findings = rewritten(make_workspace, jobs)
    assert text.endswith("  a:\n    runs-on: self-hosted\n  b:\n    runs-on: windows-latest\n")
    assert [finding.fixable for finding in findings] == [False, True]


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
    assert not findings[0].fixable
    assert findings[0].message.endswith("; cannot rewrite safely")
    assert workspace.files[WORKFLOW] == before
