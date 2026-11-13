# github-manager

Validates the GitHub repositories of several owners (users and organizations, listed in
`owners`) against central rules and fixes them through pull requests.

- Rules live in [github-manager.toml](github-manager.toml); the shared Renovate preset in
  [renovate/default.json](renovate/default.json), which waits 3 days after a release
  before proposing or automerging it (`minimumReleaseAge`).
- `check` only reports. `fix` opens **one pull request per repository** from the
  `github-manager/compliance` branch, as a single verified commit, and applies
  repository settings directly.
- Idempotent: an up-to-date pull request is left alone, a stale one is rebuilt on the
  current default branch, and an obsolete one (repo fixed by hand) is closed. The rebuild
  briefly uses a `<branch>-staging` branch, so the open pull request keeps its number.
- Archived repositories and forks are skipped; anything else can be excluded globally or
  per rule with shell globs (`exclude = ["old-*"]`).
- Files and repository settings go through the GitHub REST/GraphQL API (standard library).

## Usage

```bash
task                                     # list business tasks
task repos:list                          # repositories in scope
task repos:check -- --diff               # report violations and show planned changes
task repos:check -- -r owner/my-repo     # one repository (bare name if unambiguous)
task repos:check -- -o tyutyutyu-org     # one owner only
task repos:fix                           # open or refresh pull requests
task repos:check -- -v                   # also list compliant repositories
```

Output: one line per repository with a symbol and its result, then its findings aligned
in columns (`fix` or `manual`, rule id, message). Compliant repositories are hidden unless
`-v` / `--verbose` is given; the closing summary always counts every result:

```text
✖ tyutyutyu-org/ph_toolbox  needs fix
    fix     gitignore-baseline  .gitignore: managed block is outdated
    manual  repo-visibility     visibility is "public", expected "private" ...

42 repositories  ✔ 41 compliant  ✖ 1 needs fix
```

