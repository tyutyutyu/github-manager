"""Rules about workspace repositories."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self

import yaml

from github_manager.rules.base import (
    Finding,
    FindingKind,
    Options,
    Rule,
    Workspace,
)

DEFAULT_MANIFEST = "workspace.yaml"
ORIGIN_PATTERN = re.compile(
    r"(?:git@github\.com:|https://github\.com/)(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?"
)
RESERVED_NAMES = frozenset({".", ".."})
NOT_VISIBLE = "does not exist or is not readable (the App needs an installation on its owner)"


@dataclass(frozen=True, kw_only=True)
class WorkspaceMembers(Rule):
    """Every member repository listed in the workspace manifest must exist and be readable.

    The manifest is read from `path`; each `repositories` item needs a `name` and a GitHub
    `origin` (`git@github.com:OWNER/NAME(.git)` or `https://github.com/OWNER/NAME(.git)`).
    The check uses the read token of the member's owner. Only reports; nothing is written.
    """

    type_name: ClassVar[str] = "workspace_members"

    path: str = DEFAULT_MANIFEST

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        path = options.text("path", DEFAULT_MANIFEST)
        if path.startswith("/") or path.endswith("/"):
            raise ValueError(f"'path' {path!r} must not start or end with '/'")
        if ".." in path.split("/"):
            raise ValueError(f"'path' {path!r} must not contain a '..' segment")
        return cls(path=path, **common)

    def _manual(self, message: str) -> Finding:
        return Finding(self.id, f"{self.path}: {message}", kind=FindingKind.MANUAL)

    def apply(self, workspace: Workspace) -> list[Finding]:
        content = workspace.read(self.path)
        if content is None:
            return [self._manual("missing")]
        try:
            manifest = yaml.safe_load(content)
        except yaml.YAMLError, ValueError:
            return [self._manual("is not valid YAML")]
        members = manifest.get("repositories") if isinstance(manifest, dict) else None
        if not isinstance(members, list):
            return [self._manual("has no 'repositories' list")]
        findings = []
        for index, member in enumerate(members, 1):
            finding = self._check_member(workspace, index, member)
            if finding is not None:
                findings.append(finding)
        return findings

    @staticmethod
    def _label(index: int, name: Any, origin: Any) -> str:
        if isinstance(name, str) and name:
            return name
        if isinstance(origin, str) and origin:
            return f"repositories item {index} ({origin})"
        return f"repositories item {index}"

    def _check_member(self, workspace: Workspace, index: int, member: Any) -> Finding | None:
        name = member.get("name") if isinstance(member, dict) else None
        origin = member.get("origin") if isinstance(member, dict) else None
        label = self._label(index, name, origin)
        if not (isinstance(name, str) and name and isinstance(origin, str) and origin):
            return self._manual(f"{label}: 'name' or 'origin' is missing")
        match = ORIGIN_PATTERN.fullmatch(origin)
        if match is None or match["name"] in RESERVED_NAMES:
            return self._manual(f"{label}: unsupported origin {origin!r}")
        full_name = f"{match['owner']}/{match['name']}"
        if workspace.repo_exists(full_name):
            return None
        return self._manual(f"{label}: repository {full_name} {NOT_VISIBLE}")
