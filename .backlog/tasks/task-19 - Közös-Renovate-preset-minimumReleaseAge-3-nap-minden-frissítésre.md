---
id: TASK-19
title: 'Közös Renovate preset: minimumReleaseAge (3 nap) minden frissítésre'
status: To Do
assignee: []
created_date: '2026-11-12T12:16:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - renovate/default.json
  - https://docs.renovatebot.com/configuration-options/#minimumreleaseage
priority: medium
type: chore
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `renovate/default.json` a közös Renovate preset: a `renovate-preset` szabály (`github-manager.toml`) minden kezelt repóban megköveteli, hogy a Renovate-konfiguráció ezt terjessze ki (`local>tyutyutyu/github-manager//renovate/default`).

A preset „Automerge non-major updates" szabálya a `minor`, `patch`, `pin` és `digest` frissítéseket automatikusan merge-eli, várakozási idő nélkül. Egy kompromittált csomag- vagy action-kiadás így órákon belül, emberi szem nélkül bekerülhet a repók default ágára. A meglévő védelem (pontos pinelés, lockfájl, kötelező `verify`) a törést megfogja, a rosszindulatú kódot nem.

Döntés: a várakozási idő 3 nap.

Forrás: docs/project-review-2026-11-12.md, 2.5.

## Objective
A közös preset minden frissítésnél legalább 3 napot vár a kiadás megjelenése után, mielőtt a Renovate javasolná vagy merge-elné.

## Scope
### In scope
- Új `packageRules` elem a `renovate/default.json`-ban.
- A Renovate dokumentációjának ellenőrzése az opció viselkedéséről, az eredmény rögzítése a feladat jegyzetében.
- README-említés.

### Out of scope
- Az egyes repók saját Renovate-konfigurációja, köztük ennek a repónak a `renovate.json`-ja (külön feladat).
- A meglévő automerge-, Python- és Kotlin-szabályok módosítása.
- A `github-manager.toml` és a Python-kód.

## Implementation plan
1. A https://docs.renovatebot.com/configuration-options/#minimumreleaseage oldalon (és az onnan hivatkozott leíráson) ellenőrizni: (a) az opció neve és értékformátuma a jelenlegi Renovate-verzióban; (b) mi történik olyan datasource-nál, amely nem ad kiadási időbélyeget; (c) vonatkozik-e a biztonsági (vulnerability) frissítésekre. Az eredményt a feladat jegyzetébe írni. Ha az opció neve vagy viselkedése eltér, a dokumentált formát kell használni, és ezt jelezni.
2. `renovate/default.json`: a `packageRules` tömb ELEJÉRE (hogy a későbbi szabályok felülírhassák) új elem, a fájl meglévő stílusában `description` mezővel:
   `{"description": "Wait before proposing a new release (supply chain protection)", "matchPackageNames": ["*"], "minimumReleaseAge": "3 days"}`.
3. `README.md`: a bevezető felsorolás első pontjánál (közös Renovate preset) egy tagmondat a 3 napos várakozásról.

## Verification
- `python3 -m json.tool renovate/default.json > /dev/null` — érvényes JSON.
- `npx --yes --package renovate -- renovate-config-validator renovate/default.json` — a validátor hiba nélkül elfogadja. Ha a helyi Node-verzióval nem futtatható, ezt a jegyzetben rögzíteni kell.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- Merge után (kézi): a repó Dependency Dashboard issue-jában a 3 napnál frissebb kiadások várakozóként jelennek meg.

## Dependencies and risks
- A változás a következő Renovate-futástól minden repóra hat, amely a presetet kiterjeszti: a frissítések 3 nappal később érkeznek.
- Időbélyeg nélküli datasource-oknál a viselkedés a dokumentáció szerint alakul (1. lépés); ha ez frissítések tartós visszatartását jelentené, a szabályt az érintett datasource-okra szűkíteni kell, és ezt jelezni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `renovate/default.json` minden csomagra `minimumReleaseAge = "3 days"` értéket állít be, `description` mezővel
- [ ] #2 A meglévő `packageRules` elemek (automerge, Python minor, Kotlin csoport) tartalma változatlan
- [ ] #3 A `renovate-config-validator` hiba nélkül elfogadja a presetet
- [ ] #4 A README megemlíti a várakozási időt
- [ ] #5 A feladat jegyzete rögzíti, mit mond a Renovate dokumentációja az időbélyeg nélküli datasource-okról és a biztonsági frissítésekről
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
