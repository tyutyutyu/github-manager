---
id: TASK-39
title: >-
  Valódi kiadások: verzióemeléskor automatikus git tag és GitHub Release
  generált kiadási jegyzettel
status: To Do
assignee: []
created_date: '2026-11-12T23:54:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - pyproject.toml
  - .tasks/development.yml
  - .tasks/entrypoints.yml
  - .github/workflows/verify.yml
  - README.md
  - >-
    https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes
priority: low
type: enhancement
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A csomag verziója `0.1.0` (`pyproject.toml`); a repóban nincs git tag és nincs GitHub Release. A verzió emelésére van target (`task version-bump -- patch|minor|major` → `dev:version-bump` → `uv version --bump`; `.tasks/entrypoints.yml`, `.tasks/development.yml`; README, „Development"), de az emelésnek nincs következménye: a verziót semmi nem használja, és nem követhető, melyik állapot melyik verzió. Az `enforce` mindig a `main` csúcsáról fut.

Döntés (2026-11-13, tulajdonos): a verziót ténylegesen használjuk — verzióemeléskor git tag, GitHub Release és changelog készül; az `enforce` továbbra is a `main`-ről fut.

Adottságok:
- A `main` ágat a kezelt ruleset védi (PR kötelező, squash merge, nincs bypass actor), ezért a verzióemelés PR-ban történik, és workflow nem pusholhat a `main`-re. A ruleset csak a default ágra vonatkozik; tag létrehozását nem tiltja.
- A PR-ok squash merge-dzsel, conventional commit címmel kerülnek a `main`-re; a függőségfrissítő PR-ok címe `chore(deps): ...`.
- A workflow-k action-jei teljes SHA-ra pineltek (`.github/workflows/verify.yml`: `actions/checkout`, `astral-sh/setup-uv`), a jogosultság alapból `contents: read`.
- Nincs `.github/release.yml` és nincs `CHANGELOG.md`.

Forrás: docs/project-review-2026-11-12.md, 6.5 (Verziózás).

## Objective
Amikor a `main`-re olyan `pyproject.toml` kerül, amelynek verziójához még nincs kiadás, automatikusan létrejön a `v<verzió>` tag és a hozzá tartozó GitHub Release, generált kiadási jegyzettel.

## Scope
### In scope
- Új `release` workflow.
- `.github/release.yml` a kiadási jegyzet kategóriáihoz.
- README „Releases" szakasz.

### Out of scope
- Csomag közzététele (PyPI vagy más registry) és build artifact csatolása a kiadáshoz.
- Az `enforce` futtatása tagről; `--version` kapcsoló a CLI-ben.
- Kézzel vezetett `CHANGELOG.md`: a changelog a GitHub által a PR-címekből generált kiadási jegyzet.
- A `version-bump` target módosítása és az automatikus verzióemelés.
- Az első kiadás tényleges létrehozása (merge utáni tulajdonosi lépés).

## Implementation plan
1. Új fájl: `.github/workflows/release.yml`.
   - `on`: `push` a `main` ágra `paths: [pyproject.toml]` szűrővel, valamint `workflow_dispatch` (az első kiadáshoz és újrafuttatáshoz).
   - `permissions: contents: write` (csak ebben a workflow-ban); `concurrency` csoport `cancel-in-progress: false` beállítással; `timeout-minutes`; `runs-on: ubuntu-latest` (a repó publikus).
   - Lépések: `actions/checkout` (`persist-credentials: false`) és `astral-sh/setup-uv`, ugyanazzal a pinelt SHA-val és verzió-megjegyzéssel, mint a `verify.yml`-ben; a verzió kiolvasása `uv version --short` paranccsal; ha a `gh release view "v$VERSION"` sikeres → kilépés 0-val, „already released" üzenettel; különben `gh release create "v$VERSION" --target "$GITHUB_SHA" --title "v$VERSION" --generate-notes`. A `gh` a tokent a `GH_TOKEN: ${{ github.token }}` környezeti változóból kapja.
   - A `run` szkript nem tartalmazhat `${{ }}` kifejezést (minden érték környezeti változón át érkezik), és tag képzése előtt ellenőrzi, hogy a verzió `X.Y.Z` alakú.
2. Új fájl: `.github/release.yml` a generált jegyzet kategóriáival: külön „Dependencies" kategória a függőségfrissítő PR-oknak, a többi változás a „Changes" kategóriában. A szűrés alapja (szerző vagy címke) az legyen, amit a repó merge-elt PR-jai ténylegesen hordoznak: `gh pr list --state merged --limit 5 --json author,labels,title`.
3. `README.md`: új „Releases" szakasz a „Development" után: a kiadás menete (PR-ban `task version-bump -- <scope>` → merge → a `release` workflow létrehozza a taget és a kiadást); a verziószámozás elve (SemVer: `patch` hibajavítás, `minor` új szabálytípus vagy kapcsoló, `major` inkompatibilis konfiguráció- vagy CLI-változás); és hogy az `enforce` a `main`-ről fut, nem tagről.
4. A `github-manager.toml`, a `version-bump` target, az `enforce.yml` és a `verify.yml` nem módosul.
5. Merge utáni tulajdonosi lépés (nem része a diffnek; a feladat jegyzetében rögzítendő): a `release` workflow kézi indítása, amely létrehozza a `v0.1.0` kiadást.

## Verification
- `uv run python -c "import sys, yaml; [yaml.safe_load(open(p, encoding='utf-8')) for p in sys.argv[1:]]" .github/workflows/release.yml .github/release.yml` — mindkét fájl érvényes YAML.
- `uv version --short` — `X.Y.Z` alakú kimenet (ezt olvassa a workflow).
- `grep -n "uses:" .github/workflows/release.yml` — minden action teljes SHA-ra pinelt, a `verify.yml`-ével azonos értékekkel.
- `grep -n '\${{' .github/workflows/release.yml` — találat csak `env:` és `with:` blokkban, `run:` szkriptben nincs.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- Merge után (tulajdonos): a workflow kézi indítása → `gh release view v0.1.0` sikeres, és a `git ls-remote --tags origin v0.1.0` megadja a taget; a workflow újraindítása „already released" üzenettel, hiba nélkül ér véget.

## Dependencies and risks
- A kiadás létrehozása kifelé látható és nehezen visszavonható művelet: az első futtatás a tulajdonosé.
- A függőségfrissítő PR-ok is módosítják a `pyproject.toml`-t: a workflow ilyenkor lefut, de a meglévő kiadás miatt nem változtat semmit.
- Ha később megváltozik a PR-ok szerzője vagy címkézése, a `.github/release.yml` kategóriáit felül kell vizsgálni.
- A `contents: write` jogosultság csak ebben a workflow-ban és csak a repó saját tokenjével él; a flotta tokenjei nincsenek a jobban.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `main`-re kerülő `pyproject.toml`-változás után, ha a verzióhoz még nincs kiadás, a `release` workflow létrehozza a `v<verzió>` taget az adott commiton és a GitHub Release-t generált kiadási jegyzettel
- [ ] #2 Ha a verzióhoz már van kiadás, a workflow hiba és változtatás nélkül ér véget
- [ ] #3 A workflow kézzel is indítható; az action-jei teljes SHA-ra pineltek; `contents: write` jogosultsága csak ennek a workflow-nak van; a `run` szkript nem tartalmaz `${{ }}` kifejezést
- [ ] #4 A generált jegyzetben a függőségfrissítések külön kategóriában jelennek meg (`.github/release.yml`)
- [ ] #5 A README „Releases" szakasza leírja a kiadás menetét, a verziószámozás elvét, és azt, hogy az `enforce` a `main`-ről fut
- [ ] #6 A `version-bump` target, valamint az `enforce` és a `verify` workflow változatlan
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Az első kiadás létrehozásának módja (a workflow kézi indítása) a feladat jegyzetében szerepel
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
