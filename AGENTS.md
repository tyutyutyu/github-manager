
<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.53.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**At the beginning of each conversation in this project, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->

## Architecture

Source lives in `src/github_manager/`; read the code for details.

- `cli.py`: argument parsing, the `check`, `fix` and `repos` commands, console report and step summary.
- `config.py`: `load_config` reads `github-manager.toml` and builds each rule through `RULE_TYPES`.
- `engine.py`: `select_repos`, `process_repo`, the `RemoteWorkspace` adapter, the pull request, setting and ruleset sync, auto-merge.
- `github.py`: the `GitHub` REST/GraphQL client (no third-party GitHub library).
- `rules/base.py`: `Workspace` protocol, `Finding`, `Options`, abstract `Rule`.
- `rules/files.py`, `rules/renovate.py`, `rules/settings.py`, `rules/ruleset.py`, `rules/workflows.py`: the rule types; `rules/__init__.py` holds the `RULE_TYPES` registry.

Data flow: `cli.main` → `load_config` → `select_repos` → `process_repo` per repository → `Rule.apply` on a `Workspace` → one pull request, direct setting changes and ruleset changes.

`check` only reports (with `--diff` it shows the changes); `fix` also writes: it opens or refreshes the single pull request and applies settings and rulesets.

A `Finding` has one of three kinds (`Finding.kind`, a `FindingKind`):

- fixed by the pull request: `FindingKind.PULL_REQUEST` (file writes, the default);
- applied directly to the repository: `FindingKind.DIRECT` (settings, rulesets);
- manual: `FindingKind.MANUAL`; only reported, a human decides.

Design decisions are recorded as Backlog decisions: `backlog decision list --plain`.

## Adding a rule type

1. Add a `@dataclass(frozen=True, kw_only=True)` subclass of `Rule` with a unique `type_name` in the matching `rules/` module.
2. Implement the `_build` classmethod that reads the TOML table through `Options` (unknown keys are an error).
3. Implement `apply` that reads and writes only through the `Workspace` and returns `Finding`s of the right kind.
4. Export the class in `rules/__init__.py` and add it to `RULE_TYPES`.
5. Test it with `MemoryWorkspace` (`tests/conftest.py`) in the matching `tests/test_rules_*.py`, and add an engine test with `FakeGitHub` in `tests/test_engine.py`.
6. Document it in a README subsection under "Rule types".
7. Add a rule to `github-manager.toml` only when the owner asks for it.

## Conventions

- No test asserts the content of the real `github-manager.toml`; at most a load test.
- The fakes in `tests/conftest.py` follow GitHub's observed behaviour. When live behaviour differs, fix the fake and add a regression test (example: resetting the head branch to the default branch tip closes the open pull request).
- During development never write to the managed repositories; only read-only `gh` queries are allowed.
- Verification command: `uv run ruff format -q . && task verify`.
- Language: code, comments, README and agent files in English; Backlog tasks in Hungarian.
