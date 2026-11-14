---
id: TASK-36
title: >-
  renovate_preset: a .json5 konfigban a preset csak az extends tömb elemeként
  számítson
status: Done
assignee: []
created_date: '2026-11-12T23:54:00Z'
updated_date: '2026-11-14T01:03:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
  - tests/test_rules.py
  - README.md
priority: low
type: bug
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `RenovatePreset.apply` (`github_manager.rules`) a `.json5` végű Renovate-konfigot nem parszolja (a standard könyvtárban nincs JSON5-olvasó), hanem a `_manual(path, text)` metódussal ellenőrzi: megfelelő, ha a preset neve bárhol szerepel a szövegben (`if self.preset in text`); különben kézi lelet (`<path>: does not extend <preset>`).

Kipróbálva a tesztek `MemoryWorkspace`-ével (2026-11-13), `preset = "local>x/y"` mellett az alábbi `renovate.json5` tartalmak mind megfelelőnek számítanak, pedig egyik sem terjeszti ki a presetet:
- `{ // TODO extend local>x/y` + újsor + `}` — a név csak sorkommentben áll;
- `{ /* local>x/y */ extends: ['config:base'] }` — csak blokk-kommentben;
- `{ description: 'see local>x/y', extends: [] }` — más kulcs értékében;
- `{ extends: ['local>x/y-other'] }` — egy másik preset nevének elejeként.

A hatókörben lévő repókban ma nincs `.json5` Renovate-konfig (29 konfig, mind `.json`; 2026-11-13), így a javítás a jelenlegi eredményeket nem változtatja meg; a hiba az első ilyen fájl megjelenésekor ütne.

Meglévő tesztek: a `renovate_preset` szakasz „does not extend" paraméterezett esete és a `test_renovate_accepts_json5_that_mentions_the_preset`.

Forrás: docs/project-review-2026-11-12.md, 4.4 (`.json5` Renovate-konfiguráció).

## Objective
Egy `.json5` Renovate-konfig pontosan akkor számít megfelelőnek, ha a preset neve teljes stringként szerepel az `extends` tömb elemei között; kommentben, más értékben vagy részleges egyezésként nem.

## Scope
### In scope
- A `_manual` szöveges keresésének cseréje kommentet és stringet megkülönböztető ellenőrzésre, csak a standard könyvtárral.
- Tesztek; README-pontosítás.

### Out of scope
- JSON5-parszoló függőség felvétele (elvetve: új futásidejű függőség lenne abban a jobban, amely a flotta tokenjeit kezeli).
- `.json5` fájlok automatikus javítása (marad kézi lelet) és a `remove_extends` ellenőrzése `.json5` fájlban.
- A `.json` konfigok ága.

## Implementation plan
1. A `RenovatePreset` moduljában (a csomaggá bontás után `src/github_manager/rules/renovate.py`) új, modulszintű segéd, pl. `_json5_extends(text: str) -> list[str] | None`: az első `extends` tömb string elemei, vagy `None`, ha nincs ilyen tömb.
   - Tokenizálás egyetlen reguláris kifejezéssel, amelynek alternatívái ebben a sorrendben állnak: idézőjeles string (`"…"`) és aposztrófos string (`'…'`), mindkettő visszaper-escape-pel; sorkomment (`//` a sor végéig); blokk-komment (`/*` … `*/`, több soron át is); a `[`, a `]` és a `:` jel; azonosító (pl. `extends`). A balról első egyezés szabálya miatt a stringen belüli `//` a string része, a kommenten belüli idézőjel pedig a komment része.
   - A kommentek kiszűrése után a kulcs felismerése: `extends` azonosító, vagy `"extends"` / `'extends'` string, amelyet közvetlenül `:` és `[` token követ.
   - Az elemek: a `[` utáni string tokenek az első `]` tokenig; az elem értéke a két határoló közti nyers szöveg.
