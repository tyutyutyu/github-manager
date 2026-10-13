"""Rule types. A rule inspects a repository workspace and writes the fixes it needs.

Rules never talk to GitHub directly: they read and write through a `Workspace`,
so the same code serves `check` (changes are discarded) and `fix` (changes are
committed to a pull request).
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
    def read(self, path: str) -> str | None: ...

    def write(self, path: str, content: str) -> None: ...


@dataclass(frozen=True)
class Finding:
    rule_id: str
    message: str
    fixable: bool = True


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

    def finish(self) -> None:
        if self._raw:
            raise ValueError(f"unknown keys: {', '.join(sorted(self._raw))}")


@dataclass(frozen=True, kw_only=True)
class Rule(ABC):
    type_name: ClassVar[str]

    id: str
    exclude: list[str] = field(default_factory=list)

    def applies_to(self, repo_name: str) -> bool:
        return not any(fnmatchcase(repo_name, pattern) for pattern in self.exclude)

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
    """Every listed line must be present in the file; missing ones are appended."""

    type_name: ClassVar[str] = "required_lines"

    path: str
    lines: list[str]
    header: str | None = None

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        lines = options.text_list("lines", REQUIRED)
        if not lines:
            raise ValueError("'lines' must not be empty")
        return cls(
            path=options.text("path", REQUIRED),
            lines=lines,
            header=options.text("header"),
            **common,
        )

    def apply(self, workspace: Workspace) -> list[Finding]:
        content = workspace.read(self.path) or ""
        present = {line.strip() for line in content.splitlines()}
        missing = [line for line in self.lines if line.strip() not in present]
        if not missing:
            return []

        block = [self.header] if self.header and self.header.strip() not in present else []
        block += missing
        prefix = content if not content or content.endswith("\n") else content + "\n"
        separator = "\n" if prefix else ""
        workspace.write(self.path, prefix + separator + "\n".join(block) + "\n")
        return [Finding(self.id, f"{self.path}: missing lines: {', '.join(missing)}")]


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


RULE_TYPES: dict[str, type[Rule]] = {
    rule.type_name: rule for rule in (RequiredLines, RenovatePreset, FileSync)
}
