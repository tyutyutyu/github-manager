---
id: TASK-19
title: 'Közös Renovate preset: minimumReleaseAge (3 nap) minden frissítésre'
status: Done
assignee: []
created_date: '2026-11-12T12:16:00Z'
updated_date: '2026-11-13T00:13:00Z'
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
- [x] #1 A `renovate/default.json` minden csomagra `minimumReleaseAge = "3 days"` értéket állít be, `description` mezővel
- [x] #2 A meglévő `packageRules` elemek (automerge, Python minor, Kotlin csoport) tartalma változatlan
- [x] #3 A `renovate-config-validator` hiba nélkül elfogadja a presetet
- [x] #4 A README megemlíti a várakozási időt
- [x] #5 A feladat jegyzete rögzíti, mit mond a Renovate dokumentációja az időbélyeg nélküli datasource-okról és a biztonsági frissítésekről
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-19-kozos-renovate-preset-minimumreleaseage-3-nap-mi.

Renovate documentation check (configuration-options.md#minimumreleaseage, key-concepts/minimum-release-age.md, lib/config/options/index.ts; Renovate 44.236.5):
- (a) Option name and format: `minimumReleaseAge` (formerly `stabilityDays`), a time-duration string such as `"3 days"`; allowed in `packageRules`. Unchanged from the plan. Until the age is reached, the `renovate/stability-days` status check stays pending; with the default `internalChecksFilter=strict` no branch is created and the update appears under "Pending Status Checks" on the Dependency Dashboard. With automerge, the PR is merged only after the age has passed.
- (b) Datasources/update types without a release timestamp: governed by `minimumReleaseAgeBehaviour`, whose default since Renovate 42 is `timestamp-required`, meaning such updates are held back indefinitely. Affected: `pin` updates (not yet supported, renovatebot/renovate#40288; this preset uses `rangeStrategy=pin`), `lockFileMaintenance`, `replacement`, `bump`/`lockfileUpdate`/`rollback`, and digest updates from registries without timestamps (GHCR, Quay, ECR, `latest` tags).
- (c) Security updates: vulnerability-alert updates bypass `minimumReleaseAge` and are raised immediately (`vulnerabilityAlerts` minimumReleaseAge is null by default).

Deviation from the plan: because of (b), holding back these updates indefinitely would be a lasting block. Restricting by datasource, as the task suggests, would not fix it, because the gap depends on the update type (for example `pin` on npm or pypi). The rule therefore keeps `matchPackageNames: ["*"]` and adds the documented `minimumReleaseAgeBehaviour: "timestamp-optional"`. Updates that have a timestamp wait 3 days. Updates without one are raised without an age check, and Renovate shows a warning about them on the Dependency Dashboard.

Verification: `python3 -m json.tool renovate/default.json` OK; `npx --yes --package renovate -- renovate-config-validator renovate/default.json` (global and `--no-global` repo mode) "Config validated successfully" with Node v26.13.1; `uv run ruff format -q --check .` OK. Per the workflow instruction, `task verify` was not run here (it runs at fixed gates).

Finalization check (2026-11-13): `python3 -m json.tool renovate/default.json` OK; `renovate-config-validator renovate/default.json` rerun with Node v26.13.1: "Config validated successfully"; `uv run ruff format -q --check .` OK; workflow `task verify` exited 0 (491 tests passed, 99.41% coverage). The diff removes no lines from renovate/default.json. The post-merge Dependency Dashboard check is not automatable; the user checks it after the workflow.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added a first `packageRules` entry to the shared Renovate preset (`renovate/default.json`): `matchPackageNames: ["*"]`, `minimumReleaseAge: "3 days"`, plus `minimumReleaseAgeBehaviour: "timestamp-optional"`. Every update with a release timestamp now waits 3 days before Renovate proposes or automerges it, as supply-chain protection for the automerged minor/patch/pin/digest updates. The README intro mentions the wait.

Deviation from the plan: Renovate 42+ defaults to `timestamp-required`, which would hold back updates without a timestamp (including `pin`, which this preset uses via `rangeStrategy: pin`, `lockFileMaintenance`, `replacement`) indefinitely. Narrowing by datasource would not fix that, so the documented `timestamp-optional` behaviour is used instead. Security (vulnerability-alert) updates bypass the wait. Existing rules are unchanged.

Verification: JSON valid, `renovate-config-validator` passes, `ruff format` and `task verify` green.

Risks/follow-up: every repo extending the preset gets updates 3 days later; updates without timestamps are raised without the age check. Manual check after merge: newer-than-3-days releases appear as pending on the Dependency Dashboard.
<!-- SECTION:FINAL_SUMMARY:END -->
