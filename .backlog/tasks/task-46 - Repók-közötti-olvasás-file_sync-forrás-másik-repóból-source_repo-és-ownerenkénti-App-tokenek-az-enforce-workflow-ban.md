---
id: TASK-46
title: >-
  Repók közötti olvasás: file_sync forrás másik repóból (source_repo) és
  ownerenkénti App tokenek az enforce workflow-ban
status: Done
assignee: []
created_date: '2026-11-16T23:56:00Z'
updated_date: '2026-11-17T11:58:00Z'
labels: []
dependencies: []
modified_files:
  - src/github_manager/github.py
  - src/github_manager/engine.py
  - src/github_manager/rules/base.py
  - src/github_manager/rules/files.py
  - src/github_manager/cli.py
  - .github/workflows/enforce.yml
  - tests/conftest.py
  - README.md
priority: medium
type: feature
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A workspace profilú repók verify workflow-ja token nélkül, offline validálja a `workspace.yaml`-t egy JSON Schema ellen. A séma gazdája a privát `tyutyutyu-org/easy-github` repó. Döntés (2026-11-17): a sémát a github-manager másolja be a compliance PR-ral minden workspace repóba, a saját GitHub App tokenjével. Így nincs PAT, nincs secret, és nincs kézi munka.

Akadályok a mai kódban:
- A `file_sync` (`FileSync._build`, `src/github_manager/rules/files.py`) a forrást a config betöltésekor, helyi fájlból olvassa (`base_dir / source`). Más repóból nem tud olvasni.
- A szabályok csak a `Workspace` protokollon át olvasnak (`src/github_manager/rules/base.py`, decision-2), és a protokoll csak a kezelt repót látja.
- Az `enforce` workflow (`.github/workflows/enforce.yml`) ownerenként egy jobot futtat, egy csak arra az ownerre szóló installation tokennel (`actions/create-github-app-token`, `owner: ${{ matrix.owner }}`). A `tyutyutyu` job tokenje nem látja a `tyutyutyu-org` privát repóit, így az easy-github-ot sem.
- Helyi futáskor a `gh` CLI tokenje mindkét owner repóit látja (`resolve_token`, `src/github_manager/github.py`).
A repók közötti olvasást a tagrepó-ellenőrző szabály (külön feladat) is használni fogja.

## Objective
Egy `file_sync` szabály forrása lehet egy másik, akár másik owneré levő repó fájlja is. Az `enforce` minden ownerjobja új secret és új App-jogosultság nélkül olvasni tudja a többi owner repóit.

## Scope
### In scope
- A `Workspace` protokoll új olvasó művelete: egy fájl tartalma egy másik repó (OWNER/NAME) default ágáról. Eredménye `None`, ha a fájl vagy a repó nem létezik vagy nem olvasható. Megvalósítás a `RemoteWorkspace`-ben (`src/github_manager/engine.py`) és a `MemoryWorkspace`-ben (`tests/conftest.py`).
- Repók közötti olvasás ownerenkénti tokennel: a CLI a fő token mellett ownerenként opcionális, csak olvasó tokeneket fogad (környezeti változókból). Egy másik owner repóját azzal olvassa; ha arra az ownerre nincs külön token, a fő tokennel.
- `enforce.yml`: minden ownerjob a többi ownerre is kér installation tokent a meglévő App-pal (`actions/create-github-app-token`, a `owner` input és csak `contents: read` jog). A meglévő `GH_MANAGER_APP_CLIENT_ID` változót és `GH_MANAGER_APP_PRIVATE_KEY` secretet használja.
- `FileSync`: új opcionális `source_repo` kulcs (OWNER/NAME). Ha meg van adva, a `source` út abban a repóban értendő, és a tartalmat futáskor a `Workspace`-en át olvassa. Egy futásban forrásonként legfeljebb egy API-olvasás történik. Ha a forrás nem olvasható, a szabály egy MANUAL findingot ad (az üzenet megnevezi a forrást), és nem ír semmit.
- README: a `file_sync` opciótáblája és a „Tokens” szakasz (repók közötti olvasás).

### Out of scope
- A séma-szinkron és a workspace verify szabály felvétele a `github-manager.toml`-ba (a workspace verify feladata).
- A tagrepók létezésének ellenőrzése (külön feladat).
- Másik ref vagy ág mint forrás. Forrás nem GitHub-repóból.
- Új GitHub App, új secret, PAT vagy App-jogosultság-bővítés.
- Írás bármely kezelt repóba fejlesztés közben.

## Implementation plan
1. `src/github_manager/github.py`: a meglévő `read_file(repo, path, ref)` mintájára biztosítsd, hogy egy másik repó default ágáról is lehessen olvasni (pl. `ref` nélkül vagy a repó default ágának lekérdezésével). A 404 `None`-t adjon. A `GitHubApi` protokoll (`engine.py`) és a `FakeGitHub` (`tests/conftest.py`) kövesse ezt.
2. Ownerenkénti tokenek: a CLI (`_client` / `resolve_token` környéke, `src/github_manager/cli.py`, `github.py`) dokumentált környezeti változóból olvassa az opcionális ownerenkénti tokeneket. A változó neve legyen egyértelmű a kötőjeles owner nevekre is. Az olvasásokat a repó ownere szerint a megfelelő `GitHub` kliens végezze. Token soha ne kerüljön logba vagy hibaüzenetbe.
3. `Workspace` protokoll (`rules/base.py`), `RemoteWorkspace`, `MemoryWorkspace`: az új olvasó művelet. A `MemoryWorkspace`-ben a tesztek más repók fájljait is beállíthassák.
4. `FileSync._build`:
   - `source_repo` validálása: pontosan egy `/`, nem üres részek;
   - `source` validálása `source_repo` esetén: nem kezdődik `/`-rel és nincs benne `..` szegmens, a `RequiredFiles._build` mintájára;
   - helyi forrás esetén a viselkedés változatlan.
   A `FileSync.apply` távoli forrásnál a `Workspace`-en át olvasson. A futásonkénti egyszeri olvasást úgy oldd meg, hogy a szabály frozen dataclass maradjon (pl. gyorsítótár az olvasó rétegben).
