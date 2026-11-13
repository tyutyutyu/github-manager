"""Rules about file contents and presence."""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Self

from github_manager.rules.base import REQUIRED, Finding, Options, Rule, Workspace


@dataclass(frozen=True, kw_only=True)
class RequiredLines(Rule):
    """The file must contain a managed block, delimited by marker comments, holding `lines`.

    `lines` is one multi-line string, written into the block line by line. The
    block is replaced as a whole on every fix, so changing `lines` in the
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
        return cls(
            path=options.text("path", REQUIRED),
            lines=options.text_block("lines", REQUIRED),
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
class RequiredFiles(Rule):
    """Every file in `paths` must exist in the repository.

    Only the existence is checked, not the content. The content differs per project and
    cannot be generated, so every missing file needs manual action and nothing is written.
    """

    type_name: ClassVar[str] = "required_files"

    paths: list[str]

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        paths = options.text_list("paths", REQUIRED)
        if not paths:
            raise ValueError("'paths' must not be empty")
        for path in paths:
            if path.startswith("/") or path.endswith("/"):
                raise ValueError(f"'paths' item {path!r} must not start or end with '/'")
            if ".." in path.split("/"):
                raise ValueError(f"'paths' item {path!r} must not contain a '..' segment")
        duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate 'paths' items: {', '.join(duplicates)}")
        return cls(paths=paths, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        return [
            Finding(self.id, f"{path}: missing", fixable=False)
            for path in self.paths
            if workspace.read(path) is None
        ]
