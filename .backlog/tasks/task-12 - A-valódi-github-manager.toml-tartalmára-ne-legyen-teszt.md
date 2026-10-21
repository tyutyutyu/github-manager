---
id: TASK-12
title: A valódi github-manager.toml tartalmára ne legyen teszt
status: Done
assignee:
  - '@claude'
created_date: '2026-10-21T19:14:00Z'
updated_date: '2026-10-21T20:32:00Z'
labels: []
dependencies: []
modified_files:
  - tests/test_config.py
priority: medium
type: chore
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `tests/test_config.py` `test_repository_config_file_is_valid` tesztje betölti a valódi `github-manager.toml`-t, és tételesen ellenőrzi a tartalmát: a szabálytípusok sorrendjét, a `gitignore-baseline` `lines`/`remove_lines` listáját, a `repo-settings` `settings` és `security_and_analysis` dictjét, a `default-branch-ruleset` checkjeit, a `repo-visibility` táblát és a `self_hosted_runners` `allowed_runs_on`/`runs_on` listáit. A config fájl folyamatosan változik (pl. a `.gitignore` blokk sorai), ezért minden config-módosítás teszt-módosítást is kényszerít, és a teszt egy élő fájl pillanatképét védi, nem viselkedést. Döntés (felhasználó, 2026-10-21): a folyamatosan változó config fájl tartalmára ne legyen teszt.

A projekt-skill (`.claude/skills/github-manager-rules/SKILL.md`) több helyen előírja ezeknek az assertáknak a karbantartását (a „repo_visibility rule” szakaszban a rule-order assertion, a „self_hosted_runners rule” szakaszban a `tests/test_config.py` assertions, a „Verification” szakaszban az „Only `test_repository_config_file_is_valid` loads the real `github-manager.toml`…” pont).

## Objective
A valódi `github-manager.toml` tartalmára vonatkozó tesztellenőrzések megszűnnek; legfeljebb az marad, hogy a fájl hibátlanul betölthető (érvényes config).

## Scope
### In scope
- `test_repository_config_file_is_valid`: csak a `load_config(...)` sikeres lefutása marad (és ha szükséges, hogy legalább egy szabály van), minden tartalmi assert törlődik; a feleslegessé vált importok törlése.
- A skill három érintett pontjának átírása: a valódi config tartalmára nem írunk assertet; config-változás nem igényel tesztmódosítást.

### Out of scope
- A `parse_config` viselkedését szintetikus inputtal tesztelő tesztek (`test_defaults_apply`, `test_invalid_config_is_rejected` stb.) maradnak.
- A `github-manager.toml` tartalmának módosítása.

## Implementation plan
1. `tests/test_config.py`: a `test_repository_config_file_is_valid` törzsét cseréld egy betöltésre (pl. `config = load_config(...)`, `assert config.rules`); töröld a már nem használt importokat (`uv run ruff check --fix .`).
2. `.claude/skills/github-manager-rules/SKILL.md`: a fenti három pontból vedd ki a `tests/test_config.py` assertekre vonatkozó előírásokat; a Verification szakaszba kerüljön: „The real `github-manager.toml` is only loaded in a test, its content is never asserted.” (a fájl gitignore-olt; a handoffban jelezni).
3. `uv run ruff format -q . && task verify`.

## Verification
- `uv run ruff format -q . && task verify` — sikeres; a `github-manager.toml` bármely értékének (pl. a `.gitignore` blokk egy sorának) megváltoztatása után a tesztek továbbra is zöldek.

## Dependencies and risks
- A config hibás értékeit továbbra is a betöltéskori validáció fogja meg; a teszt ezt a betöltést futtatja.
- A párhuzamos taskok (TASK-9, TASK-10, TASK-11) nem adnak hozzá assertet a valódi config tartalmára.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test_repository_config_file_is_valid csak a valódi config betöltését ellenőrzi, tartalmi assert nélkül
- [x] #2 A github-manager.toml egy értékének megváltoztatása nem tör el tesztet
- [x] #3 A github-manager-rules skill nem írja elő a valódi config tartalmára vonatkozó assertek karbantartását
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . és task verify sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. tests/test_config.py: test_repository_config_file_is_valid csak load_config + assert config.rules; felesleges importok törlése (ruff --fix).
2. .claude/skills/github-manager-rules/SKILL.md (gitignore-olt, lokális): a három érintett pontból kivenni a test_config assertek karbantartását; Verification: 'The real github-manager.toml is only loaded in a test, its content is never asserted.'
3. uv run ruff format -q . && task verify; ellenőrzés módosított toml-lal.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
test_repository_config_file_is_valid törzse: load_config(...) + assert config.rules; a rules.py importok törölve (ruff --fix). Ellenőrzés: a toml '.DS_Store' sorát '.DS_Store_probe'-ra írva 'uv run pytest -q tests/test_config.py' -> 26 passed, majd visszaállítva. A skill (.claude/skills/github-manager-rules/SKILL.md, gitignore-olt: .gitignore:271 .claude/) három pontja átírva; 'test_config' már csak a 72. sorban, a Verification pontban szerepel ('The real github-manager.toml is only loaded in a test, its content is never asserted...'). uv run ruff format -q . -> fmt=0; task verify -> verify=0 (322 passed, 99.25% coverage, audit tiszta).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A test_repository_config_file_is_valid már csak azt ellenőrzi, hogy a valódi github-manager.toml betölthető és van benne szabály; a tartalmi assertek és a feleslegessé vált importok törölve, így config-változás nem igényel tesztmódosítást. A github-manager-rules skill (gitignore-olt, lokális fájl, nem része a diffnek) három pontja átírva: a valódi config tartalmára nem írunk assertet. Ellenőrzés ebben a sessionben: ruff format fmt=0, task verify verify=0 (322 passed); módosított toml-lal tests/test_config.py 26 passed.
<!-- SECTION:FINAL_SUMMARY:END -->
