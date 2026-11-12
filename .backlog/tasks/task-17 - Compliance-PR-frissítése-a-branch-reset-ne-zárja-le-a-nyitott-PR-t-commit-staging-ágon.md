---
id: TASK-17
title: >-
  Compliance PR frissítése: a branch-reset ne zárja le a nyitott PR-t (commit
  staging ágon)
status: To Do
assignee: []
created_date: '2026-11-12T12:16:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/engine.py
  - tests/conftest.py
  - tests/test_engine.py
priority: high
type: bug
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `_sync_pull_request` (`src/github_manager/engine.py`) az elavult compliance ágat két lépésben építi újra:
1. `api.reset_branch(name, branch, base_sha, exists=branch_sha is not None)` — az ágat a default ág csúcsára állítja;
2. `api.commit_files(name, branch, base_sha, message, changes)` — erre commitol.

A két lépés között a PR head ágának nincs eltérése a bázishoz képest, és a GitHub az ilyen nyitott PR-t automatikusan lezárja. Bizonyíték (2026-11-12): a 114 compliance PR-ból 33 zárult le merge nélkül; ebből 21-nél a `closed` és a `head_ref_force_pushed` esemény ugyanabban a másodpercben történt, a program „The default branch already satisfies the rules." megjegyzése nélkül (a másik 12-t a program zárta le szabályosan).

Következmény: a program a már lezárt PR-on hív `update_pr`-t, `Outcome.PR_UPDATED` eredményt jelent, a javítás pedig csak a következő futás új PR-jával megy tovább (új PR-szám, felesleges értesítések, elveszett auto-merge).

A tesztek nem fogták meg: a `FakeGitHub.reset_branch` (`tests/conftest.py`) nem zárja le a PR-t.

Kötöttség: a commit a GraphQL `createCommitOnBranch` hívással készül (`GitHub.commit_files`, `src/github_manager/github.py`), mert így a GitHub aláírja („single verified commit" a README-ben). Ehhez létező ág és `expectedHeadOid` kell, ezért a commit nem készíthető közvetlenül ág nélkül.

Forrás: docs/project-review-2026-11-12.md, 2.2.

## Objective
A meglévő nyitott compliance PR nyitva marad (ugyanazzal a PR-számmal), amikor a program újraépíti az ágát.

## Scope
### In scope
- A `_sync_pull_request` újraépítő ága: commit egy ideiglenes staging ágon, majd a compliance ág áthelyezése egy lépésben.
- A `FakeGitHub` igazítása a GitHub valós viselkedéséhez, regressziós tesztek.
- README: az átmeneti staging ág említése.

### Out of scope
- A `GitHubApi` protokoll és a `github.py` módosítása (a meglévő metódusok elegendők).
- A `_branch_matches`, az auto-merge és a PR lezárásának logikája.
- Írás a kezelt repókba a fejlesztés alatt.

## Implementation plan
1. `src/github_manager/engine.py`: új konstans `STAGING_SUFFIX = "-staging"`; a staging ág neve `f"{config.branch}{STAGING_SUFFIX}"`. Kötőjeles utótag kell, nem `/`: git ref nem lehet egyszerre `a/b` és `a/b/c`.
2. A `_sync_pull_request` újraépítő részében a `reset_branch` + `commit_files` páros helyett:
   a. `staging_sha = api.branch_sha(name, staging)`; `api.reset_branch(name, staging, base_sha, exists=staging_sha is not None)` (megszakadt futásból maradt staging ágat újrahasznosít);
   b. `oid = api.commit_files(name, staging, base_sha, message, changes)`;
   c. `api.reset_branch(name, branch, oid, exists=branch_sha is not None)` — a compliance ág egy lépésben kerül az új commitra (a `reset_branch` létező ágnál `force: true` PATCH, különben létrehozás);
   d. `api.delete_branch(name, staging)` — `try/finally`-ban, hogy a b vagy c lépés hibájakor is lefusson; a törlés hibája ne fedje el az eredeti hibát.
3. A PR nélküli és a még nem létező compliance ág esete ugyanezen az úton menjen (egységes folyamat).
4. `tests/conftest.py`, `FakeGitHub.reset_branch`: ha a beállított sha egyenlő a repó default ágának sha-jával (`state.branches[state.info.default_branch]`), akkor az adott head ágú nyitott PR-okat zárja le (`self.pulls[repo][number]` harmadik eleme `False`), és ezt jegyezze fel a `calls` listába.
5. `tests/test_engine.py`:
   - a `test_fix_lifecycle` „The default branch moves on" része (vagy új teszt): a második `fix` után `Outcome.PR_UPDATED`, a `fake_github.find_open_pr(name, CONFIG.branch)` ugyanazt a számot adja, a compliance ág egy commit az új bázison, és a staging ág nincs a `fake_github.repos[name].branches`-ben;
   - megmaradt staging ág: előre felvett `<branch>-staging` ág mellett a futás sikeres;
   - hibaág: ha a `commit_files` `GitHubError`-t dob, a staging ág törlődik, és a `process_repo` `Outcome.ERROR`-t ad az eredeti üzenettel;
   - a `test_stale_branch_without_pull_request_is_reused` továbbra is zöld (a `calls` elvárásait igazítani kell, ha szükséges).
6. `README.md`, a bevezető felsorolás „Idempotent" pontja: az újraépítés rövid időre egy `<branch>-staging` ágat használ.

## Verification
- `uv run pytest tests/test_engine.py --no-cov` — az új és a meglévő motor-tesztek zöldek.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- Élesítés után (kézi, csak olvasó): az első `pull request updated` eredményű futás PR-ja nyitva maradt, a száma nem változott (`gh pr view`).

## Dependencies and risks
- A staging ág pusholása a kezelt repókban elindíthatja a szűretlen `push` triggerű workflow-kat (ahogy a compliance ágé eddig is): egy plusz futás repónként, elfogadott.
- Párhuzamos futás (helyi + ütemezett): a `commit_files` `expectedHeadOid` paramétere véd; az ütemezett futásokat az `enforce.yml` `concurrency` csoportja sorosítja.
- A repónkénti hibaizoláció feladata ugyanezt a fájlt (`engine.py`) érinti: a másodikként készülő feladat a friss `main`-re építsen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Nyitott compliance PR mellett, a default ág elmozdulása után a `fix` ugyanazt a PR-t frissíti: a PR nyitva marad, a száma nem változik, az eredmény `pull request updated`
- [ ] #2 A compliance ág a futás után pontosan egy commit a default ág csúcsán, a szabályok módosításaival, és a commit továbbra is a `commit_files` (aláírt GraphQL commit) útján készül
- [ ] #3 Sikeres futás után nem marad `<branch>-staging` ág; egy korábbi megszakadt futásból maradt staging ág mellett a futás sikeres
- [ ] #4 Ha a commit vagy az ág áthelyezése hibázik, a staging ág törlődik, és a repó `error` eredményt kap az eredeti hibaüzenettel
- [ ] #5 A `FakeGitHub` lezárja a nyitott PR-t, ha a head ága a default ág csúcsára kerül, és ezt a viselkedést teszt rögzíti
- [ ] #6 A README megemlíti az újraépítéshez használt átmeneti staging ágat
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
