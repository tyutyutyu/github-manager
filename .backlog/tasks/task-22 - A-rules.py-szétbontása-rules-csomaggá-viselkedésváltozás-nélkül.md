---
id: TASK-22
title: A rules.py szétbontása rules/ csomaggá (viselkedésváltozás nélkül)
status: Done
assignee: []
created_date: '2026-11-12T12:32:00Z'
updated_date: '2026-11-13T18:32:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
  - src/github_manager/config.py
  - src/github_manager/engine.py
priority: medium
type: chore
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `src/github_manager/rules.py` 1336 sor (a projekt 800 soros lágy felső határa fölött), és egy fájlban tartalmazza:
- az alapokat: `Workspace` protokoll, `Finding`, `REQUIRED`, `Options`, `Rule`;
- mind a 10 szabálytípust (`RequiredLines`, `RenovatePreset`, `FileSync`, `BranchStrategy`, `RepoSettings`, `RepoRuleset`, `RepoVisibility`, `RequiredFiles`, `DefaultBranchPushOnly`, `SelfHostedRunners`) a konstansaikkal;
- a workflow-YAML elemzést (`_workflow_check_problem`, `_file_problem`, `_check_job_problem`, `_pull_request_trigger`, `_filter_problem`, `_branch_listed`, `_push_only_problem`, `_push_filter_problem`, `_shown`) és a YAML-segédeket (`_patterns`, `_mapping`, `_entry`, `_jobs`, `_labels`, `_json`, `_text`);
- a `RULE_TYPES` regisztert.

Minden új szabálytípus ezt a fájlt növeli (az első hónapban 17 `feat` commit).

Kívülről ezeket a neveket importálják a `github_manager.rules`-ból:
- `src/github_manager/config.py`: `REQUIRED`, `RULE_TYPES`, `Options`, `RepoVisibility`, `Rule`;
- `src/github_manager/engine.py`: `Finding`, `RepoRuleset`, `ruleset_matches`;
- `tests/test_rules.py`, `tests/test_engine.py`, `tests/test_config.py`: `NOT_READABLE`, `RULE_TYPES`, `Finding`, `ruleset_matches` és a 10 szabályosztály.

Forrás: docs/project-review-2026-11-12.md, 5.1.

## Objective
A szabályok egy `src/github_manager/rules/` csomagban, tématerületenkénti modulokban élnek, a viselkedés és a publikus import-útvonal változása nélkül.

## Scope
### In scope
- A `rules.py` tartalmának áthelyezése a csomag moduljaiba, az importok igazítása.
- `rules/__init__.py`, amely újraexportálja a kívülről használt neveket.

### Out of scope
- Bármilyen viselkedés-, név-, hibaüzenet- vagy szignatúraváltozás.
- Duplikációk megszüntetése (pl. `_labels` és `_patterns`), átnevezés, egyszerűsítés.
- A `tests/` könyvtár bármely fájljának módosítása (a tesztfájl bontása külön feladat).
- A `config.py`, `engine.py` import-sorainak megváltoztatása (maradhat `from github_manager.rules import ...`).

## Implementation plan
1. A `src/github_manager/rules.py` törlése, helyette `src/github_manager/rules/` csomag:
   - `base.py`: `Workspace`, `Finding`, `REQUIRED`, `Options`, `Rule`, `NOT_READABLE` (három szabály is használja);
   - `files.py`: `RequiredLines`, `FileSync`, `RequiredFiles`;
   - `renovate.py`: `RENOVATE_CONFIG_FILES`, `RENOVATE_SCHEMA`, `RenovatePreset`, `_rewrite_extends`, `_render_array`;
   - `settings.py`: `BranchStrategy`, `REPO_BOOL_SETTINGS`, `SECURITY_SETTINGS`, `SECURITY_STATES`, `RepoSettings`, `VISIBILITIES`, `RepoVisibility`;
   - `workflows.py`: a workflow-konstansok (`WORKFLOWS_DIR`, `SELF_HOSTED`, `UBUNTU_PATTERN`, `YAML_STR`, `UNSAFE_REWRITE`, `PULL_REQUEST`, `PULL_REQUEST_TYPES`, `PUSH`, `PUSH_FORBIDDEN_FILTERS`), `_Replacement`, `SelfHostedRunners`, `DefaultBranchPushOnly`, a workflow-check elemzés (`_Problem`, a szakaszkonstansok, `_workflow_check_problem` és társai) és a YAML-segédek;
   - `ruleset.py`: `RULESET_PREFIX`, `RULESETS_UNAVAILABLE`, `RepoRuleset`, `ruleset_matches`; a `_workflow_check_problem`-et a `workflows.py`-ból importálja;
   - `__init__.py`: a modul eredeti docstringje, a `RULE_TYPES` (változatlan sorrenddel és kulcsokkal), és újraexport `__all__`-lal: `Workspace`, `Finding`, `REQUIRED`, `Options`, `Rule`, `NOT_READABLE`, `RULE_TYPES`, `ruleset_matches` és a 10 szabályosztály.
