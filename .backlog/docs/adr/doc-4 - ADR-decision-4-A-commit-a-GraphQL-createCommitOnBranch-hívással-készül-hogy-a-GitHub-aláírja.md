---
id: doc-4
title: >-
  ADR decision-4: A commit a GraphQL createCommitOnBranch hívással készül, hogy
  a GitHub aláírja
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-4 (accepted).

## Context
A kezelt repók rulesetjei és a felhasználók elvárhatják az aláírt commitokat; a REST git-adatbázis API-val készült commitot a GitHub nem írja alá.

## Decision
A fájlváltozások commitja a GraphQL `createCommitOnBranch` mutációval készül (`GitHub.commit_files`), így a GitHub aláírja és ellenőrzöttként jelöli.

## Consequences
- A mutáció létező ágat igényel, ezért a commit az ideiglenes staging ágon készül (`_rebuild_branch`).
- A commit a várt fej-SHA-hoz kötött (`expectedHeadOid`), így párhuzamos módosításnál hibával áll le.

## Sources
- `src/github_manager/github.py` — `GitHub.commit_files`, a `createCommitOnBranch` mutáció.
- `src/github_manager/engine.py` — `GitHubApi.commit_files`, `_rebuild_branch`.
