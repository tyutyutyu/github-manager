---
id: TASK-33
title: >-
  A szabályok alaptípusainak szigorítása: Finding.kind enum és kötelező
  alapérték az Options segédekben
status: Done
assignee: []
created_date: '2026-11-12T23:54:00Z'
updated_date: '2026-11-13T22:50:00Z'
labels: []
dependencies:
  - TASK-22
  - TASK-23
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
  - src/github_manager/engine.py
  - src/github_manager/cli.py
priority: low
type: chore
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
**1. `Finding`.** A `Finding` (`github_manager.rules`; a csomaggá bontás után `src/github_manager/rules/base.py`) két logikai mezővel kódol három állapotot:
- `fixable=True, setting=False`: a compliance PR javítja (fájlmódosítás);
- `fixable=True, setting=True`: közvetlenül a repón alkalmazott beállítás vagy ruleset;
- `fixable=False`: kézi teendő.

A negyedik kombináció (`fixable=False, setting=True`) értelmetlen, de megadható. A szabályokban 21 helyen szerepel `fixable=False`, és 4 helyen `setting=True` (`RepoSettings.apply`, `RepoSettings._apply_security`, `RepoRuleset._sync` kétszer). Az olvasó helyek:
- `src/github_manager/cli.py`, `_print_report`: `finding.fixable` → `fix` / `manual` jelölő;
- `src/github_manager/engine.py`: `RepoReport.manual_findings` (`not finding.fixable`); `_verify_required` (`not finding.fixable`); `_sync_pull_request` (`not finding.setting` → a commit üzenet sorai; ide a kézi leletek is beletartoznak); `_pr_body` (`finding.fixable and not finding.setting` → „Fixed"; `finding.setting` → „Repository settings").

A tesztek közül a szabálytesztek (`tests/test_rules_*.py`) és a `tests/test_engine.py` hivatkozik ezekre a mezőkre (összesen kb. 55 hely).

