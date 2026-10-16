---
id: TASK-1
title: >-
  repo-settings szabály bővítése: allow_auto_merge, allow_update_branch,
  has_wiki
status: In Progress
assignee: []
created_date: '2026-10-14 21:38'
updated_date: '2026-10-16 11:14'
labels: []
dependencies: []
references:
  - src/github_manager/rules.py
  - renovate/default.json
documentation:
  - README.md
modified_files:
  - github-manager.toml
priority: medium
type: chore
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A github-manager központi `repo_settings` szabálya (`RepoSettings` a `src/github_manager/rules.py`-ban) logikai repó-beállításokat tart egységesen; a `fix` közvetlenül, PyGithubon (`GitHub.update_repo_settings` a `src/github_manager/github.py`-ban) állítja őket, nem pull requestben. A `github-manager.toml` `repo-settings` szabálya jelenleg csak `delete_branch_on_merge = true`-t ír elő.

Állapot 2026-10-14-én a 7 érintett repón (`uv run github-manager repos`):
- `allow_auto_merge`: mindenhol `false`.
- `allow_update_branch`: mindenhol `false`.
- `has_wiki`: `true` a `tyutyutyu-org/project-manager` és a `tyutyutyu/just-enough-quota-bar` repón, máshol `false`.

Miért kell:
- A közös Renovate preset (`renovate/default.json`) automergeli a minor/patch/pin/digest frissítéseket. Ha a default ágon kötelező status checkek lesznek (a központi branch ruleset feladata), a Renovate a GitHub platform-automerge funkcióját használja, ehhez `allow_auto_merge = true` kell.
- `allow_update_branch = true` megjeleníti az „Update branch” gombot, ami szigorú (naprakész ágat kérő) checkeknél kell.
- A wikit egyik repó sem használja.

Mindhárom kulcs szerepel a `REPO_BOOL_SETTINGS` engedélyezett listájában, kódváltozás nem kell.

## Objective
A `repo-settings` szabály a `delete_branch_on_merge` mellett előírja: `allow_auto_merge = true`, `allow_update_branch = true`, `has_wiki = false`.

## Scope
### In scope
- A `github-manager.toml` `[[rules]] id = "repo-settings"` blokkjának `settings` táblája.
- Ha a szabály melletti komment felsorolja a beállításokat, annak frissítése.

### Out of scope
- Új rule type vagy kódváltozás a `src/` alatt.
- Rulesetek és kötelező status checkek (külön feladat).
- `security_and_analysis` beállítások (külön feladat).
- Beállítás közvetlen módosítása bármely valódi repón a githubos workflow-n kívül.

## Implementation notes
1. A `github-manager.toml`-ban a `repo-settings` szabály `settings` értéke legyen: `{ delete_branch_on_merge = true, allow_auto_merge = true, allow_update_branch = true, has_wiki = false }`. A meglévő `exclude = []` maradjon.
2. A `tests/test_config.py::test_repository_config_file_is_valid` csak a szabálytípusokat ellenőrzi; ha a beállítások ellenőrzésével bővül, a `RepoSettings.settings` értékét a fenti dicttel vesse össze.
3. Valódi fiókok ellen helyben csak a `uv run github-manager repos` parancs futtatható (projektkonvenció). A tényleges eltérések ellenőrzése az `enforce` workflow kézi, `check` módú futtatásával történik.

## Verification
- `uv run ruff format -q .` majd `task verify`: formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build; mind sikeres.
- `uv run pytest tests/test_config.py -q --no-cov`: a valódi konfigurációs fájl betölthető.
- Kézi: GitHub Actions → `enforce` → Run workflow, `mode = check`. Várt: `repo-settings: setting allow_auto_merge is false, expected true` és `setting allow_update_branch is false, expected true` sor minden érintett repónál, valamint `setting has_wiki is true, expected false` a `tyutyutyu-org/project-manager` és `tyutyutyu/just-enough-quota-bar` repónál.

## Dependencies and risks
- Előfeltétel: a `repo_settings` rule type a `main`-en van. A feladat létrehozásakor csak commitolatlan munka volt a munkakönyvtárban.
- Előfeltétel: a `GH_MANAGER_TOKEN` és `GH_MANAGER_ORG_TOKEN` secret létezik Administration: Read and write joggal (README „Tokens” szakasza). Enélkül a `check` „not readable” kézi teendőt jelez.
- A `has_wiki = false` egy létező wiki tartalmát nem törli, csak elrejti; a két érintett repóban a fix előtt nézd meg, van-e wikitartalom.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `github-manager.toml` `repo-settings` szabályának `settings` táblája pontosan ezt tartalmazza: `delete_branch_on_merge = true`, `allow_auto_merge = true`, `allow_update_branch = true`, `has_wiki = false`
- [x] #2 A valódi konfigurációs fájl hibátlanul betöltődik (`tests/test_config.py::test_repository_config_file_is_valid` zöld)
- [ ] #3 Egy `check` módú `enforce` futás a három új beállítás eltéréseit `[fix]` findingként jelzi, és nem jelez `ERROR`-t a token jogai miatt
- [x] #4 Nem változik kód a `src/` alatt
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 A `task verify` sikeres
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. github-manager.toml repo-settings settings: delete_branch_on_merge, allow_auto_merge, allow_update_branch = true, has_wiki = false.
2. tests/test_config.py: assert the real config's RepoSettings.settings dict.
3. ruff format + task verify.
4. Push the branch, run the enforce workflow in check mode on it, confirm the new findings.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-1-repo-settings-szabaly-bovitese-allow-auto-merge.

Set the four settings in github-manager.toml and added a settings dict assertion to test_repository_config_file_is_valid. No change under src/.
Validation: uv run ruff format -q . && task verify -> exit 0 (95 passed, 99.08% branch coverage, audit clean, build ok).
The working tree also had unrelated github-manager.toml edits (removed excludes for tyutyutyu-org/easy-github, tyutyutyu/home-server-management, tyutyutyu/maven-mcp; one-line lines/remove_lines arrays). They were left uncommitted, outside this task.
<!-- SECTION:NOTES:END -->
