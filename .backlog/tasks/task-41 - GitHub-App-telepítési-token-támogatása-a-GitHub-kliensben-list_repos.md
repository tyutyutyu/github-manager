---
id: TASK-41
title: 'GitHub App: telepítési token támogatása a GitHub kliensben (list_repos)'
status: Done
assignee: []
created_date: '2026-11-14T09:18:00Z'
updated_date: '2026-11-14T16:43:00Z'
labels:
  - github-app
dependencies:
  - TASK-40
references:
  - doc-9
  - decision-9
  - src/github_manager/github.py
type: enhancement
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A `GitHub.list_repos` a `GET /user` hívással állapítja meg a bejelentkezett felhasználót, majd `GET /user/repos`-t vagy `GET /orgs/{owner}/repos`-t hív; ezek a felhasználói végpontok telepítési tokennel nem használhatók. A TASK-38 ADR (doc-9) szerint a repólistázás telepítési tokennel `GET /installation/repositories` legyen. A helyi futtatás (`resolve_token`: `GH_TOKEN` / `GITHUB_TOKEN` / `gh`) változatlan, a telepítési token `GH_TOKEN`-ként adható.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Telepítési token esetén a list_repos a lapozott `GET /installation/repositories` végpontot használja, `GET /user` nélkül, és a privát és archivált repókat is a `Repo` mezőivel adja vissza
- [x] #2 Személyes tokennel és `gh` CLI-vel a mostani viselkedés változatlan
- [x] #3 A token fajtájának felismerése dokumentált, és a FakeGitHub a GitHub megfigyelt viselkedését követi; a tesztek lefedik mindkét ágat
- [x] #4 A verifikáció (`uv run ruff format -q . && task verify`) zöld
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-41-github-app-telepitesi-token-tamogatasa-a-github.

Token kind detection: the ghs_ prefix (INSTALLATION_TOKEN_PREFIX) marks an installation token; list_repos then pages GET /installation/repositories (wrapped page, paginate key="repositories") and filters to the owner by full_name, no GET /user. Other tokens keep the /user + /user/repos or /orgs/{owner}/repos path. FakeGitHub.list_repos is token-independent and already matches the owner-filtered installation listing, so it needed no change. Verification: uv run ruff format -q . && task verify green (659 passed, 1 skipped sandbox test, coverage 99.28%); targeted list_repos/resolve_token/pagination tests rerun: 6 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GitHub.list_repos now supports GitHub App installation tokens: a token with the ghs_ prefix lists repositories through the paginated GET /installation/repositories endpoint (filtered to the owner, case-insensitive, archived and private repos included, no GET /user call), as decided in the TASK-38 ADR (doc-9). Personal tokens and the gh CLI keep the previous GET /user + /user/repos or /orgs/{owner}/repos behaviour; resolve_token is unchanged, so an installation token can be passed as GH_TOKEN. paginate gained an optional key for wrapped pages. The detection is documented in the README Tokens section and next to INSTALLATION_TOKEN_PREFIX. Tests: new two-page installation test plus the unchanged user/org tests; task verify green (659 passed, 1 skipped, 99.28% coverage). Follow-ups already tracked: TASK-42 (enforce workflow, README Tokens rewrite), TASK-43 (PAT removal).
<!-- SECTION:FINAL_SUMMARY:END -->
