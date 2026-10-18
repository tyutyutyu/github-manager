"""Rule types. A rule inspects a repository workspace and writes the fixes it needs.

Rules never talk to GitHub directly: they read and write through a `Workspace`,
so the same code serves `check` (changes are discarded) and `fix` (file changes are
committed to a pull request, setting and ruleset changes are applied to the repository).
"""

import contextlib
import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar, Protocol, Self

import yaml


class Workspace(Protocol):
    @property
    def default_branch(self) -> str: ...

    @property
    def full_name(self) -> str: ...

    def branch_exists(self, branch: str) -> bool: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, content: str) -> None: ...

    def paths(self, prefix: str) -> list[str] | None: ...

    def setting(self, name: str) -> Any: ...

    def change_setting(self, name: str, value: Any) -> None: ...

    def rulesets(self) -> list[dict[str, Any]] | None: ...

    def ruleset(self, ruleset_id: int) -> dict[str, Any]: ...

    def change_ruleset(
        self, name: str, ruleset_id: int | None, payload: dict[str, Any]
    ) -> None: ...


@dataclass(frozen=True)
class Finding:
    rule_id: str
    message: str
    fixable: bool = True
    # Fixed through the repository settings or rulesets, not through the pull request.
    setting: bool = False


REQUIRED = object()


