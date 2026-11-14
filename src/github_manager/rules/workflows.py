"""Workflow rules and the workflow YAML analysis they share."""

import json
from collections import Counter
from dataclasses import dataclass
from enum import IntEnum
from fnmatch import fnmatchcase
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, Self

import yaml

from github_manager.rules.base import (
    NOT_READABLE,
    REQUIRED,
    Finding,
    FindingKind,
    Options,
    Rule,
    Workspace,
)

WORKFLOWS_DIR = ".github/workflows/"
SELF_HOSTED = "self-hosted"
UBUNTU_PATTERN = "ubuntu-*"
YAML_STR = "tag:yaml.org,2002:str"
UNSAFE_REWRITE = "cannot rewrite safely"
PULL_REQUEST = "pull_request"
# The most nodes (aliases expanded) of a value shown in a message, and what replaces a larger one
# or one that cannot be rendered.
MAX_SHOWN_NODES = 50
TOO_LARGE = "(too large to show)"
NOT_SHOWABLE = "(cannot be shown)"
# The activity types a pull_request trigger runs on by default; a required check needs all.
PULL_REQUEST_TYPES = frozenset({"opened", "synchronize", "reopened"})


@dataclass(frozen=True)
class _Replacement:
    """One `runs-on` value to overwrite: `text[start:end]` becomes `text`."""

    job: str
    problem: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, kw_only=True)
