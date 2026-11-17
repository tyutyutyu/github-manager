---
id: TASK-47
title: >-
  Workspace profil: közös verify workflow sablon és az easy-github
  workspace.yaml sémájának szinkronja
status: To Do
assignee: []
created_date: '2026-11-16T23:57:00Z'
labels: []
dependencies:
  - TASK-44
  - TASK-45
  - TASK-46
modified_files:
  - templates/workspace/workspace-verify.yml
  - github-manager.toml
  - renovate/default.json
  - tests/test_templates.py
  - README.md
priority: medium
type: feature
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A workspace profilú repók (név `-workspace` utótaggal, pl. `tyutyutyu/zenget-workspace`) csak gyökérfájlokat és egy `workspace.yaml` manifestet tartalmaznak. Ez felsorolja a tagrepókat (`repositories[].name`, `repositories[].origin`), és megnevezi a backlog repót (`backlog`). A tagrepók mappái a workspace `.gitignore`-jában ki vannak zárva. A formátum az easy-github tervének vázlata: `kind: easy-github-workspace`, `backlog`, `repositories`.

Döntések (2026-11-17):
- Minden workspace repóba egy közös verify workflow kerül `file_sync`-kel. Token nélkül fut, és ezeket ellenőrzi:
  - a `workspace.yaml` megfelel a sémának;
  - konzisztencia: a `backlog` szerepel a `repositories` nevei között, és a `.gitignore` minden tagrepó mappáját kizárja;
  - yamllint és markdownlint a gyökérfájlokra.
- A sémát az easy-github repó adja ki. A github-manager a compliance PR-ral másolja be a workspace repóba, a repók közötti `file_sync` forrással (`source_repo`, korábbi feladat).

A backlog verify feladat már kialakította a sablonok mintáját: `templates/backlog/backlog-verify.yml`, `tests/test_templates.py`, valamint a Renovate `packageRules` bejegyzését a szinkronizált workflow-kra (`renovate/default.json`) és a repó saját `renovate.json`-jában a sablonok kezelését. Ezt a mintát kell követni.

## Objective
Minden workspace profilú repóban ott van a sémafájl és a közös `verify` workflow. A workflow token nélkül elbukik hibás sémán, inkonzisztens manifesten és lint hibán. A job kötelező checkként és auto-merge feltételként elfogadott.

## Scope
### In scope
- Sablon: `templates/workspace/workspace-verify.yml` → a repóban `.github/workflows/workspace-verify.yml`. A job id-je `verify`, triggerei: `push` a `main`-re és szűrő nélküli `pull_request`. `permissions: contents: read`, `runs-on: self-hosted`, SHA-ra rögzített actionök. Minden logika (a konzisztencia-ellenőrzés is) a szinkronizált fájlokban van; a workflow futáskor nem tölt le semmit a github-manager vagy az easy-github repóból.
- A sémafájl helye a workspace repóban: `.github/schemas/workspace.schema.json`.
- `github-manager.toml`, mindkettő `profiles = ["workspace"]`, kommentekkel:
  - `workspace-schema` szabály (`file_sync`, `source_repo = "tyutyutyu-org/easy-github"`, `source` = a séma útja az easy-githubban);
  - `workspace-verify-workflow` szabály (`file_sync`).
- A konzisztencia pontos szabályai:
  - a `backlog` értéke egyezik egy `repositories[].name` értékkel;
  - a `repositories[].name` értékek egyediek;
  - minden `<name>/` mappát a `.gitignore` kizár (`git check-ignore` alapján, nem szövegegyezéssel).
- A Renovate `packageRules` bejegyzésének bővítése a `.github/workflows/workspace-verify.yml`-lel.
- Sablontesztek és README.

### Out of scope
- A séma megírása vagy bármilyen írás az easy-github repóba (külső előfeltétel).
- A tagrepók létezésének ellenőrzése (külön feladat, a github-manager végzi).
- Token vagy secret használata a workflow-ban.
- Teszt a valódi `github-manager.toml` tartalmára.

