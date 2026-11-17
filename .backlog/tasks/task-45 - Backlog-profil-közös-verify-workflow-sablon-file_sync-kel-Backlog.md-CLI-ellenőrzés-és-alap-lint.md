---
id: TASK-45
title: >-
  Backlog profil: közös verify workflow sablon file_sync-kel (Backlog.md
  CLI-ellenőrzés és alap lint)
status: Done
assignee: []
created_date: '2026-11-16T23:56:00Z'
updated_date: '2026-11-17T00:31:00Z'
labels: []
dependencies:
  - TASK-44
modified_files:
  - templates/backlog/backlog-verify.yml
  - github-manager.toml
  - renovate/default.json
  - renovate.json
  - tests/test_templates.py
  - README.md
priority: medium
type: feature
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A backlog profilú repók (név `-backlog` utótaggal; a profilok bevezetése egy korábbi feladat) Backlog.md tervező repók: `.backlog/` könyvtár, `README.md`, `AGENTS.md`, `renovate.json`, alkalmazás nélkül. Verify workflow nélkül a `default-branch-ruleset` (`repo_ruleset`, `required_workflow_check = "verify"`) nem követel meg checket, és a `_verify_required` miatt (`src/github_manager/engine.py`) nincs auto-merge. Ilyenkor minden compliance PR-t kézzel kell merge-elni. Döntés (2026-11-17): minden backlog repóba egy közös, `file_sync`-kel szinkronban tartott verify workflow kerül. Ez token nélkül ellenőrzi, hogy a Backlog.md CLI hiba nélkül olvassa a `.backlog/` tartalmát, és alap Markdown/YAML lintet futtat.

Ismert tények:
- A `file_sync` (`FileSync`, `src/github_manager/rules/files.py`) a teljes fájlt a configfájlhoz relatív `source` sablonra írja. Eltérés esetén a compliance PR javítja.
- A backlog repók privátak, ezért rájuk vonatkozik a `private-self-hosted-runners` szabály (`SelfHostedRunners`, `src/github_manager/rules/workflows.py`, `allowed_runs_on = [["self-hosted"]]`). Ha a sablon nem felelne meg neki, a két szabály egymás ellen írna.
- A kötelező check neve a job `name:`-je vagy az id-je. Mátrix, reusable workflow vagy szűrt `pull_request` trigger nem számít (`RepoRuleset.workflow_check_problem`, `src/github_manager/rules/ruleset.py`).
- A közös Renovate preset (`renovate/default.json`) minden repóban fut. Egy szinkronizált workflow action-digestjét a Renovate a kezelt repóban frissítené, amit a következő `fix` visszaírna. A sablont ezért a github-manager repóban kell frissíteni (a saját `renovate.json`-ja), a kezelt repókban pedig a szinkronizált fájlt ki kell venni a Renovate alól. Az `ignorePaths` a presetben felülírná a `config:recommended` alapértelmezett listáját, ezért helyette `packageRules` + `matchFileNames` + `enabled: false` kell.
- A `backlog doctor` (Backlog.md 1.55.3) csak `--fix` esetén ír. Egy hibátlan repón 0-val lép ki; azt, hogy talált problémánál milyen kóddal lép ki, ellenőrizni kell.

## Objective
Minden backlog profilú repóban ott van a közös `verify` workflow a github-manager sablonjából. A job kötelező checkként és auto-merge feltételként elfogadott, és sem a `self_hosted_runners`, sem a Renovate nem ír bele.

## Scope
### In scope
- Sablon: `templates/backlog/backlog-verify.yml` → a repóban `.github/workflows/backlog-verify.yml`. A job id-je `verify`, triggerei: `push` a `main`-re és szűrő nélküli `pull_request`. `permissions: contents: read`, `runs-on: self-hosted`. Minden action commit SHA-ra rögzítve, verziókommenttel (a `.github/workflows/verify.yml` mintájára).
- Ellenőrzések token nélkül:
  - a Backlog.md CLI rögzített verzióval beolvassa a projektet (pl. `backlog task list --plain` és `backlog doctor`), és bármilyen jelzett hiba (duplikált ID, ciklikus függőség, olvasási hiba) a jobot pirosra állítja;
  - alap YAML- és Markdown-lint, a sablonba ágyazott konfigurációval, csak szintaktikai szintű szabályokkal, hogy a Backlog.md által generált fájlok átmenjenek.
