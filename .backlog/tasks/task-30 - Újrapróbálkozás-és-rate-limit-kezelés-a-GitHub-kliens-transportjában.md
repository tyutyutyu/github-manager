---
id: TASK-30
title: Újrapróbálkozás és rate limit kezelés a GitHub kliens transportjában
status: Done
assignee: []
created_date: '2026-11-12T23:54:00Z'
updated_date: '2026-11-13T21:45:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/github.py
  - tests/test_github.py
  - README.md
  - >-
    https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  - >-
    https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
priority: medium
type: enhancement
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `GitHub._request` (`src/github_manager/github.py`) minden kérést pontosan egyszer küld el (`TIMEOUT_SECONDS = 30`). Hibakezelése:
- `urllib.error.HTTPError` → `GitHubError("<METHOD> <url>: HTTP <kód>: <üzenet>", <kód>)`;
- `urllib.error.URLError` → `GitHubError("<METHOD> <url>: <ok>")`;
- minden más (pl. a válasz olvasása közbeni `TimeoutError`, `ConnectionResetError`, `http.client.IncompleteRead`) kezeletlenül továbbmegy.

Következmény: egyetlen átmeneti 502/503 vagy hálózati hiba az adott repót `error` eredményre viszi (a `select_repos` közben pedig az egész futást megállítja), és a rate limit válaszok (`429`, illetve `403` `Retry-After` vagy `X-RateLimit-Remaining: 0` fejléccel) ugyanígy végleges hibának számítanak. Egy teljes `check` a 30 repón kb. 150 másodpercig tart, és több száz kérést küld (mérve 2026-11-13).

A kliens hívásai kétfélék: olvasók (`GET`) és írók (`POST`, `PATCH`, `PUT`, `DELETE`; a GraphQL mutációk is `POST /graphql`). Az írók nem idempotensek (PR, megjegyzés, commit létrehozása), ezért bizonytalan kimenetelű hiba után nem ismételhetők.

A kliens tesztjei a `FakeHttp`-re épülnek (`tests/test_github.py`): a `queue(body, status, link)` sorba tett válaszokat ad vissza, 400-as vagy nagyobb státusznál `HTTPError`-t dob; a `client` fixture `GitHub("secret", opener=http)`.

Forrás: docs/project-review-2026-11-12.md, 4.3 (3. sor) és 6.1 (P1).

## Objective
A kliens transportja az átmeneti hibákat és a rate limit válaszokat korlátos számú, várakozással elválasztott újrapróbálkozással kezeli úgy, hogy író kérést soha nem ismétel meg bizonytalan kimenetel után.

## Scope
### In scope
- Újrapróbálkozás a `GitHub._request`-ben; injektálható várakozás és óra a tesztelhetőséghez.
- A nem `URLError` hálózati hibák `GitHubError`-rá alakítása.
- A `FakeHttp` bővítése (fejlécek, hálózati hiba), új tesztek, README-mondat.

### Out of scope
- A GraphQL `200`-as válaszában érkező `RATE_LIMITED` hiba kezelése.
- Kérések ütemezése, lassítása vagy párhuzamosítása.
- A `TIMEOUT_SECONDS` értéke, a `GitHubApi` protokoll (`engine.py`) és a `FakeGitHub`.
- A PyGithubon menő két hívás (`repo_settings`, `update_repo_settings`), amíg az a függőség megvan.

