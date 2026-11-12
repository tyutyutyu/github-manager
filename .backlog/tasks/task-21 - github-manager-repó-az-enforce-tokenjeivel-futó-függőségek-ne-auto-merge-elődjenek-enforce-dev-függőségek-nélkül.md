---
id: TASK-21
title: >-
  github-manager repó: az enforce tokenjeivel futó függőségek ne
  auto-merge-elődjenek; enforce dev-függőségek nélkül
status: To Do
assignee: []
created_date: '2026-11-12T12:16:00Z'
labels: []
dependencies:
  - TASK-16
  - TASK-20
references:
  - docs/project-review-2026-11-12.md
  - renovate.json
  - .github/workflows/enforce.yml
  - .github/workflows/verify.yml
  - pyproject.toml
priority: medium
type: chore
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Az `enforce` job (`.github/workflows/enforce.yml`) a `GH_MANAGER_TOKEN` és a `GH_MANAGER_ORG_TOKEN` titkokkal fut; ezek az adott owner minden repóján Contents, Pull requests, Workflows és Administration írási jogot adnak.

Ami ebben a jobban kódot futtat:
- a futásidejű függőségek (`pyproject.toml`, `[project].dependencies`: `pygithub`, `pyyaml`, `rich`, és a tranzitív csomagjaik);
- a build backend (`[build-system].requires`: `uv_build`);
- az `enforce.yml` action-jei (`actions/checkout`, `astral-sh/setup-uv`);
- a `dev` függőségcsoport (`deptry`, `pytest`, `pytest-cov`, `ruff`, `ty`) is települ, mert a `uv run --locked` az alapértelmezett csoportokat is szinkronizálja.

A repó `renovate.json`-ja csak a közös presetet terjeszti ki, amely a `minor`, `patch`, `pin` és `digest` frissítéseket automatikusan merge-eli. Egy kompromittált kiadás így emberi szem nélkül a `main`-re kerülhet, és a következő `enforce` futás a flotta-tokenekkel futtatja. A kötelező `verify` check a törést megfogja, a rosszindulatú kódot nem.

Forrás: docs/project-review-2026-11-12.md, 2.5.

## Objective
Ami az `enforce` jobban a flotta-tokenekkel fut, az ebben a repóban csak emberi jóváhagyással frissül, és a dev-eszközök nem települnek abba a jobba.

## Scope
### In scope
- `--no-dev` az `enforce.yml` indítóparancsában és a `verify.yml` füsttesztjében.
- `packageRules` a repó gyökerében lévő `renovate.json`-ban: automerge kikapcsolása a GitHub Actions, a `[project].dependencies` és a `[build-system].requires` frissítéseire.
- README-említés.

### Out of scope
- A közös preset (`renovate/default.json`) módosítása (külön feladat).
- A `dev` csoport automerge-e (marad a preset szerint).
- A Python-verzió és a tranzitív csomagok frissítési szabályai.
- Átállás GitHub Appra, a tokenek jogosultságai.

## Implementation plan
1. `.github/workflows/enforce.yml`, „Apply rules" lépés: `uv run --locked github-manager ...` → `uv run --locked --no-dev github-manager ...` (uv 0.12.13: `--no-dev` — „Disable the development dependency group"). A parancs többi része (`--exit-zero` stb.) változatlan.
2. `.github/workflows/verify.yml`, a füsttesztlépés: ugyanazok az uv-opciók, azaz `uv run --locked --no-dev github-manager --help`.
3. `renovate.json` (repó gyökere): az `extends` mellé `packageRules`, a közös preset stílusában `description` mezőkkel:
   - `{"description": "Runs with the fleet tokens in the enforce workflow: merge by hand", "matchManagers": ["github-actions"], "automerge": false}`
   - `{"description": "Runs with the fleet tokens in the enforce workflow: merge by hand", "matchManagers": ["pep621"], "matchDepTypes": ["project.dependencies", "build-system.requires"], "automerge": false}`
   A manager- és depType-neveket ellenőrizni kell a Renovate dokumentációjában (https://docs.renovatebot.com/modules/manager/pep621/ és https://docs.renovatebot.com/modules/manager/github-actions/); eltérés esetén a dokumentált neveket kell használni, és ezt a jegyzetben jelezni. Az `extends` tömb nem változhat: a `renovate-preset` szabály azt kezeli.
4. `README.md`, „Scheduled run" vagy „Tokens" szakasz: egy-két mondat arról, hogy az `enforce` dev-függőségek nélkül fut, és a futásidejű függőségek, a build backend és az action-ök frissítése kézi merge-et igényel.

## Verification
- `python3 -m json.tool renovate.json > /dev/null` — érvényes JSON.
- `npx --yes --package renovate -- renovate-config-validator renovate.json` — hiba nélkül elfogadja.
- `d="$(mktemp -d)"; UV_PROJECT_ENVIRONMENT="$d" uv run --locked --no-dev github-manager --help` — exit 0, kiírja a használati szöveget.
- `UV_PROJECT_ENVIRONMENT="$d" uv run --locked --no-dev python -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('pytest') is not None)"` — exit 0: a `pytest` nincs telepítve.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- Merge után (kézi): a következő, futásidejű függőséget vagy action-t érintő Renovate PR-on nincs bekapcsolva az auto-merge; egy `dev` csoportbeli PR-on be van.

## Dependencies and risks
- Előfeltétel az enforce telepítési hibájának javítása és az `--exit-zero` feladat: mindkettő ugyanazt az indítósort módosítja az `enforce.yml`-ben, illetve a füsttesztet a `verify.yml`-ben.
- Több kézi merge ebben a repóban; ez a szándékolt ár.
- Ha a Renovate a `pep621` managernél más depType-neveket használ, a szabály csendben nem illeszkedne: ezért kötelező a dokumentáció ellenőrzése és a merge utáni kézi ellenőrzés.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Az `enforce.yml` indítóparancsa és a `verify.yml` füsttesztje egyaránt `uv run --locked --no-dev`-et használ
- [ ] #2 A `--no-dev` környezetben a program elindul, és a `dev` csoport csomagjai (pl. `pytest`) nincsenek telepítve
- [ ] #3 A repó `renovate.json`-ja kikapcsolja az automerge-et a GitHub Actions frissítésekre, valamint a `[project].dependencies` és a `[build-system].requires` függőségeire
- [ ] #4 A `dev` csoport frissítéseire nem vonatkozik új szabály (továbbra is a közös preset szerint auto-merge-elődnek)
- [ ] #5 A `renovate.json` `extends` tömbje változatlan, és a `renovate-config-validator` hiba nélkül elfogadja a fájlt
- [ ] #6 A README leírja, hogy az `enforce` dev-függőségek nélkül fut, és mely frissítések igényelnek kézi merge-et
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
