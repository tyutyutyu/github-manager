---
id: TASK-27
title: MIT licenc hozzáadása a repóhoz
status: Done
assignee: []
created_date: '2026-11-12T12:33:00Z'
updated_date: '2026-11-13T20:41:00Z'
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
- [x] #1 A repó gyökerében `LICENSE` fájl van az MIT licenc szabványos szövegével és a `Copyright (c) 2026 Földházi István` sorral
- [x] #2 A `pyproject.toml` licenc-metaadatot tartalmaz, és az elkészült wheel `METADATA` fájljában megjelenik a `License-Expression: MIT`, a csomag pedig tartalmazza a licencfájlt
- [x] #3 A README végén „License" szakasz hivatkozik a `LICENSE` fájlra
- [x] #4 Merge után a GitHub a repó licenceként az MIT-t ismeri fel
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-27-mit-licenc-hozzaadasa-a-repohoz.

Finalization check (2026-11-13): uv_build accepted the PEP 639 form (license = "MIT", license-files = ["LICENSE"]), so no fallback form was needed. The rebuilt wheel METADATA contains 'License-Expression: MIT' and 'License-File: LICENSE'. The wheel ships github_manager-0.1.0.dist-info/licenses/LICENSE and the sdist ships LICENSE. 'uv run ruff format -q . && task verify' exited 0. AC #4 (GitHub detecting the license after merge) cannot be automated; the user checks it after the workflow with 'gh repo view tyutyutyu/github-manager --json licenseInfo'.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the MIT license to the repository. There is a new root LICENSE file with the standard MIT text and the line 'Copyright (c) 2026 Földházi István'. pyproject.toml now has license = "MIT" and license-files = ["LICENSE"] (PEP 639), and README.md ends with a '## License' section that links to LICENSE. Verification: 'uv run ruff format -q . && task verify' passed (ruff, ty, deptry, 502 tests with 99.42% coverage, uv audit, build). The wheel METADATA contains License-Expression: MIT and License-File: LICENSE, and both the wheel and the sdist include the license file. Follow-up: after merge, run 'gh repo view tyutyutyu/github-manager --json licenseInfo' to confirm GitHub detects MIT.
<!-- SECTION:FINAL_SUMMARY:END -->
