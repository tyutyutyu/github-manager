---
id: TASK-8
title: 'Színes, átláthatóbb check/fix kimenet a rich könyvtárral'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 01:20'
updated_date: '2026-10-18 01:23'
labels: []
dependencies: []
documentation:
  - README.md
priority: medium
type: enhancement
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `check` és `fix` kimenete (`_print_report`, `_print_summary` a `src/github_manager/cli.py`-ban) ma sima szöveg: minden repó egy sor (`OWNER/NAME: outcome`), alatta `[fix]`/`[manual]` findingok, a végén egy összesítő. Sok repónál a compliant sorok elnyomják a lényeget, és a findingok, diffek nehezen olvashatók.

A felhasználó döntései (2026-10-18):
- A színezést a `rich` könyvtár végzi (új, pinned függőség).
- Repónként egy fejsor szimbólummal és színnel, alatta behúzva, oszlopokba igazítva a findingok (`fix`/`manual`, szabály-id, üzenet), a végén színes összesítő.
- A compliant repók alapból nem jelennek meg, csak az összesítőben; `-v/--verbose` kapcsolóval láthatók.

Megjegyzések:
- A finding-üzenetek szögletes zárójelet tartalmaznak (pl. `(allowed: [self-hosted])`), ezeket a rich markup nem értelmezheti.
- A GitHub Actions log nem TTY, de megjeleníti az ANSI színeket; a sorok ott se törjenek 80 karakternél.
- A `GITHUB_STEP_SUMMARY` markdown tábla és a kilépési kódok nem változnak.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `rich` pinned függőségként szerepel (`uv add rich==15.0.0`), a deptry és a teljes gate zöld
- [x] #2 Repónként egy fejsor jelenik meg outcome szerinti szimbólummal és színnel; a findingok behúzva, oszlopokba igazítva (`fix`/`manual`, szabály-id, üzenet) következnek
- [x] #3 Compliant repó alapból nem jelenik meg, `-v/--verbose` mellett igen; az összesítő mindig minden outcome-ot megszámol
- [x] #4 A `--diff` kimenetben a hozzáadott és törölt sorok színezettek
- [x] #5 Színek csak terminálon vagy GitHub Actions-ben (`GITHUB_ACTIONS=true`) jelennek meg; `NO_COLOR` kikapcsolja, pipe-ba színtelen a kimenet; a sorok nem törnek
- [x] #6 A szögletes zárójeles finding-üzenetek változatlanul jelennek meg (nincs rich markup értelmezés)
- [x] #7 A hibaüzenetek (`error: ...`) a stderr-re mennek, terminálon pirossal; a kilépési kódok és a step summary nem változnak
- [x] #8 A README leírja az új kimenetet és a `-v` kapcsolót; a CLI tesztek lefedik a rejtést, a verbose módot, a színes és a színtelen kimenetet
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. uv add rich==15.0.0.
2. cli.py: Console(stdout/stderr) gyártó: soft_wrap, highlight=False, markup nélkül Text-tel; force_terminal GITHUB_ACTIONS=true esetén, NO_COLOR-t a rich kezeli.
3. Outcome -> (szimbólum, stílus) tábla; repó fejsor, findingok rich Table.grid-del igazítva; diff +/- sorok színezése; összesítő színes számokkal.
4. -v/--verbose a check és fix parancsra; COMPLIANT csak verbose mellett.
5. error: ... piros a stderr-en.
6. Tesztek átírása + új (rejtés, verbose, FORCE_COLOR ANSI, NO_COLOR, zárójeles üzenet), README.
7. task verify.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Kimenet: OUTCOME_STYLES (cli.py) adja a szimbólumot és a színt outcome-onként, egyben az összesítő sorrendjét. A Console soft_wrap=True, highlight=False; minden kiírás Text objektum, így a rich markup és az emoji-kódok nem értelmeződnek. A GITHUB_ACTIONS=true esetén force_terminal; a NO_COLOR és a FORCE_COLOR kezelését a rich végzi. A tesztekben egy autouse fixture törli a színváltozókat, hogy a CI környezete ne befolyásolja őket. A step summary nem változott.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A check/fix kimenet a rich könyvtárral (rich==15.0.0, pinned) színes és átláthatóbb lett. Repónként egy fejsor jelenik meg outcome-szimbólummal és színnel, alatta behúzva, oszlopokba igazítva a findingok (fix/manual, szabály-id, üzenet). A --diff sorai színezettek, a végén színes összesítő van. A compliant repók alapból rejtve maradnak, -v/--verbose mellett láthatók. Színek terminálon és GitHub Actions-ben jelennek meg; pipe-ba vagy NO_COLOR mellett nem, és a sorok nem törnek. A hibák a stderr-en pirosak. A kilépési kódok és a GITHUB_STEP_SUMMARY tábla változatlanok. README és CLI tesztek frissítve (rejtés, verbose, színes és színtelen kimenet, igazítás, zárójeles üzenet szó szerint). Ellenőrzés: task verify exit 0, 251 teszt, cli.py 100%.
<!-- SECTION:FINAL_SUMMARY:END -->