class Options:
    """Typed access to a rule's TOML table; rejects unknown keys."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = dict(raw)

    def _take(self, key: str, kind: type, default: Any) -> Any:
        if key not in self._raw:
            if default is REQUIRED:
                raise ValueError(f"missing required key {key!r}")
            return default
        value = self._raw.pop(key)
        if not isinstance(value, kind):
            raise ValueError(f"{key!r} must be of type {kind.__name__}")
        return value

    def text(self, key: str, default: Any = None) -> Any:
        value = self._take(key, str, default)
        if value is not None and not value:
            raise ValueError(f"{key!r} must not be empty")
        return value

    def text_list(self, key: str, default: Any = None) -> list[str]:
        value = self._take(key, list, default)
        if not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"{key!r} must be a list of non-empty strings")
        return list(value)

    def text_lists(self, key: str, default: Any = None) -> list[list[str]]:
        value = self._take(key, list, default)
        if not all(
            isinstance(item, list)
            and item
            and all(isinstance(label, str) and label for label in item)
            for item in value
        ):
            raise ValueError(f"{key!r} must be a list of non-empty lists of non-empty strings")
        return [list(item) for item in value]

    def flag(self, key: str, default: bool) -> bool:
        return self._take(key, bool, default)

    def table(self, key: str, default: Any = None) -> dict[str, Any]:
        return dict(self._take(key, dict, default))

    def has(self, key: str) -> bool:
        return key in self._raw

    def finish(self) -> None:
        if self._raw:
            raise ValueError(f"unknown keys: {', '.join(sorted(self._raw))}")


@dataclass(frozen=True, kw_only=True)
class Rule(ABC):
    type_name: ClassVar[str]

    id: str
    exclude: list[str] = field(default_factory=list)

    def applies_to(self, repo_name: str, full_name: str | None = None) -> bool:
        names = [repo_name] if full_name is None else [repo_name, full_name]
        return not any(fnmatchcase(name, pattern) for pattern in self.exclude for name in names)

    @abstractmethod
    def apply(self, workspace: Workspace) -> list[Finding]:
        """Report violations and write the fixed content into the workspace."""

    @classmethod
    def from_options(cls, raw: dict[str, Any], base_dir: Path) -> Self:
        options = Options(raw)
        rule = cls._build(
            options,
            base_dir,
            id=options.text("id", REQUIRED),
            exclude=options.text_list("exclude", []),
        )
        options.finish()
        return rule

    @classmethod
    @abstractmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self: ...


@dataclass(frozen=True, kw_only=True)
class RequiredLines(Rule):
    """The file must contain a managed block, delimited by marker comments, holding `lines`.

    The block is replaced as a whole on every fix, so changing `lines` in the
    central config updates every repository. Lines in `remove_lines` are deleted
    from the rest of the file.
    """

    type_name: ClassVar[str] = "required_lines"

    path: str
    lines: list[str]
    remove_lines: list[str] = field(default_factory=list)
    comment: str = "#"

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        lines = options.text_list("lines", REQUIRED)
        if not lines:
            raise ValueError("'lines' must not be empty")
        return cls(
            path=options.text("path", REQUIRED),
            lines=lines,
            remove_lines=options.text_list("remove_lines", []),
            comment=options.text("comment", "#"),
            **common,
        )

    @property
    def begin_marker(self) -> str:
        return f"{self.comment} >>> github-manager: {self.id}"

    @property
    def end_marker(self) -> str:
        return f"{self.comment} <<< github-manager: {self.id}"

    def apply(self, workspace: Workspace) -> list[Finding]:
        content = workspace.read(self.path) or ""
        current = content.splitlines()
        stripped = [line.strip() for line in current]
        begins = [i for i, line in enumerate(stripped) if line == self.begin_marker]
        ends = [i for i, line in enumerate(stripped) if line == self.end_marker]
        if len(begins) > 1 or len(ends) > 1 or len(begins) != len(ends) or begins > ends:
            message = f"{self.path}: malformed managed block markers"
            return [Finding(self.id, message, fixable=False)]

        block = [self.begin_marker, *self.lines, self.end_marker]
        unwanted = {line.strip() for line in self.remove_lines}
        if begins:
            before, after = current[: begins[0]], current[ends[0] + 1 :]
        else:
            before, after = current, []
        before = [line for line in before if line.strip() not in unwanted]
        after = [line for line in after if line.strip() not in unwanted]
        removed = [line for line in current if line.strip() in unwanted]
        if not begins and before and before[-1].strip():
            before.append("")
        result = "\n".join([*before, *block, *after]) + "\n"
        if result == content:
            return []

        workspace.write(self.path, result)
        changes = []
        if not begins:
            changes.append("managed block is missing")
        elif current[begins[0] : ends[0] + 1] != block:
            changes.append("managed block is outdated")
        if removed:
            changes.append(f"unwanted lines: {', '.join(line.strip() for line in removed)}")
        summary = "; ".join(changes) or "missing final newline"
        return [Finding(self.id, f"{self.path}: {summary}")]


RENOVATE_CONFIG_FILES = (
    "renovate.json",
    "renovate.json5",
    ".github/renovate.json",
    ".github/renovate.json5",
    ".gitlab/renovate.json",
    ".gitlab/renovate.json5",
    ".renovaterc",
    ".renovaterc.json",
    ".renovaterc.json5",
)
RENOVATE_SCHEMA = "https://docs.renovatebot.com/renovate-schema.json"


@dataclass(frozen=True, kw_only=True)
class RenovatePreset(Rule):
    """The repository's Renovate config must extend the central shared preset."""

    type_name: ClassVar[str] = "renovate_preset"

    preset: str
    remove_extends: list[str]

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        return cls(
            preset=options.text("preset", REQUIRED),
            remove_extends=options.text_list("remove_extends", []),
            **common,
        )

    def apply(self, workspace: Workspace) -> list[Finding]:
        existing = [path for path in RENOVATE_CONFIG_FILES if workspace.read(path) is not None]
        if not existing:
            content = {"$schema": RENOVATE_SCHEMA, "extends": [self.preset]}
            workspace.write("renovate.json", json.dumps(content, indent=2) + "\n")
            return [Finding(self.id, "renovate.json is missing")]
        if len(existing) > 1:
            names = ", ".join(existing)
            return [Finding(self.id, f"multiple Renovate configs: {names}", fixable=False)]

        path = existing[0]
        text = workspace.read(path) or ""
        if path.endswith(".json5"):
            return self._manual(path, text)
        try:
            config = json.loads(text)
        except json.JSONDecodeError as exc:
            return [Finding(self.id, f"{path}: invalid JSON ({exc.msg})", fixable=False)]
        if not isinstance(config, dict):
            return [Finding(self.id, f"{path}: top level must be an object", fixable=False)]
        extends = config.get("extends", [])
        if not isinstance(extends, list):
            return [Finding(self.id, f"{path}: 'extends' must be a list", fixable=False)]

        wanted = [item for item in extends if item not in self.remove_extends]
        if self.preset not in wanted:
            wanted.insert(0, self.preset)
        if wanted == extends:
            return []

        config["extends"] = wanted
        workspace.write(path, _rewrite_extends(text, config))
        return [Finding(self.id, f"{path}: extends {extends} -> {wanted}")]

    def _manual(self, path: str, text: str) -> list[Finding]:
        if self.preset in text:
            return []
        return [Finding(self.id, f"{path}: does not extend {self.preset}", fixable=False)]


