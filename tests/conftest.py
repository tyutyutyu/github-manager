import copy
from dataclasses import dataclass, field
from typing import Any

import pytest

from github_manager.github import GitHubError, PullRequest, Repo


@dataclass
class FakeRepo:
    info: Repo
    branches: dict[str, str] = field(default_factory=dict)
    # commit sha -> (parent sha, files)
    commits: dict[str, tuple[str | None, dict[str, str]]] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    rulesets: dict[int, dict[str, Any]] = field(default_factory=dict)
    # False: the plan does not offer rulesets (GitHub Free, private repository).
    rulesets_available: bool = True
    # True: a ruleset write is accepted but not stored (to test the read-back).
    drop_ruleset_writes: bool = False
    # False: the file list is not available (tree_paths returns None).
    tree_listable: bool = True


def server_ruleset(
    ruleset_id: int, payload: dict[str, Any], source_type: str = "Repository"
) -> dict[str, Any]:
    """A ruleset as the server returns it: the payload plus defaults GitHub adds itself."""
    ruleset = copy.deepcopy(payload)
    ruleset.update(id=ruleset_id, source_type=source_type, node_id="x", _links={})
    for rule in ruleset.get("rules", []):
        parameters = rule.get("parameters", {})
        if rule["type"] == "pull_request":
            parameters.update(required_reviewers=[], dismissal_restriction=None)
        if rule["type"] == "required_status_checks":
            for check in parameters["required_status_checks"]:
                check["integration_id"] = 15368
    return ruleset


