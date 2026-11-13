---
id: doc-7
title: >-
  ADR decision-7: Az emberi döntést igénylő szabályok csak jeleznek, nem
  javítanak
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-7 (accepted).

## Context
Egyes eltérések helyes javítása nem vezethető le gépiesen (pl. egy repó láthatósága, egy tiltott ág törlése, egy hiányzó fájl tartalma, egy workflow triggere), és rossz automatikus javítás kárt okozna.

## Decision
Ezek a szabályok `Finding(..., fixable=False)` találatot adnak, és nem írnak a workspace-be: `RepoVisibility` (láthatóság), `BranchStrategy` (ágstratégia), `RequiredFiles` (hiányzó fájlok), `DefaultBranchPushOnly` (workflow-trigger).

## Consequences
- A riport kézi teendőként mutatja ezeket; a PR törzsében nem szerepelnek javításként.
- Kezelt rulesetnél a nem javítható találat az auto-merge-et is kizárja (`_verify_required`).

## Sources
- `src/github_manager/rules/settings.py` — `RepoVisibility`, `BranchStrategy`.
- `src/github_manager/rules/files.py` — `RequiredFiles`.
- `src/github_manager/rules/workflows.py` — `DefaultBranchPushOnly`.
- `src/github_manager/rules/base.py` — `Finding.fixable`.
- Feladatok: TASK-4, TASK-13, TASK-14.