def _rewrite_extends(text: str, config: dict[str, Any]) -> str:
    """Replace only the `extends` array, keeping the rest of the file byte for byte.

    Falls back to re-serializing the whole document when the surgical edit
    cannot be verified (e.g. `extends` was absent or appears more than once).
    """
    decoder = json.JSONDecoder()
    for match in re.finditer(r'"extends"\s*:\s*(?=\[)', text):
        start = match.end()
        _, end = decoder.raw_decode(text, start)
        old_array = text[start:end]
        candidate = (
            text[:start] + _render_array(config["extends"], old_array, text, start) + text[end:]
        )
        with contextlib.suppress(json.JSONDecodeError):
            if json.loads(candidate) == config:
                return candidate
    indent = re.search(r"^( +)\S", text, re.MULTILINE)
    return json.dumps(config, indent=len(indent.group(1)) if indent else 2) + "\n"


def _render_array(items: list[str], old_array: str, text: str, start: int) -> str:
    rendered = [json.dumps(item, ensure_ascii=False) for item in items]
    item_indent = re.search(r"\[\s*?\n([ \t]*)\S", old_array)
    if item_indent is None:
        return "[" + ", ".join(rendered) + "]"
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start:start]
    close_indent = line[: len(line) - len(line.lstrip(" \t"))]
    body = ",\n".join(item_indent.group(1) + item for item in rendered)
    return f"[\n{body}\n{close_indent}]"


@dataclass(frozen=True, kw_only=True)
class FileSync(Rule):
    """The file must have exactly the content of a template kept in this repository."""

    type_name: ClassVar[str] = "file_sync"

    path: str
    content: str

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        source = base_dir / options.text("source", REQUIRED)
        return cls(
            path=options.text("path", REQUIRED),
            content=source.read_text(encoding="utf-8"),
            **common,
        )

    def apply(self, workspace: Workspace) -> list[Finding]:
        current = workspace.read(self.path)
        if current == self.content:
            return []
        workspace.write(self.path, self.content)
        state = "missing" if current is None else "differs from the template"
        return [Finding(self.id, f"{self.path}: {state}")]


@dataclass(frozen=True, kw_only=True)
class BranchStrategy(Rule):
    """The default branch must be `default_branch` and no `forbidden_branches` may exist.

    Branches are repository settings, not files, so findings need manual action.
    """

    type_name: ClassVar[str] = "branch_strategy"

    default_branch: str = "main"
    forbidden_branches: list[str] = field(default_factory=lambda: ["develop"])

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        return cls(
            default_branch=options.text("default_branch", "main"),
            forbidden_branches=options.text_list("forbidden_branches", ["develop"]),
            **common,
        )

    def apply(self, workspace: Workspace) -> list[Finding]:
        findings = []
        if workspace.default_branch != self.default_branch:
            message = (
                f"default branch is {workspace.default_branch!r}, expected {self.default_branch!r}"
            )
            findings.append(Finding(self.id, message, fixable=False))
        findings.extend(
            Finding(self.id, f"forbidden branch exists: {branch}", fixable=False)
            for branch in self.forbidden_branches
            if workspace.branch_exists(branch)
        )
        return findings