Colours (via [rich](https://github.com/Textualize/rich)) appear on a terminal and in
GitHub Actions (`GITHUB_ACTIONS=true`), not in a pipe; `NO_COLOR` turns them off and
`FORCE_COLOR` forces them. `--diff` lines are coloured too. Long lines are never wrapped.

Authentication: `GH_TOKEN` / `GITHUB_TOKEN`, otherwise the token of the logged-in `gh` CLI
(see [Tokens](#tokens)).

Retries: a `GET` request that fails with HTTP 500, 502, 503 or 504 or a network error is
tried up to three times, waiting 1 s and then 2 s. A rate-limit response (HTTP 429, or 403
with `Retry-After` or `X-RateLimit-Remaining: 0`) is retried for any method after the wait
GitHub asks for (`Retry-After`, the `X-RateLimit-Reset` time, or 60 s); if that wait is longer
than 120 s, the request fails at once. Writes (`POST`, `PATCH`, `PUT`, `DELETE`) are never
retried after a server or network error, and other 4xx responses are never retried. Every
wait is logged as a warning.

Exit codes: `0` compliant (or every finding has a pull request), `1` findings remain
(`check`), or findings need manual action (`fix`), `2` configuration, API or unexpected error.
With `--exit-zero` (`check` and `fix`), remaining findings exit with `0` too; errors still
exit with `2`. In GitHub Actions (`GITHUB_ACTIONS=true`), remaining findings also print one
`::warning title=github-manager::<n> repositories with unresolved findings` line, with or
without the switch.

## Rule types

| Type | Purpose | Enforced by |
| --- | --- | --- |
| [`required_lines`](#required_lines) | a managed block of lines in a file | pull request |
| [`renovate_preset`](#renovate_preset) | the Renovate config extends a preset | pull request |
| [`file_sync`](#file_sync) | a file equals a template | pull request |
| [`repo_settings`](#repo_settings) | repository settings have given values | applied directly |
| [`repo_ruleset`](#repo_ruleset) | a managed ruleset protects the default branch | applied directly |
| [`branch_strategy`](#branch_strategy) | the default branch and forbidden branches | report only |
| [`repo_visibility`](#repo_visibility) | the repository visibility per owner | report only |
| [`required_files`](#required_files) | listed files exist | report only |
| [`default_branch_push_only`](#default_branch_push_only) | a workflow runs only on pushes to the default branch | report only |
| [`self_hosted_runners`](#self_hosted_runners) | private workflows run on allowed self-hosted runners | pull request |

Every rule also takes these keys:

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | string | yes | | rule id shown in findings |
| `exclude` | list of strings | no | `[]` | shell globs of repositories the rule skips |

### `required_lines`

**Checks:** `path` has a managed block (between `# >>> github-manager: <id>` and
`# <<< github-manager: <id>`, comment prefix set by `comment`) holding exactly `lines`, and
no line from `remove_lines`. `lines` is one multi-line literal string (`lines = '''` …
`'''`), written into the block line by line: blank lines at the start and end and trailing
spaces are dropped, blank lines inside are kept, and an indented line is a configuration
error.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `path` | string | yes | | file holding the block |
| `lines` | multi-line string | yes | | content of the managed block |
| `remove_lines` | list of strings | no | `[]` | lines that must not appear |
| `comment` | string | no | `#` | comment prefix of the block markers |

**Fix:** replaces or appends the block, deletes the `remove_lines`.

**Reported as manual:** `path` has malformed managed block markers (a duplicated begin or
end marker, a marker without its pair, or an end marker before the begin marker); the file
is left unchanged.

### `renovate_preset`

**Checks:** the Renovate config extends `preset`.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `preset` | string | yes | | preset that must be extended |
| `remove_extends` | list of strings | no | `[]` | entries dropped from `extends` |

**Fix:** rewrites only the `extends` array (drops `remove_extends`), or creates
`renovate.json`.

**Reported as manual:** several Renovate configs in one repo, invalid JSON, `.json5`
configs.

### `file_sync`

**Checks:** `path` equals the template file `source`.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `path` | string | yes | | file in the repository |
| `source` | string | yes | | template file, relative to the configuration file |

**Fix:** overwrites the file.

**Reported as manual:** nothing.

### `repo_settings`

**Checks:** the repository settings in `settings` (booleans accepted by
`PATCH /repos/{owner}/{repo}`, e.g. `delete_branch_on_merge`) have the given values;
optional `security_and_analysis = { secret_scanning = "enabled",
secret_scanning_push_protection = "enabled" }` (only these two keys, `"enabled"` or
`"disabled"`) is checked on **public repositories only** (private and internal ones are
skipped: the features are paid there).

**Options:** at least one of the two keys is required and they must not both be empty.

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `settings` | table of booleans | see above | `{}` | `allow_auto_merge`, `allow_forking`, `allow_merge_commit`, `allow_rebase_merge`, `allow_squash_merge`, `allow_update_branch`, `delete_branch_on_merge`, `has_discussions`, `has_issues`, `has_projects`, `has_wiki`, `use_squash_pr_title_as_default`, `web_commit_signoff_required` |
| `security_and_analysis` | table of strings | see above | `{}` | `secret_scanning`, `secret_scanning_push_protection`: `"enabled"` or `"disabled"` |

**Fix:** sets them directly on the repository, not by pull request (the security part in
one request).

**Reported as manual:** settings the token cannot read.

### `repo_ruleset`

**Checks:** the default branch has a ruleset named `github-manager: <id>` that forbids
deletion and force pushes and requires a pull request (0 approvals, conversations
resolved, squash merge only), with no bypass actors, plus the configured required status
checks.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `required_status_checks` | table of glob → list of strings | no | `{}` | `{ "<glob>" = ["<check>", ...] }`: globs match the repo name or `OWNER/NAME`; a repository gets the sorted union of all matching globs' checks, none if nothing matches |
| `required_workflow_check` | string | no | none | e.g. `verify`: added to the required checks, sorted and without duplicates, only when the default branch has a workflow that certainly runs that check on pull requests (see below); otherwise reported as *manual* and left out |
| `strict_required_status_checks` | boolean | no | `false` | branches must be up to date before merging |

**Fix:** creates or replaces that ruleset directly on the repository, not by pull
request; other (manual, organization) rulesets are never touched.

`repo_ruleset` has no bypass actors: once it is applied, nobody (including the owner)
can push to a default branch directly, only a pull request can change it. Check names in
`required_status_checks` must be checks that report on the default branch, otherwise
no pull request can be merged.

`required_workflow_check` is decided statically from the workflow files directly under
`.github/workflows/` (`.yml`/`.yaml`) of the default branch commit, never from live check
runs or from files another rule writes in the pending pull request. The check is added
only when at least one file has:

- a `pull_request` trigger (`on` as a string, list or mapping) without a `paths` or
  `paths-ignore` filter (the check would stay pending on other pull requests) and whose
  `branches`/`branches-ignore` filter still runs on the default branch, and whose `types`
  filter, if any, includes `opened`, `synchronize` and `reopened` (the defaults);
- a job whose check name is exactly the configured name (case matters): its `name:`, or its
  id when it has no `name:`; the name is not the workflow name or the file name and has no
  `${{` expression;
- that job is neither a matrix job (`verify (<value>)`) nor a reusable workflow call
  (`verify / <job>`).

Otherwise the finding `required check verify is not added: ...` names the closest cause
(no such job, matrix, reusable call, no `pull_request` trigger, types filter, path
filter, branch filter, unlistable file tree, invalid YAML) and the rest of the ruleset is
still applied.
A job skipped by `if:` is not detected; GitHub counts a skipped job as passing.

**Reported as manual:** several rulesets with the same managed name; rulesets on a
private repository of the GitHub Free plan (it has no rulesets); a
`required_workflow_check` that cannot be added (see above).

### `branch_strategy`

**Checks:** the default branch is `default_branch` and none of `forbidden_branches`
exists.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `default_branch` | string | no | `main` | expected default branch |
| `forbidden_branches` | list of strings | no | `["develop"]` | branches that must not exist |

**Fix:** none.

**Reported as manual:** every finding.

### `repo_visibility`

**Checks:** the repository has the visibility given for its owner (case-insensitive;
owners missing from the table are not checked, and every key must be listed in `owners`).

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `visibility` | table of owner → string | yes | | `{ "<owner>" = "public" \| "private" }`, not empty |

**Fix:** none.

**Reported as manual:** a repository whose visibility differs from `repo_visibility`
(changing the visibility or transferring the repository is a human decision).

### `required_files`

**Checks:** every file in `paths` exists; only the existence is checked, not the content.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `paths` | list of strings | yes | | non-empty list of repository-relative paths, e.g. `[".github/workflows/sonarqube.yml"]`; no leading or trailing `/`, no `..` segment, no duplicates |

**Fix:** none; nothing is written.

**Reported as manual:** a file listed in `required_files` that does not exist (one
finding per missing file).

### `default_branch_push_only`

**Checks:** the workflow file `path` runs only on pushes to the default branch: its `on`
is a mapping whose only trigger is `push`, with a `branches` filter that is exactly the
default branch (no glob, no `!` negation, no other branch) and no `branches-ignore`,
`tags` or `tags-ignore`; `paths` and `paths-ignore` are allowed; a missing file is not
reported.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `path` | string | yes | | a direct `.yml`/`.yaml` child of `.github/workflows/`, e.g. `.github/workflows/sonarqube.yml` |

**Fix:** none; nothing is written.

**Reported as manual:** a `default_branch_push_only` workflow that can run on anything
but a push to the default branch (one finding naming the first problem).

### `self_hosted_runners`

**Checks:** in private and internal repositories (public ones are not checked), the
`runs-on` of every job in `.github/workflows/*.yml|*.yaml` equals one of the label sets
in `allowed_runs_on` (exact match as a set, case-insensitive); local `uses: ./...` calls
are skipped.

**Options:**

| Key | Type | Required | Default | Meaning |
| --- | --- | --- | --- | --- |
| `allowed_runs_on` | list of lists of strings | yes | | allowed label sets, e.g. `[["self-hosted"]]`; not empty, no duplicate sets, every set must contain `self-hosted` |
| `runs_on` | list of strings | yes | | replacement value, e.g. `["self-hosted"]`; it must equal one of the `allowed_runs_on` sets |

**Fix:** rewrites the `runs-on` of a job to `runs_on` in the pull request when it is a
single `ubuntu-*` label or a label set that contains `self-hosted` but is not allowed
(e.g. `[self-hosted, Linux, X64, zhukov]`) and the value sits on the same line as the
`runs-on` key (a scalar or a one-line list); only that value changes, the rest of the
file stays byte for byte the same, and the file is re-parsed to check the result before
it is written.

**Reported as manual:** a job of a private or internal repository whose `runs-on`
`self_hosted_runners` cannot rewrite: `windows-*`, `macos-*` and other unknown labels,
expressions, matrices, mappings, external reusable workflows, unparsable files, and
values it cannot replace safely (a multi-line list, an alias, an anchor or a tag).

## Auto-merge

With `auto_merge = true` (top-level key, default `false`), `fix` turns on **squash
auto-merge** on the compliance pull request, only when all of these hold:

- the pull request was created, updated or found up to date in this run;
- a `repo_ruleset` rule applies to the repository and requires the `verify` check
  (`required_workflow_check = "verify"` and the workflow condition above is met, so the
  ruleset the run applied really contains it); another required check, such as one set by a
  glob in `required_status_checks`, is not enough;
- that rule has no *manual* finding in the run (e.g. two managed rulesets with one name).

It runs after the repository settings and the ruleset are applied (a new repository has
`allow_auto_merge` off until then). The pull request branch is rebuilt on a change, so
auto-merge is turned on again whenever the pull request was updated; an untouched pull
request that already has it gets no new call. If enabling auto-merge fails and the pull request's
merge state (`mergeStateStatus`) is `CLEAN`, e.g. the `verify` check has already passed, the
pull request is squash-merged right away. Any other
auto-merge or merge error does not fail the repository: it is shown under the repository's line
(`auto-merge  failed: ...`) and in the *Auto-merge* column of the job summary, and the rest of the
fixes are kept. A repository that does not qualify shows `auto-merge  not enabled: verify is
not required`. `check` never enables it.

## Scheduled run

[.github/workflows/enforce.yml](.github/workflows/enforce.yml) runs `fix` daily and can
be started by hand (`check` or `fix`, optionally one repository). It runs one job per
owner, and each job reads that owner's token secret (see [Tokens](#tokens)).

The scheduled run passes `--exit-zero`, so a red run means an error (exit code `2`: a
configuration, API, installation or unexpected error), not remaining findings. Findings
show up in the job summary table and as a warning annotation on the run page.

The job runs with `uv run --locked --no-dev`, so the `dev` dependency group is not
installed next to the fleet tokens. For the same reason, this repository's
[renovate.json](renovate.json) turns off auto-merge for updates of the runtime
dependencies (`[project].dependencies`), the build backend (`[build-system].requires`) and
the GitHub Actions: those need a manual merge. `dev` group updates still auto-merge.

## Tokens

A fine-grained personal access token covers a single resource owner, so every entry in
`owners` needs its own token, stored as an Actions secret of this repository:

| Owner | Secret name | Suggested token name |
| --- | --- | --- |
| `tyutyutyu` (user) | `GH_MANAGER_TOKEN` | `github-manager (tyutyutyu)` |
| `tyutyutyu-org` (organization) | `GH_MANAGER_ORG_TOKEN` | `github-manager (tyutyutyu-org)` |

Create each one under *Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token*:

- **Resource owner:** the owner from the table.
- **Repository access:** *All repositories* (new repositories are covered automatically).
- **Repository permissions:**

  | Permission | Access | Needed for |
  | --- | --- | --- |
  | Contents | Read and write | reading files, creating the compliance branch and commit |
  | Pull requests | Read and write | opening, updating and closing the pull request |
  | Administration | Read and write | `repo_settings` (e.g. `delete_branch_on_merge`) and `repo_ruleset` (reading and writing repository rulesets) |
  | Metadata | Read-only | always required (selected automatically) |
  | Workflows | Read and write | `self_hosted_runners` (rewriting the files under `.github/workflows`) |

- **Expiration:** pick a date and renew the token before it expires; an expired token
  makes that owner's job fail with HTTP 401.

For the organization, fine-grained tokens must be allowed (*Organization settings →
Personal access tokens*); if the organization requires approval, the token only works
once an owner approves it.

Store the tokens (the command prompts for the value):

```bash
gh secret set GH_MANAGER_TOKEN --repo tyutyutyu/github-manager
gh secret set GH_MANAGER_ORG_TOKEN --repo tyutyutyu/github-manager
```

Without Administration access, a setting GitHub does not return is reported as *manual*
("not readable"); one it does return cannot be changed, and `fix` reports the repository
as an error (HTTP 403).

Adding an owner: add it to `owners`, create its token, store it under a new secret name,
and add an `owner`/`secret` pair to the job matrix in
[.github/workflows/enforce.yml](.github/workflows/enforce.yml).

Running locally: `GH_TOKEN` can hold one of these tokens (then use `-o` to limit the run
to its owner), or the `gh` CLI login is used, which works when your account has admin
rights on the repositories.

## Development

```bash
task verify                              # run every quality gate (same as CI)
task dev:format                          # format and apply safe lint fixes
task version-bump -- patch|minor|major   # bump the version via uv
```

### Integration test

`tests/test_integration_github.py` runs the compliance pull request lifecycle (created, updated
after the default branch moves, up to date, closed) against the real GitHub API. It is skipped
unless `GITHUB_MANAGER_SANDBOX_REPO` is set, so `task verify` and CI never run it.

Prerequisites:

- a dedicated sandbox repository whose name contains `sandbox` (the test refuses any other name);
- its default branch accepts direct pushes, because the test commits to it;
- it is outside the scope of the real rules: either not under the configured `owners`, or listed in
  the global `exclude`;
- a token, as for normal runs, with write access to that repository.

The test uses its own synthetic configuration, never `github-manager.toml`, and closes its pull
request and deletes its branches afterwards, even on failure.

```bash
GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> task dev:test-integration
```

## License

This project is licensed under the MIT License; see [LICENSE](LICENSE).