class SelfHostedRunners(Rule):
    """Every job of a private or internal repository must run on an allowed self-hosted runner.

    `allowed_runs_on` lists the accepted label sets; a job's `runs-on` must equal one of them
    exactly (as a set, ignoring case). A single `ubuntu-*` label and a label set that contains
    `self-hosted` but is not allowed are rewritten to `runs_on`, when the value sits on the
    same line as its `runs-on` key (a scalar or a flow list); the rest of the file stays
    byte for byte the same. Every other job (other operating systems, unknown labels,
    expressions, matrices, mappings, external reusable workflows) and workflow files that
    cannot be parsed are reported as manual. Public repositories are not checked.
    """

    type_name: ClassVar[str] = "self_hosted_runners"

    allowed_runs_on: list[list[str]]
    runs_on: list[str]

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        allowed = options.text_lists("allowed_runs_on", REQUIRED)
        if not allowed:
            raise ValueError("'allowed_runs_on' must not be empty")
        seen: set[frozenset[str]] = set()
        for labels in allowed:
            folded = frozenset(label.casefold() for label in labels)
            if SELF_HOSTED not in folded:
                raise ValueError(
                    f"'allowed_runs_on' set {json.dumps(labels)} must contain {SELF_HOSTED!r}"
                )
            if folded in seen:
                raise ValueError(f"duplicate 'allowed_runs_on' set: {json.dumps(labels)}")
            seen.add(folded)
        runs_on = options.text_list("runs_on", REQUIRED)
        if not runs_on:
            raise ValueError("'runs_on' must not be empty")
        if frozenset(label.casefold() for label in runs_on) not in seen:
            raise ValueError(
                f"'runs_on' {json.dumps(runs_on)} must equal one of the 'allowed_runs_on' sets"
            )
        return cls(allowed_runs_on=allowed, runs_on=runs_on, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        visibility = workspace.setting("visibility")
        if visibility is None:
            return [Finding(self.id, f"setting visibility {NOT_READABLE}", kind=FindingKind.MANUAL)]
        if visibility == "public":
            return []
        listed = workspace.paths(WORKFLOWS_DIR)
        if listed is None:
            message = f"{WORKFLOWS_DIR}: the workflow files cannot be listed"
            return [Finding(self.id, message, kind=FindingKind.MANUAL)]
        return [
            finding
            for path in _workflow_files(listed)
            for finding in self._check_file(workspace, path)
        ]

    def _check_file(self, workspace: Workspace, path: str) -> list[Finding]:
        text = workspace.read(path)
        if text is None:
            return [self._manual(path, "the file is not readable")]
        parsed = _jobs(text)
        jobs = parsed.entries
        if jobs is None:
            return [self._manual(path, parsed.error or "")]
        findings = []
        replacements = []
        # Jobs that share one mapping through an alias reach the same value node.
        reached = Counter(id(_entry(job, "runs-on")[1]) for job in jobs.values())
        for name, job in jobs.items():
            problem = self._job_problem(job)
            if problem is None:
                continue
            if not self._rewritable(job):
                findings.append(self._manual(path, f"job {name}: {problem}"))
                continue
            replacement = self._replacement(name, problem, job, text)
            if replacement is None or reached[id(_entry(job, "runs-on")[1])] > 1:
                findings.append(self._manual(path, f"job {name}: {problem}; {UNSAFE_REWRITE}"))
            else:
                replacements.append(replacement)
        if not replacements:
            return findings
        ordered = sorted(replacements, key=lambda item: item.start, reverse=True)
        overlapping = any(before.end > after.start for after, before in pairwise(ordered))
        new_text = text
        for replacement in ordered:
            new_text = (
                new_text[: replacement.start] + replacement.text + new_text[replacement.end :]
            )
        if overlapping or not self._verified(new_text, replacements):
            findings.extend(
                self._manual(path, f"job {item.job}: {item.problem}; {UNSAFE_REWRITE}")
                for item in replacements
            )
            return findings
        workspace.write(path, new_text)
        wanted = json.dumps(self.runs_on)
        findings.extend(
            Finding(self.id, f"{path}: job {item.job}: {item.problem}; set runs-on to {wanted}")
            for item in replacements
        )
        return findings

    def _manual(self, path: str, problem: str) -> Finding:
        return Finding(self.id, f"{path}: {problem}", kind=FindingKind.MANUAL)

    def _verified(self, new_text: str, replacements: list[_Replacement]) -> bool:
        """True when the rewritten file parses and every rewritten job is now allowed."""
        jobs = _jobs(new_text).entries
        return jobs is not None and all(
            item.job in jobs and self._job_problem(jobs[item.job]) is None for item in replacements
        )

    def _rewritable(self, job: yaml.Node) -> bool:
        """True for a single `ubuntu-*` label or a label set with `self-hosted`."""
        labels = _strings((_mapping(job) or {}).get("runs-on"))
        if labels is None or any("${{" in label for label in labels):
            return False
        folded = frozenset(label.casefold() for label in labels)
        if folded in self._allowed_sets():
            return False
        return SELF_HOSTED in folded or (
            len(folded) == 1 and fnmatchcase(next(iter(folded)), UBUNTU_PATTERN)
        )

    def _replacement(
        self, name: str, problem: str, job: yaml.Node, text: str
    ) -> _Replacement | None:
        """The edit for a job's `runs-on`, or None when the value is not safe to splice."""
        key, value = _entry(job, "runs-on")
        if key is None or value is None:
            return None
        start, end = value.start_mark, value.end_mark
        one_line = key.start_mark.line == start.line == end.line
        scalar_or_flow = isinstance(value, yaml.ScalarNode) or (
            isinstance(value, yaml.SequenceNode) and bool(value.flow_style)
        )
        # An anchor or tag belongs to the node's own span; dropping it would break aliases.
        if not (one_line and scalar_or_flow) or text[start.index] in "&!":
            return None
        # A list item that is an alias starts outside the list; an anchored or tagged one
        # starts with its `&` or `!`.
        items = value.value if isinstance(value, yaml.SequenceNode) else []
        if any(
            not start.index < item.start_mark.index < end.index
            or text[item.start_mark.index] in "&!*"
            for item in items
        ):
            return None
        rendered = self.runs_on[0] if len(self.runs_on) == 1 else f"[{', '.join(self.runs_on)}]"
        return _Replacement(name, problem, start.index, end.index, rendered)

    def _job_problem(self, job: yaml.Node) -> str | None:
        fields = _mapping(job)
        if fields is None:
            return "is not a mapping"
        runs_on = fields.get("runs-on")
        if runs_on is None:
            uses = fields.get("uses")
            if _text(uses) is None:
                return "has neither 'runs-on' nor 'uses'"
            if (_text(uses) or "").startswith("./"):
                return None
            return f"calls {json.dumps(_text(uses))} without 'runs-on' (check the runner manually)"
        allowed = " or ".join(json.dumps(labels) for labels in self.allowed_runs_on)
        if _text(runs_on) is not None:
            labels = [_text(runs_on) or ""]
        elif isinstance(runs_on, yaml.SequenceNode):
            texts = [_text(item) for item in runs_on.value]
            if any(text is None for text in texts):
                return (
                    f"runs-on {_json(runs_on)} has a list item that is not a string"
                    f" (check manually; allowed: {allowed})"
                )
            labels = [text for text in texts if text is not None]
        else:
            return (
                f"runs-on {_json(runs_on)} must be a string or a list of strings"
                f" (check manually; allowed: {allowed})"
            )
        actual = json.dumps(labels)
        if any("${{" in label for label in labels):
            return f"runs-on {actual} contains an expression (check manually; allowed: {allowed})"
        if frozenset(label.casefold() for label in labels) in self._allowed_sets():
            return None
        return f"runs-on {actual} is not an allowed self-hosted runner (allowed: {allowed})"

    def _allowed_sets(self) -> set[frozenset[str]]:
        return {frozenset(label.casefold() for label in labels) for labels in self.allowed_runs_on}


def _workflow_files(listed: list[str]) -> list[str]:
    """The direct `.yml`/`.yaml` children of the workflows directory."""
    return [
        path
        for path in listed
        if path.endswith((".yml", ".yaml")) and "/" not in path[len(WORKFLOWS_DIR) :]
    ]


PUSH = "push"
# Keys under `push` that are forbidden: `paths` and `paths-ignore` only narrow the trigger.
PUSH_FORBIDDEN_FILTERS = ("branches-ignore", "tags", "tags-ignore")


@dataclass(frozen=True, kw_only=True)
class DefaultBranchPushOnly(Rule):
    """The workflow file `path` must run only on pushes to the default branch.

    Its `on` must be a mapping whose only trigger is `push`, with a `branches` filter that is
    exactly the default branch (no glob, no negation, no other branch) and no
    `branches-ignore`, `tags` or `tags-ignore`; `paths` and `paths-ignore` are allowed. Every
    deviation needs manual action; a missing file is not reported and nothing is written.
    """

    type_name: ClassVar[str] = "default_branch_push_only"

    path: str

    @classmethod
    def _build(cls, options: Options, base_dir: Path, **common: Any) -> Self:
        path = options.text("path", REQUIRED)
        name = path.removeprefix(WORKFLOWS_DIR)
        if (
            name == path
            or "/" in name
            or not name.endswith((".yml", ".yaml"))
            or name in (".yml", ".yaml")
        ):
            raise ValueError(
                f"'path' {path!r} must be a .yml or .yaml file directly in {WORKFLOWS_DIR}"
            )
        return cls(path=path, **common)

    def apply(self, workspace: Workspace) -> list[Finding]:
        text = workspace.read(self.path)
        if text is None:
            return []
        problem = _push_only_problem(text, workspace.default_branch)
        if problem is None:
            return []
        return [Finding(self.id, f"{self.path}: {problem}", kind=FindingKind.MANUAL)]


def _push_only_problem(text: str, branch: str) -> str | None:
    """The first reason the workflow does not run only on pushes to `branch`; None if it does."""
    root, error = _compose(text)
    if error is not None:
        return error
    if not isinstance(root, yaml.MappingNode):
        return "invalid YAML (the root is not a mapping)"
    # PyYAML (YAML 1.1) loads the key `on` as True, but the node holds the text.
    _, trigger = _entry(root, "on")
    if trigger is None:
        return "no 'on' trigger"
    triggers = _mapping(trigger)
    if triggers is None:
        return (
            f"'on' is {_shown(trigger)}, not a mapping: "
            "without a push branches filter it runs on every branch"
        )
    others = sorted(name for name in triggers if name != PUSH)
    if others:
        return f"other triggers: {', '.join(others)} (only push to {branch} is allowed)"
    if PUSH not in triggers:
        return "no push trigger"
    return _push_filter_problem(_mapping(triggers[PUSH]) or {}, branch)


def _shown(node: yaml.Node) -> str:
    """A message rendering of a non-mapping YAML node that never constructs its value."""
    patterns = _strings(node)
    if patterns is not None:
        return json.dumps(patterns[0] if isinstance(node, yaml.ScalarNode) else patterns)
    if isinstance(node, yaml.ScalarNode):
        return node.value or "empty"
    return "a list with non-string items"


def _push_filter_problem(filters: dict[str, yaml.Node], branch: str) -> str | None:
    if "branches" not in filters:
        return "push has no branches filter (it runs on every branch)"
    patterns = _strings(filters["branches"])
    if patterns is None:
        return "push branches cannot be read"
    if patterns != [branch]:
        return (
            f"push branches {json.dumps(patterns)} must be exactly "
            f"{json.dumps([branch])} (the default branch)"
        )
    forbidden = [key for key in PUSH_FORBIDDEN_FILTERS if key in filters]
    if forbidden:
        return (
            f"push has {', '.join(forbidden)} (only branches, paths and paths-ignore are allowed)"
        )
    return None


class _Stage(IntEnum):
    """Stages of `_file_problem`, in the order it checks them."""

    UNREADABLE = 0
    NO_JOB = 1
    JOB_UNUSABLE = 2
    NO_TRIGGER = 3
    TYPES_FILTER = 4
    BRANCH_FILTER = 5
    PATH_FILTER = 6


class _Problem(NamedTuple):
    """Why a workflow file does not run a check; a higher `stage` is closer to a valid file."""

    stage: _Stage
    message: str


def _workflow_check_problem(workspace: Workspace, check: str, branch: str) -> str | None:
    """Why no workflow runs the `check` on pull requests to `branch`; None when one certainly does.

    A file qualifies when it triggers on `pull_request` without a filter that can skip the
    default branch or leave the check pending, and has a plain job whose check name is exactly
    `check`. Only the default branch commit counts, not files written by earlier rules (they
    exist only in the unmerged pull request). The text names the problem of the file that came
    closest.
    """
    listed = workspace.original_paths(WORKFLOWS_DIR)
    if listed is None:
        return f"{WORKFLOWS_DIR}: the workflow files cannot be listed"
    problems = []
    for path in _workflow_files(listed):
        text = workspace.original(path)
        problem = (
            _Problem(_Stage.UNREADABLE, "the file is not readable")
            if text is None
            else _file_problem(text, check, branch)
        )
        if problem is None:
            return None
        problems.append(_Problem(problem.stage, f"{path}: {problem.message}"))
    if not problems:
        return f"{WORKFLOWS_DIR}: no workflow file (.yml or .yaml)"
    return max(problems, key=lambda problem: problem.stage).message


def _file_problem(text: str, check: str, branch: str) -> _Problem | None:
    root, error = _compose(text)
    if error is not None:
        return _Problem(_Stage.UNREADABLE, error)
    jobs = _jobs_of(root)
    if root is None or jobs is None:
        return _Problem(_Stage.UNREADABLE, "no 'jobs' mapping")
    job_problem = _check_job_problem(jobs, check)
    if job_problem is not None:
        return job_problem
    # PyYAML (YAML 1.1) loads the key `on` as True, but the node holds the text.
    _, trigger = _entry(root, "on")
    found, filters = _pull_request_trigger(trigger)
    if not found:
        return _Problem(_Stage.NO_TRIGGER, "no pull_request trigger")
    return _filter_problem(filters, branch)


def _check_job_problem(jobs: dict[str, yaml.Node], check: str) -> _Problem | None:
    """None when a job reports exactly `check`: its `name`, or its id without a `name`."""
    problem = _Problem(
        _Stage.NO_JOB, f"no job reports the check {check!r} (its name, or its id without a name)"
    )
    for job_id, job in jobs.items():
        fields = _mapping(job)
        if fields is None:
            continue
        name = _text(fields["name"]) if "name" in fields else job_id
        if name is not None and "${{" in name:
            problem = _Problem(
                _Stage.JOB_UNUSABLE, f"job {job_id}: the name contains an expression"
            )
        elif name != check:
            continue
        elif "uses" in fields:
            problem = _Problem(
                _Stage.JOB_UNUSABLE,
                f"job {job_id} calls a reusable workflow (its check is '{check} / <job>')",
            )
        elif "strategy" in fields and "matrix" in (_mapping(fields["strategy"]) or {"matrix": 0}):
            problem = _Problem(
                _Stage.JOB_UNUSABLE, f"job {job_id} has a matrix (its check is '{check} (<value>)')"
            )
        else:
            return None
    return problem


def _pull_request_trigger(trigger: yaml.Node | None) -> tuple[bool, yaml.Node | None]:
    """Whether `on` includes `pull_request`, and that trigger's configuration node."""
    if isinstance(trigger, yaml.SequenceNode):
        return any(_text(item) == PULL_REQUEST for item in trigger.value), None
    if isinstance(trigger, yaml.MappingNode):
        key, config = _entry(trigger, PULL_REQUEST)
        return key is not None, config
    return _text(trigger) == PULL_REQUEST, None


def _filter_problem(filters: yaml.Node | None, branch: str) -> _Problem | None:
    fields = _mapping(filters) or {}
    if "types" in fields:
        types = _strings(fields["types"])
        if types is None:
            return _Problem(_Stage.TYPES_FILTER, "pull_request types cannot be read")
        if not PULL_REQUEST_TYPES.issubset(types):
            return _Problem(
                _Stage.TYPES_FILTER,
                f"pull_request types {sorted(types)} do not cover "
                f"{', '.join(sorted(PULL_REQUEST_TYPES))}",
            )
    for key, ignore in (("branches", False), ("branches-ignore", True)):
        if key not in fields:
            continue
        patterns = _strings(fields[key])
        if patterns is None:
            return _Problem(_Stage.BRANCH_FILTER, f"pull_request {key} cannot be read")
        if _branch_listed(branch, patterns) is ignore:
            return _Problem(
                _Stage.BRANCH_FILTER,
                f"pull_request {key} does not run on the default branch {branch}",
            )
    for key in ("paths", "paths-ignore"):
        if key in fields:
            return _Problem(
                _Stage.PATH_FILTER,
                f"pull_request has {key}: the check stays pending on a pull request "
                "that touches no matching file",
            )
    return None


def _branch_listed(branch: str, patterns: list[str]) -> bool:
    """True when `branch` matches the filter; a later `!pattern` removes an earlier match."""
    listed = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if fnmatchcase(branch, pattern.removeprefix("!")):
            listed = not negated
    return listed


def _strings(node: yaml.Node | None) -> list[str] | None:
    """The values of a string or a list of strings; None for any other node."""
    if _text(node) is not None:
        return [_text(node) or ""]
    if isinstance(node, yaml.SequenceNode):
        texts = [_text(item) for item in node.value]
        if all(text is not None for text in texts):
            return [text for text in texts if text is not None]
    return None


def _mapping(node: yaml.Node | None) -> dict[str, yaml.Node] | None:
    """The scalar-keyed entries of a YAML mapping node, in document order."""
    if not isinstance(node, yaml.MappingNode):
        return None
    return {key.value: value for key, value in node.value if isinstance(key, yaml.ScalarNode)}


def _entry(node: yaml.Node, name: str) -> tuple[yaml.Node | None, yaml.Node | None]:
    """The key and value nodes of the scalar key `name` in a YAML mapping node."""
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode) and key.value == name:
                return key, value
    return None, None


