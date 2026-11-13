---
id: TASK-29
title: >-
  AGENTS.md: architektúra-áttekintés, új szabálytípus hozzáadása és
  tesztkonvenciók
status: Done
assignee: []
created_date: '2026-11-12T12:33:00Z'
updated_date: '2026-11-13T21:30:00Z'
labels: []
dependencies:
  - TASK-22
  - TASK-23
  - TASK-24
references:
  - docs/project-review-2026-11-12.md
  - AGENTS.md
  - CLAUDE.md
  - tests/conftest.py
priority: low
type: docs
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Az `AGENTS.md` ma csak a Backlog.md által kezelt blokkot tartalmazza (a `<!-- BACKLOG.MD GUIDELINES START -->` és a `<!-- BACKLOG.MD GUIDELINES END -->` jelölő között); a `CLAUDE.md` egyetlen sora `@AGENTS.md`. A projekt szabályairól szóló helyi skill (`.claude/skills/github-manager-rules`) nem volt verziózva, és 2026-11-12-én törlődött. Így nincs verziózott, ágenseknek és új fejlesztőknek szóló leírás:
- az architektúráról (melyik modul miért felel);
- arról, hogyan kell új szabálytípust hozzáadni (ma a lezárt TASK-13 és TASK-14 tervéből lehet kikövetkeztetni);
- a projekt konvencióiról, amelyek eddig csak beszélgetésekben és lezárt feladatokban rögzültek.

Forrás: docs/project-review-2026-11-12.md, 5.3 és 5.4.

## Objective
Az `AGENTS.md` a Backlog-blokk mellett tömören leírja az architektúrát, az új szabálytípus hozzáadásának lépéseit és a projekt teszt- és munkakonvencióit.

## Scope
### In scope
- Új szakaszok az `AGENTS.md`-ben, a Backlog-blokk után.

### Out of scope
- A Backlog-blokk bármilyen módosítása (a Backlog.md kezeli).
- A `CLAUDE.md`, a README és a kód módosítása.
- Új konvenciók bevezetése: csak a már érvényeseket kell leírni.

## Implementation plan
1. Az új tartalom a `<!-- BACKLOG.MD GUIDELINES END -->` sor UTÁN kerüljön, angolul (az ágensfájlok nyelve), legfeljebb kb. 100 sorban.
2. `## Architecture`: a modulok és a felelősségük a tényleges fájlszerkezet szerint (`cli`, `config`, `engine`, a `rules` csomag moduljai, `github`); az adatfolyam (`cli.main` → `load_config` → `select_repos` → `process_repo` → `Rule.apply` a `Workspace`-en → PR / beállítás / ruleset); a `check` és a `fix` különbsége; a háromféle lelet (`Finding.fixable`, `Finding.setting`): PR-ral javított, közvetlenül alkalmazott, kézi.
3. `## Adding a rule type`: lépéslista a meglévő minta szerint: `frozen`, `kw_only` dataclass `type_name`-mel a megfelelő `rules` modulban; `_build` az `Options`-szel (ismeretlen kulcs hiba); `apply` csak a `Workspace`-en át; felvétel a `RULE_TYPES`-ba; tesztek `MemoryWorkspace`-szel a megfelelő `tests/test_rules_*.py` fájlban és egy motor-teszt `FakeGitHub`-bal a `tests/test_engine.py`-ban; README alfejezet; a `github-manager.toml`-ba új szabály csak a tulajdonos kérésére kerül.
4. `## Conventions`:
   - a valódi `github-manager.toml` tartalmára nincs teszt, legfeljebb betöltési teszt (TASK-12);
   - a fake-ek a GitHub megfigyelt viselkedését követik: ha az éles viselkedés eltér, a fake-et kell igazítani regressziós teszttel (példa: a default ág csúcsára állított head ág lezárja a nyitott PR-t);
   - fejlesztés közben a kezelt repókba írni tilos; csak olvasó `gh` lekérdezés megengedett;
   - ellenőrző parancs: `uv run ruff format -q . && task verify`;
   - nyelv: kód, kommentek, README és ágensfájlok angolul; a Backlog feladatok magyarul.
