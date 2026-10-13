"""Validate and fix GitHub repositories against central rules."""

import sys

from github_manager.cli import main as run


def main() -> None:
    sys.exit(run())
