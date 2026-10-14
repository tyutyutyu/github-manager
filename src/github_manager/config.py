"""Load and validate the central rule configuration (TOML)."""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from github_manager.rules import REQUIRED, RULE_TYPES, Options, Rule

DEFAULT_CONFIG_PATH = Path("github-manager.toml")


class ConfigError(Exception):
    """The configuration file is missing or invalid."""


@dataclass(frozen=True)
class Config:
    owners: list[str]
    rules: Sequence[Rule]
    exclude: list[str] = field(default_factory=list)
    include_forks: bool = False
    branch: str = "github-manager/compliance"
    pr_title: str = "chore: align repository with central rules"
    commit_message: str = "chore: align repository with central rules"


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    return parse_config(raw, base_dir=path.parent)


def parse_config(raw: dict[str, Any], base_dir: Path) -> Config:
    settings = dict(raw)
    rules_raw = settings.pop("rules", [])
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ConfigError("at least one [[rules]] entry is required")
    rules = [_parse_rule(entry, base_dir) for entry in rules_raw]
    ids = [rule.id for rule in rules]
    duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
    if duplicates:
        raise ConfigError(f"duplicate rule ids: {', '.join(duplicates)}")

    defaults = Config(owners=[], rules=[])
    options = Options(settings)
    try:
        config = Config(
            owners=_owners(options.text_list("owners", REQUIRED)),
            rules=rules,
            exclude=options.text_list("exclude", []),
            include_forks=options.flag("include_forks", defaults.include_forks),
            branch=options.text("branch", defaults.branch),
            pr_title=options.text("pr_title", defaults.pr_title),
            commit_message=options.text("commit_message", defaults.commit_message),
        )
        options.finish()
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return config


def _owners(owners: list[str]) -> list[str]:
    if not owners:
        raise ValueError("'owners' must not be empty")
    lowered = [owner.lower() for owner in owners]
    duplicates = sorted({owner for owner in lowered if lowered.count(owner) > 1})
    if duplicates:
        raise ValueError(f"duplicate owners: {', '.join(duplicates)}")
    return owners


def _parse_rule(entry: Any, base_dir: Path) -> Rule:
    if not isinstance(entry, dict):
        raise ConfigError("every [[rules]] entry must be a table")
    options = dict(entry)
    rule_type = options.pop("type", None)
    rule_id = options.get("id", "<missing id>")
    rule_class = RULE_TYPES.get(rule_type) if isinstance(rule_type, str) else None
    if rule_class is None:
        known = ", ".join(sorted(RULE_TYPES))
        raise ConfigError(f"rule {rule_id}: unknown type {rule_type!r} (known: {known})")
    try:
        return rule_class.from_options(options, base_dir)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ConfigError(f"rule {rule_id}: {exc}") from exc
