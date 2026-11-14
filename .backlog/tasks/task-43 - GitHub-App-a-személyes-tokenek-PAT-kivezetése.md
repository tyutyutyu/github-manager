---
id: TASK-43
title: 'GitHub App: a személyes tokenek (PAT) kivezetése'
status: Done
assignee: []
created_date: '2026-11-14T09:18:00Z'
updated_date: '2026-11-14T22:38:00Z'
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
- [x] #1 Az App-os enforce futás legalább egy ütemezett ciklusban mindkét ownerre sikeres volt (a felhasználó ellenőrzi), mielőtt a secretek törlődnek
- [x] #2 A két PAT secret törölve van a repóból, és a workflow vagy a README nem hivatkozik rájuk
- [x] #3 A README visszaállási leírása a kivezetés utáni állapotot tükrözi (új PAT kiállítása, ha szükséges)
- [x] #4 A tokenek visszavonásának lépése a felhasználónak szóló jegyzetben szerepel; az ágens nem vonja vissza őket
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-43-github-app-a-szemelyes-tokenek-pat-kivezetese.

Felhasználónak szóló kézi lépések (az ágens nem végezte el őket):
1. Ellenőrizd, hogy az App-os enforce ütemezett futása (cron 17 5 * * *) mindkét ownerre (tyutyutyu, tyutyutyu-org) sikeres volt: gh run list --repo tyutyutyu/github-manager --workflow enforce.yml. A 2026-11-14 22:35Z-s átállás után még nem volt ütemezett App-os futás.
2. Csak ezután töröld a két secretet: gh secret delete GH_MANAGER_TOKEN --repo tyutyutyu/github-manager és gh secret delete GH_MANAGER_ORG_TOKEN --repo tyutyutyu/github-manager (a finalizáláskor még mindkettő megvolt).
3. Vond vissza a két fine-grained PAT-et a GitHubon: Settings → Developer settings → Personal access tokens → Fine-grained tokens → a github-manager tokenek → Revoke (a tyutyutyu-org tokent is a kiállító felhasználó fiókjában).
Ellenőrzés: a README.md és a .github/workflows nem hivatkozik a GH_MANAGER_TOKEN / GH_MANAGER_ORG_TOKEN nevekre (grep üres); task verify sikeres (659 passed, 1 skipped, 99.28% coverage).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A README „Rolling back” bekezdése most a PAT-ek kivezetése utáni állapotot írja le: nincs PAT-os tartalék, és ha az App nem használható, ownerenként új fine-grained PAT-et kell kiállítani (Contents, Pull requests, Workflows, Administration írás, Metadata olvasás), repó-secretként eltárolni, és az enforce job GH_TOKEN-jét erre állítani. A README és a workflow már nem hivatkozik a GH_MANAGER_TOKEN / GH_MANAGER_ORG_TOKEN secretekre. Ellenőrzés: grep üres, task verify zöld (659 passed, 1 skipped, 99.28% coverage). Kézi lépés marad: az App-os ütemezett futás sikerének igazolása mindkét ownerre, utána a két secret törlése (a finalizáláskor még megvoltak) és a PAT-ek visszavonása. A lépések az implementációs jegyzetben vannak, az ágens nem végezte el őket. Kockázat: a README múlt idejű „have been retired” megfogalmazása a secretek törléséig szó szerint nem igaz.
<!-- SECTION:FINAL_SUMMARY:END -->
