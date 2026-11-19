---
id: TASK-48
title: >-
  Új workspace_members szabálytípus: a workspace.yaml tagrepói léteznek (csak
  jelzés)
status: Done
assignee: []
created_date: '2026-11-16T23:57:00Z'
updated_date: '2026-11-19T09:23:00Z'
labels: []
dependencies:
  - TASK-44
  - TASK-46
modified_files:
  - src/github_manager/rules/__init__.py
  - src/github_manager/rules/base.py
  - src/github_manager/engine.py
  - src/github_manager/github.py
  - tests/conftest.py
  - github-manager.toml
  - README.md
priority: medium
type: feature
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A workspace profilú repók `workspace.yaml` manifestje felsorolja a tagrepókat. Példa: `repositories: [{name: zenget, origin: git@github.com:tyutyutyu/zenget.git}, …]`. A tagrepók között privátak is vannak (pl. a `-backlog` repó), és lehetnek más owner alatt is.

Döntés (2026-11-17): a tagrepók létezését nem a workspace repó workflow-ja ellenőrzi, mert a `GITHUB_TOKEN` nem látja a többi privát repót, és a döntés szerint nincs PAT vagy secret. Helyette egy új github-manager szabály ellenőriz, a meglévő App tokenjeivel. Ha egy tagrepó nem létezik vagy nem érhető el, a szabály csak jelez (MANUAL, decision-7).

A repók közötti olvasást (ownerenkénti tokenek, `Workspace`-bővítés) egy korábbi feladat vezette be; ez a szabály arra épít. Minták:
- `RequiredFiles` (`src/github_manager/rules/files.py`): csak jelző szabály;
- `Options` (`src/github_manager/rules/base.py`);
- `RULE_TYPES` (`src/github_manager/rules/__init__.py`);
- a PyYAML már függőség (`rules/workflows.py` használja).

## Objective
Új `workspace_members` szabálytípus: a workspace manifestben felsorolt minden tagrepó létezik és elérhető. Minden eltérés egy MANUAL finding, és a szabály semmit nem ír.

## Scope
### In scope
- `WorkspaceMembers(Rule)`, `type_name = "workspace_members"`, egy opcióval: `path` (alapértelmezés `workspace.yaml`).
- Az `origin` formátumok:
  - `git@github.com:OWNER/NAME(.git)`;
  - `https://github.com/OWNER/NAME(.git)`.
- MANUAL findingok, a `path`-ot és a tagrepó nevét megnevező üzenettel:
  - a manifest hiányzik;
  - nem érvényes YAML;
  - nincs benne `repositories` lista;
  - egy elemből hiányzik a `name` vagy az `origin`;
  - nem támogatott `origin` (más host vagy formátum);
  - a tagrepó nem létezik vagy nem olvasható.
- Egy új, csak olvasó `Workspace` művelet: létezik-e egy OWNER/NAME repó, a repók közötti olvasás tokenjeivel (`RemoteWorkspace`, `MemoryWorkspace`, `GitHubApi`, `FakeGitHub`).
- `github-manager.toml`: `workspace-members` szabály `profiles = ["workspace"]` értékkel, kommenttel.
- README: új `### workspace_members` alszakasz a „Rule types” alatt.

### Out of scope
- A `workspace.yaml` sémája és belső konzisztenciája (a workspace verify workflow végzi).
- Tagrepók létrehozása, archivált állapotuk vagy láthatóságuk ellenőrzése.
- A manifest javítása vagy írása.
- Teszt a valódi `github-manager.toml` tartalmára.

## Implementation plan
1. `github.py`: létezés-lekérdezés (`GET /repos/{owner}/{repo}`). 200 → létezik; 404 → nem létezik vagy nem látható. Más hiba `GitHubError`, amit a repónkénti hibaizoláció kezel. Az olvasás a repó ownerének tokenjével történjen (a repók közötti olvasás feladatának mechanizmusa szerint).
2. `rules/base.py` `Workspace` protokoll, `RemoteWorkspace` (`engine.py`), `MemoryWorkspace` és `FakeGitHub` (`tests/conftest.py`): az új művelet. Egy futáson belül repónként legfeljebb egyszer kérdezzen le.
3. `src/github_manager/rules/workspace.py` (új modul) vagy a `files.py`:
   - `WorkspaceMembers._build`: `path` validálása a `RequiredFiles` szabályai szerint;
   - `apply`: `workspace.read(path)` → `yaml.safe_load` → elemenként origin-feldolgozás és létezés-ellenőrzés, a manifest sorrendjében.
