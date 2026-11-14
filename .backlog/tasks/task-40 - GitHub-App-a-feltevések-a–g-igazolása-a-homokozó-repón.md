---
id: TASK-40
title: 'GitHub App: a feltevések (a–g) igazolása a homokozó repón'
status: To Do
assignee: []
created_date: '2026-11-14T09:17:00Z'
labels:
  - github-app
dependencies:
  - TASK-38
references:
  - doc-9
  - decision-9
  - tests/test_integration_github.py
type: chore
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A TASK-38 ADR (decision-9, doc-9) az átállást elfogadta, de a hét feltevést (a–g) a spike alatt nem lehetett kipróbálni, mert a kísérleti App és a homokozó elérése nem állt rendelkezésre. Az átállás kódja és workflow-ja csak az igazolás után készülhet, mert egy cáfolt feltevés (például hogy az App-tokennel nyitott PR nem indítja a verify checket) megváltoztatná a felépítést. A tulajdonosnak előbb létre kell hoznia a kísérleti Appot (Contents, Pull requests, Administration, Workflows: read/write; Metadata: read), és kizárólag a homokozó repóra kell telepítenie; az azonosító és a privát kulcs a repón kívül marad.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Minden feltevéshez (a–g) rögzítve van a futtatott parancs és a megfigyelt eredmény, titok nélkül
- [ ] #2 Az eredmények a doc-9 ADR-ben vannak, és ahol egy feltevés megdőlt, az ADR döntése (decision-9) frissítve vagy visszavonva van
- [ ] #3 A homokozóban nem maradt nyitott PR, kísérleti ág vagy ruleset; a beállítások vissza vannak állítva
<!-- AC:END -->
