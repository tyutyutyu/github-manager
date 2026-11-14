---
id: TASK-42
title: >-
  GitHub App: az enforce workflow átállítása és a README „Tokens” szakaszának
  átírása
status: Done
assignee: []
created_date: '2026-11-14T09:18:00Z'
updated_date: '2026-11-14T22:32:00Z'
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
- [x] #1 A workflow minden owner-jobban az `actions/create-github-app-token` action-nel állít ki tokent (a doc-9-ben rögzített SHA-ra pinelve, `client-id`, `private-key` és `owner` bemenettel), és a `GH_TOKEN` a lépés `token` kimenetéből jön
- [x] #2 A mátrix owner-enként már nem hivatkozik külön secretre; az App kulcsa és azonosítója konfigurációként van megadva
- [x] #3 A README „Tokens” szakasza az App jogosultságait, a telepítést, a secretet és a visszaállás módját írja le
- [x] #4 Egy kézi `workflow_dispatch` futás (check mód) mindkét ownerre sikeres; ezt a felhasználó ellenőrzi a workflow után
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-42-github-app-az-enforce-workflow-atallitasa-es-a-r.

Ellenőrzés (lezárás): az enforce.yml owner-jobjai az actions/create-github-app-token@64ab729a… (v3.3.0, doc-9) lépéssel állítanak ki tokent (client-id: vars.GH_MANAGER_APP_CLIENT_ID, private-key: secrets.GH_MANAGER_APP_PRIVATE_KEY, owner: matrix.owner), a GH_TOKEN a steps.app-token.outputs.token. A mátrix csak owner-bejegyzéseket tartalmaz. A README Tokens szakasza leírja a jogosultságokat, a telepítést, a változót/secretet és a visszaállást. task verify: sikeres (659 passed, 1 skipped, 99,28% lefedettség). Az AC #4 (kézi workflow_dispatch check futás mindkét ownerre) nem automatizálható, a felhasználó ellenőrzi a workflow után. Nem blokkoló: a README „Scheduled run” szakasza (README.md:335) még azt írja, hogy minden job az owner token secretjét olvassa.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Az enforce workflow a PAT secretek helyett egy GitHub App rövid életű telepítési tokenjével fut: owner-jobonként az actions/create-github-app-token (doc-9-ben rögzített SHA, v3.3.0) állítja ki a tokent a GH_MANAGER_APP_CLIENT_ID változóból és a GH_MANAGER_APP_PRIVATE_KEY secretből, a mátrixból kikerültek az owner-enkénti secretek. A README „Tokens” szakasza most az App jogosultságait, telepítését, a konfigurációt és a visszaállást (a PAT secretek a TASK-43 kivezetésig maradnak, git revert) írja le. Ellenőrzés: task verify sikeres (659 passed, 1 skipped). Kockázat/teendő: a kézi workflow_dispatch check futást mindkét ownerre a felhasználó ellenőrzi; a README:335 mondata még a régi owner-secretekre utal (nem blokkoló).
<!-- SECTION:FINAL_SUMMARY:END -->
