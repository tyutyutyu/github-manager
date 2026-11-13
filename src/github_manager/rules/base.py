"""Rule foundations: the workspace protocol, findings, options and the rule base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, ClassVar, Protocol, Self


class Workspace(Protocol):
    @property
    def default_branch(self) -> str: ...

    @property
    def full_name(self) -> str: ...

    def branch_exists(self, branch: str) -> bool: ...

    def read(self, path: str) -> str | None: ...

    def write(self, path: str, content: str) -> None: ...

    def paths(self, prefix: str) -> list[str] | None: ...

    def original(self, path: str) -> str | None:
        """The file on the default branch commit, without pending writes."""
        ...

    def original_paths(self, prefix: str) -> list[str] | None:
        """The paths on the default branch commit, without pending writes."""
        ...

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

    def text_block(self, key: str, default: Any = None) -> list[str]:
        """A multi-line string as lines: outer blank lines and trailing spaces dropped."""
        value = self._take(key, str, default)
        lines = [line.rstrip() for line in value.splitlines()]
        for number, line in enumerate(lines, 1):
            if line != line.lstrip():
                raise ValueError(f"{key!r} line {number} must not be indented: {line!r}")
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            raise ValueError(f"{key!r} must not be empty")
        return lines

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


NOT_READABLE = "is not readable (the token needs Administration access)"
