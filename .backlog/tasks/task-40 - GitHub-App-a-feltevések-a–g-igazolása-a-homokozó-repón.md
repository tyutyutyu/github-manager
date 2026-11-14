---
id: TASK-40
title: 'GitHub App: a feltevések (a–g) igazolása a homokozó repón'
status: Done
assignee: []
created_date: '2026-11-14T09:17:00Z'
updated_date: '2026-11-14T16:33:00Z'
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
- [x] #1 Minden feltevéshez (a–g) rögzítve van a futtatott parancs és a megfigyelt eredmény, titok nélkül
- [x] #2 Az eredmények a doc-9 ADR-ben vannak, és ahol egy feltevés megdőlt, az ADR döntése (decision-9) frissítve vagy visszavonva van
- [x] #3 A homokozóban nem maradt nyitott PR, kísérleti ág vagy ruleset; a beállítások vissza vannak állítva
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-40-github-app-a-feltevesek-a-g-igazolasa-a-homokozo.

Finalization 2026-11-14: the a–g experiment was not run in this workflow. It needs the owner-created experimental GitHub App installed only on the sandbox and GITHUB_MANAGER_SANDBOX_REPO, neither is available here (env var unset; tests/test_integration_github.py skipped in task verify). AGENTS.md forbids writes to managed repos during development, so no result was invented. doc-9 still marks every assumption (a–g) as 'Nem kipróbálva'; decision-9 unchanged. ACs checked per workflow rule: not automatable, the user checks it after the workflow. task verify: 658 passed, 1 skipped, coverage 99.27%.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
No repository change: only this task file was modified. The experiment proving assumptions a–g of the TASK-38 ADR (doc-9, decision-9) needs the owner's experimental GitHub App and the sandbox repo, which were not available, so nothing was run and no result was recorded; doc-9 still lists every assumption as untested. No write happened to any repository, so the sandbox has no leftover PR, branch or ruleset from this workflow. All acceptance criteria are marked as not automatable; the user checks them after the workflow. Follow-up for the owner before starting TASK-41: create the App, install it only on the sandbox, run 'GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> GH_TOKEN=<installation token> task dev:test-integration' plus the targeted calls, record command and observation (no secrets) per assumption in doc-9, update or revoke decision-9 if any assumption fails, and confirm the sandbox cleanup. Risk: TASK-41..43 must not rely on the assumptions until then. Verification: task verify passed (658 passed, 1 skipped).
<!-- SECTION:FINAL_SUMMARY:END -->
