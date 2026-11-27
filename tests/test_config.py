from pathlib import Path

import pytest

from github_manager.config import ConfigError, load_config, parse_config
from github_manager.rules import RepoRuleset

RULES = [
    {"id": "gi", "type": "required_lines", "path": ".gitignore", "lines": ".env"},
    {"id": "rn", "type": "renovate_preset", "preset": "local>o/c"},
]


def test_repository_config_file_is_valid() -> None:
    config = load_config(Path(__file__).parent.parent / "github-manager.toml")
    assert config.rules


def test_defaults_apply(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text(
        'owners = ["me"]\nexclude = ["old-*"]\n'
        '[[rules]]\nid = "gi"\ntype = "required_lines"\npath = ".gitignore"\nlines = ".env"\n'
    )
    config = load_config(path)
    assert config.exclude == ["old-*"]
    assert config.branch == "github-manager/compliance"
    assert not config.include_forks
    assert not config.auto_merge


def test_auto_merge_flag_is_parsed() -> None:
    config = parse_config({"owners": ["me"], "rules": RULES, "auto_merge": True}, Path())
    assert config.auto_merge


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"rules": RULES}, "missing required key 'owners'"),
        ({"owners": ["me"]}, "at least one"),
        ({"owners": [], "rules": RULES}, "'owners' must not be empty"),
        ({"owners": ["me", "Me"], "rules": RULES}, "duplicate owners: me"),
        ({"owners": ["me"], "rules": RULES, "brnach": "x"}, "unknown keys: brnach"),
        ({"owners": ["me"], "rules": RULES, "include_forks": "yes"}, "must be of type bool"),
        ({"owners": ["me"], "rules": RULES, "auto_merge": "yes"}, "must be of type bool"),
        ({"owners": ["me"], "rules": [*RULES, RULES[0]]}, "duplicate rule ids: gi"),
        ({"owners": ["me"], "rules": ["x"]}, "must be a table"),
        ({"owners": ["me"], "rules": [{"id": "x", "type": "nope"}]}, "rule x: unknown type 'nope'"),
        ({"owners": ["me"], "rules": [{"id": "x", "type": "required_lines"}]}, "rule x: missing"),
    ],
)
def test_invalid_config_is_rejected(raw, message) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(raw, Path())


def visibility_rule(**table) -> dict:
    return {"id": "rv", "type": "repo_visibility", "visibility": table}


def test_visibility_owners_must_be_listed_in_owners() -> None:
    raw = {"owners": ["me"], "rules": [visibility_rule(me="public", typo="private", Oops="public")]}
    with pytest.raises(ConfigError, match="rule rv: visibility owners not in 'owners': Oops, typo"):
        parse_config(raw, Path())


def test_visibility_owners_match_case_insensitively_and_may_be_partial() -> None:
    raw = {"owners": ["Me", "other"], "rules": [visibility_rule(me="public")]}
    assert parse_config(raw, Path()).owners == ["Me", "other"]


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"allowed_runs_on": []},
        {"allowed_runs_on": "self-hosted"},
        {"allowed_runs_on": [[""]]},
        {"allowed_runs_on": [["linux"]]},
        {"allowed_runs_on": [["self-hosted"], ["Self-Hosted"]]},
        {"allowed_runs_on": [["self-hosted"]]},
        {"allowed_runs_on": [["self-hosted"]], "runs_on": []},
        {"allowed_runs_on": [["self-hosted"]], "runs_on": [""]},
        {"allowed_runs_on": [["self-hosted"]], "runs_on": ["ubuntu-latest"]},
        {"allowed_runs_on": [["self-hosted"]], "runs_on": ["self-hosted"], "typo": 1},
        {
            "allowed_runs_on": [["self-hosted"]],
            "runs_on": ["self-hosted"],
            "job_runs_on": {"deploy": ["zhukov"]},
        },
    ],
)
def test_invalid_self_hosted_runners_options_are_config_errors(options) -> None:
    rule = {"id": "sh", "type": "self_hosted_runners", **options}
    with pytest.raises(ConfigError, match="rule sh:"):
        parse_config({"owners": ["me"], "rules": [rule]}, Path())


@pytest.mark.parametrize("value", ["", 1, ["verify"]])
def test_invalid_required_workflow_check_is_a_config_error(value) -> None:
    rule = {"id": "dr", "type": "repo_ruleset", "required_workflow_check": value}
    with pytest.raises(ConfigError, match="rule dr: 'required_workflow_check'"):
        parse_config({"owners": ["me"], "rules": [rule]}, Path())


def test_required_workflow_check_is_accepted() -> None:
    rule = {"id": "dr", "type": "repo_ruleset", "required_workflow_check": "verify"}
    [parsed] = parse_config({"owners": ["me"], "rules": [rule]}, Path()).rules
    assert isinstance(parsed, RepoRuleset)
    assert parsed.required_workflow_check == "verify"


def test_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")
    broken = tmp_path / "broken.toml"
    broken.write_text("owner = ")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(broken)


def with_profiles(profiles, rules=RULES) -> dict:
    return {"owners": ["me"], "rules": rules, "profiles": profiles}


@pytest.mark.parametrize(
    ("profiles", "message"),
    [
        ({"common": ["*"]}, "'common' is reserved"),
        ({"Common": ["*"]}, "'common' is reserved"),
        ({"ws": []}, "non-empty list"),
        ({"ws": "*-workspace"}, "non-empty list"),
        ({"ws": [1]}, "non-empty list"),
        ({"ws": [""]}, "non-empty list"),
        ({"": ["*"]}, "must not be empty"),
        ({"ws": ["a"], "WS": ["b"]}, "duplicate profile names: ws"),
    ],
)
def test_invalid_profiles_are_rejected(profiles, message) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(with_profiles(profiles), Path())


def test_profiles_default_to_none_and_rules_to_common() -> None:
    config = parse_config({"owners": ["me"], "rules": RULES}, Path())
    assert config.profiles == {}
    assert config.rules[0].profiles == ["common"]


def test_rule_profiles_are_read_and_checked_against_the_definitions() -> None:
    rules = [{**RULES[0], "profiles": ["common", "ws"]}]
    config = parse_config(with_profiles({"ws": ["*-workspace"]}, rules), Path())
    assert config.profiles == {"ws": ["*-workspace"]}
    assert config.rules[0].profiles == ["common", "ws"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "'profiles' must not be empty"),
        (["common", "common"], "duplicate profiles: common"),
        (["ws"], "undefined profiles: ws"),
        ("common", "must be of type list"),
    ],
)
def test_invalid_rule_profiles_are_config_errors(value, message) -> None:
    rules = [{**RULES[0], "profiles": value}]
    with pytest.raises(ConfigError, match=f"rule gi: .*{message}|{message}"):
        parse_config({"owners": ["me"], "rules": rules}, Path())