## Implementation plan
1. `src/github_manager/github.py`, névvel ellátott konstansok: `MAX_ATTEMPTS = 3`, `BACKOFF_SECONDS = 1` (várakozás a k. sikertelen kísérlet után: `BACKOFF_SECONDS * 2 ** (k - 1)`, azaz 1 s, majd 2 s), `SECONDARY_LIMIT_WAIT_SECONDS = 60`, `MAX_RATE_LIMIT_WAIT_SECONDS = 120`, `TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})`.
2. `GitHub.__init__`: két új, csak kulcsszóval adható paraméter: `sleep: Callable[[float], None] = time.sleep` és `clock: Callable[[], float] = time.time`.
3. A `_request` egy kísérletét végző rész köré ciklus (legfeljebb `MAX_ATTEMPTS` kísérlet). Egy sikertelen kísérlet besorolása:
   - **rate limit**: `HTTP 429`, vagy `HTTP 403`, amelynek van `Retry-After` fejléce, vagy amelynek `X-RateLimit-Remaining` fejléce `"0"`. A várakozás: a `Retry-After` egész másodpercben, ha van és értelmezhető; különben ha az `X-RateLimit-Remaining` `"0"`, akkor `X-RateLimit-Reset` (epoch másodperc) − `clock()` + 1, de legalább 1; különben `SECONDARY_LIMIT_WAIT_SECONDS`. Ha a várakozás nagyobb, mint `MAX_RATE_LIMIT_WAIT_SECONDS`: nincs várakozás és nincs ismétlés, azonnal `GitHubError` (a szokásos üzenet, kiegészítve azzal, hogy rate limit, és hány másodperc múlva szűnik meg; a `status` megmarad). Különben `sleep(várakozás)` és újabb kísérlet — **bármely metódusnál**, mert a GitHub a kérést nem hajtotta végre.
   - **átmeneti hiba**: a `TRANSIENT_STATUSES` egyike, vagy hálózati hiba: `urllib.error.URLError`, amely nem `HTTPError`; egyéb `OSError` (ide tartozik a `TimeoutError` és a `ConnectionError`); `http.client.HTTPException`. Újabb kísérlet **csak `GET` esetén**, az 1. lépés szerinti várakozással. Más metódusnál azonnali `GitHubError`. Figyelem: a `HTTPError` maga is `OSError`, ezért azt előbb kell kezelni.
   - **minden más** (a többi `4xx`): azonnali `GitHubError`, változatlanul.
4. Az utolsó kísérlet hibája a mai formátumú `GitHubError`: HTTP-hibánál `<METHOD> <url>: HTTP <kód>: <üzenet>` kitöltött `status`-szal, hálózati hibánál `<METHOD> <url>: <ok>`. A formátum nem változhat: a `list_rulesets`, a `branch_sha`, a `tree_paths` és a `read_file` a `status`-ra, illetve az üzenet szövegére épít.
5. Minden várakozás előtt egy `logging.getLogger(__name__).warning(...)` sor: metódus, URL, az ok (HTTP-kód vagy a hiba), a várakozás hossza és a kísérlet sorszáma. A token nem kerülhet a logba.
6. `tests/test_github.py`:
   - a `FakeHttp.queue` kapjon `headers: dict[str, str] | None` paramétert (a válasz, illetve a `HTTPError` fejléceibe kerül), és legyen mód hálózati hibát sorba tenni (pl. `queue_error(exc)`), amelyet a `__call__` kivált;
   - a `client` fixture rögzítő `sleep`-et és állítható `clock`-ot adjon át, hogy a tesztek ne várjanak;
   - azok a meglévő tesztek, amelyek `GET` kérésre egyetlen `5xx` választ tesznek sorba (pl. a `test_list_rulesets_other_errors_are_raised` `500`-as esete), `MAX_ATTEMPTS` választ tegyenek sorba;
   - új tesztek az elfogadási feltételek szerint; mindegyik ellenőrzi a kiment kérések számát (`http.requests`) és a rögzített várakozásokat.
7. `README.md`: a futtatást leíró részben egy-két mondat az újrapróbálkozásról (mit ismétel, meddig vár, mit nem ismétel soha).

## Verification
- `uv run pytest tests/test_github.py --no-cov` — az új és az igazított tesztek zöldek, valódi várakozás nélkül.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.
- `uv run github-manager check -r github-manager` a változtatás előtt és után — csak olvasó füstteszt a valódi API-n; a két kimenet megegyezik.

