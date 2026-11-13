import inspect

import pytest

from github_manager.rules import Finding, FindingKind, Options


def test_finding_defaults_to_pull_request_kind() -> None:
    assert Finding("r", "message").kind is FindingKind.PULL_REQUEST


@pytest.mark.parametrize("method", ["text_list", "text_block", "text_lists", "table"])
def test_options_collection_readers_require_default(method: str) -> None:
    parameter = inspect.signature(getattr(Options, method)).parameters["default"]
    assert parameter.default is inspect.Parameter.empty


def test_options_text_accepts_none_default() -> None:
    assert Options({}).text("key") is None
