---
id: TASK-23
title: A tests/test_rules.py szétbontása a rules/ csomag moduljai szerint
status: Done
assignee: []
created_date: '2026-11-12T12:33:00Z'
updated_date: '2026-11-13T19:01:00Z'
labels: []
dependencies:
  - TASK-22
references:
  - docs/project-review-2026-11-12.md
  - tests/test_rules.py
  - tests/conftest.py
priority: low
type: chore
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `tests/test_rules.py` 1822 sor, és a szabálytípusok tesztjeit kommentsorral elválasztott szakaszokban tartalmazza: `required_lines`, `renovate_preset`, `file_sync`, `branch_strategy`, `repo_settings`, `repo_ruleset`, `repo_ruleset: required_workflow_check`, `repo_visibility`, `required_files`, `default_branch_push_only`, `self_hosted_runners`, `self_hosted_runners: rewriting`. A fájl elején közös segédek vannak (pl. `PRESET`, `required_lines()`, `renovate()`).

A szabályok forrása ekkorra a `src/github_manager/rules/` csomagban van (`base.py`, `files.py`, `renovate.py`, `settings.py`, `ruleset.py`, `workflows.py`). A tesztfájl ugyanúgy nő minden új szabálytípussal, mint korábban a `rules.py`.

A közös fixture-ök (`make_workspace`, `fake_github`, `with_server_defaults`) a `tests/conftest.py`-ban vannak, és minden tesztfájlból elérhetők. A pytest `--import-mode=importlib` móddal fut (`pyproject.toml`).

Forrás: docs/project-review-2026-11-12.md, 5.1.

## Objective
A szabálytesztek a forrásmodulokat tükröző, 800 sornál rövidebb fájlokban vannak, a tesztek tartalmának és számának változása nélkül.

## Scope
### In scope
- A `tests/test_rules.py` felosztása: `tests/test_rules_files.py`, `tests/test_rules_renovate.py`, `tests/test_rules_settings.py`, `tests/test_rules_ruleset.py`, `tests/test_rules_workflows.py`.
- A fájl eleji segédek áthelyezése oda, ahol használják őket.

### Out of scope
- Tesztek hozzáadása, törlése, átnevezése vagy átírása.
- A `src/` bármely fájljának módosítása.
- A `tests/test_engine.py` és a többi tesztfájl bontása.

## Implementation plan
1. A bontás előtt rögzíteni a tesztek számát: `uv run pytest --collect-only -q --no-cov | tail -1`.
2. Szakaszok elosztása:
   - `test_rules_files.py`: `required_lines`, `file_sync`, `required_files`;
   - `test_rules_renovate.py`: `renovate_preset`;
   - `test_rules_settings.py`: `branch_strategy`, `repo_settings`, `repo_visibility`;
   - `test_rules_ruleset.py`: `repo_ruleset`, `repo_ruleset: required_workflow_check`;
   - `test_rules_workflows.py`: `default_branch_push_only`, `self_hosted_runners`, `self_hosted_runners: rewriting`.
3. Minden segédfüggvény és konstans abba a fájlba kerül, amelyik használja. Ha egy segédet több fájl használ, fixture-ként a `tests/conftest.py`-ba kerül; tesztfájlok egymásból nem importálnak.
4. A `tests/test_rules.py` törlése. Az importok maradjanak `from github_manager.rules import ...` formában.
5. Ha valamelyik új fájl meghaladná a 800 sort, a `self_hosted_runners` szakaszok külön fájlba kerülnek (`tests/test_rules_self_hosted_runners.py`).

## Verification
- `uv run pytest --collect-only -q --no-cov | tail -1` — a tesztek száma megegyezik a bontás előttivel.
- `git diff --stat main -- src` — üres.
- `wc -l tests/test_rules_*.py` — egyik fájl sem hosszabb 800 sornál.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld, a lefedettség változatlan.

## Dependencies and risks
- Előfeltétel a `rules.py` csomaggá bontása: a tesztfájlok annak moduljait tükrözik.
- Kockázat: áthelyezés közben kimaradó teszt; ezt a tesztszám előtte–utána összevetése fogja meg.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `tests/test_rules.py` megszűnt; a tesztjei a `tests/test_rules_*.py` fájlokban vannak, a `rules/` csomag moduljai szerint
- [x] #2 A tesztek száma (paraméterezett esetekkel együtt) megegyezik a bontás előttivel, a tesztfüggvények neve és törzse változatlan
- [x] #3 Egyik új tesztfájl sem hosszabb 800 sornál, és tesztfájl nem importál másik tesztfájlból
- [x] #4 A `src/` könyvtár nem módosult, a lefedettség nem csökkent
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-23-a-tests-test-rules-py-szetbontasa-a-rules-csomag.

Verified: rule tests 339 before and after split (whole suite 502); AST comparison of all 154 top-level definitions shows identical bodies; no cross-imports between test files; git diff main -- src empty; max file 714 lines (test_rules_workflows.py); coverage unchanged at 99.42%. The SONAR string constant is duplicated in test_rules_files.py and test_rules_workflows.py instead of becoming a conftest fixture, because a fixture would change test signatures/bodies (AC #2).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Split tests/test_rules.py (1822 lines) into test_rules_files.py, test_rules_renovate.py, test_rules_settings.py, test_rules_ruleset.py and test_rules_workflows.py, mirroring the rules/ package modules. Test names, bodies and count (339) are unchanged; ruff format and task verify pass with coverage unchanged (99.42%). Note: the SONAR path constant is duplicated in two files to keep test bodies untouched.
<!-- SECTION:FINAL_SUMMARY:END -->