**2. `Options`.** A `text_list`, `text_block`, `text_lists` és `table` segéd paramétere `default: Any = None`, de `None` alapértékkel hiányzó kulcsnál elszállnak (kipróbálva: `Options({}).text_list("k")` → `TypeError: 'NoneType' object is not iterable`). Ma minden hívó ad alapértéket (`REQUIRED`, `[]`, `{}`), így a hiba rejtve marad. A `text` segédnél a `None` alapérték érvényes („nincs megadva"); a `RepoRuleset` használja.

Forrás: docs/project-review-2026-11-12.md, 4.3 (4. és 7. sor).

## Objective
A szabályok alaptípusai nem engednek meg értelmetlen állapotot: a lelet fajtáját egyetlen enum hordozza, és az `Options` lista-, blokk- és táblaolvasói nem hívhatók alapérték nélkül.

## Scope
### In scope
- `FindingKind` enum; a `Finding` mezőinek cseréje; minden létrehozó és olvasó hely átállítása a forrásban és a tesztekben.
- A négy `Options` segéd `default` paramétere kötelező.
- A `FindingKind` újraexportja a `github_manager.rules`-ból.

### Out of scope
- A kimenet (CLI-sorok, PR-törzs, commit üzenet, job summary) bármely változása.
- A leletek üzenetei és a szabályok logikája; új leletfajta bevezetése.
- A `RepoReport` átalakítása.

## Implementation plan
1. `src/github_manager/rules/base.py`: `class FindingKind(StrEnum)` három taggal, mindegyik fölött egysoros kommenttel: `PULL_REQUEST = "pull request"` (a compliance PR javítja), `DIRECT = "direct"` (beállítás vagy ruleset, közvetlenül alkalmazva), `MANUAL = "manual"` (kézi teendő). A `Finding` mezői: `rule_id: str`, `message: str`, `kind: FindingKind = FindingKind.PULL_REQUEST`. A `fixable` és a `setting` mező megszűnik; kompatibilitási property nem készül (egy igazságforrás).
2. A létrehozó helyek: `fixable=False` → `kind=FindingKind.MANUAL`; `setting=True` → `kind=FindingKind.DIRECT`; az alapérték marad a PR-ral javított lelet.
3. Az olvasó helyek, viselkedésváltozás nélkül:
   - `finding.fixable` → `finding.kind is not FindingKind.MANUAL`;
   - `not finding.fixable` → `finding.kind is FindingKind.MANUAL`;
   - `finding.setting` → `finding.kind is FindingKind.DIRECT`;
   - `not finding.setting` → `finding.kind is not FindingKind.DIRECT`;
   - `finding.fixable and not finding.setting` → `finding.kind is FindingKind.PULL_REQUEST`.
4. `src/github_manager/rules/__init__.py`: a `FindingKind` felvétele az újraexportok és az `__all__` közé.
5. `Options`: a `text_list`, a `text_block`, a `text_lists` és a `table` szignatúrájában a `default` paraméter alapérték nélküli (`default: Any`); a `text` változatlan. Minden meglévő hívó már ad alapértéket; ezt a `ty check` és a tesztek igazolják.
6. Tesztek: a `Finding(...)` konstrukciók és a `.fixable` / `.setting` állítások átírása a `kind`-ra (`tests/test_rules_*.py`, `tests/test_engine.py`); a tesztek szándéka nem változik. Új teszt: a `Finding` alapértelmezett fajtája `FindingKind.PULL_REQUEST`.
7. Ha az `AGENTS.md` a háromféle leletet a `Finding.fixable` / `Finding.setting` mezőkkel írja le, a leírást a `FindingKind`-ra kell igazítani.

## Verification
- `grep -rn "fixable" src tests` — nincs találat.
- `grep -rn "setting=True\|finding\.setting" src tests` — nincs találat (a `workspace.setting(...)` és a `change_setting(...)` hívások maradnak).
- `uv run pytest --collect-only -q --no-cov | tail -1` a változtatás előtt és után — a tesztek száma nem csökkent.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- `NO_COLOR=1 uv run github-manager check -r github-manager` a változtatás előtt és után — csak olvasó; a két kimenet megegyezik.

## Dependencies and risks
- Előfeltétel a `rules.py` és a `tests/test_rules.py` szétbontása: a feladat sok sort érint ugyanazokban a fájlokban, és a tiszta áthelyezést nem szabad viselkedést érintő átírással keverni.
- Az `engine.py`-t más nyitott feladatok is módosítják (PR-frissítés, hibaizoláció, `RepoReport`); az olvasó helyeket szimbólum szerint kell megkeresni, nem sorszám alapján.
- Kockázat: elírt megfeleltetés a PR-törzs szakaszaiban vagy a commit üzenetben; ezt a meglévő motor- és CLI-tesztek fogják meg.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `Finding` fajtáját egyetlen `kind: FindingKind` mező hordozza (`PULL_REQUEST`, `DIRECT`, `MANUAL`); a `fixable` és a `setting` mező megszűnt, és a `src/` és a `tests/` nem hivatkozik rájuk
- [x] #2 A `FindingKind` importálható a `github_manager.rules`-ból
- [x] #3 A CLI kimenete, a PR törzse, a commit üzenet és a job summary ugyanazokra a leletekre megegyezik a változtatás előttivel
- [x] #4 Az `Options.text_list`, `text_block`, `text_lists` és `table` nem hívható `default` nélkül; az `Options.text` továbbra is elfogadja a `None` alapértéket
- [x] #5 A tesztek száma nem csökkent, és a valódi konfiguráció betölthető
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-33-a-szabalyok-alaptipusainak-szigoritasa-finding-k.

Véglegesítés ellenőrzése (2026-11-13):
- grep -rn fixable src tests és grep setting=True/finding.setting: nincs találat.
- 21 helyen kind=FindingKind.MANUAL, 4 helyen kind=FindingKind.DIRECT (settings.py 2, ruleset.py 2).
- Tesztszám: 614 (bázis b9bdf27) -> 620 (új tests/test_rules_base.py 6 esettel); csak 4 tesztnév változott, eset nem törlődött.
- NO_COLOR=1 github-manager check -r github-manager a bázis-kódon (git archive másolat) és a változtatás után: azonos kimenet (1 repositories, 1 compliant), mindkettő exit 0; csak olvasó futás.
- Options({}).text_list('k') -> TypeError: missing required argument 'default'; Options({}).text('key') -> None.
- uv run ruff format -q . && task verify: exit 0, 619 passed / 1 skipped, lefedettség 99.45%, ruff/ty/deptry/audit/build zöld.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A Finding két logikai mezője (fixable, setting) helyett egyetlen kind: FindingKind (StrEnum: PULL_REQUEST, DIRECT, MANUAL; alapérték PULL_REQUEST) hordozza a lelet fajtáját, így az értelmetlen fixable=False, setting=True kombináció már nem adható meg. Minden létrehozó hely (21 MANUAL, 4 DIRECT) és olvasó hely (cli._print_report, RepoReport.manual_findings, _verify_required, _sync_pull_request, _pr_body) viselkedésváltozás nélkül átállt; a FindingKind a github_manager.rules-ból is exportálva van. Az Options.text_list, text_block, text_lists és table default paramétere kötelező, a text változatlanul None alapértékű. Az AGENTS.md leletleírása a FindingKind-ra frissült; új tests/test_rules_base.py teszteli az alapértelmezett fajtát és az Options szignatúrákat.

Ellenőrzés: a régi mezőkre nincs hivatkozás a src/ és tests/ alatt; tesztszám 614 -> 620; a valódi konfiguráció betöltési tesztje zöld; a csak olvasó check -r github-manager kimenete a változtatás előtt és után azonos; uv run ruff format -q . && task verify zöld (619 passed, 1 skipped, 99.45%).

Kockázat: a live összevetés megfelelő repón nem mutat leletet, így a PR-törzs és commit üzenet egyezését a meglévő motor- és CLI-tesztek, valamint a predikátumok kódszintű ekvivalenciája igazolja.
<!-- SECTION:FINAL_SUMMARY:END -->
