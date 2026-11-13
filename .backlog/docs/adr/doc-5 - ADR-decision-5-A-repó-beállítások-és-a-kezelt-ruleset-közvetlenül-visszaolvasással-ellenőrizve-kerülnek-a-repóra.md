---
id: doc-5
title: >-
  ADR decision-5: A repó-beállítások és a kezelt ruleset közvetlenül,
  visszaolvasással ellenőrizve kerülnek a repóra
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-5 (accepted).

## Context
A repó-beállítások és a rulesetek nem fájlok, ezért pull requesttel nem módosíthatók. A ruleset írásánál a GitHub csendben eltérhet a kérttől, és a repóban lehetnek más, kézzel kezelt rulesetek.

## Decision
`fix` alatt a beállítás-változások (`update_repo_settings`) és a ruleset-változások (`_apply_ruleset`) közvetlenül a repóra kerülnek, nem PR-ral. A ruleset írása után a program visszaolvassa és összeveti a kérttel (`ruleset_matches`); eltérésnél hibát ad, újrapróbálás nélkül. Csak a `github-manager: <rule id>` nevű (`RULESET_PREFIX`) ruleset a kezelt; a többi rulesethez a program nem nyúl.

## Consequences
- A beállítások azonnal érvényesek, review nélkül.
- A kézzel kezelt rulesetek érintetlenek maradnak.
- Sikertelen ruleset-írás a repó hibájaként jelenik meg.

## Sources
- `src/github_manager/engine.py` — `_fix`, `_apply_ruleset`.
- `src/github_manager/rules/ruleset.py` — `RepoRuleset`, `RULESET_PREFIX`, `ruleset_matches`.
- Feladat: TASK-2.
