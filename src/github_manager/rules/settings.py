"""Rules about branch, repository settings and visibility."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Self

from github_manager.rules.base import NOT_READABLE, REQUIRED, Finding, Options, Rule, Workspace


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


# Boolean repository settings accepted by `PATCH /repos/{owner}/{repo}`.
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


@dataclass(frozen=True, kw_only=True)
class RepoSettings(Rule):
    """The repository settings must have the values in `settings`.

    `security_and_analysis` additionally requires the secret scanning features, on public
    repositories only (they are paid features on private ones, which are skipped).
    Fixes are applied to the repository directly (through the REST API), not by pull request.
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