5. Ha a Backlogban már vannak ADR-ek (`backlog decision list --plain`), egy sor mutasson rájuk; ha nincsenek, ez a sor maradjon ki.
6. Minden megnevezett fájlt és szimbólumot ellenőrizni kell a jelenlegi kódban.

## Verification
- `git diff main -- AGENTS.md` — csak hozzáadott sorok vannak, mind a `<!-- BACKLOG.MD GUIDELINES END -->` sor után.
- `git diff --stat main -- CLAUDE.md README.md src tests` — üres.
- Kézi ellenőrzés: az `AGENTS.md`-ben megnevezett minden útvonal létezik (`ls`), minden szimbólum megtalálható (`grep -rn "<szimbólum>" src tests`).
- `uv run ruff format -q . && task verify` — a minőségkapuk zöldek.

## Dependencies and risks
- Előfeltétel a `rules.py` csomaggá bontása, a `test_rules.py` szétbontása és a PyGithub megszüntetése: az útmutató a végleges fájlszerkezetet és a végleges klienst írja le.
- Kockázat: az útmutató elavul, ha a szerkezet változik; ezért tömör legyen, és a részletekért a kódra mutasson.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Az `AGENTS.md` Backlog-blokkja bájtra változatlan; az új tartalom a `<!-- BACKLOG.MD GUIDELINES END -->` sor után áll, angolul
- [x] #2 Van „Architecture" szakasz, amely a tényleges modulokat, az adatfolyamot, a `check` és `fix` különbségét és a háromféle leletet írja le
- [x] #3 Van „Adding a rule type" szakasz, amelynek lépései alapján egy új szabálytípus a kód, a regiszter, a tesztek és a README szintjén hozzáadható
- [x] #4 Van „Conventions" szakasz a leírásban felsorolt öt konvencióval
- [x] #5 Az `AGENTS.md`-ben megnevezett minden fájl és szimbólum létezik a jelenlegi kódban, és a `CLAUDE.md`, a README és a kód nem módosult
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-29-agents-md-architektura-attekintes-uj-szabalytipu.

Finalization check (2026-11-13): AGENTS.md lines 1-24 byte-identical to HEAD (cmp); git diff adds 41 lines after line 24 only. All named paths exist (ls) and all symbols found with grep in src/tests (cli.main, load_config, select_repos, process_repo, RemoteWorkspace, GitHub, Workspace, Finding, Options, Rule, RULE_TYPES, MemoryWorkspace, FakeGitHub). git diff --stat 32644530 -- CLAUDE.md README.md src tests is empty. ADR pointer kept because backlog decision list shows decision-1..8. Note: the HEAD Backlog block has no GUIDELINES START marker, only the END marker; the block was left untouched. task verify: exit 0, 502 passed, 1 skipped (sandbox), coverage 99.42%.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
AGENTS.md now has three English sections after the Backlog block (left unchanged): Architecture (modules, data flow cli.main -> load_config -> select_repos -> process_repo -> Rule.apply, check vs fix, the three Finding kinds, pointer to Backlog decisions), Adding a rule type (7 steps: frozen kw_only dataclass with type_name, _build via Options, apply via Workspace, RULE_TYPES registration, MemoryWorkspace/FakeGitHub tests, README subsection, config only on owner request) and Conventions (the five existing conventions). Why: the deleted local skill left no versioned guide for agents and new developers. Verification: every named file and symbol checked with ls/grep; CLAUDE.md, README, src and tests unchanged; ruff format and task verify green (502 passed, 1 skipped, 99.42% coverage). Risk: the guide goes stale when the structure changes; it stays short and points to the code.
<!-- SECTION:FINAL_SUMMARY:END -->
