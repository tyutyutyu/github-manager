from dataclasses import dataclass, field

import pytest

from github_manager.github import GitHubError, PullRequest, Repo


@dataclass
class FakeRepo:
    info: Repo
    branches: dict[str, str] = field(default_factory=dict)
    # commit sha -> (parent sha, files)
    commits: dict[str, tuple[str | None, dict[str, str]]] = field(default_factory=dict)


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
    ) -> str:
        full = f"owner/{name}"
        repo = FakeRepo(Repo(name, full, default_branch, archived, fork))
        if files is not None:
            repo.commits["base"] = (None, dict(files))
            repo.branches[default_branch] = "base"
        self.repos[full] = repo
        self.pulls[full] = {}
        return full

    def files_at(self, repo: str, branch: str) -> dict[str, str]:
        state = self.repos[repo]
        return state.commits[state.branches[branch]][1]

    # --- GitHubApi -----------------------------------------------------------

    def list_repos(self, owner: str) -> list[Repo]:
        return [repo.info for repo in self.repos.values()]

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
        return set(self.repos[repo].commits[sha][1])

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


class MemoryWorkspace:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = dict(files or {})

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def write(self, path: str, content: str) -> None:
        self.files[path] = content


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def make_workspace():
    return MemoryWorkspace