## Dependencies and risks
- A PyGithub megszüntetése után a két beállítás-hívás is ezen a transporton megy, és külön teendő nélkül megkapja ezt a viselkedést. A két feladat sorrendje tetszőleges; a másodikként készülő a friss `main`-re építsen.
- A repónkénti hibaizoláció után a kezeletlen hálózati hiba `unexpected ...` részletű `error` eredmény; e feladat után szabályos `GitHubError`.
- Kockázat: hosszabb futás tartós kiesésnél. Korlát: kérésenként legfeljebb két várakozás, egyenként legfeljebb `MAX_RATE_LIMIT_WAIT_SECONDS`; a job időkerete 30 perc.
- Kockázat: író kérés megismétlése. Ezt zárja ki a szabály: író kérés csak rate limit válasz után ismételhető.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `GET` kérés `500`, `502`, `503` vagy `504` válasz, illetve hálózati hiba után legfeljebb kétszer ismétlődik (összesen `MAX_ATTEMPTS = 3` kísérlet), 1, majd 2 másodperces várakozással; ha egy későbbi kísérlet sikeres, a hívó a sikeres választ kapja
- [x] #2 `POST`, `PATCH`, `PUT` és `DELETE` kérés `5xx` válasz vagy hálózati hiba után nem ismétlődik: pontosan egy kérés megy ki, és `GitHubError` keletkezik
- [x] #3 `429` válasz, illetve `403` válasz `Retry-After` vagy `X-RateLimit-Remaining: 0` fejléccel bármely metódusnál várakozás után ismétlődik; a várakozás a `Retry-After`, ennek hiányában az `X-RateLimit-Reset`-ből számolt idő, ennek hiányában 60 másodperc
- [x] #4 Ha a szükséges várakozás meghaladja a `MAX_RATE_LIMIT_WAIT_SECONDS` értékét, nincs várakozás és nincs ismétlés: a `GitHubError` üzenete megnevezi a rate limitet és a hátralévő időt
- [x] #5 `403` válasz rate limit fejlécek nélkül (jogosultsági hiba) és minden egyéb `4xx` válasz nem ismétlődik; az üzenet és a `status` változatlan
- [x] #6 A válasz olvasása közbeni `TimeoutError`, a megszakadt kapcsolat és a `http.client.HTTPException` `GitHubError`-ként jelenik meg, nem más kivételként
- [x] #7 A kísérletek kimerülése után a `GitHubError` üzenetformátuma és `status` mezője megegyezik a maival, és minden várakozásról `WARNING` szintű logsor készül, amely nem tartalmazza a tokent
- [x] #8 A README leírja az újrapróbálkozás szabályait
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-30-ujraprobalkozas-es-rate-limit-kezeles-a-github-k.

Ellenőrzés (2026-11-13): uv run pytest tests/test_github.py --no-cov: 136 passed, valódi várakozás nélkül; uv run ruff format -q . && task verify: exit 0 (605 passed, 1 skipped – az integrációs homokozó env változó nincs beállítva; lefedettség 99,44%). A hibatörzs olvasása közbeni hálózati hiba is kezelt: a detail ilyenkor a HTTP reason, a status megmarad. A plan szerinti valódi API-s füstteszt (check -r github-manager) nem futott a lezáráskor; csak olvasó, a felhasználó utólag ellenőrizheti.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A GitHub._request mostantól legfeljebb MAX_ATTEMPTS=3 kísérlettel dolgozik. GET kérést 500/502/503/504 vagy hálózati hiba (URLError, OSError, http.client.HTTPException, a hibatörzs olvasásának hibája is) után 1, majd 2 s várakozással ismétel; író metódust (POST/PATCH/PUT/DELETE) ilyenkor soha. Rate limit (429, illetve 403 Retry-After vagy X-RateLimit-Remaining: 0 fejléccel) után bármely metódus ismétlődik a Retry-After, az X-RateLimit-Reset alapján számolt idő, különben 60 s várakozással; 120 s fölött azonnali GitHubError 'rate limited; resets in N s' kiegészítéssel, a status megmarad. Más 4xx változatlanul azonnal hiba. A végső GitHubError formátuma és status mezője a régi; minden várakozás előtt WARNING logsor token nélkül. A sleep és a clock kulcsszavas paraméterként injektálható. Tesztek: FakeHttp fejléc- és hálózatihiba-támogatással, FakeTime, új retry/rate limit tesztek, igazított 5xx tesztek. README: újrapróbálkozási szabályok. Ellenőrzés: task verify zöld (605 passed, 1 skipped), lefedettség 99,44%. Kockázat: tartós kiesésnél hosszabb futás (kérésenként legfeljebb 2 várakozás, egyenként legfeljebb 120 s). A valódi API-s füstteszt a felhasználónál marad.
<!-- SECTION:FINAL_SUMMARY:END -->
