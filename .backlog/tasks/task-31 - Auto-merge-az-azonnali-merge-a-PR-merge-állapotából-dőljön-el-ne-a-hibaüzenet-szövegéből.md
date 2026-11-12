---
id: TASK-31
title: >-
  Auto-merge: az azonnali merge a PR merge-állapotából dőljön el, ne a
  hibaüzenet szövegéből
status: To Do
assignee: []
created_date: '2026-11-12T23:54:00Z'
labels: []
dependencies:
  - TASK-28
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/engine.py
  - src/github_manager/github.py
  - tests/conftest.py
  - tests/test_engine.py
  - tests/test_github.py
  - https://docs.github.com/en/graphql/reference/enums#mergestatestatus
priority: low
type: enhancement
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A program két helyen dönt a GitHub ember által olvasható hibaüzenetének szövege alapján:

1. `src/github_manager/engine.py`, `_auto_merge`: ha az `api.enable_auto_merge` `GitHubError`-t dob, és az üzenet (kisbetűsítve) tartalmazza a `CLEAN_STATUS = "clean status"` szöveget, a program közvetlenül merge-el (`api.merge_pr`, eredmény: `merged (squash)`). A GitHub ugyanis megtagadja az auto-merge bekapcsolását olyan PR-on, amely azonnal merge-elhető (megfigyelt üzenet: `Pull request is in clean status`). Ha a GitHub átfogalmazza az üzenetet, az ilyen PR-ok minden futáskor `failed: ...` eredményt kapnak, és nem merge-elődnek.
2. `src/github_manager/github.py`, `list_rulesets`: `403` válasz, amelynek üzenete tartalmazza a `RULESETS_UPGRADE = "Upgrade to GitHub Pro"` szöveget → `None` („a csomag nem kínál ruleseteket"). Megfigyelt üzenet: `Upgrade to GitHub Pro or make this repository public to enable this feature.` Más `403` (pl. hiányzó jogosultság) hibaként megy tovább; ezt a `test_list_rulesets_other_errors_are_raised` rögzíti.

Az első esetre van strukturált jel: a GraphQL `PullRequest.mergeStateStatus` mező (`MergeStateStatus` enum: `BEHIND`, `BLOCKED`, `CLEAN`, `DIRTY`, `DRAFT`, `HAS_HOOKS`, `UNKNOWN`, `UNSTABLE`). A mező a jelenlegi tokennel lekérdezhető (ellenőrizve 2026-11-13, csak olvasó lekérdezéssel; már merge-elt PR-ra `UNKNOWN`-t ad). A második esetre nincs: a `403` törzse csak `message`, `documentation_url` és `status` mezőt tartalmaz.

Kapcsolódó elemek: a `GitHubApi` protokoll (`engine.py`); a `FakeGitHub` (`tests/conftest.py`: `auto_merge_error`, `merge_error`, `enable_auto_merge`, `merge_pr`); a `CLEAN_STATUS_ERROR` konstans és az auto-merge tesztek (`tests/test_engine.py`); a `test_enable_auto_merge_raises_graphql_errors` (`tests/test_github.py`); a homokozó repón futó integrációs teszt (`tests/test_integration_github.py`, `task dev:test-integration`). A kódban nincs több hibaüzenet-szövegre épülő döntés.

Forrás: docs/project-review-2026-11-12.md, 4.3 (2. sor).

## Objective
Az auto-merge sikertelen bekapcsolása után a program a PR lekérdezett merge-állapota alapján dönt az azonnali merge-ről; a motor nem vizsgál hibaüzenet-szöveget, a ruleset-elérhetőség szöveges felismerése pedig dokumentált, tesztekkel rögzített kivétel marad.

## Scope
### In scope
- Új kliens-hívás a PR merge-állapotára; a `GitHubApi` protokoll és a `FakeGitHub` bővítése.
- Az `_auto_merge` átírása; a `CLEAN_STATUS` konstans törlése.
- A `RULESETS_UPGRADE` egyezés kis- és nagybetűtől független; a megfigyelt üzenet és az indoklás kommentben.
- Az integrációs teszt bővítése egy lépéssel, amely a valódi GitHubon igazolja a feltevést.

### Out of scope
- Az auto-merge jogosultsági feltétele (`_verify_required`, `VERIFY_CHECK`).
- A merge módja (squash) és a `merge_pr` hívás.
- Újrapróbálkozás és rate limit kezelés a transportban.

## Implementation plan
1. `src/github_manager/github.py`: új GraphQL lekérdezés-konstans és metódus: `merge_state(self, repo: str, pull: PullRequest) -> str`. Lekérdezés: `query($id: ID!) { node(id: $id) { ... on PullRequest { mergeStateStatus } } }`, a változó a `pull.node_id`. A visszatérési érték az enum szövege; ha a `node` `null`, vagy nincs benne a mező: `"UNKNOWN"`.
2. `src/github_manager/engine.py`: a `GitHubApi` protokollba `def merge_state(self, repo: str, pull: PullRequest) -> str: ...`; új konstans `MERGEABLE_NOW = "CLEAN"`; a `CLEAN_STATUS` törlése. Az `_auto_merge` belső `except GitHubError` ága:
   - ha `api.merge_state(name, pull) != MERGEABLE_NOW`: az eredeti hiba megy tovább (`raise`), az eredmény `failed: <eredeti üzenet>`;
   - különben `api.merge_pr(name, pull.number)`, az eredmény `merged (squash)`.
   A külső `except GitHubError` változatlan: a `merge_state` vagy a `merge_pr` hibája is `failed: ...` szöveg, a repó feldolgozása nem áll meg.
3. `tests/conftest.py`, `FakeGitHub`: `merge_states: dict[tuple[str, int], str]` (hiányzó kulcsra `"BLOCKED"`), és `merge_state` metódus, amely a hívást a `calls` listába is felveszi.
4. `tests/test_engine.py`: a `CLEAN_STATUS_ERROR`-ra épülő tesztek átírása állapot-alapúra, és új esetek:
   - bekapcsolási hiba + `CLEAN` → `merge_pr` hívás, `merged (squash)`, tetszőleges hibaüzenet mellett;
   - bekapcsolási hiba + `BLOCKED`, illetve `UNKNOWN` → nincs `merge_pr`, az eredmény `failed: <eredeti üzenet>`;
   - sikeres bekapcsolás → nincs `merge_state` hívás;
   - a `merge_state` hibája → `failed: ...`, a riport eredménye nem `error`.
5. `tests/test_github.py`: a `merge_state` tesztje `FakeHttp`-vel: a kérés `POST /graphql`, a változó a `node_id`; `CLEAN` válasz; `node: null` → `UNKNOWN`.
6. `src/github_manager/github.py`, `list_rulesets`: az egyezés legyen kis- és nagybetűtől független (`RULESETS_UPGRADE.lower() in str(exc).lower()`). A konstans fölötti komment rögzítse a teljes megfigyelt üzenetet, és azt, hogy a válasz nem hordoz strukturált kódot, ezért marad a szöveges egyezés; ha a GitHub átfogalmazza, a repó `error` eredményt kap a `403` üzenetével (ezt a meglévő teszt rögzíti).
7. `tests/test_integration_github.py`: a PR létrehozása utáni lépésben (a homokozó repóban nincs kötelező check) két állítás:
   - az `api.merge_state(repo, pull)` értéke `CLEAN` — legfeljebb 5 lekérdezéssel, 2 másodperces szünetekkel, mert a GitHub az állapotot aszinkron számolja;
   - ezután az `api.enable_auto_merge(repo, pull)` `GitHubError`-t ad.
   A megfigyelt állapotsorozatot és a hibaüzenetet a feladat jegyzetében rögzíteni kell. A teszt a PR-t itt nem merge-eli.
8. Ha a 7. lépés azt mutatja, hogy az állapot az első lekérdezéskor jellemzően `UNKNOWN`, a `GitHub.merge_state` ismételje a lekérdezést korlátosan (legfeljebb 3 lekérdezés, 1 másodperces szünet, injektálható várakozással), és ezt teszt fedje. Ha az első lekérdezés már `CLEAN`, ismétlés nem kell.
9. `README.md`: ha az auto-merge leírása a „clean status" hibára hivatkozik, a megfogalmazás igazítása: azonnali merge akkor történik, ha a bekapcsolás nem sikerül és a PR állapota `CLEAN`.

## Verification
- `uv run pytest tests/test_engine.py tests/test_github.py --no-cov` — az új és az átírt tesztek zöldek.
- `grep -rn -i "clean status" src` — nincs találat.
- `GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> task dev:test-integration` — zöld; a megfigyelt állapotsorozat a feladat jegyzetében.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.

## Dependencies and risks
- Előfeltétel a homokozó repón futó integrációs teszt: a feltevést (a „clean status" miatt elutasított PR `mergeStateStatus` értéke `CLEAN`) csak a valódi GitHubon lehet igazolni, a kezelt repókba írni tilos.
- Viselkedésváltozás: bármilyen bekapcsolási hiba után merge történik, ha a PR `CLEAN` (pl. akkor is, ha az auto-merge nincs engedélyezve a repóban). Ez megfelel a szándéknak: az `_auto_merge` csak ott fut, ahol a kezelt ruleset megköveteli a `verify` checket, a `CLEAN` pedig azt jelenti, hogy minden kötelező feltétel teljesült; a merge-et a GitHub a ruleset szerint ellenőrzi.
- Ha az állapot `UNKNOWN`, a PR ebben a futásban nem merge-elődik (`failed: ...`); a következő futás újrapróbálja.
- A `tests/conftest.py`-t és az `engine.py`-t más nyitott feladatok is módosítják; a helyeket szimbólum szerint kell megkeresni, és a másodikként készülő a friss `main`-re építsen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ha az auto-merge bekapcsolása hibát ad, és a PR lekérdezett `mergeStateStatus` értéke `CLEAN`, a program squash merge-et hajt végre, és az eredmény `merged (squash)` — a hibaüzenet szövegétől függetlenül
- [ ] #2 Ha a bekapcsolás hibát ad, és az állapot nem `CLEAN` (pl. `BLOCKED`, `UNKNOWN`), nincs merge, az eredmény `failed: <eredeti hibaüzenet>`, és a repó eredménye nem `error`
- [ ] #3 Sikeres bekapcsolásnál nem történik állapot-lekérdezés
- [ ] #4 A `src/` nem tartalmazza a `clean status` szöveget, és az `engine.py` nem vizsgál hibaüzenet-szöveget
- [ ] #5 A `list_rulesets` Free-csomag felismerése kis- és nagybetűtől független; a konstans kommentje rögzíti a megfigyelt üzenetet és azt, miért marad szöveges az egyezés; más `403` továbbra is hibát ad
- [ ] #6 A homokozó repón futó integrációs teszt igazolja, hogy a kötelező check nélküli nyitott PR állapota `CLEAN`, és hogy rajta az auto-merge bekapcsolása hibát ad; a megfigyelt állapotsorozat a feladat jegyzetében szerepel
- [ ] #7 A `FakeGitHub` modellezi a merge-állapotot, és a `GitHubApi` protokoll tartalmazza az új hívást
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
