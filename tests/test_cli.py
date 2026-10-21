from pathlib import Path

import pytest

from github_manager import cli
from github_manager.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main
from github_manager.github import GitHubError

CONFIG = """
owners = ["owner"]
[[rules]]
id = "gi"
type = "required_lines"
path = ".gitignore"
lines = ".env"
[[rules]]
id = "rn"
type = "renovate_preset"
preset = "local>o/c"
exclude = ["*"]
"""


@pytest.fixture(autouse=True)
def plain_output(monkeypatch) -> None:
    """Colour detection must not depend on the environment the tests run in (CI)."""
    for name in ("GITHUB_ACTIONS", "FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "github-manager.toml"
    path.write_text(CONFIG)
    return path


def run(fake_github, config_path: Path, *args: str) -> int:
    return main(["--config", str(config_path), *args], api_factory=lambda: fake_github)


def test_repos_lists_selected_repositories(fake_github, config_path, capsys) -> None:
    fake_github.add_repo("app", {}, default_branch="develop")
    assert run(fake_github, config_path, "repos") == EXIT_OK
    assert capsys.readouterr().out == "owner/app (develop)\n"


def test_check_exit_codes_and_output(fake_github, config_path, capsys) -> None:
    fake_github.add_repo(
        "ok", {".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"}
    )
    assert run(fake_github, config_path, "check") == EXIT_OK

    fake_github.add_repo("bad", {})
    assert run(fake_github, config_path, "check", "--diff") == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "owner/ok" not in out
    assert "✖ owner/bad  needs fix\n    fix     gi  .gitignore: managed block is missing\n" in out
    assert "\n      +.env\n" in out
    assert out.endswith("\n2 repositories  ✔ 1 compliant  ✖ 1 needs fix\n")
    assert fake_github.pulls["owner/bad"] == {}


def test_verbose_lists_compliant_repositories(fake_github, config_path, capsys) -> None:
    fake_github.add_repo(
        "ok", {".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"}
    )
    assert run(fake_github, config_path, "check", "-v") == EXIT_OK
    assert capsys.readouterr().out == "✔ owner/ok  compliant\n\n1 repositories  ✔ 1 compliant\n"


@pytest.mark.parametrize("variable", ["FORCE_COLOR", "GITHUB_ACTIONS"])
def test_output_is_coloured_on_a_terminal_and_in_actions(
    fake_github, config_path, monkeypatch, capsys, variable
) -> None:
    monkeypatch.setenv(variable, "true" if variable == "GITHUB_ACTIONS" else "1")
    stale = "# >>> github-manager: gi\nstale\n# <<< github-manager: gi\n"
    fake_github.add_repo("bad", {".gitignore": stale})
    assert run(fake_github, config_path, "check", "--diff") == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "\x1b[33m✖\x1b[0m \x1b[1mowner/bad\x1b[0m  \x1b[33mneeds fix\x1b[0m" in out
    assert "\x1b[32m      +.env\x1b[0m" in out
    assert "\x1b[1m      --- a/.gitignore\x1b[0m" in out
    assert "\x1b[36m      @@ " in out
    assert "\x1b[31m      -stale\x1b[0m" in out
    assert "\n       # >>> github-manager: gi\n" in out


def test_no_color_disables_colours(fake_github, config_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("NO_COLOR", "1")
    fake_github.add_repo("bad", {})
    run(fake_github, config_path, "check")
    assert "\x1b[3" not in capsys.readouterr().out


def test_findings_are_aligned_and_printed_verbatim(fake_github, tmp_path, capsys) -> None:
    path = tmp_path / "c.toml"
    path.write_text(
        CONFIG
        + '[[rules]]\nid = "runners"\ntype = "self_hosted_runners"\n'
        + 'allowed_runs_on = [["self-hosted"]]\nruns_on = ["self-hosted"]\n'
    )
    workflow = "jobs:\n  b:\n    runs-on: windows-latest\n"
    fake_github.add_repo(
        "app", {".github/workflows/ci.yml": workflow}, settings={"visibility": "private"}
    )
    assert run(fake_github, path, "check") == EXIT_FINDINGS
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "    fix     gi       .gitignore: managed block is missing"
    assert lines[2] == (
        '    manual  runners  .github/workflows/ci.yml: job b: runs-on ["windows-latest"] '
        'is not an allowed self-hosted runner (allowed: ["self-hosted"])'
    )


def test_errors_are_red_on_a_terminal(fake_github, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert run(fake_github, tmp_path / "missing.toml", "check") == EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.err.startswith("\x1b[1;31merror: config file not found")
    assert captured.out == ""


def test_fix_opens_pull_requests_and_writes_step_summary(
    fake_github, config_path, tmp_path, monkeypatch, capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    fake_github.add_repo("bad", {})

    assert run(fake_github, config_path, "fix", "--repo", "bad") == EXIT_OK
    assert "✚ owner/bad  pull request created  https://example/owner/bad/pull/1\n" in (
        capsys.readouterr().out
    )
    assert "| owner/bad | pull request created https://example/owner/bad/pull/1 |" in (
        summary.read_text()
    )


def test_fix_fails_on_findings_that_need_manual_action(fake_github, tmp_path) -> None:
    path = tmp_path / "c.toml"
    path.write_text(CONFIG.replace('exclude = ["*"]', ""))
    fake_github.add_repo(
        "app",
        {
            ".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n",
            "renovate.json": "{broken",
        },
    )
    assert run(fake_github, path, "fix") == EXIT_FINDINGS


def test_fix_reports_visibility_mismatch_as_manual(fake_github, tmp_path, capsys) -> None:
    path = tmp_path / "c.toml"
    path.write_text(
        'owners = ["owner"]\n[[rules]]\nid = "rv"\ntype = "repo_visibility"\n'
        'visibility = { owner = "private" }\n'
    )
    fake_github.add_repo("app", {}, settings={"visibility": "public"})
    assert run(fake_github, path, "fix") == EXIT_FINDINGS
    assert "\n    manual  rv  visibility is " in capsys.readouterr().out
    assert not [call for call in fake_github.calls if call.startswith("settings")]


def test_errors_exit_with_error_code(fake_github, config_path, tmp_path, capsys) -> None:
    assert run(fake_github, tmp_path / "missing.toml", "check") == EXIT_ERROR
    assert "error: config file not found" in capsys.readouterr().err

    assert run(fake_github, config_path, "check", "-r", "nope") == EXIT_ERROR


def test_repository_errors_do_not_stop_the_run(fake_github, config_path, monkeypatch) -> None:
    fake_github.add_repo("a", {})
    fake_github.add_repo(
        "b", {".gitignore": "# >>> github-manager: gi\n.env\n# <<< github-manager: gi\n"}
    )
    original = fake_github.tree_paths

    def flaky(repo: str, sha: str):
        if repo == "owner/a":
            raise GitHubError("rate limited", 403)
        return original(repo, sha)

    monkeypatch.setattr(fake_github, "tree_paths", flaky)
    assert run(fake_github, config_path, "check") == EXIT_ERROR


def test_default_api_uses_resolved_token(monkeypatch) -> None:
    monkeypatch.setattr(cli, "resolve_token", lambda: "t")
    assert cli._default_api() is not None


AUTO_MERGE_CONFIG = (
    'owners = ["owner"]\nauto_merge = true\n'
    '[[rules]]\nid = "gi"\ntype = "required_lines"\npath = ".gitignore"\nlines = ".env"\n'
    '[[rules]]\nid = "dr"\ntype = "repo_ruleset"\nrequired_workflow_check = "verify"\n'
)
VERIFY_WORKFLOW = "on: pull_request\njobs:\n  verify:\n    runs-on: ubuntu-latest\n"


def test_fix_prints_auto_merge_result_and_escapes_it_in_the_job_summary(
    fake_github, tmp_path, monkeypatch, capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    path = tmp_path / "c.toml"
    path.write_text(AUTO_MERGE_CONFIG)
    fake_github.add_repo("app", {".github/workflows/verify.yml": VERIFY_WORKFLOW})
    fake_github.auto_merge_error = "GraphQL: not allowed | try\nlater"

    assert run(fake_github, path, "fix", "--repo", "app") == EXIT_OK
    output = capsys.readouterr().out
    assert "    auto-merge  failed: GraphQL: not allowed | try\nlater\n" in output
    assert "| owner/app | pull request created https://example/owner/app/pull/1 |" in (
        summary.read_text()
    )
    assert "| failed: GraphQL: not allowed \\| try<br>later |" in summary.read_text()


def test_fix_prints_why_auto_merge_was_skipped(fake_github, tmp_path, capsys) -> None:
    path = tmp_path / "c.toml"
    path.write_text(AUTO_MERGE_CONFIG)
    fake_github.add_repo("app", {})

    run(fake_github, path, "fix")

    assert "    auto-merge  not enabled: verify is not required\n" in capsys.readouterr().out