# Boolean repository settings accepted by PyGithub's `Repository.edit`.
REPO_BOOL_SETTINGS = frozenset(
    {
        "allow_auto_merge",
        "allow_forking",
        "allow_merge_commit",
        "allow_rebase_merge",
        "allow_squash_merge",
        "allow_update_branch",
        "delete_branch_on_merge",
        "has_discussions",
        "has_issues",
        "has_projects",
        "has_wiki",
        "use_squash_pr_title_as_default",
        "web_commit_signoff_required",
    }
)


# Security features of `security_and_analysis` that a public repository may require.
SECURITY_SETTINGS = frozenset({"secret_scanning", "secret_scanning_push_protection"})
SECURITY_STATES = frozenset({"enabled", "disabled"})
NOT_READABLE = "is not readable (the token needs Administration access)"


@dataclass(frozen=True, kw_only=True)
class RepoSettings(Rule):
    """The repository settings must have the values in `settings`.

    `security_and_analysis` additionally requires the secret scanning features, on public
    repositories only (they are paid features on private ones, which are skipped).
    Fixes are applied to the repository directly (through PyGithub), not by pull request.
    """

    type_name: ClassVar[str] = "repo_settings"

    settings: dict[str, bool] = field(default_factory=dict)
    security_and_analysis: dict[str, str] = field(default_factory=dict)

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        if not options.has("settings") and not options.has("security_and_analysis"):
            raise ValueError("missing required key 'settings' or 'security_and_analysis'")
        settings = options.table("settings", {})
        security = options.table("security_and_analysis", {})
        if not settings and not security:
            raise ValueError("'settings' must not be empty")
        unknown = sorted(set(settings) - REPO_BOOL_SETTINGS)
        if unknown:
            raise ValueError(f"unknown settings: {', '.join(unknown)}")
        not_bool = sorted(name for name, value in settings.items() if not isinstance(value, bool))
        if not_bool:
            raise ValueError(f"settings must be true or false: {', '.join(not_bool)}")
        unknown = sorted(set(security) - SECURITY_SETTINGS)
        if unknown:
            raise ValueError(f"unknown security_and_analysis settings: {', '.join(unknown)}")
        invalid = sorted(name for name, value in security.items() if value not in SECURITY_STATES)
        if invalid:
            raise ValueError(
                f"security_and_analysis values must be enabled or disabled: {', '.join(invalid)}"
            )
        return cls(settings=settings, security_and_analysis=security, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        findings = []
        for name, wanted in self.settings.items():
            current = workspace.setting(name)
            if current == wanted:
                continue
            if current is None:
                message = f"setting {name} {NOT_READABLE}"
                findings.append(Finding(self.id, message, fixable=False))
                continue
            workspace.change_setting(name, wanted)
            message = f"setting {name} is {json.dumps(current)}, expected {json.dumps(wanted)}"
            findings.append(Finding(self.id, message, setting=True))
        if self.security_and_analysis and workspace.setting("visibility") == "public":
            findings.extend(self._apply_security(workspace))
        return findings

    def _apply_security(self, workspace: Workspace) -> list[Finding]:
        current = workspace.setting("security_and_analysis")
        if not isinstance(current, dict):
            message = f"setting security_and_analysis {NOT_READABLE}"
            return [Finding(self.id, message, fixable=False)]
        findings = []
        payload = {}
        for name, wanted in self.security_and_analysis.items():
            entry = current.get(name)
            status = entry.get("status") if isinstance(entry, dict) else None
            if status == wanted:
                continue
            label = f"security_and_analysis.{name}"
            if status is None:
                message = f"setting {label} {NOT_READABLE}"
                findings.append(Finding(self.id, message, fixable=False))
                continue
            payload[name] = {"status": wanted}
            message = f"setting {label} is {json.dumps(status)}, expected {json.dumps(wanted)}"
            findings.append(Finding(self.id, message, setting=True))
        if payload:
            workspace.change_setting("security_and_analysis", payload)
        return findings


RULESET_PREFIX = "github-manager: "
RULESETS_UNAVAILABLE = (
    "rulesets are not available (a private repository on the GitHub Free plan: "
    "upgrade to GitHub Pro or make the repository public)"
)


@dataclass(frozen=True, kw_only=True)
class RepoRuleset(Rule):
    """The default branch must be protected by a ruleset owned by github-manager.

    The ruleset is named `github-manager: <rule id>`; it forbids deleting and force
    pushing the default branch and requires a pull request, without bypass actors.
    `required_status_checks` maps repository globs (name or OWNER/NAME) to check names;
    a repository gets the union of the checks of every matching glob. Other rulesets are
    never touched. Fixes are applied to the repository directly, not by pull request.
    """

    type_name: ClassVar[str] = "repo_ruleset"

    required_status_checks: dict[str, list[str]] = field(default_factory=dict)
    strict_required_status_checks: bool = False

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        checks = options.table("required_status_checks", {})
        for pattern, names in checks.items():
            if not pattern:
                raise ValueError("'required_status_checks' patterns must not be empty")
            if (
                not isinstance(names, list)
                or not names
                or not all(isinstance(name, str) and name for name in names)
            ):
                raise ValueError(
                    f"'required_status_checks' {pattern!r} must be a non-empty list "
                    "of non-empty strings"
                )
        return cls(
            required_status_checks=checks,
            strict_required_status_checks=options.flag("strict_required_status_checks", False),
            **common,
        )

    @property
    def ruleset_name(self) -> str:
        return f"{RULESET_PREFIX}{self.id}"

    def checks_for(self, full_name: str) -> list[str]:
        name = full_name.split("/", 1)[-1]
        return sorted(
            {
                check
                for pattern, checks in self.required_status_checks.items()
                if fnmatchcase(name, pattern) or fnmatchcase(full_name, pattern)
                for check in checks
            }
        )

    def payload(self, full_name: str) -> dict[str, Any]:
        rules: list[dict[str, Any]] = [
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
        ]
        checks = self.checks_for(full_name)
        if checks:
            rules.append(
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": self.strict_required_status_checks,
                        "do_not_enforce_on_create": False,
                        "required_status_checks": [{"context": check} for check in checks],
                    },
                }
            )
        return {
            "name": self.ruleset_name,
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "rules": rules,
        }

    def apply(self, workspace: Workspace) -> list[Finding]:
        listed = workspace.rulesets()
        if listed is None:
            return [Finding(self.id, RULESETS_UNAVAILABLE, fixable=False)]
        managed = [
            item
            for item in listed
            if item.get("source_type") == "Repository" and item.get("name") == self.ruleset_name
        ]
        if len(managed) > 1:
            message = f"multiple rulesets named {self.ruleset_name}"
            return [Finding(self.id, message, fixable=False)]

        wanted = self.payload(workspace.full_name)
        if not managed:
            workspace.change_ruleset(self.ruleset_name, None, wanted)
            return [Finding(self.id, f"ruleset {self.ruleset_name} is missing", setting=True)]
        ruleset_id = managed[0]["id"]
        if ruleset_matches(workspace.ruleset(ruleset_id), wanted):
            return []
        workspace.change_ruleset(self.ruleset_name, ruleset_id, wanted)
        return [Finding(self.id, f"ruleset {self.ruleset_name} is outdated", setting=True)]


