---
id: TASK-32
title: >-
  A workflow-YAML segédek tisztítása: duplikációk megszüntetése és névvel
  ellátott típusok
status: Done
assignee: []
created_date: '2026-11-12T23:54:00Z'
updated_date: '2026-11-13T22:41:00Z'
labels: []
dependencies:
  - TASK-22
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
priority: low
type: chore
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A workflow-fájlokat elemző kód (a `rules.py` csomaggá bontása után a `src/github_manager/rules/workflows.py`, illetve ha az a bontáskor kettévált, a YAML-segédek modulja) négy karbantarthatósági gondot hordoz:

1. A `_labels(node)` és a `_patterns(node)` függvény törzse szó szerint azonos („string vagy stringek listája → `list[str]`, minden másra `None`"); csak a docstring és a paraméter típusa (`yaml.Node | None`, illetve `yaml.Node`) tér el. Hívók: `_shown`, `_push_filter_problem`, `_filter_problem` (kétszer) → `_patterns`; `SelfHostedRunners._rewritable` → `_labels`.
2. A `yaml.compose(text, Loader=yaml.SafeLoader)` hívás és a `yaml.YAMLError` kezelése háromszor szerepel: `_push_only_problem`, `_file_problem`, `_jobs`. Az üzenet mindhárom helyen `invalid YAML (<exc.problem>)`; egyetlen eltérés, hogy `problem` nélküli kivételnél a `_jobs` `invalid YAML (invalid YAML)`-t, a másik kettő `invalid YAML (invalid)`-ot ad. A `jobs` leképezés kiolvasása (`top = _mapping(root)`, majd `_mapping(top.get("jobs"))`) a `_file_problem`-ben és a `_jobs`-ban is megvan.
3. A `_file_problem` szakaszai egy `range(7)` kibontásából kapják az értéküket (`_UNREADABLE`, `_NO_JOB`, `_JOB_UNUSABLE`, `_NO_TRIGGER`, `_TYPES_FILTER`, `_BRANCH_FILTER`, `_PATH_FILTER`); a `_Problem.stage` típusa `int`. Új szakasz beszúrásakor a számot kézzel kell igazítani.
4. A `_jobs(text)` névtelen `(jobs, error)` párt ad vissza; hívói a `SelfHostedRunners._check_file` és a `SelfHostedRunners._verified`.

A tesztek csak publikus neveket importálnak a `github_manager.rules`-ból (a szabályosztályokat, valamint: `Finding`, `RULE_TYPES`, `NOT_READABLE`, `ruleset_matches`); a fenti segédeket nem.

Forrás: docs/project-review-2026-11-12.md, 4.3 (1., 6. és 8. sor).

## Objective
A workflow-YAML segédekben minden logika egy helyen van és névvel ellátott típusokat használ, a szabályok megfigyelhető viselkedésének változása nélkül.

## Scope
### In scope
- A `_labels` és a `_patterns` összevonása egy függvénybe.
- Egyetlen `yaml.compose` hívási hely és egyetlen `jobs`-kiolvasás.
- `IntEnum` a szakaszokra; névvel ellátott visszatérési típus a `_jobs`-ra.

### Out of scope
- Bármely szabály viselkedése és hibaüzenete (az alább megnevezett egyetlen kivétellel).
- A `_json`, a `_text`, a `_mapping` és az `_entry` logikája; a `_pull_request_trigger` és az `_entry` visszatérési típusa.
- A `tests/` könyvtár bármely fájljának módosítása.
- A workflow-modul(ok)on kívüli kód.

## Implementation plan
1. Új `_strings(node: yaml.Node | None) -> list[str] | None` a közös törzzsel és semleges docstringgel; a `_labels` és a `_patterns` törlése; az öt hívó átállítása.
2. Új segéd a parszolásra, pl. `_compose(text: str) -> _Document`, ahol a `_Document` `NamedTuple` (`root: yaml.Node | None`, `error: str | None`); hiba esetén `error = f"invalid YAML ({getattr(exc, 'problem', None) or 'invalid'})"`. A `_push_only_problem`, a `_file_problem` és a `_jobs` ezt hívja; ezután pontosan egy `yaml.compose` hívás marad. A hívók saját ágai változatlan szöveggel a hívóban maradnak (`_push_only_problem`: „the root is not a mapping"; `_file_problem` és `_jobs`: „no 'jobs' mapping"). Megengedett egyetlen üzenetváltozás: `problem` nélküli `YAMLError` esetén a `_jobs` üzenete `invalid YAML (invalid YAML)` helyett `invalid YAML (invalid)`.
3. A `jobs` leképezés kiolvasása közös segédbe kerül (pl. `_jobs_of(root: yaml.Node | None) -> dict[str, yaml.Node] | None`), amelyet a `_file_problem` és a `_jobs` is használ.
4. `class _Stage(IntEnum)` a hét taggal, a mai sorrendben (`UNREADABLE` … `PATH_FILTER`); `_Problem.stage: _Stage`; a modulszintű `_UNREADABLE` stb. nevek helyett `_Stage.UNREADABLE` stb. A `_workflow_check_problem` `max(problems, key=...)` kiválasztásának eredménye nem változhat.
5. A `_jobs` visszatérési típusa `NamedTuple` (pl. `_Jobs` `entries` és `error` mezővel); a két hívó mezőnévvel éri el.
6. A docstringek és kommentek igazítása az új nevekhez.

## Verification
- `git diff --stat main -- tests` — üres: a tesztek nem változtak.
- `grep -rn "_labels\|_patterns\|range(7)" src/github_manager/rules/` — nincs találat.
- `grep -rn "yaml.compose(" src/github_manager/rules/ | wc -l` — az eredmény 1.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld, a lefedettség nem csökken.

## Dependencies and risks
- Előfeltétel a `rules.py` csomaggá bontása (tiszta áthelyezés): e feladat arra a szerkezetre épül, és a két diff így nem keveredik.
- A `runs-on` érték korlátos megjelenítése (`_json`) ugyanebben a modulban dolgozik; a két feladat független, a másodikként készülő a friss `main`-re építsen.
- Az egyenértékűség bizonyítéka a változatlan tesztkészlet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `_labels` és a `_patterns` helyett egyetlen függvény adja a „string vagy stringlista" értékét, és mind az öt korábbi hívó azt használja
- [x] #2 A workflow-modul(ok)ban pontosan egy `yaml.compose` hívás van, és a YAML-hiba üzenete egy helyen készül
- [x] #3 A `jobs` leképezés kiolvasása egyetlen függvényben van
- [x] #4 A szakaszok egy `IntEnum` tagjai, a `_Problem.stage` típusa ez az enum, és a „legközelebb jutott fájl" kiválasztása változatlan
- [x] #5 A `_jobs` névvel ellátott mezőjű típust ad vissza
- [x] #6 A `tests/` könyvtár nem módosult, és minden teszt zöld; a hibaüzenetek változatlanok, kivéve a `problem` nélküli YAML-hiba `_jobs`-beli tartalékszövegét
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-32-a-workflow-yaml-segedek-tisztitasa-duplikaciok-m.

Ellenőrzés a lezáráskor: a `git diff --stat main -- tests` üres; a `_labels\|_patterns\|range(7)` grep nem talál semmit; a `yaml.compose(` pontosan egyszer szerepel (a `_compose`-ban). `uv run ruff format -q . && task verify` zöld: 613 teszt sikeres, 1 kihagyva (nincs beállítva a GITHUB_MANAGER_SANDBOX_REPO), a lefedettség 99,45%. A main ágon ugyanennyi a nem lefedett sor (5) és a részleges ág (6), vagyis a lefedettség nem csökkent. A `_file_problem` őrfeltétele `root is None or jobs is None` lett, hogy a ty típusellenőrzés elfogadja; a viselkedés ugyanaz, mert None gyökérre a `_jobs_of` is None-t ad.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A workflow-YAML segédek (src/github_manager/rules/workflows.py) tisztítása, a szabályok viselkedésének változása nélkül. A `_labels` és a `_patterns` helyett egy `_strings` függvény van, és mind az öt hívó ezt használja. Egyetlen `_compose` segéd hívja a `yaml.compose`-t, és csak itt készül az `invalid YAML (...)` üzenet; a `_Document` NamedTuple-t adja vissza. A `jobs` leképezést csak a `_jobs_of` olvassa ki. A szakaszok a `_Stage(IntEnum)` tagjai, a sorrend a régi, így a `max`-alapú kiválasztás sem változott. A `_jobs` `_Jobs(entries, error)` NamedTuple-t ad vissza. Egyetlen, engedélyezett üzenetváltozás van: `problem` nélküli YAMLError esetén a `_jobs` most `invalid YAML (invalid)` üzenetet ad. Ellenőrzés: a tests/ nem változott, a `task verify` zöld (613 sikeres, 1 kihagyott integrációs teszt), a lefedettség 99,45%, ugyanannyi, mint a main ágon. Kockázat: alacsony, belső, privát segédeket érint.
<!-- SECTION:FINAL_SUMMARY:END -->
