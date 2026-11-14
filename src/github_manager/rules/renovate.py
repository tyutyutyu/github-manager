"""The Renovate preset rule."""

import contextlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self

from github_manager.rules.base import (
    REQUIRED,
    Finding,
    FindingKind,
    Options,
    Rule,
    Workspace,
    line_ending,
)

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
            return [
                Finding(self.id, f"multiple Renovate configs: {names}", kind=FindingKind.MANUAL)
            ]

        path = existing[0]
        text = workspace.read(path) or ""
        if path.endswith(".json5"):
            return self._manual(path, text)
        try:
            config = json.loads(text)
        except json.JSONDecodeError as exc:
            return [Finding(self.id, f"{path}: invalid JSON ({exc.msg})", kind=FindingKind.MANUAL)]
        if not isinstance(config, dict):
            return [
                Finding(self.id, f"{path}: top level must be an object", kind=FindingKind.MANUAL)
            ]
        extends = config.get("extends", [])
        if not isinstance(extends, list):
            return [Finding(self.id, f"{path}: 'extends' must be a list", kind=FindingKind.MANUAL)]

        wanted = [item for item in extends if item not in self.remove_extends]
        if self.preset not in wanted:
            wanted.insert(0, self.preset)
        if wanted == extends:
            return []

        config["extends"] = wanted
        workspace.write(path, _rewrite_extends(text, config))
        return [Finding(self.id, f"{path}: extends {extends} -> {wanted}")]

    def _manual(self, path: str, text: str) -> list[Finding]:
        if self.preset in (_json5_extends(text) or []):
            return []
        return [Finding(self.id, f"{path}: does not extend {self.preset}", kind=FindingKind.MANUAL)]


_JSON5_TOKEN = re.compile(
    r"""(?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')"""
    r"|(?P<comment>//[^\n]*|/\*.*?\*/)"
    r"|(?P<punct>[\[\]:])"
    r"|(?P<name>[A-Za-z_$][\w$]*)",
    re.DOTALL,
)
_EXTENDS_KEYS = frozenset({"extends", '"extends"', "'extends'"})


def _json5_extends(text: str) -> list[str] | None:
    """Return the string items of the first `extends` array in a JSON5 text, or None.

    A regex tokenizer that tells strings from comments, not a JSON5 parser: it takes the
    first `extends` array even when it sits in a nested object (e.g. a `packageRules`
    item), and an item is its raw text between the quotes (escapes are not decoded).
    """
    tokens = [m for m in _JSON5_TOKEN.finditer(text) if m.lastgroup != "comment"]
    for index, token in enumerate(tokens[:-2]):
        if token.group() not in _EXTENDS_KEYS:
            continue
        if [t.group() for t in tokens[index + 1 : index + 3]] != [":", "["]:
            continue
        items: list[str] = []
        for item in tokens[index + 3 :]:
            if item.group() == "]":
                break
            if item.lastgroup == "string":
                items.append(item.group()[1:-1])
        return items
    return None


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
    rendered = json.dumps(config, indent=len(indent.group(1)) if indent else 2) + "\n"
    return rendered.replace("\n", line_ending(text))


def _render_array(items: list[str], old_array: str, text: str, start: int) -> str:
    rendered = [json.dumps(item, ensure_ascii=False) for item in items]
    item_indent = re.search(r"\[\s*?\n([ \t]*)\S", old_array)
    if item_indent is None:
        return "[" + ", ".join(rendered) + "]"
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start:start]
    close_indent = line[: len(line) - len(line.lstrip(" \t"))]
    newline = "\r\n" if "\r\n" in old_array else "\n"
    body = f",{newline}".join(item_indent.group(1) + item for item in rendered)
    return f"[{newline}{body}{newline}{close_indent}]"
