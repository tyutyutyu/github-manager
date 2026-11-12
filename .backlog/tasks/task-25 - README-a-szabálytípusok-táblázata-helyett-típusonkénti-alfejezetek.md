---
id: TASK-25
title: 'README: a szabálytípusok táblázata helyett típusonkénti alfejezetek'
status: To Do
assignee: []
created_date: '2026-11-12T12:33:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - README.md
priority: low
type: docs
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `README.md` „Rule types" szakasza egy háromoszlopos táblázat (Type / Checks / Fix) 10 sorral. Több cella egész bekezdés (különösen a `required_lines`, `repo_ruleset`, `repo_settings` és `self_hosted_runners` sora), ami nehezen olvasható, nehezen szerkeszthető, és a diffekben egyetlen hosszú sorként jelenik meg. A táblázat után további, típusokhoz tartozó bekezdések állnak: a „Not fixed automatically" felsorolás, a `repo_ruleset` megjegyzései és a `required_workflow_check` részletei.

A leírás tartalmilag pontos és teljes; a gond a forma.

Forrás: docs/project-review-2026-11-12.md, 5.3.

## Objective
A README minden szabálytípust saját, egységes szerkezetű alfejezetben ír le, tartalomvesztés nélkül.

## Scope
### In scope
- A „Rule types" szakasz átszerkesztése: rövid áttekintő táblázat + 10 alfejezet.
- A táblázat utáni, típushoz tartozó bekezdések beolvasztása a megfelelő alfejezetbe.

### Out of scope
- A README többi szakasza (Usage, Auto-merge, Scheduled run, Tokens, Development).
- Bármilyen kód-, konfiguráció- vagy viselkedésváltozás.
- Új tartalom kitalálása: csak az kerülhet be, ami a kódból igazolható.

## Implementation plan
1. A „Rule types" elejére rövid áttekintő táblázat: típus, egymondatos cél, érvényesítés módja (`pull request` / `applied directly` / `report only`), a típus neve az alfejezetre mutató horgony.
2. Típusonként `### \`<type>\`` alfejezet, mindegyik ugyanazzal a szerkezettel:
   - **Checks** — mit ellenőriz;
   - **Options** — táblázat: kulcs, típus, kötelező-e, alapérték, jelentés;
   - **Fix** — mit ír, vagy hogy csak jelez;
   - **Reported as manual** — mely eseteket nem javít.
3. Az opciókat a szabályosztályok `_build` metódusaiból kell ellenőrizni (a `rules` modulban), a közös `id` és `exclude` kulcsot a szakasz elején egyszer leírni.
4. A „Not fixed automatically" felsorolás, a `repo_ruleset` megjegyzései (nincs bypass actor; a check-neveknek jelenteniük kell) és a `required_workflow_check` statikus elemzésének leírása a megfelelő alfejezetbe kerül; a jelenlegi szöveg minden állítása megmarad.
5. Nyelv: angol, a README többi részével egyezően. A belső hivatkozások (pl. `#tokens`) működjenek.

## Verification
- `grep -c '^### `' README.md` — legalább 10 (típusonként egy alfejezet).
- Kézi összevetés: `git diff main -- README.md` alapján a régi táblázat minden sorának minden állítása megtalálható az új szövegben.
- Kézi ellenőrzés: minden `_build` metódusban olvasott opció szerepel a típus Options táblázatában.
- `uv run ruff format -q . && task verify` — a minőségkapuk zöldek (a README a csomag `readme` mezője, a build olvassa).

## Dependencies and risks
- Több nyitott feladat módosítja a README más részeit, a PyGithub megszüntetése pedig a `repo_settings` leírását: ütközés esetén a friss `main`-re kell építeni, és az ott már módosított szöveget kell átszerkeszteni.
- Kockázat a csendes tartalomvesztés; ezt a kézi összevetés fogja meg.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A „Rule types" szakasz rövid áttekintő táblázattal kezdődik (típus, cél, érvényesítés módja), és mind a 10 szabálytípusnak saját alfejezete van
- [ ] #2 Minden alfejezet ugyanazt a szerkezetet követi: Checks, Options (kulcs, típus, kötelező, alapérték), Fix, Reported as manual
- [ ] #3 A korábbi táblázat és az utána álló, típushoz tartozó bekezdések minden állítása megtalálható az új szövegben
- [ ] #4 Minden opció, amelyet a szabályok `_build` metódusai olvasnak, szerepel a megfelelő Options táblázatban, és a README nem említ nem létező opciót
- [ ] #5 A README többi szakasza változatlan, a belső hivatkozások működnek
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
