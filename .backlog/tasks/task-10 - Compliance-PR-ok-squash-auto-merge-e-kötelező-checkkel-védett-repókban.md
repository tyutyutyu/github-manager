---
id: TASK-10
title: >-
  Compliance PR-ok squash auto-merge-e, csak kötelező verify checkkel védett
  repókban
status: To Do
assignee: []
created_date: '2026-10-21T18:13:00Z'
updated_date: '2026-10-21T20:17:00Z'
labels: []
dependencies:
  - TASK-9
  - TASK-11
modified_files:
  - src/github_manager/config.py
  - src/github_manager/github.py
  - src/github_manager/engine.py
  - src/github_manager/cli.py
  - github-manager.toml
  - tests/conftest.py
  - tests/test_engine.py
  - tests/test_github.py
  - README.md
priority: high
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A github-manager compliance PR-jait (`branch` a `github-manager.toml`-ban) ma kézzel kell mergelni. Elvárás: squash auto-merge (squash-only: TASK-9), de csak ott, ahol a `verify` check kötelező (TASK-11). Amíg egy repóban nincs kötelező `verify`, addig az auto-merge szabály nem futhat rá; más kötelező check (pl. egy glob-bal előírt `test`) ehhez nem elég.

Ismert buktatók:
- Sorrend: `src/github_manager/engine.py` `_process` előbb `_sync_pull_request`-et hív, utána `update_repo_settings`-et és `_apply_ruleset`-et. Ha az auto-merge a PR-szinkron része lenne, új repóban az `allow_auto_merge` még `false`, a hívás `GitHubError`-t dob, a repó `ERROR` lesz, és a beállítások/ruleset sosem kerülnek fel. Az auto-merge-nek a settings és a ruleset UTÁN kell futnia, és hibája nem állíthatja le a repó feldolgozását.
- Ha a kötelező check már zölden lefutott, a PR `clean` állapotú; a GitHub `enablePullRequestAutoMerge` ilyenkor „clean status” hibát ad. Mivel a `verify` kötelező és teljesült, a squash merge közvetlenül biztonságos.
- A PR ága minden futáskor újragenerálódhat (`reset_branch` force push); egy korábban olvasott „auto-merge már be van kapcsolva” állapot ilyenkor elavult lehet.
- `PullRequest` (`src/github_manager/github.py`) ma csak `number`-t és `url`-t tárol; a GraphQL mutációhoz a PR `node_id` kell, a REST válasz `auto_merge` mezője mutatja a bekapcsolt állapotot. `GitHub.graphql` már létezik, és `GitHubError`-t dob GraphQL hibára.
- A token meglévő jogosultságai (Contents, Pull requests, Workflows read/write) elegendők.

Megjegyzés: a `feature/TASK-9-10-squash-auto-merge` ágon van egy commit nélküli előzetes megvalósítás, amely még bármilyen kötelező checkre engedélyezi az auto-merge-et; a jogosultságot a TASK-11 lekérdezésére kell átállítani.

## Objective
`fix` módban a github-manager a compliance PR-on squash auto-merge-et kapcsol be (vagy már teljesült feltételeknél közvetlenül squash-merge-el), kizárólag olyan repóban, ahol a menedzselt ruleset a `verify` checket kötelezővé teszi, a beállítások és a ruleset alkalmazása után, és egy sikertelen auto-merge soha nem akadályozza a repó többi javítását.

## Scope
### In scope
- Felső szintű config kulcs: `auto_merge` (bool, alapértelmezés `false`) a `Config`-ban (`src/github_manager/config.py`), `github-manager.toml`-ban `auto_merge = true`.
- `GitHub` (és a `GitHubApi` Protocol, `FakeGitHub`): PR `node_id` és `auto_merge` állapot; auto-merge bekapcsolása GraphQL-lel (`enablePullRequestAutoMerge`, `mergeMethod: SQUASH`); közvetlen squash merge REST-tel (`PUT /repos/{repo}/pulls/{number}/merge`, `merge_method: squash`).
- Engine: jogosultság (TASK-11 lekérdezése), sorrend, hibakezelés, riport; CLI kimenet és job summary; README; tesztek.

### Out of scope
- Squash-only beállítás (TASK-9), a `verify` ellenőrzés és kötelezővé tétele (TASK-11).
- Renovate PR-ok.
- Bármilyen írás más repókba ezen a kódon kívül; valós `fix` futtatás.

