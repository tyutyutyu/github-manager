---
id: TASK-35
title: 'required_lines és renovate_preset: a meglévő sorvégek (CRLF) megtartása'
status: To Do
assignee: []
created_date: '2026-11-12T23:54:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
  - tests/test_rules.py
  - README.md
priority: low
type: bug
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `RequiredLines.apply` (`github_manager.rules`) a fájlt `content.splitlines()`-szal bontja sorokra, és az eredményt `"\n".join(...) + "\n"`-nel állítja össze, ezért a CRLF sorvégű fájlt teljes egészében LF-re írja át. Kipróbálva a tesztek `MemoryWorkspace`-ével (2026-11-13), `id = "r"`, `lines = "x"` szabállyal:

- Bemenet: `a\r\nb\r\n` → lelet: `managed block is missing`; az új tartalom `a\nb\n\n# >>> github-manager: r\nx\n# <<< github-manager: r\n` — minden meglévő sor megváltozott.
- Bemenet: `a\r\n# >>> github-manager: r\r\nx\r\n# <<< github-manager: r\r\n` (a blokk már helyes) → lelet: `missing final newline` (téves), és a fájl LF-re íródik át.

A második eset szerint egy CRLF sorvégű, egyébként megfelelő fájl soha nem számít megfelelőnek, amíg a compliance PR át nem írja az egészet.

A `RenovatePreset` hasonlóan viselkedik a `_rewrite_extends` / `_render_array` függvényekben (kipróbálva):
- többsoros `extends` tömb CRLF fájlban: az újraírt tömb sorai LF-fel készülnek (`",\n".join`), a fájl többi része CRLF marad → kevert sorvégek: `{\r\n  "extends": [\n    "local>x/y"\n  ]\r\n}\r\n`;
- ha az `extends` hiányzik, a tartalék ág a teljes dokumentumot `json.dumps`-szal írja újra, LF-fel.

A `self_hosted_runners` már megtartja a sorvégeket (teszt: `test_self_hosted_runners_rewrite_keeps_line_endings`).

Forrás: docs/project-review-2026-11-12.md, 4.4 (CRLF sorvégek).

## Objective
A `required_lines` és a `renovate_preset` szabály a fájl meglévő sorait bájtra változatlanul hagyja, az általa írt sorokat a fájl uralkodó sorvégével írja, és pusztán sorvég-eltérés miatt nem jelez leletet.

## Scope
### In scope
- A két szabály írási logikája; közös segéd az uralkodó sorvég megállapítására.
- Tesztek mindkét szabályra; README-pontosítás.

### Out of scope
- `file_sync`: ott a sablon a mérvadó, a fájl a sablon pontos mása lesz.
- Új fájl létrehozása (pl. hiányzó `renovate.json`): LF marad.
- A sorvégek egységesítése, `.gitattributes`- vagy `.editorconfig`-szabály.
- A `str.splitlines` által kezelt egyéb sorelválasztó karakterek külön kezelése.

## Implementation plan
1. Közös segéd (a `rules.py` csomaggá bontása után a `src/github_manager/rules/base.py`-ban, előtte a `rules.py`-ban), pl. `_newline(text: str) -> str`: `"\r\n"`, ha a `\r\n`-re végződő sorok száma nagyobb, mint a csak `\n`-re végződőké; különben `"\n"` (üres szövegnél és döntetlennél is).
2. `RequiredLines.apply`:
   - a sorokra bontás tartsa meg a sorvégeket (`splitlines(keepends=True)`); a jelölők és a `remove_lines` összevetése továbbra is `strip()` után történik, a blokk tartalmáé a sor sorvég nélküli szövegével;
   - a blokkon kívüli megmaradó sorok változatlan bájtokkal kerülnek az eredménybe;
   - ha a meglévő blokk tartalma megegyezik a kívánttal, a blokk sorai is változatlanok; különben a blokk minden sora az uralkodó sorvéggel készül;
   - a blokk elé beszúrt üres sor és a fájl végéről hiányzó sorvég az uralkodó sorvéggel készül;
   - a leletek szövege és feltételei változatlanok (`managed block is missing`, `managed block is outdated`, `unwanted lines: ...`, `missing final newline`), de pusztán sorvég-eltérés miatt nem keletkezik lelet, és nem történik írás.
3. `RenovatePreset`: a `_render_array` többsoros ága a régi tömbben talált sorvéget használja (`"\r\n"`, ha az `old_array` tartalmazza; különben `"\n"`); a `_rewrite_extends` tartalék ága az eredményt az eredeti szöveg uralkodó sorvégére alakítja. Az „csak az `extends` tömb változik, újraparszolással ellenőrizve" működés változatlan.
4. Tesztek a szabálytesztek között (`tests/test_rules.py`; a tesztfájl szétbontása után `tests/test_rules_files.py` és `tests/test_rules_renovate.py`), a `test_self_hosted_runners_rewrite_keeps_line_endings` mintájára sorvégre paraméterezve (`"\n"`, `"\r\n"`):
   - blokk nélküli fájl: a régi sorok bájtra változatlanok, a blokk az adott sorvéggel kerül a végére;
   - helyes blokkú fájl: nincs lelet, nincs írás;
   - elavult blokk: csak a blokk sorai változnak;
   - `remove_lines`: csak a törlendő sor tűnik el;
   - kevert sorvégű fájl: az érintetlen sorok megtartják a saját sorvégüket, az új sorok az uralkodót kapják;
   - sorvég nélküli utolsó sor: `missing final newline`, a pótlás az uralkodó sorvég;
   - Renovate: többsoros és egysoros `extends` CRLF fájlban, valamint a tartalék ág — az eredményben nincs csupasz `\n`.
5. `README.md`: a `required_lines` és a `renovate_preset` leírásába egy-egy tagmondat: a meglévő sorvégek megmaradnak.

## Verification
- `uv run pytest tests -k "required_lines or renovate" --no-cov` — az új és a meglévő tesztek zöldek.
- `git diff main -- tests` — a meglévő tesztek törzse nem változott, csak új tesztek kerültek be.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.

## Dependencies and risks
- A `rules.py` csomaggá bontása és a `tests/test_rules.py` szétbontása ugyanezt a kódot mozgatja. A feladat szimbólumokra hivatkozik (`RequiredLines.apply`, `_rewrite_extends`, `_render_array`); a másodikként készülő a friss `main`-re építsen.
- Viselkedésváltozás: a kevert sorvégű fájlok ma LF-re egységesülnek, ezután nem. Ez szándékos: a szabály dolga a blokk, nem a sorvégek egységesítése.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CRLF sorvégű fájlban a `required_lines` a blokkot CRLF-fel írja, és a blokkon kívüli sorok bájtra változatlanok
- [ ] #2 Olyan fájlra, amely a sorvégektől eltekintve megfelel (helyes blokk, nincs törlendő sor, van záró sorvég), a `required_lines` nem ad leletet és nem ír — CRLF és kevert sorvég mellett sem
- [ ] #3 Kevert sorvégű fájlban az érintetlen sorok megtartják a saját sorvégüket; az új sorok az uralkodó sorvéget kapják (döntetlennél és üres fájlnál LF-et)
- [ ] #4 A `renovate_preset` által átírt CRLF fájlban nem marad csupasz LF: sem a többsoros `extends` tömbben, sem a teljes újraírás tartalék ágán
- [ ] #5 LF sorvégű fájlokra mindkét szabály kimenete megegyezik a változtatás előttivel: a meglévő tesztek módosítás nélkül zöldek
- [ ] #6 A README megemlíti, hogy a két szabály megtartja a meglévő sorvégeket
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
