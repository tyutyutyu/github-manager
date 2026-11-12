---
id: TASK-27
title: MIT licenc hozzáadása a repóhoz
status: To Do
assignee: []
created_date: '2026-11-12T12:33:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - pyproject.toml
  - README.md
priority: low
type: chore
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `tyutyutyu/github-manager` repó publikus, de nincs `LICENSE` fájlja: a `gh repo view --json licenseInfo` értéke `null`, és a `pyproject.toml` `[project]` táblájában sincs licencmező. Licenc nélkül a kód jogilag „minden jog fenntartva", vagyis más nem használhatja fel, pedig a közös Renovate presetet (`renovate/default.json`) és a szabályokat a repó nyilvánosan közzéteszi.

Döntés (2026-11-12, tulajdonos): MIT licenc.

Adatok: a szerzői jog jogosultja a `pyproject.toml` `authors` mezője szerint „Földházi István"; az első commit éve 2026.

Forrás: docs/project-review-2026-11-12.md, 5.3.

## Objective
A repó MIT licenc alatt áll: a licenc fájlként, a csomag metaadataiban és a README-ben is megjelenik.

## Scope
### In scope
- `LICENSE` fájl a repó gyökerében.
- Licenc-metaadat a `pyproject.toml`-ban.
- Rövid „License" szakasz a README végén.

### Out of scope
- Licencfejlécek a forrásfájlokban.
- A kezelt repók licencének ellenőrzése vagy szabályba foglalása.
- Harmadik féltől származó csomagok licenceinek áttekintése.

## Implementation plan
1. `LICENSE` a repó gyökerében: az MIT licenc szabványos szövege (SPDX: `MIT`), a szerzői jogi sor: `Copyright (c) 2026 Földházi István`.
2. `pyproject.toml`, `[project]`: `license = "MIT"` és `license-files = ["LICENSE"]` (PEP 639). Ha a `uv_build` backend ezt a formát nem fogadja el, a dokumentációja szerinti formát kell használni, és ezt a feladat jegyzetében jelezni.
3. `README.md` végére `## License` szakasz egy mondattal és hivatkozással a `LICENSE` fájlra.

## Verification
- `uv run ruff format -q . && task verify` — a build is sikeres.
- `unzip -p dist/*.whl '*/METADATA' | grep -i '^License'` — a kimenet tartalmazza a `License-Expression: MIT` sort és a licencfájl hivatkozását.
- Merge után: `gh repo view tyutyutyu/github-manager --json licenseInfo` — a GitHub MIT licencet ismer fel.

## Dependencies and risks
- Nincs előfeltétel.
- A licenc a közzététel után a korábbi commitokra is értelmezhető felhasználási jogot ad; ez a döntés szándékolt következménye.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A repó gyökerében `LICENSE` fájl van az MIT licenc szabványos szövegével és a `Copyright (c) 2026 Földházi István` sorral
- [ ] #2 A `pyproject.toml` licenc-metaadatot tartalmaz, és az elkészült wheel `METADATA` fájljában megjelenik a `License-Expression: MIT`, a csomag pedig tartalmazza a licencfájlt
- [ ] #3 A README végén „License" szakasz hivatkozik a `LICENSE` fájlra
- [ ] #4 Merge után a GitHub a repó licenceként az MIT-t ismeri fel
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
