---
id: TASK-42
title: >-
  GitHub App: az enforce workflow átállítása és a README „Tokens” szakaszának
  átírása
status: To Do
assignee: []
created_date: '2026-11-14T09:18:00Z'
labels:
  - github-app
dependencies:
  - TASK-41
references:
  - doc-9
  - decision-9
  - .github/workflows/enforce.yml
  - README.md
type: enhancement
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Az `enforce` workflow ownerenként hosszú életű személyes tokennel fut (`GH_MANAGER_TOKEN`, `GH_MANAGER_ORG_TOKEN`). A TASK-38 ADR (doc-9) szerint egy publikus App két telepítéssel (`tyutyutyu`, `tyutyutyu-org`) állítson ki rövid életű telepítési tokent minden futásban. A workflow és a README „Tokens” szakasza a PAT-eket az App-pal váltja fel; a PAT secretek a kivezetésig (külön feladat) megmaradnak a visszaálláshoz.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A workflow minden owner-jobban az `actions/create-github-app-token` action-nel állít ki tokent (a doc-9-ben rögzített SHA-ra pinelve, `client-id`, `private-key` és `owner` bemenettel), és a `GH_TOKEN` a lépés `token` kimenetéből jön
- [ ] #2 A mátrix owner-enként már nem hivatkozik külön secretre; az App kulcsa és azonosítója konfigurációként van megadva
- [ ] #3 A README „Tokens” szakasza az App jogosultságait, a telepítést, a secretet és a visszaállás módját írja le
- [ ] #4 Egy kézi `workflow_dispatch` futás (check mód) mindkét ownerre sikeres; ezt a felhasználó ellenőrzi a workflow után
<!-- AC:END -->
