---
id: TASK-43
title: 'GitHub App: a személyes tokenek (PAT) kivezetése'
status: To Do
assignee: []
created_date: '2026-11-14T09:18:00Z'
labels:
  - github-app
dependencies:
  - TASK-42
references:
  - doc-9
  - decision-9
  - README.md
type: chore
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Az App-os `enforce` futás bizonyított sikere után a két hosszú életű token (`GH_MANAGER_TOKEN`, `GH_MANAGER_ORG_TOKEN`) már nem kell. A TASK-38 ADR (doc-9) szerint a secretek az App-os futás igazolt sikeréig megmaradnak a visszaálláshoz; a tokenek visszavonása a tulajdonos kézi lépése.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Az App-os enforce futás legalább egy ütemezett ciklusban mindkét ownerre sikeres volt (a felhasználó ellenőrzi), mielőtt a secretek törlődnek
- [ ] #2 A két PAT secret törölve van a repóból, és a workflow vagy a README nem hivatkozik rájuk
- [ ] #3 A README visszaállási leírása a kivezetés utáni állapotot tükrözi (új PAT kiállítása, ha szükséges)
- [ ] #4 A tokenek visszavonásának lépése a felhasználónak szóló jegyzetben szerepel; az ágens nem vonja vissza őket
<!-- AC:END -->