def ruleset_matches(current: Any, wanted: Any) -> bool:
    """True when `current` carries everything in `wanted`.

    Only the keys in `wanted` count: GitHub adds defaults of its own (e.g. `required_reviewers`,
    `integration_id`). Lists compare without regard to order.
    """
    if isinstance(wanted, dict):
        return isinstance(current, dict) and all(
            key in current and ruleset_matches(current[key], value) for key, value in wanted.items()
        )
    if isinstance(wanted, list):
        if not isinstance(current, list) or len(current) != len(wanted):
            return False
        remaining = list(current)
        for item in wanted:
            found = next((c for c in remaining if ruleset_matches(c, item)), None)
            if found is None:
                return False
            remaining.remove(found)
        return True
    return current == wanted and type(current) is type(wanted)


VISIBILITIES = frozenset({"public", "private"})


@dataclass(frozen=True, kw_only=True)
class RepoVisibility(Rule):
    """The repositories of an owner must have the visibility given in `visibility`.

    `visibility` maps an owner to `public` or `private`; owners missing from it are not
    checked. Changing the visibility or transferring a repository is a human decision, so
    every mismatch needs manual action and nothing is written.
    """

    type_name: ClassVar[str] = "repo_visibility"

    visibility: dict[str, str]

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        visibility = options.table("visibility", REQUIRED)
        if not visibility:
            raise ValueError("'visibility' must not be empty")
        invalid = sorted(owner for owner, value in visibility.items() if value not in VISIBILITIES)
        if invalid:
            raise ValueError(f"visibility values must be public or private: {', '.join(invalid)}")
        lowered = [owner.lower() for owner in visibility]
        duplicates = sorted({owner for owner in lowered if lowered.count(owner) > 1})
        if duplicates:
            raise ValueError(f"duplicate visibility owners: {', '.join(duplicates)}")
        return cls(visibility=visibility, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        owner = workspace.full_name.split("/", 1)[0]
        wanted = next(
            (value for key, value in self.visibility.items() if key.lower() == owner.lower()),
            None,
        )
        if wanted is None:
            return []
        current = workspace.setting("visibility")
        if current is None:
            return [Finding(self.id, f"setting visibility {NOT_READABLE}", fixable=False)]
        if current == wanted:
            return []
        message = (
            f"visibility is {json.dumps(current)}, expected {json.dumps(wanted)} "
            f"for owner {owner} (change it or transfer the repository)"
        )
        return [Finding(self.id, message, fixable=False)]


WORKFLOWS_DIR = ".github/workflows/"
SELF_HOSTED = "self-hosted"
UBUNTU_PATTERN = "ubuntu-*"
YAML_STR = "tag:yaml.org,2002:str"
UNSAFE_REWRITE = "cannot rewrite safely"


@dataclass(frozen=True)
class _Replacement:
    """One `runs-on` value to overwrite: `text[start:end]` becomes `text`."""

    job: str
    problem: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, kw_only=True)