class FakeGitHub:
    """In-memory stand-in for `github_manager.github.GitHub`."""

    def __init__(self) -> None:
        self.repos: dict[str, FakeRepo] = {}
        self.pulls: dict[
            str, dict[int, tuple[str, str, bool]]
        ] = {}  # repo -> number -> (head, body, open)
        self.calls: list[str] = []
        self._counter = 0

    def add_repo(
        self,
        name: str,
        files: dict[str, str] | None,
        *,
        archived: bool = False,
        fork: bool = False,
        default_branch: str = "main",
        owner: str = "owner",
        settings: dict[str, Any] | None = None,
        rulesets_available: bool = True,
        tree_listable: bool = True,
    ) -> str:
        full = f"{owner}/{name}"
        repo = FakeRepo(
            Repo(name, full, default_branch, archived, fork),
            settings=settings or {},
            rulesets_available=rulesets_available,
            tree_listable=tree_listable,
        )
        if files is not None:
            repo.commits["base"] = (None, dict(files))
            repo.branches[default_branch] = "base"
        self.repos[full] = repo
        self.pulls[full] = {}
        return full

    def add_ruleset(
        self,
        repo: str,
        payload: dict[str, Any],
        *,
        source_type: str = "Repository",
    ) -> int:
        state = self.repos[repo]
        ruleset_id = max(state.rulesets, default=100) + 1
        state.rulesets[ruleset_id] = server_ruleset(ruleset_id, payload, source_type)
        return ruleset_id

    def files_at(self, repo: str, branch: str) -> dict[str, str]:
        state = self.repos[repo]
        return state.commits[state.branches[branch]][1]

    # --- GitHubApi -----------------------------------------------------------

    def list_repos(self, owner: str) -> list[Repo]:
        prefix = f"{owner.lower()}/"
        return [
            repo.info
            for repo in self.repos.values()
            if repo.info.full_name.lower().startswith(prefix)
        ]

    def branch_sha(self, repo: str, branch: str) -> str | None:
        return self.repos[repo].branches.get(branch)

    def compare(self, repo: str, base: str, head: str) -> tuple[int, int, set[str]]:
        commits = self.repos[repo].commits
        ahead, sha = 0, head
        while sha != base and sha is not None:
            ahead += 1
            sha = commits[sha][0]
        base_files, head_files = commits[base][1], commits[head][1]
        changed = {
            path
            for path in base_files.keys() | head_files.keys()
            if base_files.get(path) != head_files.get(path)
        }
        return ahead, 0 if sha == base else 1, changed

    def tree_paths(self, repo: str, sha: str) -> set[str] | None:
        state = self.repos[repo]
        return set(state.commits[sha][1]) if state.tree_listable else None

    def read_file(self, repo: str, path: str, ref: str) -> str | None:
        self.calls.append(f"read {path}@{ref}")
        if path == "broken":
            raise GitHubError("boom", 500)
        return self.repos[repo].commits[ref][1].get(path)

    def reset_branch(self, repo: str, branch: str, sha: str, *, exists: bool) -> None:
        assert (branch in self.repos[repo].branches) == exists
        self.calls.append(f"reset {branch}")
        self.repos[repo].branches[branch] = sha

    def delete_branch(self, repo: str, branch: str) -> None:
        self.calls.append(f"delete {branch}")
        del self.repos[repo].branches[branch]

    def commit_files(
        self, repo: str, branch: str, head_sha: str, message: str, files: dict[str, str]
    ) -> str:
        state = self.repos[repo]
        assert state.branches[branch] == head_sha
        self._counter += 1
        sha = f"c{self._counter}"
        state.commits[sha] = (head_sha, {**state.commits[head_sha][1], **files})
        state.branches[branch] = sha
        self.calls.append(f"commit {sorted(files)}")
        return sha

    def find_open_pr(self, repo: str, branch: str) -> PullRequest | None:
        for number, (head, _, is_open) in self.pulls[repo].items():
            if head == branch and is_open:
                return PullRequest(number, f"https://example/{repo}/pull/{number}")
        return None

    def create_pr(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequest:
        number = len(self.pulls[repo]) + 1
        self.pulls[repo][number] = (head, body, True)
        self.calls.append("create pr")
        return PullRequest(number, f"https://example/{repo}/pull/{number}")

    def update_pr(self, repo: str, number: int, title: str, body: str) -> None:
        head, _, is_open = self.pulls[repo][number]
        self.pulls[repo][number] = (head, body, is_open)
        self.calls.append("update pr")

    def close_pr(self, repo: str, number: int, comment: str) -> None:
        head, body, _ = self.pulls[repo][number]
        self.pulls[repo][number] = (head, body, False)
        self.calls.append("close pr")

    def repo_settings(self, repo: str) -> dict[str, Any]:
        return dict(self.repos[repo].settings)

    def update_repo_settings(self, repo: str, settings: dict[str, Any]) -> None:
        self.repos[repo].settings.update(settings)
        self.calls.append(f"settings {sorted(settings)}")

    def list_rulesets(self, repo: str) -> list[dict[str, Any]] | None:
        state = self.repos[repo]
        if not state.rulesets_available:
            return None
        # The listing carries summaries only.
        return [
            {"id": item["id"], "name": item["name"], "source_type": item["source_type"]}
            for item in state.rulesets.values()
        ]

    def get_ruleset(self, repo: str, ruleset_id: int) -> dict[str, Any]:
        return copy.deepcopy(self.repos[repo].rulesets[ruleset_id])

    def create_ruleset(self, repo: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.repos[repo]
        self.calls.append(f"create ruleset {payload['name']}")
        ruleset_id = max(state.rulesets, default=100) + 1
        if not state.drop_ruleset_writes:
            state.rulesets[ruleset_id] = server_ruleset(ruleset_id, payload, "Repository")
        return {"id": ruleset_id}

    def update_ruleset(self, repo: str, ruleset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.repos[repo]
        self.calls.append(f"update ruleset {ruleset_id}")
        if not state.drop_ruleset_writes:
            state.rulesets[ruleset_id] = server_ruleset(ruleset_id, payload, "Repository")
        return {"id": ruleset_id}


class MemoryWorkspace:
    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        default_branch: str = "main",
        branches: set[str] | None = None,
        settings: dict[str, Any] | None = None,
        full_name: str = "owner/app",
        rulesets: list[dict[str, Any]] | None = None,
        rulesets_available: bool = True,
        listable: bool = True,
    ) -> None:
        self.files = dict(files or {})
        # The default branch commit: `write` changes only `files`.
        self.original_files = dict(self.files)
        self.full_name = full_name
        # Each item is a full server ruleset.
        self.ruleset_items = rulesets or []
        self.rulesets_available = rulesets_available
        self.listable = listable
        self.ruleset_changes: list[tuple[str, int | None, dict[str, Any]]] = []
        self.settings = dict(settings or {})
        self.default_branch = default_branch
        self.branches = {default_branch} if branches is None else branches

    def branch_exists(self, branch: str) -> bool:
        return branch in self.branches

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def paths(self, prefix: str) -> list[str] | None:
        if not self.listable:
            return None
        return sorted(path for path in self.files if path.startswith(prefix))

    def original(self, path: str) -> str | None:
        return self.original_files.get(path)

    def original_paths(self, prefix: str) -> list[str] | None:
        if not self.listable:
            return None
        return sorted(path for path in self.original_files if path.startswith(prefix))

    def setting(self, name: str) -> Any:
        return self.settings.get(name)

    def change_setting(self, name: str, value: Any) -> None:
        self.settings[name] = value

    def rulesets(self) -> list[dict[str, Any]] | None:
        return self.ruleset_items if self.rulesets_available else None

    def ruleset(self, ruleset_id: int) -> dict[str, Any]:
        return next(item for item in self.ruleset_items if item["id"] == ruleset_id)

    def change_ruleset(self, name: str, ruleset_id: int | None, payload: dict[str, Any]) -> None:
        self.ruleset_changes.append((name, ruleset_id, payload))


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def make_workspace():
    return MemoryWorkspace


@pytest.fixture
def with_server_defaults():
    def build(payload: dict[str, Any], ruleset_id: int = 7, source_type: str = "Repository"):
        return server_ruleset(ruleset_id, payload, source_type)

    return build