class _Document(NamedTuple):
    """A composed YAML document, or the reason it cannot be parsed."""

    root: yaml.Node | None
    error: str | None


def _compose(text: str) -> _Document:
    """The YAML node tree of `text`, or the invalid YAML message."""
    try:
        return _Document(yaml.compose(text, Loader=yaml.SafeLoader), None)
    except yaml.YAMLError as exc:
        return _Document(None, f"invalid YAML ({getattr(exc, 'problem', None) or 'invalid'})")


def _jobs_of(root: yaml.Node | None) -> dict[str, yaml.Node] | None:
    """The `jobs` entries of a workflow root node; None when there is no `jobs` mapping."""
    top = _mapping(root)
    return _mapping(top.get("jobs")) if top is not None else None


class _Jobs(NamedTuple):
    """The `jobs` entries of a workflow file, or None and the reason they cannot be read."""

    entries: dict[str, yaml.Node] | None
    error: str | None


def _jobs(text: str) -> _Jobs:
    """The `jobs` entries of a workflow file, or None and the reason they cannot be read."""
    root, error = _compose(text)
    if error is not None:
        return _Jobs(None, error)
    jobs = _jobs_of(root)
    if jobs is None:
        return _Jobs(None, "no 'jobs' mapping")
    return _Jobs(jobs, None)