class SelfHostedRunners(Rule):
    """Every job of a private or internal repository must run on an allowed self-hosted runner.

    `allowed_runs_on` lists the accepted label sets; a job's `runs-on` must equal one of them
    exactly (as a set, ignoring case). A single `ubuntu-*` label and a label set that contains
    `self-hosted` but is not allowed are rewritten to `runs_on`, when the value sits on the
    same line as its `runs-on` key (a scalar or a flow list); the rest of the file stays
    byte for byte the same. Every other job (other operating systems, unknown labels,
    expressions, matrices, mappings, external reusable workflows) and workflow files that
    cannot be parsed are reported as manual. Public repositories are not checked.
    """

    type_name: ClassVar[str] = "self_hosted_runners"

    allowed_runs_on: list[list[str]]
    runs_on: list[str]

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        allowed = options.text_lists("allowed_runs_on", REQUIRED)
        if not allowed:
            raise ValueError("'allowed_runs_on' must not be empty")
        seen: set[frozenset[str]] = set()
        for labels in allowed:
            folded = frozenset(label.casefold() for label in labels)
            if SELF_HOSTED not in folded:
                raise ValueError(
                    f"'allowed_runs_on' set {json.dumps(labels)} must contain {SELF_HOSTED!r}"
                )
            if folded in seen:
                raise ValueError(f"duplicate 'allowed_runs_on' set: {json.dumps(labels)}")
            seen.add(folded)
        runs_on = options.text_list("runs_on", REQUIRED)
        if not runs_on:
            raise ValueError("'runs_on' must not be empty")
        if frozenset(label.casefold() for label in runs_on) not in seen:
            raise ValueError(
                f"'runs_on' {json.dumps(runs_on)} must equal one of the 'allowed_runs_on' sets"
            )
        return cls(allowed_runs_on=allowed, runs_on=runs_on, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        visibility = workspace.setting("visibility")
        if visibility is None:
            return [Finding(self.id, f"setting visibility {NOT_READABLE}", fixable=False)]
        if visibility == "public":
            return []
        listed = workspace.paths(WORKFLOWS_DIR)
        if listed is None:
            message = f"{WORKFLOWS_DIR}: the workflow files cannot be listed"
            return [Finding(self.id, message, fixable=False)]
        files = [
            path
            for path in listed
            if path.endswith((".yml", ".yaml")) and "/" not in path[len(WORKFLOWS_DIR) :]
        ]
        return [finding for path in files for finding in self._check_file(workspace, path)]

    def _check_file(self, workspace: Workspace, path: str) -> list[Finding]:
        text = workspace.read(path)
        if text is None:
            return [self._manual(path, "the file is not readable")]
        jobs, error = _jobs(text)
        if jobs is None:
            return [self._manual(path, error or "")]
        findings = []
        replacements = []
        # Jobs that share one mapping through an alias reach the same value node.
        reached = Counter(id(_entry(job, "runs-on")[1]) for job in jobs.values())
        for name, job in jobs.items():
            problem = self._job_problem(job)
            if problem is None:
                continue
            if not self._rewritable(job):
                findings.append(self._manual(path, f"job {name}: {problem}"))
                continue
            replacement = self._replacement(name, problem, job, text)
            if replacement is None or reached[id(_entry(job, "runs-on")[1])] > 1:
                findings.append(self._manual(path, f"job {name}: {problem}; {UNSAFE_REWRITE}"))
            else:
                replacements.append(replacement)
        if not replacements:
            return findings
        ordered = sorted(replacements, key=lambda item: item.start, reverse=True)
        overlapping = any(before.end > after.start for after, before in pairwise(ordered))
        new_text = text
        for replacement in ordered:
            new_text = (
                new_text[: replacement.start] + replacement.text + new_text[replacement.end :]
            )
        if overlapping or not self._verified(new_text, replacements):
            findings.extend(
                self._manual(path, f"job {item.job}: {item.problem}; {UNSAFE_REWRITE}")
                for item in replacements
            )
            return findings
        workspace.write(path, new_text)
        wanted = json.dumps(self.runs_on)
        findings.extend(
            Finding(self.id, f"{path}: job {item.job}: {item.problem}; set runs-on to {wanted}")
            for item in replacements
        )
        return findings

    def _manual(self, path: str, problem: str) -> Finding:
        return Finding(self.id, f"{path}: {problem}", fixable=False)

    def _verified(self, new_text: str, replacements: list[_Replacement]) -> bool:
        """True when the rewritten file parses and every rewritten job is now allowed."""
        jobs, _ = _jobs(new_text)
        return jobs is not None and all(
            item.job in jobs and self._job_problem(jobs[item.job]) is None for item in replacements
        )

    def _rewritable(self, job: yaml.Node) -> bool:
        """True for a single `ubuntu-*` label or a label set with `self-hosted`."""
        labels = _labels((_mapping(job) or {}).get("runs-on"))
        if labels is None or any("${{" in label for label in labels):
            return False
        folded = frozenset(label.casefold() for label in labels)
        if folded in self._allowed_sets():
            return False
        return SELF_HOSTED in folded or (
            len(folded) == 1 and fnmatchcase(next(iter(folded)), UBUNTU_PATTERN)
        )

    def _replacement(
        self, name: str, problem: str, job: yaml.Node, text: str
    ) -> _Replacement | None:
        """The edit for a job's `runs-on`, or None when the value is not safe to splice."""
        key, value = _entry(job, "runs-on")
        if key is None or value is None:
            return None
        start, end = value.start_mark, value.end_mark
        one_line = key.start_mark.line == start.line == end.line
        scalar_or_flow = isinstance(value, yaml.ScalarNode) or (
            isinstance(value, yaml.SequenceNode) and bool(value.flow_style)
        )
        # An anchor or tag belongs to the node's own span; dropping it would break aliases.
        if not (one_line and scalar_or_flow) or text[start.index] in "&!":
            return None
        # A list item that is an alias starts outside the list; an anchored or tagged one
        # starts with its `&` or `!`.
        items = value.value if isinstance(value, yaml.SequenceNode) else []
        if any(
            not start.index < item.start_mark.index < end.index
            or text[item.start_mark.index] in "&!*"
            for item in items
        ):
            return None
        rendered = self.runs_on[0] if len(self.runs_on) == 1 else f"[{', '.join(self.runs_on)}]"
        return _Replacement(name, problem, start.index, end.index, rendered)

    def _job_problem(self, job: yaml.Node) -> str | None:
        fields = _mapping(job)
        if fields is None:
            return "is not a mapping"
        runs_on = fields.get("runs-on")
        if runs_on is None:
            uses = fields.get("uses")
            if _text(uses) is None:
                return "has neither 'runs-on' nor 'uses'"
            if (_text(uses) or "").startswith("./"):
                return None
            return f"calls {json.dumps(_text(uses))} without 'runs-on' (check the runner manually)"
        allowed = " or ".join(json.dumps(labels) for labels in self.allowed_runs_on)
        if _text(runs_on) is not None:
            labels = [_text(runs_on) or ""]
        elif isinstance(runs_on, yaml.SequenceNode):
            texts = [_text(item) for item in runs_on.value]
            if any(text is None for text in texts):
                return (
                    f"runs-on {_json(runs_on)} has a list item that is not a string"
                    f" (check manually; allowed: {allowed})"
                )
            labels = [text for text in texts if text is not None]
        else:
            return (
                f"runs-on {_json(runs_on)} must be a string or a list of strings"
                f" (check manually; allowed: {allowed})"
            )
        actual = json.dumps(labels)
        if any("${{" in label for label in labels):
            return f"runs-on {actual} contains an expression (check manually; allowed: {allowed})"
        if frozenset(label.casefold() for label in labels) in self._allowed_sets():
            return None
        return f"runs-on {actual} is not an allowed self-hosted runner (allowed: {allowed})"

    def _allowed_sets(self) -> set[frozenset[str]]:
        return {frozenset(label.casefold() for label in labels) for labels in self.allowed_runs_on}


def _mapping(node: yaml.Node | None) -> dict[str, yaml.Node] | None:
    """The scalar-keyed entries of a YAML mapping node, in document order."""
    if not isinstance(node, yaml.MappingNode):
        return None
    return {key.value: value for key, value in node.value if isinstance(key, yaml.ScalarNode)}


def _entry(node: yaml.Node, name: str) -> tuple[yaml.Node | None, yaml.Node | None]:
    """The key and value nodes of the scalar key `name` in a YAML mapping node."""
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode) and key.value == name:
                return key, value
    return None, None


