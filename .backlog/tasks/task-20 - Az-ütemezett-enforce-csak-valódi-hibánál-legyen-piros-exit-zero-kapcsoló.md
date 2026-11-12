---
id: TASK-20
title: 'Az ütemezett enforce csak valódi hibánál legyen piros: --exit-zero kapcsoló'
status: To Do
assignee: []
created_date: '2026-11-12T12:16:00Z'
labels: []
dependencies:
  - TASK-16
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/cli.py
  - .github/workflows/enforce.yml
  - tests/test_cli.py
  - README.md
priority: medium
type: enhancement
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `main` (`src/github_manager/cli.py`) kilépési kódjai: `EXIT_OK = 0`; `EXIT_FINDINGS = 1`, ha lelet maradt (`check`: bármely finding, `fix`: csak a *manual* findingok); `EXIT_ERROR = 2` konfigurációs vagy API-hibánál, illetve ha bármely repó `Outcome.ERROR`.

Az Actions felületen az `1` és a `2` egyaránt piros. A flottában jellemzően van kézi lelet (láthatóság, hiányzó fájl), így a napi `enforce` futás működő állapotban is többnyire piros. Emiatt a 2026-10-18 óta tartó teljes leállás (telepítési hiba, exit code 2) ugyanúgy nézett ki, mint egy átlagos nap, és 25 napig nem tűnt fel.

Forrás: docs/project-review-2026-11-12.md, 2.4.

## Objective
Az ütemezett `enforce` job csak hiba (kilépési kód 2) esetén piros; a megmaradó leletek zöld futásban, figyelmeztetésként látszanak.

## Scope
### In scope
- `--exit-zero` kapcsoló a `check` és a `fix` parancson.
- Egy `::warning` annotáció GitHub Actions alatt, ha lelet maradt.
- Az `enforce.yml` indítóparancsa használja a kapcsolót.
- Tesztek, README („Exit codes", „Scheduled run").

### Out of scope
- Az alapértelmezett kilépési kódok megváltoztatása (kapcsoló nélkül minden marad).
- Követő issue vagy más csatorna a kézi leletekre.
- Külön jelzés arra, ha N napja nem volt sikeres futás: ha a piros csak hibát jelent, a GitHub hibás futásról küldött értesítése elegendő.

## Implementation plan
1. `src/github_manager/cli.py`, `build_parser`: `--exit-zero` (`action="store_true"`) a `check` és a `fix` parancson, a meglévő `for command in (check, fix)` ciklusban; help: `exit with 0 when findings remain (errors still exit with 2)`.
2. `main`: az `EXIT_ERROR` ágak változatlanok és elsőbbséget élveznek. Ha lelet maradt és `args.exit_zero` igaz, a visszatérés `EXIT_OK`, különben `EXIT_FINDINGS`.
3. Annotáció: ha `os.environ.get("GITHUB_ACTIONS") == "true"` és lelet maradt (a kapcsolótól függetlenül), pontosan egy sor kerül a stdoutra: `::warning title=github-manager::<n> repositories with unresolved findings`, ahol `<n>` a megmaradó lelettel rendelkező repók száma (`check`: van finding; `fix`: van *manual* finding). A sor a sor elején kezdődjön, ANSI-kód és rich-formázás nélkül, különben az Actions nem ismeri fel.
4. `.github/workflows/enforce.yml`, „Apply rules" lépés: `github-manager "$MODE" --exit-zero --owner "$OWNER" ...`. Az uv-opciók nem változnak.
5. `tests/test_cli.py` (a `run` segédfüggvénnyel és a `config_path` fixture-rel):
   - `check --exit-zero` lelettel → `EXIT_OK`; `fix --exit-zero` *manual* lelettel → `EXIT_OK`;
   - `--exit-zero` mellett repó-hiba → `EXIT_ERROR`; hiányzó konfiguráció → `EXIT_ERROR`;
   - kapcsoló nélkül a meglévő elvárások változatlanok;
   - `monkeypatch.setenv("GITHUB_ACTIONS", "true")` és lelet: a kimenetben pontosan egy `::warning title=github-manager::` kezdetű sor van a helyes számmal; lelet nélkül nincs; a változó nélkül nincs.
6. `README.md`: az „Exit codes" bekezdés kiegészítése a kapcsolóval; a „Scheduled run" szakaszban: az ütemezett futás `--exit-zero`-val megy, a piros futás hibát jelent, a leletek a job summary-ben és figyelmeztetésként látszanak.

## Verification
- `uv run pytest tests/test_cli.py --no-cov` — az új és a meglévő CLI-tesztek zöldek.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- Merge után: `gh workflow run enforce.yml -f mode=check`; a futás zöld, a futás oldalán megjelenik a figyelmeztetés, ha vannak leletek.

## Dependencies and risks
- Előfeltétel az enforce telepítési hibájának javítása: ugyanazt a sort módosítja az `enforce.yml`-ben, és nélküle a futás el sem jut a programig.
- Kockázat: zöld futásban a leletek kevésbé feltűnőek; ezt az annotáció és a job summary ellensúlyozza.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `check --exit-zero` és a `fix --exit-zero` 0-val lép ki, ha csak leletek maradtak
- [ ] #2 `--exit-zero` mellett is 2 a kilépési kód konfigurációs hibánál, API-hibánál és akkor, ha bármely repó `error` eredményű
- [ ] #3 Kapcsoló nélkül a kilépési kódok változatlanok (0, 1, 2)
- [ ] #4 GitHub Actions alatt, megmaradó leletek esetén pontosan egy `::warning title=github-manager::` kezdetű sor jelenik meg a stdouton az érintett repók számával; leletek nélkül és Actions-en kívül nem
- [ ] #5 Az `enforce.yml` indítóparancsa `--exit-zero`-t használ
- [ ] #6 A README „Exit codes" és „Scheduled run" része leírja a kapcsolót és azt, hogy az ütemezett futásban a piros hibát jelent
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
