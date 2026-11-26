import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from github_manager.rules import RepoRuleset, SelfHostedRunners

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SYNCED_WORKFLOWS = {
    "backlog": (
        TEMPLATES / "backlog" / "backlog-verify.yml",
        ".github/workflows/backlog-verify.yml",
    ),
    "workspace": (
        TEMPLATES / "workspace" / "workspace-verify.yml",
        ".github/workflows/workspace-verify.yml",
    ),
}


@pytest.fixture(params=sorted(SYNCED_WORKFLOWS))
def template(request) -> tuple[str, str]:
    source, workflow_path = SYNCED_WORKFLOWS[request.param]
    return workflow_path, source.read_text(encoding="utf-8")


def test_template_passes_self_hosted_runners(make_workspace, template) -> None:
    workflow_path, template_text = template
    rule = SelfHostedRunners.from_options(
        {
            "id": "sh",
            "allowed_runs_on": [["self-hosted"]],
            "runs_on": ["self-hosted"],
        },
        Path(),
    )
    workspace = make_workspace({workflow_path: template_text}, settings={"visibility": "private"})

    assert rule.apply(workspace) == []
    assert workspace.files == {workflow_path: template_text}


def test_template_satisfies_required_verify_check(make_workspace, template) -> None:
    workflow_path, template_text = template
    rule = RepoRuleset.from_options({"id": "dr", "required_workflow_check": "verify"}, Path())
    workspace = make_workspace({workflow_path: template_text})

    assert rule.workflow_check_problem(workspace) is None


def test_template_pins_actions_and_needs_no_secrets(template) -> None:
    _, template_text = template
    uses = [
        line.split("uses:")[1].strip() for line in template_text.splitlines() if "uses:" in line
    ]

    assert uses
    for reference in uses:
        action, _, version = reference.partition("@")
        sha, _, comment = version.partition(" # ")
        assert len(sha) == 40, action
        assert comment.startswith("v"), action
    assert "secrets." not in template_text
    assert "contents: read" in template_text


def _manifest_consistency_script() -> str:
    source, _ = SYNCED_WORKFLOWS["workspace"]
    workflow = yaml.safe_load(source.read_text(encoding="utf-8"))
    step = next(
        step
        for step in workflow["jobs"]["verify"]["steps"]
        if step.get("name") == "Check the manifest consistency"
    )
    lines = step["run"].splitlines()
    assert lines[0] == "python - <<'PY'"
    assert lines[-1] == "PY"
    return "\n".join(lines[1:-1])


def _run_manifest_check(directory: Path, backlog: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    assert git
    subprocess.run([git, "init", "-q", str(directory)], check=True)  # noqa: S603 - absolute path, fixed arguments
    (directory / ".gitignore").write_text("/core/\n/web/\n", encoding="utf-8")
    manifest = {
        "kind": "easy-github-workspace",
        "backlog": backlog,
        "repositories": [
            {"name": "core", "origin": "git@github.com:owner/core.git"},
            {"name": "web", "origin": "git@github.com:owner/web.git"},
        ],
    }
    (directory / "workspace.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return subprocess.run(  # noqa: S603 - the script is this repository's own template
        [sys.executable, "-c", _manifest_consistency_script()],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("backlog", [".", "core"])
def test_manifest_check_accepts_workspace_or_member_backlog(tmp_path: Path, backlog) -> None:
    result = _run_manifest_check(tmp_path, backlog)

    assert result.returncode == 0, result.stdout


def test_manifest_check_rejects_unknown_backlog(tmp_path: Path) -> None:
    result = _run_manifest_check(tmp_path, "missing")

    assert result.returncode == 1
    assert "::error::backlog 'missing' is not" in result.stdout
