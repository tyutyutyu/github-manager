---
id: TASK-41
title: 'GitHub App: telepítési token támogatása a GitHub kliensben (list_repos)'
status: To Do
assignee: []
created_date: '2026-11-14T09:18:00Z'
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
- [ ] #1 Telepítési token esetén a list_repos a lapozott `GET /installation/repositories` végpontot használja, `GET /user` nélkül, és a privát és archivált repókat is a `Repo` mezőivel adja vissza
- [ ] #2 Személyes tokennel és `gh` CLI-vel a mostani viselkedés változatlan
- [ ] #3 A token fajtájának felismerése dokumentált, és a FakeGitHub a GitHub megfigyelt viselkedését követi; a tesztek lefedik mindkét ágat
- [ ] #4 A verifikáció (`uv run ruff format -q . && task verify`) zöld
<!-- AC:END -->