5. `enforce.yml`: a többi owner tokenjeinek lépései és az env átadás. A meglévő tokenlépést és az `uv run` parancsot ne változtasd meg.
6. Tesztek:
   - `tests/test_github.py`: olvasás másik repóból, 404 → `None`, ownerenkénti token választása.
   - `tests/test_rules_files.py`: távoli forrás egyezik / eltér / hiányzik (MANUAL, nincs írás); config-hibák.
   - `tests/test_engine.py`: egy futás több repóján a forrás egyszer olvasódik (`fake_github.calls`).
   - `tests/test_cli.py`: a token-környezeti változók feldolgozása.
7. README frissítése.

## Verification
- `uv run ruff format -q . && task verify` — minden ellenőrzés sikeres.
- `uv run github-manager repos` — a valódi config betölthető.
- A `.github/workflows/enforce.yml` átnézése: nincs új secret vagy változó, a többi owner tokenje csak `contents: read` jogot kér.

## Dependencies and risks
- Nincs előfeltétel a feladatok között. A workspace verify és a tagrepó-szabály erre épül.
- Kockázat: a `create-github-app-token` jogszűkítő inputjainak neve verziófüggő. Mitigáció: a rögzített v3.3.0 action `action.yml`-jét ellenőrizd.
- Kockázat: egy minden owner repóját olvasó token kiszivárgása. Mitigáció: csak olvasási jog, rövid élettartam (job végén visszavonva), nincs logolás.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A Workspace protokoll olvasni tud egy fájlt egy másik OWNER/NAME repó default ágáról; nem létező vagy nem olvasható fájl vagy repó esetén None az eredmény
- [x] #2 A CLI ownerenként opcionális olvasó tokent fogad dokumentált környezeti változóból, és egy másik owner repóját azzal olvassa; token nélkül a fő tokent használja; token nem jelenik meg kimenetben
- [x] #3 Az enforce workflow minden ownerjobja a többi ownerre is kér csak contents: read jogú installation tokent a meglévő App-pal, új secret vagy változó nélkül
- [x] #4 A file_sync source_repo kulccsal a forrást a megadott repóból olvassa, futásonként forrásonként legfeljebb egyszer; helyi forrással a viselkedés változatlan
- [x] #5 Nem olvasható távoli forrásnál a file_sync MANUAL findingot ad a forrás megnevezésével, és nem ír
- [x] #6 Hibás source_repo (nem OWNER/NAME), abszolút vagy .. szegmenst tartalmazó távoli source és ismeretlen kulcs config-hiba
- [x] #7 A README file_sync opciótáblája és Tokens szakasza leírja a távoli forrást és az ownerenkénti tokeneket
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . && task verify sikeres
- [x] #2 Nincs új secret, PAT vagy App-jogosultság
- [x] #3 A diff nem tartalmaz a feladathoz nem tartozó változást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-46-repok-kozotti-olvasas-file-sync-forras-masik-rep.

Lezárási ellenőrzés (2026-11-17): uv run ruff format -q . && task verify sikeres (709 passed, 1 skipped integrációs teszt, 99% lefedettség); uv run github-manager repos betölti a valódi configot; git diff --check tiszta. A rögzített create-github-app-token v3.3.0 action.yml-je tartalmazza az owner és permission-contents inputokat.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A file_sync új source_repo (OWNER/NAME) kulccsal másik, akár másik owneré levő repó default ágáról olvashatja a forrást. Új Workspace.read_repo_file művelet (RemoteWorkspace a futásonként közös RepoFileCache-en át, MemoryWorkspace other_repos-szal); GitHub.read_default_file None-t ad 404, 401/403 (nem rate limit) és használhatatlan tartalom esetén. Ownerenkénti opcionális olvasó tokenek a GH_READ_TOKEN_<OWNER> változókból (kötőjel -> _), token nélkül a fő token; token nem kerül kimenetbe. Nem olvasható forrás: MANUAL finding a forrás nevével, írás nélkül. Config-hiba: hibás source_repo, abszolút vagy '..' szegmenses távoli source, ismeretlen kulcs. enforce.yml: minden ownerjob a másik ownerre csak contents: read installation tokent kér a meglévő App-pal, új secret/változó nélkül. README file_sync tábla és Tokens szakasz frissítve. Ellenőrzés: task verify sikeres (709 passed), repos parancs OK. Kockázat: új owner felvételekor az enforce.yml olvasó-token lépéseit is bővíteni kell.
<!-- SECTION:FINAL_SUMMARY:END -->