def _exceeds_shown_nodes(node: yaml.Node) -> bool:
    """Whether the node has more than MAX_SHOWN_NODES nodes once aliases are expanded.

    A shared (aliased) node is counted at every reach and the walk stops as soon as the
    limit is passed, so it is bounded for alias bombs and self-referencing anchors.
    """
    pending = [node]
    count = 0
    while pending:
        current = pending.pop()
        count += 1
        if count > MAX_SHOWN_NODES:
            return True
        if isinstance(current, yaml.SequenceNode):
            pending.extend(current.value)
        elif isinstance(current, yaml.MappingNode):
            for key, value in current.value:
                pending.extend((key, value))
    return False


def _json(node: yaml.Node) -> str:
    """The JSON rendering of a YAML node's value, for messages; never raises, bounded size."""
    if _exceeds_shown_nodes(node):
        return TOO_LARGE
    try:
        return json.dumps(yaml.SafeLoader("").construct_document(node), default=str)
    except yaml.YAMLError, ValueError, TypeError, AttributeError:
        # Display-only boundary: construction (bad !!int, !!timestamp) or JSON encoding
        # (non-string keys such as dates) must never take the rule down.
        return NOT_SHOWABLE


def _text(node: yaml.Node | None) -> str | None:
    """The value of a YAML string scalar node; None for any other node."""
    if isinstance(node, yaml.ScalarNode) and node.tag == YAML_STR:
        return node.value
    return None