- `github-manager.toml`: új `backlog-verify-workflow` szabály (`type = "file_sync"`, `profiles = ["backlog"]`), kommenttel.
- Renovate:
  - `renovate/default.json`: egy `packageRules` bejegyzés, amely `matchFileNames`-szel kikapcsolja a `.github/workflows/backlog-verify.yml` frissítését. Úgy kell felépíteni, hogy a workspace sablon fájlneve később ugyanebbe a bejegyzésbe kerüljön.
  - A repó saját `renovate.json`-ja: a `templates/**/*.yml` fájlokat a github-actions manager is kezelje.
- Tesztek a sablonra, README (a „Profiles” szakaszban vagy egy új „Templates” alszakaszban).

### Out of scope
- A workspace verify sablon és a séma-szinkron (külön feladat).
- Új szabálytípus vagy a `FileSync` módosítása.
- Bármilyen írás a kezelt repókba fejlesztés közben (csak olvasó `gh` lekérdezés megengedett).
- Teszt a valódi `github-manager.toml` tartalmára.

## Implementation plan
1. Ellenőrizd helyben (csak olvasva, egy ideiglenes másolaton, a scratchpadben), hogyan jelez hibát a `backlog doctor` és a `backlog task list`: kilépési kód vagy kimenet. Ha a doctor hibánál is 0-val lép ki, a workflow a kimenet alapján bukjon el. A megfigyelést rögzítsd az implementációs jegyzetben.
2. Írd meg a `templates/backlog/backlog-verify.yml` sablont (In scope szerint). A Backlog.md CLI verziója legyen rögzítve, Renovate által frissíthető formában.
3. `github-manager.toml`: a `backlog-verify-workflow` szabály (`path = ".github/workflows/backlog-verify.yml"`, `source = "templates/backlog/backlog-verify.yml"`, `profiles = ["backlog"]`).
4. Renovate: `renovate/default.json` `packageRules` bejegyzés és a repó saját `renovate.json` `managerFilePatterns` (vagy a telepített Renovate-verzió megfelelő kulcsa) a `templates/**/*.yml` fájlokra. Validáld a Renovate sémájával (`npx --yes --package renovate -- renovate-config-validator`, ha elérhető).
5. Tesztek egy új `tests/test_templates.py`-ban, amely csak a sablonfájlt olvassa, a configot nem:
   - a sablon tartalmával feltöltött `MemoryWorkspace`-en a `SelfHostedRunners(allowed_runs_on=[["self-hosted"]], runs_on=["self-hosted"])` nem ad findingot;
   - egy `RepoRuleset(required_workflow_check="verify")` `workflow_check_problem` értéke `None`.
6. README frissítése.

## Verification
- `uv run ruff format -q . && task verify` — minden ellenőrzés sikeres, az új sablontesztek zöldek.
- `uv run github-manager repos` — a valódi config betölthető.
- `uv run github-manager check --diff -o tyutyutyu --repo zenget-backlog` (csak olvasó) — a diffben a `.github/workflows/backlog-verify.yml` a sablonnal azonos tartalommal jelenik meg, más profil repóiban nem.
- Kézi ellenőrzés a scratchpadben: a sablon lépései egy backlog repó helyi másolatán lefutnak, és egy szándékosan duplikált task ID esetén hibával állnak le.

