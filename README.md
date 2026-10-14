# github-manager

Validates the GitHub repositories of several owners (users and organizations, listed in
`owners`) against central rules and fixes them through pull requests.

- Rules live in [github-manager.toml](github-manager.toml); the shared Renovate preset in
  [renovate/default.json](renovate/default.json).
- `check` only reports. `fix` opens **one pull request per repository** from the
  `github-manager/compliance` branch, as a single verified commit.
- Idempotent: an up-to-date pull request is left alone, a stale one is rebuilt on the
  current default branch, and an obsolete one (repo fixed by hand) is closed.
- Archived repositories and forks are skipped; anything else can be excluded globally or
  per rule with shell globs (`exclude = ["old-*"]`).
- No runtime dependencies: Python standard library + GitHub REST/GraphQL API.

## Usage

```bash
task                                     # list business tasks
task repos:list                          # repositories in scope
task repos:check -- --diff               # report violations and show planned changes
task repos:check -- -r owner/my-repo     # one repository (bare name if unambiguous)
task repos:check -- -o tyutyutyu-org     # one owner only
task repos:fix                           # open or refresh pull requests
```

Authentication: `GH_TOKEN` / `GITHUB_TOKEN`, otherwise the token of the logged-in `gh` CLI.

Exit codes: `0` compliant (or every finding has a pull request), `1` findings remain
(`check`), or findings need manual action (`fix`), `2` configuration or API error.

## Rule types

| Type | Checks | Fix |
| --- | --- | --- |
| `required_lines` | `path` has a managed block (between `# >>> github-manager: <id>` and `# <<< github-manager: <id>`, comment prefix set by `comment`) holding exactly `lines`, and no line from `remove_lines` | replaces or appends the block, deletes the `remove_lines` |
| `renovate_preset` | the Renovate config extends `preset` | rewrites only the `extends` array (drops `remove_extends`), or creates `renovate.json` |
| `file_sync` | `path` equals the template file `source` | overwrites the file |
| `branch_strategy` | the default branch is `default_branch` (default `main`) and none of `forbidden_branches` (default `["develop"]`) exists | none: reported as *manual* |

Not fixed automatically (reported as *manual*): several Renovate configs in one repo,
invalid JSON, and `.json5` configs.

## Scheduled run

[.github/workflows/enforce.yml](.github/workflows/enforce.yml) runs `fix` daily and can
be started by hand (`check` or `fix`, optionally one repository). It needs the
`GH_MANAGER_TOKEN` secret: a fine-grained token for *All repositories* with
Contents and Pull requests read/write (Workflows read/write only if a rule edits
`.github/workflows`).

## Development

```bash
task verify                              # run every quality gate (same as CI)
task dev:format                          # format and apply safe lint fixes
task version-bump -- patch|minor|major   # bump the version via uv
```
