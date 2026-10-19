"""Command line interface: `check`, `fix` and `repos`."""

import argparse
import os
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from rich.console import Console
from rich.text import Text

from github_manager.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from github_manager.engine import GitHubApi, Outcome, RepoReport, process_repo, select_repos
from github_manager.github import GitHub, GitHubError, resolve_token

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

ApiFactory = Callable[[], GitHubApi]

# Symbol and style of each outcome, in the order the summary lists them.
OUTCOME_STYLES = {
    Outcome.COMPLIANT: ("✔", "green"),
    Outcome.PR_CLOSED: ("✔", "green"),
    Outcome.PR_UP_TO_DATE: ("✔", "cyan"),
    Outcome.PR_CREATED: ("✚", "cyan"),
    Outcome.PR_UPDATED: ("↻", "cyan"),
    Outcome.SETTINGS_UPDATED: ("↻", "cyan"),
    Outcome.NEEDS_FIX: ("✖", "yellow"),
    Outcome.SKIPPED: ("○", "dim"),
    Outcome.ERROR: ("✖", "bold red"),
}


def _console(*, stderr: bool = False) -> Console:
    """Colours on a terminal and in GitHub Actions (its log is no TTY but shows ANSI
    colours), none in a pipe or with NO_COLOR; long lines are never wrapped."""
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    return Console(
        stderr=stderr, force_terminal=True if in_actions else None, soft_wrap=True, highlight=False
    )


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
            "-v", "--verbose", action="store_true", help="also list compliant repositories"
        )
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
    console = _console()
    try:
        config = load_config(args.config)
        api = api_factory()
        repos = select_repos(api, config, getattr(args, "repo", []), args.owner)
    except (ConfigError, GitHubError) as exc:
        _console(stderr=True).print(Text(f"error: {exc}", style="bold red"))
        return EXIT_ERROR

    if args.command == "repos":
        for repo in repos:
            console.print(
                Text.assemble((repo.full_name, "bold"), (f" ({repo.default_branch})", "dim"))
            )
        return EXIT_OK

    fix = args.command == "fix"
    reports = []
    for repo in repos:
        report = process_repo(api, config, repo, fix=fix)
        reports.append(report)
        if report.outcome is not Outcome.COMPLIANT or args.verbose:
            _print_report(console, report, show_diff=getattr(args, "diff", False))

    _print_summary(console, reports)
    _write_step_summary(reports)
    if any(report.outcome is Outcome.ERROR for report in reports):
        return EXIT_ERROR
    unresolved = (report.manual_findings if fix else report.findings for report in reports)
    return EXIT_FINDINGS if any(unresolved) else EXIT_OK


def _print_report(console: Console, report: RepoReport, *, show_diff: bool) -> None:
    symbol, style = OUTCOME_STYLES[report.outcome]
    header = Text.assemble(
        (symbol, style), " ", (report.repo, "bold"), "  ", (report.outcome, style)
    )
    if report.detail:
        header.append(f"  {report.detail}", style="dim")
    console.print(header)
    width = max((len(finding.rule_id) for finding in report.findings), default=0)
    for finding in report.findings:
        marker = ("fix   ", "yellow") if finding.fixable else ("manual", "bold red")
        padding = " " * (width - len(finding.rule_id) + 2)
        line = Text.assemble("    ", marker, "  ", (finding.rule_id, "bold"), padding)
        console.print(line.append(finding.message))
    if show_diff:
        for diff in report.diffs:
            for diff_line in diff.rstrip("\n").split("\n"):
                console.print(Text("      " + diff_line, style=_diff_style(diff_line)))


def _diff_style(line: str) -> str:
    if line.startswith(("+++", "---")):
        return "bold"
    if line.startswith("@@"):
        return "cyan"
    if line.startswith("+"):
        return "green"
    if line.startswith("-"):
        return "red"
    return ""


def _print_summary(console: Console, reports: list[RepoReport]) -> None:
    counts = Counter(report.outcome for report in reports)
    summary = Text.assemble("\n", (f"{len(reports)} repositories", "bold"))
    for outcome, (symbol, style) in OUTCOME_STYLES.items():
        if counts[outcome]:
            summary.append(f"  {symbol} {counts[outcome]} {outcome}", style=style)
    console.print(summary)


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
