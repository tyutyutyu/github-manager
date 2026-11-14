---
id: TASK-37
title: >-
  self_hosted_runners: a runs-on érték korlátos megjelenítése (YAML alias-bomba,
  ismeretlen tag, önhivatkozás)
status: Done
assignee: []
created_date: '2026-11-12T23:54:00Z'
updated_date: '2026-11-14T07:04:00Z'
labels: []
dependencies:
  - TASK-18
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/rules.py
  - tests/test_rules.py
  - tests/test_engine.py
priority: medium
type: bug
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `_json(node)` segéd (`github_manager.rules`; a csomaggá bontás után a workflow-modulban) a kézi leletek üzenetéhez JSON-ná alakítja a `runs-on` értékét:

    json.dumps(yaml.SafeLoader("").construct_document(node), default=str)

Két hívója van, mindkettő a `SelfHostedRunners._job_problem`-ben: amikor a `runs-on` lista egy eleme nem string, és amikor a `runs-on` se nem string, se nem lista. Három bemenet töri el (kipróbálva a tesztek `MemoryWorkspace`-ével, privát repóval, 2026-11-12 és 2026-11-13):

1. **Alias-bomba.** Egy 338 bájtos workflow: kilenc szinten egymásba ágyazott, szintenként kilencszer hivatkozott aliasok, a végén `runs-on: {x: *i}`. A `yaml.compose` 5 ms, a `construct_document` gyakorlatilag 0 ms (az aliasolt csomópontok közös objektumok), de a kifejtett érték 9^9 ≈ 387 millió elem: a `json.dumps` 20 másodperc alatt sem végzett. Egy ilyen fájl a 30 perces job-időkeretet is elviheti, és az adott owner minden további repója kimarad.
2. **Ismeretlen YAML-tag.** `runs-on: !foo bar` vagy `runs-on: [!foo bar]` → `yaml.constructor.ConstructorError`.
3. **Önhivatkozó horgony.** `runs-on: &r {x: *r}` → `ValueError: Circular reference detected`.

A 2. és a 3. esetben a kivétel kijut a szabályból; a repónkénti hibaizoláció óta ez a repót `error` eredményre viszi (`unexpected ...`), holott a helyes eredmény egy kézi lelet. Az 1. esetet a hibaizoláció nem fogja meg.

A meglévő tesztek rögzítik a szokásos megjelenítést, pl. `runs-on {"group": "big"} must be a string or a list of strings`, `runs-on ["self-hosted", 3] has a list item that is not a string`, `runs-on null must be a string or a list of strings`. A hibaizoláció regressziós tesztje (`tests/test_engine.py`) a `runs-on: !foo bar` workflow-val vált ki váratlan kivételt.

A modul többi YAML-segédje (`_text`, `_mapping`, `_entry`, a string-lista olvasó, `_shown`) csak a közvetlen gyerekeket nézi és értéket nem konstruál, így nem érintett; a `yaml.compose` futásideje lineáris.

Forrás: docs/project-review-2026-11-12.md, 4.4 (YAML alias-bomba) és 2.3.

## Objective
A `runs-on` érték megjelenítése korlátos idejű, és soha nem dob kivételt: a túl nagy vagy nem megjeleníthető érték helyén rövid helyettesítő szöveg kerül a kézi leletbe.

## Scope
### In scope
- A `_json` korlátozása és hibatűrővé tétele.
- Tesztek a három bemenetre; a hibaizoláció regressziós tesztjének átállítása más kiváltó okra.

### Out of scope
- A `runs-on` megítélésének szabályai és a többi üzenet.
- Fájlméret-korlát, a `yaml.compose` hívások.
- A `process_repo` hibakezelése.

## Implementation plan
1. A `_json` moduljában névvel ellátott konstansok: `MAX_SHOWN_NODES = 50`, valamint két helyettesítő szöveg, pl. `TOO_LARGE = "(too large to show)"` és `NOT_SHOWABLE = "(cannot be shown)"`.
2. Új segéd, amely megszámolja a csomópontból elérhető csomópontokat **alias-kifejtéssel** (ugyanazt a csomópontot minden eléréskor újra számolja, memoizálás nélkül), és azonnal megáll, amint a szám meghaladja a korlátot. A bejárás mélysége így legfeljebb a korlát, és önhivatkozásnál is véget ér.
3. `_json(node)`:
   - ha a számláló meghaladja a `MAX_SHOWN_NODES` értékét → `TOO_LARGE`;
   - különben a mai konstruálás és `json.dumps`; `yaml.YAMLError` esetén → `NOT_SHOWABLE`;
   - a szokásos értékekre a kimenet változatlan.
4. Tesztek a `self_hosted_runners` tesztjei között (`tests/test_rules.py`; a tesztfájl szétbontása után `tests/test_rules_workflows.py`):
   - alias-bomba hat szinttel (9^6 = 531 441 kifejtett elem: javítás nélkül sem akasztja meg a tesztfutást, de az üzenet óriási lenne): pontosan egy kézi lelet a jobra, amelynek üzenete tartalmazza a `TOO_LARGE` szöveget, és rövidebb 300 karakternél;
   - `runs-on: !foo bar` és `runs-on: [!foo bar]`: kézi lelet a `NOT_SHOWABLE` szöveggel, kivétel nélkül;
   - `runs-on: &r {x: *r}`: kézi lelet, kivétel nélkül;
   - mindhárom esetben ugyanabban a fájlban egy második, szabálytalan job is megkapja a saját leletét (az értékelés nem áll meg az első jobnál).
