from pathlib import Path

import pytest

from github_manager.config import ConfigError, load_config, parse_config
from github_manager.rules import (
    BranchStrategy,
    RenovatePreset,
    RepoRuleset,
    RepoSettings,
    RepoVisibility,
    RequiredLines,
)

RULES = [
    {"id": "gi", "type": "required_lines", "path": ".gitignore", "lines": [".env"]},
    {"id": "rn", "type": "renovate_preset", "preset": "local>o/c"},
]


def test_repository_config_file_is_valid() -> None:
    config = load_config(Path(__file__).parent.parent / "github-manager.toml")
    assert config.owners == ["tyutyutyu", "tyutyutyu-org"]
    assert [type(rule) for rule in config.rules] == [
        RenovatePreset,
        RequiredLines,
        BranchStrategy,
        RepoSettings,
        RepoRuleset,
        RepoVisibility,
    ]
    repo_settings = config.rules[3]
    assert isinstance(repo_settings, RepoSettings)
    assert repo_settings.settings == {
        "delete_branch_on_merge": True,
        "allow_auto_merge": True,
        "allow_update_branch": True,
        "has_wiki": False,
    }
    assert repo_settings.security_and_analysis == {
        "secret_scanning": "enabled",
        "secret_scanning_push_protection": "enabled",
    }
    ruleset = config.rules[4]
    assert isinstance(ruleset, RepoRuleset)
    assert ruleset.id == "default-branch-ruleset"
    assert ruleset.required_status_checks == {
        "tyutyutyu/github-manager": ["verify"],
        "tyutyutyu-org/ph_toolbox": ["verify"],
        "tyutyutyu-org/youtube-mirror": ["test"],
    }
    assert not ruleset.strict_required_status_checks
    visibility = config.rules[5]
    assert isinstance(visibility, RepoVisibility)
    assert visibility.id == "repo-visibility"
    assert visibility.visibility == {"tyutyutyu": "public", "tyutyutyu-org": "private"}


def test_defaults_apply(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text(
        'owners = ["me"]\nexclude = ["old-*"]\n'
        '[[rules]]\nid = "gi"\ntype = "required_lines"\npath = ".gitignore"\nlines = [".env"]\n'
    )
    config = load_config(path)
    assert config.exclude == ["old-*"]
    assert config.branch == "github-manager/compliance"
    assert not config.include_forks


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"rules": RULES}, "missing required key 'owners'"),
        ({"owners": ["me"]}, "at least one"),
        ({"owners": [], "rules": RULES}, "'owners' must not be empty"),
        ({"owners": ["me", "Me"], "rules": RULES}, "duplicate owners: me"),
        ({"owners": ["me"], "rules": RULES, "brnach": "x"}, "unknown keys: brnach"),
        ({"owners": ["me"], "rules": RULES, "include_forks": "yes"}, "must be of type bool"),
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


def test_missing_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")
    broken = tmp_path / "broken.toml"
    broken.write_text("owner = ")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(broken)
