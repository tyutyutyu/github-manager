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
```

Authentication: `GH_TOKEN` / `GITHUB_TOKEN`, otherwise the token of the logged-in `gh` CLI
(see [Tokens](#tokens)).

Exit codes: `0` compliant (or every finding has a pull request), `1` findings remain
(`check`), or findings need manual action (`fix`), `2` configuration or API error.

## Rule types

| Type | Checks | Fix |
| --- | --- | --- |
| `required_lines` | `path` has a managed block (between `# >>> github-manager: <id>` and `# <<< github-manager: <id>`, comment prefix set by `comment`) holding exactly `lines`, and no line from `remove_lines` | replaces or appends the block, deletes the `remove_lines` |
| `renovate_preset` | the Renovate config extends `preset` | rewrites only the `extends` array (drops `remove_extends`), or creates `renovate.json` |
| `file_sync` | `path` equals the template file `source` | overwrites the file |
| `repo_settings` | the repository settings in `settings` (booleans accepted by PyGithub's `Repository.edit`, e.g. `delete_branch_on_merge`) have the given values | sets them directly on the repository, not by pull request |
| `branch_strategy` | the default branch is `default_branch` (default `main`) and none of `forbidden_branches` (default `["develop"]`) exists | none: reported as *manual* |

Not fixed automatically (reported as *manual*): several Renovate configs in one repo,
invalid JSON, `.json5` configs, and settings the token cannot read.

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
  | Administration | Read and write | `repo_settings` (e.g. `delete_branch_on_merge`) |
  | Metadata | Read-only | always required (selected automatically) |
  | Workflows | Read and write | only if a rule edits files under `.github/workflows` |

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
