"""Command line interface: `check`, `fix` and `repos`."""

import argparse
import os
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from github_manager.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from github_manager.engine import GitHubApi, Outcome, RepoReport, process_repo, select_repos
from github_manager.github import GitHub, GitHubError, resolve_token

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

ApiFactory = Callable[[], GitHubApi]


def _default_api() -> GitHubApi:
    return GitHub(resolve_token())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-manager",
        description="Validate and fix GitHub repositories against central rules.",
    )
    parser.add_argument(
        "-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="rule file (TOML)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="report rule violations; changes nothing")
    check.add_argument("--diff", action="store_true", help="show the changes a fix would make")
    fix = commands.add_parser("fix", help="open or refresh one pull request per repository")
    repos = commands.add_parser("repos", help="list the repositories the rules apply to")
    for command in (check, fix, repos):
        command.add_argument(
            "-o",
            "--owner",
            action="append",
            default=[],
            help="limit to a configured owner (repeatable)",
        )
    for command in (check, fix):
        command.add_argument(
            "-r",
            "--repo",
            action="append",
            default=[],
            help="limit to a repository: OWNER/NAME, or NAME if unambiguous (repeatable)",
        )
    return parser


def main(argv: Sequence[str] | None = None, api_factory: ApiFactory = _default_api) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        api = api_factory()
        repos = select_repos(api, config, getattr(args, "repo", []), args.owner)
    except (ConfigError, GitHubError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.command == "repos":
        for repo in repos:
            print(f"{repo.full_name} ({repo.default_branch})")
        return EXIT_OK

    fix = args.command == "fix"
    reports = []
    for repo in repos:
        report = process_repo(api, config, repo, fix=fix)
        reports.append(report)
        _print_report(report, show_diff=getattr(args, "diff", False))

    _print_summary(reports)
    _write_step_summary(reports)
    if any(report.outcome is Outcome.ERROR for report in reports):
        return EXIT_ERROR
    unresolved = (report.manual_findings if fix else report.findings for report in reports)
    return EXIT_FINDINGS if any(unresolved) else EXIT_OK


def _print_report(report: RepoReport, *, show_diff: bool) -> None:
    detail = f" ({report.detail})" if report.detail else ""
    print(f"{report.repo}: {report.outcome}{detail}")
    for finding in report.findings:
        marker = "fix" if finding.fixable else "manual"
        print(f"  [{marker}] {finding.rule_id}: {finding.message}")
    if show_diff:
        for diff in report.diffs:
            print("    " + diff.rstrip("\n").replace("\n", "\n    "))


def _print_summary(reports: list[RepoReport]) -> None:
    counts = Counter(report.outcome for report in reports)
    summary = ", ".join(f"{count} {outcome}" for outcome, count in sorted(counts.items()))
    print(f"\n{len(reports)} repositories: {summary or 'none'}")


def _write_step_summary(reports: list[RepoReport]) -> None:
    """Markdown table for the GitHub Actions job summary, when running there."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    lines = ["| Repository | Result | Findings |", "| --- | --- | --- |"]
    for report in reports:
        findings = "<br>".join(f"{f.rule_id}: {f.message}" for f in report.findings)
        result = f"{report.outcome} {report.detail}".strip()
        lines.append(f"| {report.repo} | {result} | {findings.replace('|', '\\|')} |")
    with Path(target).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")
