---
id: doc-6
title: >-
  ADR decision-6: Auto-merge csak ott, ahol a kezelt ruleset megköveteli a
  verify checket
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-6 (accepted).

## Context
A compliance PR automatikus merge-e csak akkor biztonságos, ha egy kötelező check előbb igazolja, hogy a változás nem töri el a repót.

## Decision
Az auto-merge (squash) csak akkor kapcsolódik be, ha egy, a repóra vonatkozó `RepoRuleset` szabály `required_workflow_check` értéke `verify` (`VERIFY_CHECK`), egy workflow biztosan futtatja ezt a checket a PR-okon, és a szabálynak nincs nem javítható találata (`_verify_required`). Különben a riport `VERIFY_NOT_REQUIRED`. Ha a GitHub azért utasítja el, mert a PR azonnal merge-elhető (`CLEAN_STATUS`), a program azonnal merge-el.

## Consequences
- `verify` nélküli repókban a PR emberi merge-re vár.
- Az auto-merge hibája csak szövegként jelenik meg, a repó feldolgozását nem állítja meg.

## Sources
- `src/github_manager/engine.py` — `VERIFY_CHECK`, `_verify_required`, `_auto_merge`, `CLEAN_STATUS`, `VERIFY_NOT_REQUIRED`.
- `src/github_manager/rules/ruleset.py` — `RepoRuleset.required_workflow_check`, `requires_workflow_check`.
- Feladatok: TASK-10, TASK-11.
