---
id: TASK-16
title: >-
  Az enforce workflow telepítési hibájának javítása (--no-build + PyYAML) és
  füstteszt a verify-ban
status: To Do
assignee: []
created_date: '2026-11-12T12:16:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - .github/workflows/enforce.yml
  - .github/workflows/verify.yml
priority: high
type: bug
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `.github/workflows/enforce.yml` „Apply rules" lépése ezzel a paranccsal indít:
`uv run --locked --no-build github-manager "$MODE" --owner "$OWNER" ${REPO:+--repo "$REPO"}`.

2026-10-18 óta minden ütemezett futás mindkét owner jobjában itt áll meg, a program el sem indul (exit code 2):
`error: Distribution pyyaml==6.0.3 @ registry+https://pypi.org/simple can't be installed because it is marked as --no-build but has no binary distribution`.
A legutóbbi 30 futásból az utolsó 25 ütemezett futás hibás; a 10-18, 10-27, 11-06 és 11-11 napi logok szó szerint ezt a hibát adják. A központi szabályokat azóta csak a helyi futtatások érvényesítik.

Okok:
- a `--no-build` kapcsolót a `60f7213` commit vezette be (SonarCloud-lelet miatt);
- a PyYAML-t a `762a5d4` commit (TASK-5) hozta be; a `uv.lock` `pyyaml` bejegyzésében csak `sdist` van, wheel nincs (`requires-python = "==3.15.2"`);
- a uv 0.12.13-ban a `--no-build` alól nincs csomagonkénti kivétel (a `--no-build-package` az ellenkező irány).

A `verify` workflow ezt nem fogja meg: a `task verify` → `dev:install` (`.tasks/development.yml`) `uv sync --locked --all-extras --all-groups`-ot futtat `--no-build` nélkül, tehát más telepítési úton megy, és zöld.

Forrás: docs/project-review-2026-11-12.md, 2.1.

## Objective
Az `enforce` futás telepítése sikeres és a program elindul; a `verify` job elbukik, ha az `enforce` indítóparancsa nem telepíthető vagy nem indul el.

## Scope
### In scope
- A `--no-build` elhagyása az `enforce.yml` indítóparancsából.
- Füstteszt-lépés a `verify.yml` `verify` jobjában, ugyanazokkal az uv-opciókkal.
- Komment mindkét workflow-ban az opciók egyezéséről.

### Out of scope
- A kilépési kód kezelése és az `--exit-zero` (külön feladat).
- A `--no-dev` és a Renovate automerge szűkítése (külön feladat).
- A PyYAML cseréje, a Python-verzió módosítása.
- Python-kód és tesztek módosítása.

## Implementation plan
1. `.github/workflows/enforce.yml`, „Apply rules" lépés: `uv run --locked --no-build github-manager ...` → `uv run --locked github-manager ...`. Fölé rövid komment: a PyYAML-hoz nincs wheel, az sdist-et a `uv.lock` hash rögzíti (`--locked`), és az uv-opcióknak egyezniük kell a `verify.yml` füsttesztjével.
2. `.github/workflows/verify.yml`, `verify` job: új lépés a `go-task/setup-task` lépés után és a `- run: task verify` ELŐTT (még friss a környezet): `name: Smoke-test the enforce start command`, `run: uv run --locked github-manager --help`. Komment: az uv-opciók egyezzenek az `enforce.yml`-lel. A lépés a `verify` jobon belül maradjon: a ruleset a `verify` checket követeli meg, egy külön job nem blokkolná a merge-et.
3. A `--help` elég: a `github_manager` import betölti a `rich`, `yaml` és `github` (PyGithub) csomagokat.

## Verification
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- `UV_PROJECT_ENVIRONMENT="$(mktemp -d)" uv run --locked github-manager --help` — friss környezetben kiírja a használati szöveget, exit 0.
- Merge után: `gh workflow run enforce.yml -f mode=check`, majd `gh run list --workflow enforce --limit 1` és `gh run view <id> --log` — mindkét job logjában megjelenik az összesítő sor (`N repositories ...`), és nincs `can't be installed` hiba. Ennél a feladatnál a leletek miatti exit code 1 elfogadott.

## Dependencies and risks
- A SonarCloud-lelet (sdist build futtat kódot) visszatérhet: indoklás, hogy a `--locked` a lockfájl hash-ével rögzíti a forráscsomagot; a leletet elfogadottként kell jelölni.
- A kézi `enforce` futás `check` módban csak olvas, a kezelt repókba nem ír.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Az `enforce.yml` indítóparancsa nem tartalmaz `--no-build` kapcsolót, a `--locked` megmarad
- [ ] #2 A `verify.yml` `verify` jobjában a `task verify` előtt egy lépés lefuttatja a `uv run --locked github-manager --help` parancsot, ugyanazokkal az uv-opciókkal, mint az `enforce.yml`
- [ ] #3 Kézzel indított `enforce` futásban (`mode=check`) mindkét owner jobja eljut az összesítő sorig, telepítési hiba nélkül
- [ ] #4 Mindkét workflow-ban komment jelzi, hogy az uv-opcióknak egyezniük kell
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 A kézi `enforce` futás eredménye (futás azonosítója, a jobok állapota) rögzítve van a feladat jegyzetében
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
