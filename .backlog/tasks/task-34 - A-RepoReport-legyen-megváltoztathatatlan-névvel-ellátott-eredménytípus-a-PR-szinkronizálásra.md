---
id: TASK-34
title: >-
  A RepoReport legyen megváltoztathatatlan; névvel ellátott eredménytípus a
  PR-szinkronizálásra
status: To Do
assignee: []
created_date: '2026-11-12T23:54:00Z'
labels: []
dependencies:
  - TASK-17
  - TASK-18
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/engine.py
  - src/github_manager/cli.py
  - tests/test_engine.py
priority: low
type: chore
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `RepoReport` (`src/github_manager/engine.py`) az egyetlen nem `frozen` adatosztály a modellben: a szabályok, a `Finding`, a `Repo`, a `PullRequest` és a `RulesetChange` mind `frozen`. A feldolgozás a riportot a létrehozása után mezőnként írja át a fix ágon:
- az `outcome` és a `detail` a PR-szinkronizálás eredményéből kap értéket;
- az `outcome` a beállítások és rulesetek alkalmazása után `Outcome.SETTINGS_UPDATED` lehet;
- az `auto_merge` az `_auto_merge` eredményét kapja.

A `_sync_pull_request` névtelen hármast ad vissza (`tuple[Outcome, str, PullRequest | None]`), amelyet a hívó pozíció szerint bont ki; a riportot paraméterként is megkapja, és az `outcome`-ját, valamint a leleteit olvassa.

A projekt kódolási szabálya az immutable adatmodell; a rejtett átírás megnehezíti annak követését, hol dől el egy repó végső eredménye.

A compliance PR frissítésének javítása és a repónkénti hibaizoláció ugyanezt a kódrészt alakítja át (az utóbbi a `_process`-t kiértékelő és javító szakaszra bontja, és a hibaágon is riportot állít össze); ez a feladat az ő végállapotukra épül.

Forrás: docs/project-review-2026-11-12.md, 4.3 (5. és 6. sor).

## Objective
A `RepoReport` `frozen` adatosztály, amelyet a feldolgozás egyszer állít össze vagy `dataclasses.replace`-szel származtat, és a PR-szinkronizálás névvel ellátott mezőjű eredményt ad.

## Scope
### In scope
- `RepoReport` → `@dataclass(frozen=True)`; minden mezőírás megszüntetése az `engine.py`-ban.
- Névvel ellátott visszatérési típus a `_sync_pull_request`-re.

### Out of scope
- A `findings` és a `diffs` mező típusa (marad `list`, ahogy a `Rule.exclude` is).
- A `GitHubApi.compare` hármasa és a `FakeGitHub`.
- Bármely megfigyelhető viselkedés: eredmények, részletek, auto-merge szövegek, kimenet.
- A `Finding` mezői.

## Implementation plan
1. `src/github_manager/engine.py`: a `RepoReport` legyen `frozen=True`; a `manual_findings` property marad.
2. Új névvel ellátott típus a `_sync_pull_request` eredményére (`NamedTuple` vagy `frozen` dataclass, pl. `_PullRequestSync` `outcome`, `detail` és `pull` mezővel). A függvény nem módosítja a paramétereit; a hívó mezőnévvel olvas.
3. A fix szakasz a részeredményeket helyi változókban gyűjti (PR-eredmény, beállítás- és ruleset-változások, auto-merge szöveg), és a végső riportot egyszer hozza létre, vagy `dataclasses.replace(report, ...)`-szel származtatja. Változatlan marad: az `Outcome.NEEDS_FIX` → `Outcome.SETTINGS_UPDATED` szabály, és a lépések sorrendje (PR → beállítások → rulesetek → auto-merge).
4. Az `_auto_merge` a riportból csak olvas (`outcome`, `findings`). Ma a már véglegesített `outcome`-ot látja (a `SETTINGS_UPDATED` átírás után); a hívó ugyanezt az értéket adja át neki a származtatott riporttal.
5. A hibaág (a leleteket megtartó `ERROR` riport) szintén új példányt hoz létre, nem ír át mezőt.
6. Tesztek: a meglévők változatlan elvárásokkal zöldek; ha egy teszt riportmezőt ír át, `dataclasses.replace`-re kell cserélni. Új teszt a `tests/test_engine.py`-ban: a `RepoReport` egy mezőjének írása `dataclasses.FrozenInstanceError`-t ad.

## Verification
- `grep -n "report\.[a-z_]* = \|report\.outcome, report\.detail" src/github_manager/engine.py` — nincs találat.
- `uv run pytest tests/test_engine.py tests/test_cli.py --no-cov` — zöld.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld.

## Dependencies and risks
- Előfeltétel a compliance PR frissítésének javítása és a repónkénti hibaizoláció: mindkettő ugyanazokat a függvényeket (`_process`, `_sync_pull_request`, `process_repo`) írja át; ez a feladat utánuk következik, hogy ne ütközzenek.
- A `Finding.kind` bevezetése ugyanezt a modult érinti más sorokban; a másodikként készülő a friss `main`-re építsen.
- Kockázat: az `_auto_merge` más `outcome`-ot lát, mint ma; ezt a meglévő auto-merge tesztek fogják meg (pl. a „already enabled" eset).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `RepoReport` `frozen` adatosztály; egy mezőjének írása `FrozenInstanceError`-t ad, és ezt teszt rögzíti
- [ ] #2 Az `engine.py` sehol nem ír át riportmezőt: a végső riport egyszer jön létre, vagy `dataclasses.replace`-szel származik
- [ ] #3 A `_sync_pull_request` névvel ellátott mezőjű eredményt ad, és nem módosítja a paramétereit
- [ ] #4 Minden meglévő motor- és CLI-teszt változatlan elvárásokkal zöld: az eredmények, a részletek és az auto-merge szövegek nem változtak
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