## Dependencies and risks
- Előfeltétel: a profilok bevezetése (a `profiles` kulcs és a backlog profil).
- Kockázat: a self-hosted runneren hiányozhat a Node vagy a Python. Mitigáció: a sablon setup-actionökkel telepítse őket.
- Kockázat: a lint túl szigorú lehet a generált Backlog-fájlokra. Mitigáció: csak szintaktikai szabályok, és a kézi ellenőrzés egy valódi backlog repó helyi másolatán.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A templates/backlog/backlog-verify.yml sablon verify id-jű jobja main push-ra és szűrő nélküli pull_request-re fut, contents: read joggal, runs-on: self-hosted, SHA-ra rögzített actionökkel, token vagy secret nélkül
- [x] #2 A workflow elbukik, ha a Backlog.md CLI hibát jelez (pl. duplikált task ID), vagy ha a YAML- vagy Markdown-lint hibát talál; egy hibátlan, generált Backlog.md projekten átmegy
- [x] #3 A github-manager.toml backlog-verify-workflow file_sync szabálya csak a backlog profilra vonatkozik, és a .github/workflows/backlog-verify.yml fájlt tartja a sablonnal azonosan
- [x] #4 Teszt igazolja, hogy a sablonon a self_hosted_runners szabály nem ad findingot, és a repo_ruleset a verify jobot kötelező checkként elfogadja
- [x] #5 A közös Renovate preset kikapcsolja a szinkronizált workflow frissítését a kezelt repókban (packageRules + matchFileNames, ignorePaths nélkül), a github-manager saját renovate.json-ja pedig a templates/**/*.yml sablonokat is frissíti
- [x] #6 A README leírja a backlog profil verify workflow-ját és a sablonok frissülését
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . && task verify sikeres
- [x] #2 A kézi ellenőrzés (hibátlan és duplikált ID-s backlog) eredménye az implementációs jegyzetben
- [x] #3 Nincs írás kezelt repóba és nincs teszt a valódi github-manager.toml tartalmára
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-45-backlog-profil-kozos-verify-workflow-sablon-file.

Kézi ellenőrzés (2026-11-17, Backlog.md 1.55.3, ideiglenes /tmp projekt, `backlog init` + 2 generált task):
- Hibátlan projekt: a 'Read the Backlog.md project' lépés szkriptje exit 0, `backlog doctor` exit 0 ('No duplicate IDs ... found'); yamllint exit 0; markdownlint-cli2 0.24.1 a sablon konfigurációjával 0 issue.
- Duplikált task ID (TASK-2 két fájlban): `backlog doctor` exit 1 ('1 duplicate task ID group'), a lépés szkriptje exit 1.
- Megfigyelés: a `backlog doctor` hibánál nem 0-val lép ki; a `backlog task list` és a doctor a nem értelmezhető taskfájlt exit 0-val kihagyja, csak DEBUG=1 mellett írja stderr-re ('Failed to parse'), ezért a lépés erre is bukik (a korábbi javításban ellenőrizve: exit 1 hibás, 0 javított fájllal). Távoli refresh hiba (nincs origin) csak figyelmeztetés.
- Lint negatív esetek: duplikált YAML kulcs -> yamllint exit 1; üres link (MD042) -> markdownlint-cli2 exit 1.
- A github-manager saját, Backlog.md által generált .backlog/ könyvtára (68 md fájl) átmegy mindkét linten.
Csak olvasó ellenőrzések: `uv run github-manager repos` betölti a configot; `check --diff --repo zenget-backlog` a .github/workflows/backlog-verify.yml-t 'missing'-ként, a sablon tartalmával mutatja; zenget és zenget-workspace checkjében nincs backlog-verify-workflow. Kezelt repóba nem történt írás.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A backlog profilú repók közös verify workflow-t kapnak: templates/backlog/backlog-verify.yml (job id verify, main push + szűrő nélküli pull_request, contents: read, runs-on: self-hosted, SHA-ra rögzített actionök, token nélkül). Lépései: backlog doctor és task list DEBUG=1-gyel (duplikált ID, ciklus, nem értelmezhető taskfájl esetén piros), yamllint (key-duplicates + szintaxis) és markdownlint-cli2 csak szintaktikai szabályokkal; az eszközverziók Renovate által frissíthető env változók. A github-manager.toml backlog-verify-workflow file_sync szabálya profiles = ["backlog"]. A renovate/default.json packageRules + matchFileNames bejegyzéssel kikapcsolja a szinkronizált fájl frissítését a kezelt repókban; a saját renovate.json a templates/**/*.yml-t a github-actions managerrel és egy regex managerrel kezeli. tests/test_templates.py igazolja, hogy a self_hosted_runners nem ad findingot és a repo_ruleset elfogadja a verify checket. README: 'Backlog profile verify workflow' alszakasz. Ellenőrzés: ruff format + task verify zöld (684 passed, 1 skipped, 99.30%); kézi scratch ellenőrzés és csak olvasó check a jegyzetben. Kockázat: a self-hosted runneren futó első valódi futás még nem látott; a Renovate config validátort ebben a lezárásban nem futtattam.
<!-- SECTION:FINAL_SUMMARY:END -->