## Implementation plan
1. Előfeltétel ellenőrzése csak olvasva: `gh api repos/tyutyutyu-org/easy-github/contents/schemas` — a workspace séma létezik az easy-github default ágán. Ha nem létezik, a feladat blokkolt; ne készíts helyettesítő sémát.
2. `templates/workspace/workspace-verify.yml`:
   - sémaellenőrzés rögzített verziójú validátorral (pl. `check-jsonschema` `uvx`-szel);
   - konzisztencia-ellenőrzés a fájlba ágyazott scripttel;
   - yamllint és markdownlint, a fájlba ágyazott, szintaktikai szintű konfigurációval.
   Minden eszközverzió legyen rögzítve, Renovate által frissíthető formában.
3. `github-manager.toml`: a két szabály (In scope szerint).
4. `renovate/default.json`: a meglévő `matchFileNames` lista bővítése.
5. `tests/test_templates.py`: ugyanazok az ellenőrzések, mint a backlog sablonra (`SelfHostedRunners`: nincs finding; `RepoRuleset(required_workflow_check="verify").workflow_check_problem` → `None`).
6. Kézi ellenőrzés: a sablon lépései a scratchpadben, a `zenget-workspace` egy helyi másolatán.
   - A jó manifest átmegy.
   - Bukik, ha a `backlog` nincs a listában, ha egy tagmappa nincs a `.gitignore`-ban, és ha egy kötelező mező hiányzik.
7. README: a workspace profil leírása, a séma eredete és frissülése (az easy-github változása a következő `fix` futással kerül a repókba).

## Verification
- `uv run ruff format -q . && task verify` — minden ellenőrzés sikeres.
- `uv run github-manager repos` — a valódi config betölthető.
- `uv run github-manager check --diff -o tyutyutyu --repo zenget-workspace` (csak olvasó, App vagy `gh` token, amely az easy-github-ot is látja) — a diff a sémát és a workflow-t a forrásokkal azonos tartalommal mutatja.
- A kézi ellenőrzés eredménye rögzítve az implementációs jegyzetben.

## Dependencies and risks
- Előfeltételek:
  - a profilok bevezetése;
  - a backlog verify sablon (minta és Renovate-bejegyzés);
  - a repók közötti `file_sync` forrás.
- Külső előfeltétel (blokkoló): az easy-github repóban el kell készülnie a `workspace.yaml` JSON Schemájának, fix úton, a default ágon. Ezt az easy-github saját backlogjában kell vállalni; ebből a repóból oda írni tilos.
- Kockázat: ha a séma szigorúbb a mostani manifesteknél, a verify piros lesz, és a compliance PR nem merge-elődik automatikusan. Mitigáció: a `check --diff` és a kézi ellenőrzés még a bekapcsolás előtt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A templates/workspace/workspace-verify.yml sablon verify id-jű jobja main push-ra és szűrő nélküli pull_request-re fut, contents: read joggal, runs-on: self-hosted, SHA-ra rögzített actionökkel, token vagy secret nélkül, és futáskor nem tölt le semmit a github-manager vagy az easy-github repóból
- [ ] #2 A workflow elbukik, ha a workspace.yaml nem felel meg a .github/schemas/workspace.schema.json sémának, ha a backlog nem szerepel a repositories nevei között, ha egy név ismétlődik, ha egy tagmappát a .gitignore nem zár ki (git check-ignore), vagy ha a yamllint vagy markdownlint hibát talál
- [ ] #3 A github-manager.toml workspace-schema szabálya (file_sync, source_repo = tyutyutyu-org/easy-github) és workspace-verify-workflow szabálya csak a workspace profilra vonatkozik
- [ ] #4 Teszt igazolja, hogy a sablonon a self_hosted_runners szabály nem ad findingot, és a repo_ruleset a verify jobot kötelező checkként elfogadja
- [ ] #5 A Renovate preset a .github/workflows/workspace-verify.yml frissítését is kikapcsolja a kezelt repókban
- [ ] #6 A README leírja a workspace profilt, a séma eredetét és frissülését
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 uv run ruff format -q . && task verify sikeres
- [ ] #2 A kézi ellenőrzés (jó és hibás manifestek) eredménye az implementációs jegyzetben
- [ ] #3 Nincs írás az easy-github vagy más kezelt repóba, és nincs teszt a valódi github-manager.toml tartalmára
<!-- DOD:END -->
