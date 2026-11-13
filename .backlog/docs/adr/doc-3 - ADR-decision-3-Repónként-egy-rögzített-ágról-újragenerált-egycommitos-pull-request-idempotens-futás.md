---
id: doc-3
title: >-
  ADR decision-3: Repónként egy, rögzített ágról újragenerált, egycommitos pull
  request; idempotens futás
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-3 (accepted).

## Context
A program sok repót igazít a központi szabályokhoz, és rendszeresen fut. Az ismételt futás nem halmozhat fel PR-okat vagy commitokat, és nem írhat felül szükségtelenül egy már helyes ágat.

## Decision
Repónként egyetlen pull request van, a konfigurált rögzített ágról (`config.branch`). Ha az ág pontosan egy commit az alapág fölött, és pontosan a kívánt változásokat tartalmazza (`_branch_matches`), csak a PR címe és törzse frissül (`PR_UP_TO_DATE`). Különben az ág minden futáskor egyetlen új commitként újraépül az alapág tetején (`_rebuild_branch`): a commit egy ideiglenes `<branch>-staging` ágon (`STAGING_SUFFIX`) készül, majd a PR-ág egy lépésben erre áll át, és a staging ág mindig törlődik. Ha nincs változás, a nyitott PR bezárul és az ág törlődik (`PR_CLOSED`).

## Consequences
- A futás idempotens: változatlan állapotban nem keletkezik új commit.
- A PR-ág kézi commitjai a következő futáskor elvesznek.
- A staging ág miatt a PR feje egy pillanatra sem egyezik az alappal, így a GitHub nem zárja be a PR-t.

## Sources
- `src/github_manager/engine.py` — `_sync_pull_request`, `_rebuild_branch`, `_branch_matches`, `STAGING_SUFFIX`.
- `README.md` — bevezető.