2. A `_manual` ezt használja: megfelelő, ha a `self.preset` pontos egyezéssel szerepel a kapott listában; különben a mai kézi lelet, változatlan szöveggel.
3. Tesztek (`tests/test_rules.py`; a tesztfájl szétbontása után `tests/test_rules_renovate.py`), paraméterezve:
   - megfelelő: `{extends: ['<preset>']}`; `{"extends": ["<preset>"]}`; többsoros tömb záró vesszővel; tömb kommenttel az elemek között; a preset nem első elemként;
   - nem megfelelő (kézi lelet): a Context négy esete; `extends` nélküli fájl; `extends: []`; a preset neve csak a tömb utáni kommentben.
   A `test_renovate_accepts_json5_that_mentions_the_preset` neve igazodjon az új szabályhoz (pl. `..._that_extends_the_preset`).
4. `README.md`: a `renovate_preset` leírásában, illetve a „Not fixed automatically" bekezdésben pontosítás: a `.json5` konfig akkor megfelelő, ha az `extends` tömbje tartalmazza a presetet; javítani a program nem tudja.

## Verification
- `uv run pytest tests -k renovate --no-cov` — az új és a meglévő tesztek zöldek.
- `uv tree --no-dev` — a futásidejű függőségek listája nem bővült.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.

## Dependencies and risks
- Ismert pontatlanság: a segéd az első `extends` tömböt nézi, akkor is, ha az beágyazott objektumban áll (pl. a `packageRules` egy elemében). A teljes pontossághoz JSON5-parszoló kellene; a korlátot a segéd docstringje rögzítse.
- Escape-et tartalmazó string elem nem egyezik a presettel → kézi lelet (a biztonságos irány).
- A `rules.py` csomaggá bontása ugyanezt a kódot mozgatja; a feladat szimbólumra hivatkozik (`RenovatePreset._manual`), a másodikként készülő a friss `main`-re építsen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Egy `.json5` konfig megfelelő, ha a preset teljes stringként az `extends` tömb eleme — idézőjeles és aposztrófos stringgel, idézőjeles és idézőjel nélküli kulccsal, többsoros tömbben és kommentek között is
- [x] #2 Kézi lelet keletkezik, ha a preset neve csak sor- vagy blokk-kommentben, más kulcs értékében, vagy egy hosszabb presetnév részeként szerepel
- [x] #3 Kézi lelet keletkezik, ha nincs `extends` tömb, vagy az üres; a lelet szövege változatlan (`<path>: does not extend <preset>`), és a program `.json5` fájlt továbbra sem ír
- [x] #4 A projekt futásidejű függőségei nem bővültek
- [x] #5 A README leírja a `.json5` konfigok ellenőrzésének szabályát
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-36-renovate-preset-a-json5-konfigban-a-preset-csak.

Ellenőrzés (2026-11-14): `uv run pytest tests -k renovate --no-cov` 27 passed; `uv tree --no-dev` csak pyyaml és rich; `git diff 6b14df1 -- pyproject.toml uv.lock` üres; ruff format/check zöld; a workflow `task verify` futása exit 0 (649 passed, 1 skipped, 99.26% lefedettség). Ismert korlát a docstringben: az első `extends` tömböt nézi beágyazott objektumban is, az escape-eket nem dekódolja.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A `RenovatePreset._manual` a `.json5` konfigban már nem részszöveg-keresést végez: az új `_json5_extends` segéd (csak `re`, standard könyvtár) regex-tokenizálással elválasztja a stringeket a kommentektől, megkeresi az első `extends` / `"extends"` / `'extends'` kulcsot `:` `[` után, és visszaadja a tömb string elemeit; a preset pontos egyezéssel kell, hogy szerepeljen. Így a kommentben, más kulcs értékében vagy hosszabb presetnév részeként előforduló név kézi leletet ad (változatlan szöveg: `<path>: does not extend <preset>`); `.json5` fájlt a program továbbra sem ír. Tesztek: 5 megfelelő és 7 nem megfelelő paraméterezett eset a `tests/test_rules_renovate.py`-ban; README pontosítva. Ellenőrzés: renovate tesztek 27 passed, `task verify` exit 0, új futásidejű függőség nincs. Kockázat: az első `extends` tömböt beágyazott objektumban (pl. `packageRules`) is elfogadja, és escape-et tartalmazó elem nem egyezik — mindkettő a docstringben rögzítve.
<!-- SECTION:FINAL_SUMMARY:END -->
