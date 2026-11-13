---
id: doc-2
title: 'ADR decision-2: A szabályok csak a Workspace protokollon át olvasnak és írnak'
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-2 (accepted).

## Context
A szabályoknak ugyanúgy kell működniük ellenőrzéskor (`check`) és javításkor (`fix`), és tesztelhetőnek kell lenniük GitHub-hívások nélkül.

## Decision
A szabályok soha nem hívják közvetlenül a GitHubot: minden olvasás és írás a `Workspace` protokollon át megy. Éles futásban a `RemoteWorkspace` valósítja meg, amely a változásokat gyűjti. `check` alatt a változások eldobódnak; `fix` alatt a fájlváltozások pull requestbe kerülnek, a beállítás- és ruleset-változások közvetlenül a repóra.

## Consequences
- Ugyanaz a szabálykód szolgálja a `check`-et és a `fix`-et; a riport diffjei a gyűjtött írásokból készülnek.
- Új képességhez (pl. új beállítástípus) előbb a `Workspace` protokollt kell bővíteni.
- A szabályok a GitHub nélkül, saját workspace-szel tesztelhetők.

## Sources
- `src/github_manager/rules/__init__.py` — modul-docstring.
- `src/github_manager/rules/base.py` — `Workspace`, `Rule.apply`.
- `src/github_manager/engine.py` — `RemoteWorkspace`, `_evaluate`, `_fix` (`changes`, `setting_changes`, `ruleset_changes`).
