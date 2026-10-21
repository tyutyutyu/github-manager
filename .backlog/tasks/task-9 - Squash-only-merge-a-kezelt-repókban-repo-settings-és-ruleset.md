---
id: TASK-9
title: Squash-only merge a kezelt repókban (repo-settings és ruleset)
status: To Do
assignee: []
created_date: '2026-10-21T18:12:00Z'
updated_date: '2026-10-21T20:17:00Z'
labels: []
dependencies: []
modified_files:
  - github-manager.toml
  - src/github_manager/rules.py
  - tests/test_config.py
  - tests/test_rules.py
  - README.md
priority: medium
type: enhancement
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A felhasználó döntése: a kezelt repókban egyetlen elfogadott merge-módszer a squash. Ma a `repo-settings` szabály (`github-manager.toml`, `[[rules]] id = "repo-settings"`) nem kezeli a merge-módszereket, és a `RepoRuleset.payload` (`src/github_manager/rules.py`) a `pull_request` szabályban `"allowed_merge_methods": ["merge", "squash", "rebase"]`-et ír. Élő állapot (2026-10-21, csak olvasva): a legtöbb repóban mindhárom módszer engedélyezett; `tyutyutyu/maven-mcp` már squash-only, `tyutyutyu-org/brand-site-ui`-ban a rebase ki van kapcsolva. Az `allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge` már szerepel a `REPO_BOOL_SETTINGS` allowlistben, ezért új kulcsot nem kell felvenni.

A compliance PR-ok auto-merge-e (külön task) erre épül: squash módszerrel kapcsolja be az auto-merge-et.

## Objective
A github-manager minden kezelt repóban squash-only merge-et állít be: repó-beállításként és a menedzselt ruleset `allowed_merge_methods` mezőjében is.

## Scope
### In scope
- `github-manager.toml`: a `repo-settings` szabály `settings` táblája kiegészül: `allow_squash_merge = true`, `allow_merge_commit = false`, `allow_rebase_merge = false`.
- `RepoRuleset.payload`: `allowed_merge_methods` értéke `["squash"]`.
- Tesztek, README, a projekt skill frissítése.

### Out of scope
- A compliance PR-ok auto-merge-e (külön task).
- Squash commit cím/üzenet beállítások (`squash_merge_commit_title` stb. nem bool, nincs a láncban).
- Renovate preset módosítása (a Renovate az engedélyezett módszert használja).

## Implementation plan
1. `github-manager.toml`: a `repo-settings` `settings` inline táblájába vedd fel a három kulcsot a fenti értékekkel; a megjegyzésben jelezd, hogy a squash az egyetlen engedélyezett merge-módszer.
2. `src/github_manager/rules.py` `RepoRuleset.payload`: `"allowed_merge_methods": ["squash"]`. A `RepoRuleset` docstringjében és a toml `default-branch-ruleset` megjegyzésében említsd meg a squash-only merge-et.
3. A valódi `github-manager.toml` tartalmára nem kerül teszt-assert (lásd TASK-12).
4. `tests/test_rules.py`: legyen teszt, amely kimondja, hogy a payload `pull_request` szabályának `allowed_merge_methods` értéke pontosan `["squash"]`; és egy, hogy a régi (`["merge","squash","rebase"]`) módszerekkel létező menedzselt ruleset `outdated` findingot ad (`with_server_defaults` fixture-rel).
5. `README.md` Rule types táblázat: a `repo_ruleset` sorba kerüljön be a squash-only merge; a `repo_settings` példái maradhatnak.
6. `.claude/skills/github-manager-rules/SKILL.md` „repo_ruleset rule” szakasza: a payload leírásába kerüljön be a `allowed_merge_methods: ["squash"]` (a fájl gitignore-olt, a handoffban jelezni kell).

## Verification
- `uv run ruff format -q . && task verify` — formázás, lint, ty, pytest ≥80% branch coverage, audit, build; sikeres kimenet.
- `uv run github-manager repos` — a valós config betölthető (csak olvasó parancs).

## Dependencies and risks
- A meglévő menedzselt rulesetek a következő `fix` futáskor `outdated`-ként frissülnek (várt viselkedés).
- Merge commitot vagy rebase-t használó kézi munkafolyamat megszűnik a kezelt repókban; ez a felhasználó kifejezett döntése.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A github-manager.toml repo-settings settings táblája tartalmazza: allow_squash_merge = true, allow_merge_commit = false, allow_rebase_merge = false
- [ ] #2 RepoRuleset.payload pull_request szabályában allowed_merge_methods pontosan ["squash"]
- [ ] #3 Régi merge-módszerlistával létező menedzselt ruleset outdated findingot ad és fix módban frissül
- [ ] #4 README repo_ruleset sora és a github-manager-rules skill payload-leírása a squash-only merge-et írja
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 uv run ruff format -q . és task verify sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->