def _jobs(text: str) -> tuple[dict[str, yaml.Node] | None, str | None]:
    """The `jobs` entries of a workflow file, or None and the reason they cannot be read."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem", None) or "invalid YAML"
        return None, f"invalid YAML ({problem})"
    top = _mapping(root)
    jobs = _mapping(top.get("jobs")) if top is not None else None
    if jobs is None:
        return None, "no 'jobs' mapping"
    return jobs, None


def _labels(node: yaml.Node | None) -> list[str] | None:
    """The labels of a `runs-on` string or list of strings; None for any other node."""
    if _text(node) is not None:
        return [_text(node) or ""]
    if isinstance(node, yaml.SequenceNode):
        texts = [_text(item) for item in node.value]
        if all(text is not None for text in texts):
            return [text for text in texts if text is not None]
    return None


def _json(node: yaml.Node) -> str:
    """The JSON rendering of a YAML node's value, for messages."""
    return json.dumps(yaml.SafeLoader("").construct_document(node), default=str)


def _text(node: yaml.Node | None) -> str | None:
    """The value of a YAML string scalar node; None for any other node."""
    if isinstance(node, yaml.ScalarNode) and node.tag == YAML_STR:
        return node.value
    return None


RULE_TYPES: dict[str, type[Rule]] = {
    rule.type_name: rule
    for rule in (
        RequiredLines,
        RenovatePreset,
        FileSync,
        BranchStrategy,
        RepoSettings,
        RepoRuleset,
        RepoVisibility,
        SelfHostedRunners,
    )
}
