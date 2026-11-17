from pathlib import Path

import pytest

from github_manager.rules import RepoRuleset, SelfHostedRunners

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
BACKLOG_VERIFY = TEMPLATES / "backlog" / "backlog-verify.yml"
WORKFLOW_PATH = ".github/workflows/backlog-verify.yml"


@pytest.fixture
def template_text() -> str:
    return BACKLOG_VERIFY.read_text(encoding="utf-8")


def test_backlog_verify_template_passes_self_hosted_runners(make_workspace, template_text) -> None:
    rule = SelfHostedRunners.from_options(
        {
            "id": "sh",
            "allowed_runs_on": [["self-hosted"]],
            "runs_on": ["self-hosted"],
        },
        Path(),
    )
    workspace = make_workspace({WORKFLOW_PATH: template_text}, settings={"visibility": "private"})

    assert rule.apply(workspace) == []
    assert workspace.files == {WORKFLOW_PATH: template_text}


def test_backlog_verify_template_satisfies_required_verify_check(
    make_workspace, template_text
) -> None:
    rule = RepoRuleset.from_options({"id": "dr", "required_workflow_check": "verify"}, Path())
    workspace = make_workspace({WORKFLOW_PATH: template_text})

    assert rule.workflow_check_problem(workspace) is None


def test_backlog_verify_template_pins_actions_and_needs_no_secrets(template_text) -> None:
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
