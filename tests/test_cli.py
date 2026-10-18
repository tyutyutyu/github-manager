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
    assert "owner/bad: needs fix\n  [fix] gi: .gitignore: managed block is missing" in out
    assert "    +.env" in out
    assert "2 repositories: 1 compliant, 1 needs fix" in out
    assert fake_github.pulls["owner/bad"] == {}


def test_fix_opens_pull_requests_and_writes_step_summary(
    fake_github, config_path, tmp_path, monkeypatch, capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    fake_github.add_repo("bad", {})

    assert run(fake_github, config_path, "fix", "--repo", "bad") == EXIT_OK
    assert "owner/bad: pull request created (https://example/owner/bad/pull/1)" in (
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
    assert "  [manual] rv: visibility is " in capsys.readouterr().out
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