2. A nevek maradjanak változatlanok (az aláhúzással kezdődő segédek is), hogy a diff tiszta áthelyezés legyen. Körkörös import nem keletkezhet: `base` ← többi modul ← `__init__`.
3. Ha a `workflows.py` meghaladná a 800 sort, a workflow-check elemzés és a YAML-segédek külön modulba kerüljenek (pl. `workflow_yaml.py`).
4. A `pyproject.toml` beállításai (`source_pkgs`, `known_first_party`) csomagra is érvényesek; módosítás várhatóan nem kell.

## Verification
- `git diff --stat main -- tests` — üres: a tesztek nem változtak.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld, a lefedettség nem csökken.
- `wc -l src/github_manager/rules/*.py` — egyik modul sem hosszabb 800 sornál.
- `uv run python -c "from github_manager.rules import RULE_TYPES; print(sorted(RULE_TYPES))"` — ugyanaz a 10 típusnév, mint előtte.
- `uv run github-manager repos` — a valódi konfiguráció betölthető (csak olvasó parancs).

## Dependencies and risks
- Nagy, mechanikus diff: akkor érdemes elvégezni, amikor nincs nyitott ág, amely a `rules.py`-t módosítja, különben nehéz rebase következik.
- A változatlan tesztek adják az egyenértékűség bizonyítékát; ezért tilos ebben a feladatban tesztet módosítani.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `src/github_manager/rules.py` megszűnt; helyette a `src/github_manager/rules/` csomag tartalmazza a szabályokat tématerületenkénti modulokban
- [x] #2 A `github_manager.rules`-ból továbbra is importálható: `Workspace`, `Finding`, `REQUIRED`, `Options`, `Rule`, `NOT_READABLE`, `RULE_TYPES`, `ruleset_matches` és a 10 szabályosztály
- [x] #3 A `tests/` könyvtár egyetlen fájlja sem módosult, és minden meglévő teszt zöld
- [x] #4 A csomag egyik modulja sem hosszabb 800 sornál
- [x] #5 Az osztályok, függvények, konstansok és hibaüzenetek tartalma változatlan: a diff csak áthelyezést és import-igazítást tartalmaz
- [x] #6 A `RULE_TYPES` ugyanazt a 10 típusnevet tartalmazza, és a valódi konfiguráció betölthető
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-22-a-rules-py-szetbontasa-rules-csomagga-viselkedes.

Finalization verification (2026-11-13):
- rules.py deleted (staged); package src/github_manager/rules/ with __init__ (50 lines), base (158), files (142), renovate (113), ruleset (199), settings (198), workflows (544). No module over 800 lines, so no separate workflow_yaml.py was needed.
- Import graph: base <- files/renovate/settings/workflows <- ruleset (imports _workflow_check_problem from workflows) <- __init__; no cycles.
- AST comparison against fca5fe4:src/github_manager/rules.py: all 57 top-level definitions and assignments (decorators included) match byte for byte, each exists exactly once; the only addition is __all__ (18 names) in __init__.py. The other differences are per-module imports and module docstrings.
- git diff --stat fca5fe4 -- tests pyproject.toml config.py engine.py: empty.
- ruff format --check and task verify: exit 0 (502 tests passed, total coverage 99%).
- RULE_TYPES: the same 10 type names; uv run github-manager repos exit 0 (32 repositories listed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Split src/github_manager/rules.py (1336 lines) into the src/github_manager/rules/ package with topic modules: base, files, renovate, settings, workflows and ruleset. __init__.py keeps the original docstring and RULE_TYPES (same order), and re-exports the public names through __all__. The goal is to keep every module under the 800-line limit without changing behavior or import paths.

Verification: an AST comparison shows all 57 original top-level definitions moved byte for byte. tests/, config.py, engine.py and pyproject.toml are unchanged. task verify passed (502 tests, 99% coverage). RULE_TYPES has the same 10 types, and github-manager repos loads the real config.

Risk: this is a large move-only diff. Open branches that touch rules.py will need a rebase.
<!-- SECTION:FINAL_SUMMARY:END -->