4. Regisztráció: `rules/__init__.py` export és `RULE_TYPES`.
5. Tesztek:
   - `tests/test_rules_workspace.py` (`MemoryWorkspace`): minden létezik → nincs finding; minden In scope MANUAL eset; mindkét origin-formátum `.git`-tel és anélkül; ismeretlen kulcs config-hiba; nincs írás.
   - `tests/test_engine.py` (`FakeGitHub`): `fix` módban a hiányzó tag nem nyit PR-t, nem ír.
6. `github-manager.toml` és README.

## Verification
- `uv run ruff format -q . && task verify` — minden ellenőrzés sikeres.
- `uv run github-manager repos` — a valódi config betölthető.
- `uv run github-manager check -o tyutyutyu --repo zenget-workspace` (csak olvasó) — létező tagrepók esetén nincs `workspace-members` finding.

## Dependencies and risks
- Előfeltételek: a profilok bevezetése és a repók közötti olvasás.
- Kockázat: egy olyan owner tagrepója, amelyre az Appnak nincs telepítése, mindig „nem olvasható” lesz. Ez szándékos jelzés; az üzenet ezt mondja ki.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A workspace_members szabálytípus regisztrálva van; ha a path (alapértelmezés workspace.yaml) minden tagrepója létezik, nincs finding
- [x] #2 MANUAL findingot ad hiányzó vagy érvénytelen YAML manifestre, hiányzó repositories listára, name vagy origin nélküli elemre, nem támogatott originre és nem létező vagy nem olvasható tagrepóra; az üzenet megnevezi a tagot
- [x] #3 A git@github.com:OWNER/NAME és https://github.com/OWNER/NAME origin formátumot .git utótaggal és anélkül is felismeri
- [x] #4 A tagrepó létezését a Workspace-en át, a repó ownerének tokenjével kérdezi le, futásonként repónként legfeljebb egyszer
- [x] #5 A szabály check és fix módban sem ír, nem nyit PR-t és nem módosít beállítást; ismeretlen kulcs config-hiba
- [x] #6 A github-manager.toml workspace-members szabálya csak a workspace profilra vonatkozik; a README Rule types alatt van workspace_members alszakasz
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . && task verify sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz a feladathoz nem tartozó változást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-48-uj-workspace-members-szabalytipus-a-workspace-ya.

Ellenőrzés (finalizálás): `uv run ruff format -q . && task verify` exit 0 (756 passed, 1 skipped; lefedettség 99%, rules/workspace.py 100%). `uv run github-manager repos` betölti a valódi configot. `uv run github-manager check -o tyutyutyu --repo zenget-workspace` (csak olvasó): nincs workspace-members finding. A létezés-cache kulcsa kisbetűs OWNER/NAME, így eltérő írásmód egy lekérdezés.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Új `workspace_members` szabálytípus (src/github_manager/rules/workspace.py): a `path` (alapértelmezés workspace.yaml) manifest `repositories` listájának minden tagrepója létezik és olvasható. Csak MANUAL findingot ad (hiányzó/érvénytelen YAML manifest, nincs repositories lista, hiányzó name/origin, nem támogatott origin, nem létező vagy nem olvasható tagrepó); semmit nem ír. Origin: git@github.com:OWNER/NAME és https://github.com/OWNER/NAME, .git-tel vagy anélkül (szigorú fullmatch). Új csak olvasó `Workspace.repo_exists` művelet: GitHub.repo_exists (GET /repos/{repo}, az owner tokenjével; 404/401/403 → False, más hiba GitHubError), RemoteWorkspace a futásonként közös RepoFileCache-en át repónként egyszer kérdez; FakeGitHub és MemoryWorkspace bővítve. Regisztráció RULE_TYPES-ban, github-manager.toml workspace-members szabály profiles=["workspace"], README alszakasz, AGENTS.md modullista. Ellenőrzés: task verify zöld (756 passed, 1 skipped), a valódi config betölthető, a zenget-workspace élő check-je nem ad workspace-members findingot. Kockázat: App-telepítés nélküli owner tagrepója mindig 'nem olvasható' jelzést kap (szándékos, az üzenet kimondja).
<!-- SECTION:FINAL_SUMMARY:END -->
