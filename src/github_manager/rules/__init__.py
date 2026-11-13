"""Rule types. A rule inspects a repository workspace and writes the fixes it needs.

Rules never talk to GitHub directly: they read and write through a `Workspace`,
so the same code serves `check` (changes are discarded) and `fix` (file changes are
committed to a pull request, setting and ruleset changes are applied to the repository).
"""

from github_manager.rules.base import NOT_READABLE, REQUIRED, Finding, Options, Rule, Workspace
from github_manager.rules.files import FileSync, RequiredFiles, RequiredLines
from github_manager.rules.renovate import RenovatePreset
from github_manager.rules.ruleset import RepoRuleset, ruleset_matches
from github_manager.rules.settings import BranchStrategy, RepoSettings, RepoVisibility
from github_manager.rules.workflows import DefaultBranchPushOnly, SelfHostedRunners

__all__ = [
    "NOT_READABLE",
    "REQUIRED",
    "RULE_TYPES",
    "BranchStrategy",
    "DefaultBranchPushOnly",
    "FileSync",
    "Finding",
    "Options",
    "RenovatePreset",
    "RepoRuleset",
    "RepoSettings",
    "RepoVisibility",
    "RequiredFiles",
    "RequiredLines",
    "Rule",
    "SelfHostedRunners",
    "Workspace",
    "ruleset_matches",
]

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
        RequiredFiles,
        DefaultBranchPushOnly,
        SelfHostedRunners,
    )
}
