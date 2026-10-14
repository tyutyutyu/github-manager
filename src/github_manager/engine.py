"""Evaluate rules against repositories and turn fixes into one pull request per repository."""

import difflib
from dataclasses import dataclass, field
from enum import StrEnum
from fnmatch import fnmatchcase
from typing import Protocol

from github_manager.config import Config
from github_manager.github import GitHubError, PullRequest, Repo
from github_manager.rules import Finding


class GitHubApi(Protocol):
    def list_repos(self, owner: str) -> list[Repo]: ...
    def branch_sha(self, repo: str, branch: str) -> str | None: ...
    def compare(self, repo: str, base: str, head: str) -> tuple[int, int, set[str]]: ...
    def tree_paths(self, repo: str, sha: str) -> set[str] | None: ...
    def read_file(self, repo: str, path: str, ref: str) -> str | None: ...
    def reset_branch(self, repo: str, branch: str, sha: str, *, exists: bool) -> None: ...
    def delete_branch(self, repo: str, branch: str) -> None: ...
    def commit_files(
        self, repo: str, branch: str, head_sha: str, message: str, files: dict[str, str]
    ) -> str: ...
    def find_open_pr(self, repo: str, branch: str) -> PullRequest | None: ...
    def create_pr(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequest: ...
    def update_pr(self, repo: str, number: int, title: str, body: str) -> None: ...
    def close_pr(self, repo: str, number: int, comment: str) -> None: ...


class Outcome(StrEnum):
    COMPLIANT = "compliant"
    NEEDS_FIX = "needs fix"
    SKIPPED = "skipped"
    PR_CREATED = "pull request created"
    PR_UPDATED = "pull request updated"
    PR_UP_TO_DATE = "pull request up to date"
    PR_CLOSED = "obsolete pull request closed"
    ERROR = "error"


@dataclass
class RepoReport:
    repo: str
    outcome: Outcome
    findings: list[Finding] = field(default_factory=list)
    diffs: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def manual_findings(self) -> list[Finding]:
        return [finding for finding in self.findings if not finding.fixable]


class RemoteWorkspace:
    """Files of one commit, read lazily, with local writes layered on top."""

    def __init__(self, api: GitHubApi, repo: str, sha: str, default_branch: str) -> None:
        self._api = api
        self._repo = repo
        self._sha = sha
        self.default_branch = default_branch
        self._paths = api.tree_paths(repo, sha)
        self._original: dict[str, str | None] = {}
        self._written: dict[str, str] = {}

    def branch_exists(self, branch: str) -> bool:
        return self._api.branch_sha(self._repo, branch) is not None

    def original(self, path: str) -> str | None:
        if path not in self._original:
            if self._paths is not None and path not in self._paths:
                self._original[path] = None
            else:
                self._original[path] = self._api.read_file(self._repo, path, self._sha)
        return self._original[path]

    def read(self, path: str) -> str | None:
        return self._written[path] if path in self._written else self.original(path)

    def write(self, path: str, content: str) -> None:
        self._written[path] = content

    def changes(self) -> dict[str, str]:
        return {
            path: content
            for path, content in sorted(self._written.items())
            if content != self.original(path)
        }

    def diff(self, path: str) -> str:
        before = (self.original(path) or "").splitlines(keepends=True)
        after = self._written[path].splitlines(keepends=True)
        return "".join(difflib.unified_diff(before, after, f"a/{path}", f"b/{path}"))


def select_repos(
    api: GitHubApi, config: Config, only: list[str], owners: list[str] | None = None
) -> list[Repo]:
    """Repositories in scope, across every configured owner.

    `only` entries are `owner/name` or a bare `name` that must be unambiguous;
    `owners` limits the run to some of the configured owners.
    """
    configured = {owner.lower(): owner for owner in config.owners}
    unknown_owners = sorted({owner for owner in owners or [] if owner.lower() not in configured})
    if unknown_owners:
        raise GitHubError(f"owners not in the configuration: {', '.join(unknown_owners)}")
    wanted = {owner.lower() for owner in owners} if owners else set(configured)
    repos = [
        repo for key, owner in configured.items() if key in wanted for repo in api.list_repos(owner)
    ]

    picked = _pick_repos(repos, only)
    return [
        repo
        for repo in sorted(repos, key=lambda repo: repo.full_name.lower())
        if (not only or repo.full_name in picked)
        and not (repo.archived or (repo.fork and not config.include_forks))
        and not _excluded(repo, config.exclude)
    ]


def _pick_repos(repos: list[Repo], only: list[str]) -> set[str]:
    picked: set[str] = set()
    for entry in only:
        key = entry.lower()
        field = "full_name" if "/" in key else "name"
        matches = [repo.full_name for repo in repos if getattr(repo, field).lower() == key]
        if not matches:
            raise GitHubError(f"unknown repository: {entry}")
        if len(matches) > 1:
            raise GitHubError(f"ambiguous repository {entry}: {', '.join(sorted(matches))}")
        picked.update(matches)
    return picked


def _excluded(repo: Repo, patterns: list[str]) -> bool:
    return any(
        fnmatchcase(repo.name, pattern) or fnmatchcase(repo.full_name, pattern)
        for pattern in patterns
    )


def process_repo(api: GitHubApi, config: Config, repo: Repo, *, fix: bool) -> RepoReport:
    try:
        return _process(api, config, repo, fix=fix)
    except GitHubError as exc:
        return RepoReport(repo.full_name, Outcome.ERROR, detail=str(exc))


def _process(api: GitHubApi, config: Config, repo: Repo, *, fix: bool) -> RepoReport:
    base_sha = api.branch_sha(repo.full_name, repo.default_branch)
    if base_sha is None:
        return RepoReport(repo.full_name, Outcome.SKIPPED, detail="empty repository")

    workspace = RemoteWorkspace(api, repo.full_name, base_sha, repo.default_branch)
    findings: list[Finding] = []
    for rule in config.rules:
        if rule.applies_to(repo.name, repo.full_name):
            findings.extend(rule.apply(workspace))
    changes = workspace.changes()
    report = RepoReport(
        repo.full_name,
        Outcome.NEEDS_FIX if findings else Outcome.COMPLIANT,
        findings=findings,
        diffs=[workspace.diff(path) for path in changes],
    )
    if fix:
        report.outcome, report.detail = _sync_pull_request(
            api, config, repo, base_sha, report, changes
        )
    return report


def _sync_pull_request(
    api: GitHubApi,
    config: Config,
    repo: Repo,
    base_sha: str,
    report: RepoReport,
    changes: dict[str, str],
) -> tuple[Outcome, str]:
    name, branch = repo.full_name, config.branch
    pull = api.find_open_pr(name, branch)
    branch_sha = api.branch_sha(name, branch)

    if not changes:
        if pull is None:
            return report.outcome, ""
        api.close_pr(name, pull.number, "The default branch already satisfies the rules.")
        if branch_sha is not None:
            api.delete_branch(name, branch)
        return Outcome.PR_CLOSED, pull.url

    body = _pr_body(report)
    if (
        pull is not None
        and branch_sha is not None
        and _branch_matches(api, name, base_sha, branch_sha, changes)
    ):
        api.update_pr(name, pull.number, config.pr_title, body)
        return Outcome.PR_UP_TO_DATE, pull.url

    api.reset_branch(name, branch, base_sha, exists=branch_sha is not None)
    message = f"{config.commit_message}\n\n" + "\n".join(_finding_lines(report.findings))
    api.commit_files(name, branch, base_sha, message, changes)
    if pull is not None:
        api.update_pr(name, pull.number, config.pr_title, body)
        return Outcome.PR_UPDATED, pull.url
    pull = api.create_pr(name, repo.default_branch, branch, config.pr_title, body)
    return Outcome.PR_CREATED, pull.url


def _branch_matches(
    api: GitHubApi, repo: str, base_sha: str, branch_sha: str, changes: dict[str, str]
) -> bool:
    """True when the branch is exactly one commit on top of base carrying these changes."""
    ahead, behind, paths = api.compare(repo, base_sha, branch_sha)
    return (ahead, behind, paths) == (1, 0, set(changes)) and all(
        api.read_file(repo, path, branch_sha) == text for path, text in changes.items()
    )


def _finding_lines(findings: list[Finding]) -> list[str]:
    return [f"- {finding.rule_id}: {finding.message}" for finding in findings]


def _pr_body(report: RepoReport) -> str:
    fixed = [finding for finding in report.findings if finding.fixable]
    lines = [
        "This pull request was opened by **github-manager** to align the repository "
        "with the central rules.",
        "",
        "### Fixed",
        *_finding_lines(fixed),
    ]
    if report.manual_findings:
        lines += ["", "### Needs manual action", *_finding_lines(report.manual_findings)]
    lines += ["", "_The branch is regenerated on every run; do not push to it by hand._"]
    return "\n".join(lines)
