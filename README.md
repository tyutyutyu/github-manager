# github-manager

Validates the GitHub repositories of several owners (users and organizations, listed in
`owners`) against central rules and fixes them through pull requests.

- Rules live in [github-manager.toml](github-manager.toml); the shared Renovate preset in
  [renovate/default.json](renovate/default.json).
- `check` only reports. `fix` opens **one pull request per repository** from the
  `github-manager/compliance` branch, as a single verified commit, and applies
  repository settings directly.
- Idempotent: an up-to-date pull request is left alone, a stale one is rebuilt on the
  current default branch, and an obsolete one (repo fixed by hand) is closed.
- Archived repositories and forks are skipped; anything else can be excluded globally or
  per rule with shell globs (`exclude = ["old-*"]`).
- Files go through the GitHub REST/GraphQL API (standard library); repository settings
  through [PyGithub](https://github.com/PyGithub/PyGithub).

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

Exit codes: `0` compliant (or every finding has a pull request), `1` findings remain
(`check`), or findings need manual action (`fix`), `2` configuration or API error.

## Rule types

| Type | Checks | Fix |
| --- | --- | --- |
| `required_lines` | `path` has a managed block (between `# >>> github-manager: <id>` and `# <<< github-manager: <id>`, comment prefix set by `comment`) holding exactly `lines`, and no line from `remove_lines` (a list). `lines` is one multi-line literal string (`lines = '''` … `'''`), written into the block line by line: blank lines at the start and end and trailing spaces are dropped, blank lines inside are kept, and an indented line is a configuration error | replaces or appends the block, deletes the `remove_lines` |
| `renovate_preset` | the Renovate config extends `preset` | rewrites only the `extends` array (drops `remove_extends`), or creates `renovate.json` |
| `file_sync` | `path` equals the template file `source` | overwrites the file |
| `repo_settings` | the repository settings in `settings` (booleans accepted by PyGithub's `Repository.edit`, e.g. `delete_branch_on_merge`) have the given values; optional `security_and_analysis = { secret_scanning = "enabled", secret_scanning_push_protection = "enabled" }` (only these two keys, `"enabled"` or `"disabled"`) is checked on **public repositories only** (private and internal ones are skipped: the features are paid there) | sets them directly on the repository, not by pull request (the security part in one request) |
| `repo_ruleset` | the default branch has a ruleset named `github-manager: <id>` that forbids deletion and force pushes and requires a pull request (0 approvals, conversations resolved), with no bypass actors; optional `required_status_checks = { "<glob>" = ["<check>", ...] }` (globs match the repo name or `OWNER/NAME`; a repository gets the sorted union of all matching globs' checks, none if nothing matches) and `strict_required_status_checks` (default `false`) | creates or replaces that ruleset directly on the repository, not by pull request; other (manual, organization) rulesets are never touched. A private repository on the GitHub Free plan has no rulesets: reported as *manual* |
| `branch_strategy` | the default branch is `default_branch` (default `main`) and none of `forbidden_branches` (default `["develop"]`) exists | none: reported as *manual* |
| `repo_visibility` | the repository has the visibility given by `visibility = { "<owner>" = "public" \| "private" }` for its owner (case-insensitive; owners missing from the table are not checked, and every key must be listed in `owners`) | none: reported as *manual* (changing the visibility or transferring the repository is a human decision) |
| `self_hosted_runners` | in private and internal repositories (public ones are not checked), the `runs-on` of every job in `.github/workflows/*.yml\|*.yaml` equals one of the label sets in `allowed_runs_on = [["self-hosted"]]` (exact match as a set, case-insensitive; every set must contain `self-hosted`) | rewrites the `runs-on` of a job to `runs_on` (required, e.g. `["self-hosted"]`; it must equal one of the `allowed_runs_on` sets) in the pull request when it is a single `ubuntu-*` label or a label set that contains `self-hosted` but is not allowed (e.g. `[self-hosted, Linux, X64, zhukov]`) and the value sits on the same line as the `runs-on` key (a scalar or a one-line list); only that value changes, the rest of the file stays byte for byte the same, and the file is re-parsed to check the result before it is written. Everything else is reported as *manual* (see below); local `uses: ./...` calls are skipped |

Not fixed automatically (reported as *manual*): several Renovate configs in one repo,
invalid JSON, `.json5` configs, settings the token cannot read, several rulesets with
the same managed name, rulesets on a private repository of the GitHub Free plan, and a
repository whose visibility differs from `repo_visibility`, and a job of a private or
internal repository whose `runs-on` `self_hosted_runners` cannot rewrite: `windows-*`,
`macos-*` and other unknown labels, expressions, matrices, mappings, external reusable
workflows, unparsable files, and values it cannot replace safely (a multi-line list, an
alias, an anchor or a tag).

`repo_ruleset` has no bypass actors: once it is applied, nobody (including the owner)
can push to a default branch directly, only a pull request can change it. Check names in
`required_status_checks` must be checks that report on the default branch, otherwise
no pull request can be merged.

## Scheduled run

[.github/workflows/enforce.yml](.github/workflows/enforce.yml) runs `fix` daily and can
be started by hand (`check` or `fix`, optionally one repository). It runs one job per
owner, and each job reads that owner's token secret (see [Tokens](#tokens)).

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
