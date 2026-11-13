"""The default-branch ruleset rule."""

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, ClassVar, Self

from github_manager.rules.base import Finding, Options, Rule, Workspace
from github_manager.rules.workflows import _workflow_check_problem

RULESET_PREFIX = "github-manager: "
RULESETS_UNAVAILABLE = (
    "rulesets are not available (a private repository on the GitHub Free plan: "
    "upgrade to GitHub Pro or make the repository public)"
)


@dataclass(frozen=True, kw_only=True)
class RepoRuleset(Rule):
    """The default branch must be protected by a ruleset owned by github-manager.

    The ruleset is named `github-manager: <rule id>`; it forbids deleting and force
    pushing the default branch and requires a pull request that can only be squash
    merged, without bypass actors.
    `required_status_checks` maps repository globs (name or OWNER/NAME) to check names;
    a repository gets the union of the checks of every matching glob. Other rulesets are
    never touched. Fixes are applied to the repository directly, not by pull request.

    `required_workflow_check` names a check (e.g. `verify`) that is added to the required
    checks only when a workflow on the default branch certainly runs it on pull requests
    (see `workflow_check_problem`); otherwise a manual finding says what is missing, because
    a required check that never reports blocks every merge.
    """

    type_name: ClassVar[str] = "repo_ruleset"

    required_status_checks: dict[str, list[str]] = field(default_factory=dict)
    strict_required_status_checks: bool = False
    required_workflow_check: str | None = None

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
            required_workflow_check=options.text("required_workflow_check", None),
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

    def workflow_check_problem(self, workspace: Workspace) -> str | None:
        """Why the workflow check cannot be required in this repository; None when it can.

        Also None when the rule has no `required_workflow_check`: use `requires_workflow_check`
        to ask whether the check is required.
        """
        if self.required_workflow_check is None:
            return None
        return _workflow_check_problem(
            workspace, self.required_workflow_check, workspace.default_branch
        )

    def requires_workflow_check(self, workspace: Workspace) -> bool:
        """True when the managed ruleset requires the workflow check in this repository.

        False where rulesets are not available, because then no ruleset requires it.
        """
        return (
            self.required_workflow_check is not None
            and workspace.rulesets() is not None
            and self.workflow_check_problem(workspace) is None
        )

    def _checks(self, full_name: str, workflow_check: bool) -> list[str]:
        checks = set(self.checks_for(full_name))
        if workflow_check and self.required_workflow_check is not None:
            checks.add(self.required_workflow_check)
        return sorted(checks)

    def payload(self, full_name: str, checks: list[str] | None = None) -> dict[str, Any]:
        """The ruleset body; `checks` defaults to the matching globs' checks."""
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
                    "allowed_merge_methods": ["squash"],
                },
            },
        ]
        checks = self.checks_for(full_name) if checks is None else checks
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
        problem = self.workflow_check_problem(workspace)
        valid = self.required_workflow_check is not None and problem is None
        checks = self._checks(workspace.full_name, valid)
        findings = self._sync(workspace, checks)
        if problem:
            message = f"required check {self.required_workflow_check} is not added: {problem}"
            findings.append(Finding(self.id, message, fixable=False))
        return findings

    def _sync(self, workspace: Workspace, checks: list[str]) -> list[Finding]:
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

        wanted = self.payload(workspace.full_name, checks)
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