## Implementation plan
1. `config.py`: `auto_merge: bool = False`, `options.flag("auto_merge", defaults.auto_merge)`; `github-manager.toml`: `auto_merge = true` megjegyzéssel (csak kötelező `verify` mellett, squash).
2. `github.py`: `PullRequest`-be `node_id` és `auto_merge`; `find_open_pr`/`create_pr` töltse ki. Új `enable_auto_merge(repo, pull)` és `merge_pr(repo, number)`; felvétel a `GitHubApi` Protocolba és a `FakeGitHub`-ba (`calls` rögzítés, hibaszimuláció).
3. Jogosultság: `config.auto_merge` igaz; a PR-szinkron eredménye `PR_CREATED`/`PR_UPDATED`/`PR_UP_TO_DATE`; van alkalmazódó `RepoRuleset`, amely TASK-11 lekérdezése szerint ebben a repóban a `verify`-t kötelezővé teszi, és ennek a szabálynak nincs `fixable=False` findingja ebben a futásban. Más kötelező check önmagában nem elég.
4. `engine._process`: az auto-merge a settings-frissítés és a `_apply_ruleset` UTÁN fut. `PR_UPDATED` esetén a korábban olvasott `auto_merge` állapotot ne vedd figyelembe (kapcsold be újra). „clean status” hibára `merge_pr`. Minden más `GitHubError` a riportba kerül (pl. `RepoReport.auto_merge`), az outcome nem lesz `ERROR`. Nem jogosult repónál a riport röviden jelezze az okot (pl. „verify is not required”).
5. `cli.py`: az auto-merge eredménye a repó sora alatt és a job summary-ben (a cellában `|` és sortörés escape-elve).
6. Tesztek (`tests/test_engine.py`, `tests/test_github.py`, `tests/test_cli.py`; config-parse a `tests/test_config.py`-ban, de NEM a valódi `github-manager.toml` tartalmára):
   - jogosult repóban az auto-merge hívás a settings/ruleset írások után jön;
   - csak más kötelező checkkel (verify nélkül) nincs auto-merge és nincs merge hívás;
   - `auto_merge = false` mellett nincs hívás; PR nélkül nincs auto-merge;
   - újraírt ágon (`PR_UPDATED`) újra bekapcsol; `PR_UP_TO_DATE`-nél bekapcsolt állapotnál nincs újabb hívás;
   - „clean status” → `merge_pr`; egyéb auto-merge vagy merge hiba → nem `ERROR`, a settings és a ruleset mégis felkerül, a hiba szövege a riportban;
   - rulesetet nem támogató repóban nincs auto-merge;
   - `enable_auto_merge` és `merge_pr` a várt GraphQL/REST kérést küldi.
7. `README.md` Auto-merge szakasz; `.claude/skills/github-manager-rules/SKILL.md` az engine sorrendjéről és a jogosultságról.

## Verification
- `uv run ruff format -q . && task verify` — sikeres.
- `uv run github-manager repos` — a valós config betölthető (csak olvasó parancs).

## Dependencies and risks
- Függ: TASK-9 (squash engedélyezett), TASK-11 (a `verify` kötelező-e lekérdezés).
- Ha a `verify` sosem fut le a PR-on, az auto-merge függőben marad; ártalmatlan.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 auto_merge felső szintű bool config kulcs (alapértelmezés false), a github-manager.toml-ban true
- [ ] #2 Fix módban a compliance PR-on squash auto-merge kapcsol be, kizárólag ha a menedzselt ruleset a verify checket kötelezővé teszi, a repo settings és ruleset írások után
- [ ] #3 Verify nélküli repóban (akkor is, ha más kötelező check van) nincs auto-merge és nincs merge hívás, a riport jelzi az okot
- [ ] #4 Clean status hibára (a verify már teljesült) a PR közvetlenül squash-mergelődik
- [ ] #5 Újraírt PR-ágon az auto-merge újra bekapcsol; már bekapcsolt, változatlan PR-nál nincs újabb hívás
- [ ] #6 Auto-merge vagy merge hiba nem ad ERROR outcome-ot, nem akadályozza a settings/ruleset alkalmazását, és a hibaszöveg megjelenik a kimenetben és a job summary-ben
- [ ] #7 GitHub.enable_auto_merge és merge_pr a várt GraphQL/REST kérést küldi
- [ ] #8 README és a github-manager-rules skill leírja az auto-merge feltételeit és sorrendjét
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 uv run ruff format -q . és task verify sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->