5. `tests/test_engine.py`: a hibaizoláció regressziós tesztje ne a `!foo bar` workflow-ra épüljön (az e feladat után kézi lelet), hanem egy tesztbeli szabályra, amelynek `apply` metódusa `RuntimeError`-t dob; az elvárás egyébként változatlan (`Outcome.ERROR`, `unexpected RuntimeError: ...` részlet, traceback a stderr-en).

## Verification
- `uv run pytest tests -k self_hosted --no-cov` — zöld, a futásidő nem nő érezhetően.
- `uv run pytest tests/test_engine.py --no-cov` — zöld.
- Kézi ellenőrzés: a Context 1. pontja szerinti kilencszintű bomba `MemoryWorkspace`-ben, ideiglenes szkripttel futtatva, 1 másodpercen belül kézi leletet ad; a szkript nem kerül a diffbe.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.

## Dependencies and risks
- Előfeltétel a repónkénti hibaizoláció: annak regressziós tesztjét ez a feladat állítja át.
- A `rules.py` csomaggá bontása és a workflow-segédek tisztítása ugyanazt a modult érinti; a feladat szimbólumra hivatkozik (`_json`), a másodikként készülő a friss `main`-re építsen.
- Kockázat: egy jogos, nagy `runs-on` leképezés is helyettesítő szöveget kap. Az 50 csomópontos korlát a valós `runs-on` értékeknek (néhány címke, `group` és `labels`) bőven elég, és a lelet így is megnevezi a jobot és a teendőt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A kilenc szinten egymásba ágyazott aliasokat tartalmazó workflow-ra a szabály 1 másodpercen belül kézi leletet ad, amely az érték helyén rövid helyettesítő szöveget tartalmaz
- [x] #2 Ismeretlen YAML-tagú `runs-on` (skalárként és listaelemként is) kézi leletet ad, nem kivételt
- [x] #3 Önhivatkozó horgonyú `runs-on` kézi leletet ad, nem kivételt
- [x] #4 A szokásos `runs-on` értékek üzenetei változatlanok: a meglévő `self_hosted_runners` tesztek módosítás nélkül zöldek
- [x] #5 Ugyanabban a fájlban a hibás job mellett álló többi job értékelése megtörténik
- [x] #6 A váratlan kivétel repónkénti izolációját továbbra is teszt fedi, olyan kiváltó okkal, amely nem a `runs-on` megjelenítésén múlik
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-37-self-hosted-runners-a-runs-on-ertek-korlatos-meg.

Eltérés a tervtől: a `_json` a `yaml.YAMLError` mellett a `ValueError`, `TypeError` és `AttributeError` kivételt is elkapja (hibás `!!int`/`!!float`/`!!timestamp` érték, nem string kulcs, pl. dátum a JSON-kódolásnál); ezekre is van paraméteres teszt. Az önhivatkozó horgonyt a csomópontszámláló fogja meg (`TOO_LARGE`), a konstruálásig el sem jut.
Ellenőrzés (2026-11-14): kilencszintű alias-bomba (585 bájt) ideiglenes, repón kívüli szkripttel `MemoryWorkspace`-ben: 0,006 s, kézi lelet `(too large to show)` szöveggel, a b job is megkapta a saját leletét. `pytest -k self_hosted --no-cov`: 142 passed; `tests/test_engine.py`: 74 passed; `uv run ruff format -q . && task verify`: exit 0, 658 passed, 1 skipped, lefedettség 99,27%.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A `runs-on` érték megjelenítése (`_json`, `src/github_manager/rules/workflows.py`) korlátos és kivételmentes lett. Az új `_exceeds_shown_nodes` aliasokat kifejtve, memoizálás nélkül számolja a csomópontokat, és `MAX_SHOWN_NODES = 50` felett azonnal megáll; ilyenkor a lelet `(too large to show)` szöveget kap. Ez kezeli az alias-bombát és az önhivatkozó horgonyt. A konstruálási és JSON-kódolási hibák (ismeretlen tag, hibás `!!int`/`!!timestamp`, nem string kulcs) helyén `(cannot be shown)` áll. A szokásos értékek üzenete változatlan.

Tesztek: paraméteres teszt a `tests/test_rules_workflows.py`-ban (hatszintű bomba, `!foo bar`, `[!foo bar]`, hibás tagek, dátumkulcs, `&r {x: *r}`); mindegyikben a második job is megkapja a leletét. A `tests/test_engine.py` hibaizolációs tesztje mostantól egy `RuntimeError`-t dobó `ExplodingRule`-ra épül.

Ellenőrzés: a kilencszintű bomba 0,006 s alatt kézi leletet ad; `task verify` zöld (658 passed, 1 skipped, 99,27%).

Kockázat: egy jogos, 50 csomópontnál nagyobb `runs-on` is helyettesítő szöveget kap, de a lelet így is megnevezi a jobot.
<!-- SECTION:FINAL_SUMMARY:END -->
