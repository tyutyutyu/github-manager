---
id: TASK-28
title: >-
  Kézzel indítható integrációs teszt homokozó repón: a compliance PR életciklusa
  a valódi GitHubon
status: To Do
assignee: []
created_date: '2026-11-12T12:33:00Z'
labels: []
dependencies:
  - TASK-17
references:
  - docs/project-review-2026-11-12.md
  - tests/conftest.py
  - src/github_manager/engine.py
  - .tasks/development.yml
  - pyproject.toml
priority: medium
type: enhancement
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Minden teszt fake-ekre épül: a motor a `FakeGitHub`-ra (`tests/conftest.py`), a kliens a `FakeHttp`-re (`tests/test_github.py`). Ezek a GitHub *feltételezett* viselkedését modellezik. A 2026-11-12-i felülvizsgálat két legsúlyosabb lelete (az `enforce` telepítési hibája, illetve hogy a branch-reset lezárja a nyitott compliance PR-t) a fake és a valóság közti résben volt, 99,4%-os lefedettség mellett.

Hiányzik egy kicsi, a valódi GitHubon futó teszt, amely a motor PR-életciklusát igazolja, és megmutatja, ha a GitHub másképp viselkedik, mint a fake.

Forrás: docs/project-review-2026-11-12.md, 5.4.

## Objective
Egy kézzel indítható integrációs teszt egy erre fenntartott homokozó repón végigviszi a compliance PR életciklusát a valódi GitHub API-n; az alapértelmezett tesztfutás és a CI ezt nem futtatja.

## Scope
### In scope
- Új tesztfájl `integration` markerrel, környezeti változóval kapcsolva.
- Marker regisztrálása, külön fejlesztői task, README-leírás.

### Out of scope
- Futtatás CI-ban, titkok felvétele a repóba.
- A beállítások, rulesetek és az auto-merge integrációs tesztje.
- A homokozó repó létrehozása (a tulajdonos kézi előfeltétele).
- Írás bármely más repóba.

## Implementation plan
1. `pyproject.toml`, `[tool.pytest]`: `markers = ["integration: talks to the real GitHub API; needs GITHUB_MANAGER_SANDBOX_REPO"]` (a `strict = true` miatt a marker regisztrálása kötelező).
2. Új fájl: `tests/test_integration_github.py`, modulszintű `pytestmark = pytest.mark.integration`.
   - Ha a `GITHUB_MANAGER_SANDBOX_REPO` (`OWNER/NAME`) nincs beállítva: `pytest.skip`.
   - Védelem: ha a repó neve nem tartalmazza a `sandbox` szót, a teszt hibával megáll, mielőtt bármit hívna.
   - Kliens: `GitHub(resolve_token())`.
   - Saját, szintetikus `Config` a tesztben (`parse_config`): `owners = [<owner>]`, egy `required_lines` szabály egy erre szolgáló fájlra (pl. `.github-manager-sandbox`), saját ágnév (pl. `github-manager/integration-test`), `auto_merge = false`. A teszt nem tölti be a `github-manager.toml`-t, és csak a megadott repóra hívja a `process_repo`-t.
3. Forgatókönyv (egy tesztfüggvény, lépésenkénti assertekkel):
   a. előkészítés: az esetleg megmaradt nyitott PR lezárása, a teszt ágainak törlése, a kezelt fájl eltávolítása vagy nem megfelelő állapotba hozása a default ágon;
   b. `process_repo(..., fix=True)` → `Outcome.PR_CREATED`, a PR nyitva van;
   c. a default ág elmozdítása egy ártalmatlan commit-tal (pl. időbélyeget tartalmazó fájl, `api.commit_files` a default ágra);
   d. `process_repo` → `Outcome.PR_UPDATED`, a `find_open_pr` ugyanazt a PR-számot adja (ez a branch-reset hiba valós regressziós tesztje);
   e. `process_repo` változás nélkül → `Outcome.PR_UP_TO_DATE`;
   f. a default ág megfelelővé tétele (a kezelt blokk commitolása a default ágra) → `process_repo` → `Outcome.PR_CLOSED`, a compliance ág törölve.
4. Takarítás `try/finally`-ban vagy fixture-rel: a teszt PR-jának lezárása és az ágak törlése hiba esetén is.
5. `.tasks/development.yml`: új `test-integration` task: `uv run pytest -m integration --no-cov {{.CLI_ARGS}}`. A `test` és a `verify` task változatlan: változó nélkül a teszt kihagyva jelenik meg.
6. `README.md`, „Development": előfeltételek (homokozó repó, amelynek a default ágára közvetlenül lehet pusholni, és amely nincs a szabályok hatókörében: vagy nem a konfigurált ownerek alatt van, vagy szerepel a globális `exclude` listán), és a futtatás: `GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> task dev:test-integration`.

## Verification
- `uv run pytest tests/test_integration_github.py --no-cov -rs` változó nélkül — a teszt `skipped`, hálózati hívás nélkül.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld, a lefedettségi küszöb teljesül.
- `GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> task dev:test-integration` — a teszt zöld a valódi repón; utána `gh pr list --repo <owner>/<name> --state open` üres, és a teszt ágai nem léteznek.
- `GITHUB_MANAGER_SANDBOX_REPO=owner/app task dev:test-integration` — a névvédelem miatt azonnal hibával megáll, hívás nélkül.

## Dependencies and risks
- Előfeltétel a compliance PR frissítésének javítása (staging ág): nélküle a d. lépés a valódi GitHubon elbukik.
- Előfeltétel a tulajdonos részéről: egy homokozó repó megadása. Enélkül a valódi futtatást igazoló elfogadási feltétel nem teljesíthető, és a feladat nem zárható le.
- A teszt valódi PR-t, ágakat és commitokat hoz létre a homokozó repóban; a névvédelem és a szintetikus konfiguráció biztosítja, hogy máshová ne írjon.
- Ha a GitHub a fake-től eltérően viselkedik, a `FakeGitHub`-ot kell a megfigyelt viselkedéshez igazítani, regressziós teszttel.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `GITHUB_MANAGER_SANDBOX_REPO` változó nélkül az integrációs teszt kihagyva (skipped) jelenik meg, a `task verify` zöld, és nem történik hálózati hívás
- [ ] #2 A változó megadásával a `task dev:test-integration` a valódi repón végigviszi az életciklust: PR létrejön → a default ág elmozdul → ugyanaz a nyitott PR frissül → naprakész → a PR lezárul és az ága törlődik
- [ ] #3 A teszt csak a megadott repóba ír: saját szintetikus konfigurációt használ, nem tölti be a `github-manager.toml`-t, és megtagadja a futást, ha a repó neve nem tartalmazza a `sandbox` szót
- [ ] #4 A teszt a végén, hiba esetén is, lezárja a saját PR-ját és törli az ágait
- [ ] #5 Az `integration` marker regisztrálva van, és a README „Development" szakasza leírja az előfeltételeket és a futtatást
- [ ] #6 A valódi homokozó repón futtatott teszt eredménye rögzítve van a feladat jegyzetében
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
