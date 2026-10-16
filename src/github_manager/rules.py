"""Rule types. A rule inspects a repository workspace and writes the fixes it needs.

Rules never talk to GitHub directly: they read and write through a `Workspace`,
so the same code serves `check` (changes are discarded) and `fix` (file changes are
committed to a pull request, setting changes are applied to the repository).
"""

import contextlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, ClassVar, Protocol, Self


class Workspace(Protocol):
    @property
    def default_branch(self) -> str: ...

    def branch_exists(self, branch: str) -> bool: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, content: str) -> None: ...

    def setting(self, name: str) -> Any: ...

    def change_setting(self, name: str, value: Any) -> None: ...


@dataclass(frozen=True)
class Finding:
    rule_id: str
    message: str
    fixable: bool = True
    # Fixed through the repository settings, not through the pull request.
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


RULE_TYPES: dict[str, type[Rule]] = {
    rule.type_name: rule
    for rule in (RequiredLines, RenovatePreset, FileSync, BranchStrategy, RepoSettings)
}
