from pathlib import Path

import pytest

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
