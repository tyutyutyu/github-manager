---
id: doc-1
title: 'ADR decision-1: Repository settings on the own REST client'
type: other
created_date: '2026-11-13T19:04:00Z'
updated_date: '2026-11-13T19:04:00Z'
---
# ADR decision-1: Repository settings on the own REST client

Decision: decision-1 (accepted, 2026-11-12, owner). Task: TASK-24.

## Context
The `GitHub` client reached everything through its standard-library transport except
`repo_settings` and `update_repo_settings`, which used PyGithub (added in 86ada10). PyGithub
brought most of the runtime dependency tree for two calls, had different error handling,
timeout and retry behaviour, and issued an extra `GET` before every settings write.

## Decision
Read settings with `GET /repos/{owner}/{repo}` and write them with one
`PATCH /repos/{owner}/{repo}` (the settings dict unchanged as body) on the own transport.
Remove the PyGithub dependency.

## Consequences
- Runtime dependencies shrink to `pyyaml` and `rich`.
- Settings errors use the transport format and keep `GitHubError.status`.
- PyGithub built-in retries are gone; these calls behave like every other client call.
