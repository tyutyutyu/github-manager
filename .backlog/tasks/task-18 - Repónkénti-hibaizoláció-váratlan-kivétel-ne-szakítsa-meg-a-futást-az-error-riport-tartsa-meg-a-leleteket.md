---
id: TASK-18
title: >-
  Repónkénti hibaizoláció: váratlan kivétel ne szakítsa meg a futást, az error
  riport tartsa meg a leleteket
status: Done
assignee: []
created_date: '2026-11-12T12:16:00Z'
updated_date: '2026-11-13T00:03:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/engine.py
  - src/github_manager/github.py
  - tests/test_engine.py
  - tests/test_cli.py
priority: high
type: bug
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `process_repo` (`src/github_manager/engine.py`) csak `GitHubError`-t kap el:

    try:
        return _process(api, config, repo, fix=fix)
    except GitHubError as exc:
        return RepoReport(repo.full_name, Outcome.ERROR, detail=str(exc))

Minden más kivétel kijut a `cli.main` repó-ciklusából: a futás tracebackkel megáll, a hátralévő repók kimaradnak, nincs összesítő és nincs job summary.

Reprodukálva (2026-11-12) a tesztek fake-jeivel: privát repó, `self_hosted_runners` szabály, és ez a workflow:

    jobs:
      b:
        runs-on: !foo bar

A `SelfHostedRunners._job_problem` → `_json()` (`src/github_manager/rules.py`) `yaml.constructor.ConstructorError`-t dob, amely kijut a `process_repo`-ból.

Kódolvasás alapján ugyanez a sorsa a válasz olvasása közbeni `TimeoutError`-nak, a megszakadt kapcsolatnak és a váratlan alakú API-válasznak (`KeyError`): a `GitHub._request` (`src/github_manager/github.py`) csak `urllib.error.HTTPError`-t és `URLError`-t alakít `GitHubError`-rá.

Második hiány: a hibaágon készülő `RepoReport` eldobja a már kiértékelt findingokat és diffeket, így a hibás repóról semmi más nem látszik.

Forrás: docs/project-review-2026-11-12.md, 2.3.

## Objective
Egy repó feldolgozása közben fellépő bármely kivétel csak azt a repót viszi `error` eredményre: a futás a többi repóval folytatódik, és a riport megtartja a már kiértékelt leleteket.

## Scope
### In scope
- `process_repo`: minden `Exception` elfogása, megkülönböztető `detail`, traceback a stderr-re.
- A fix lépésekben történt hiba riportja megtartja a kiértékelés findingjait és diffjeit (`GitHubError` esetén is).
- Tesztek, README „Exit codes" mondat.

### Out of scope
- A `_json()` javítása, hogy az ismeretlen YAML-tag hiba helyett *manual* finding legyen (külön szabály-javítás).
- Újrapróbálkozás, időkorlát és rate limit kezelés a `github.py`-ban.
- A kilépési kódok jelentésének módosítása (külön feladat).

## Implementation plan
1. `src/github_manager/engine.py`, `process_repo`: `except Exception` (a `BaseException` nem, hogy a `KeyboardInterrupt` továbbra is megszakítson). `GitHubError` esetén a `detail` marad `str(exc)`; más kivételnél `f"unexpected {type(exc).__name__}: {exc}"`, és a traceback a stderr-re kerül (`traceback.print_exc()`).
2. A `_process` szétbontása két szakaszra úgy, hogy a kiértékelés eredménye a hibaágon is elérhető legyen (pl. kiértékelő függvény, amely a workspace-t, a riportot és a változásokat adja vissza, és külön függvény a fix lépésekre). Ha a fix szakasz hibázik, a visszaadott riport `outcome=Outcome.ERROR`, a `detail` a hiba, a `findings` és a `diffs` a kiértékelésből származik. A kiértékelés közbeni hibánál a findingok nélküli `ERROR` riport elfogadott. Ahol kézenfekvő, `dataclasses.replace` a mezők utólagos átírása helyett.
3. `src/github_manager/cli.py`: várhatóan nem kell módosítani — a `_print_report` minden eredménynél kiírja a findingokat, a `main` pedig `EXIT_ERROR`-t ad, ha van `Outcome.ERROR`. Ezt teszt igazolja.
4. `tests/test_engine.py`:
   - a fenti `runs-on: !foo bar` workflow privát repóban (`settings={"visibility": "private"}`) `self_hosted_runners` szabállyal: `Outcome.ERROR`, a `detail` `unexpected ConstructorError`-ral kezdődik, a stderr-en traceback van (`capsys`);
   - fix szakaszbeli hiba (pl. `fake_github.commit_files` `GitHubError`-t dob): `Outcome.ERROR`, a `report.findings` nem üres;
   - `KeyboardInterrupt` a feldolgozás közben továbbterjed (`pytest.raises`).
5. `tests/test_cli.py` (minta: `test_repository_errors_do_not_stop_the_run`): két repó, az első váratlan kivételt dob; a második feldolgozása megtörténik, megjelenik az összesítő sor, a kilépési kód `EXIT_ERROR`.
6. `README.md`, „Exit codes": a `2` jelentése „configuration, API or unexpected error".

## Verification
- `uv run pytest tests/test_engine.py tests/test_cli.py --no-cov` — az új és a meglévő tesztek zöldek.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld (lefedettség ≥ 80%).

## Dependencies and risks
- A blanket `except Exception` programhibát is `error` eredménnyé alakít: ezért kötelező a traceback a stderr-en és a kivétel típusa a `detail`-ben.
- A compliance PR frissítésének javítása ugyanezt a fájlt (`engine.py`, `_sync_pull_request` környéke) érinti: a másodikként készülő feladat a friss `main`-re építsen.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Ha egy repó feldolgozása nem `GitHubError` kivételt dob, a repó `error` eredményt kap `unexpected <KivételTípus>: <üzenet>` részlettel, és a többi repó feldolgozása folytatódik
- [x] #2 A váratlan kivétel tracebackje a stderr-re kerül
- [x] #3 Ha a hiba a szabályok kiértékelése után, a fix lépéseiben történik, az `error` riport tartalmazza a kiértékelt findingokat és diffeket, és a CLI kiírja őket
- [x] #4 Hibás repó mellett is megjelenik az összesítő és a job summary, a kilépési kód `2`
- [x] #5 A `KeyboardInterrupt` továbbra is megszakítja a futást
- [x] #6 Regressziós teszt fedi a `runs-on: !foo bar` workflow-t: a futás nem áll meg, a repó `error` eredményű
- [x] #7 A README „Exit codes" mondata a váratlan hibát is a `2` kódhoz sorolja
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run ruff format -q .` és `task verify` sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-18-reponkenti-hibaizolacio-varatlan-kivetel-ne-szak.

Validation: `uv run ruff format -q .` changed nothing; `uv run pytest tests/test_engine.py tests/test_cli.py --no-cov` 87 passed; workflow `task verify` exit 0 (491 passed, coverage 99.41%). Deviation from plan: `traceback.print_exception(exc)` instead of `traceback.print_exc()` (same stderr output, works outside the except block). `_process` split into `_evaluate` (returns `_Evaluation` or a ready skip report) and `_fix` (returns a new report via `dataclasses.replace`). cli.py unchanged.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
process_repo now catches every Exception (not BaseException) per repository. GitHubError keeps its message as detail; any other error gets 'unexpected <Type>: <message>' and its traceback on stderr. _process is split into _evaluate and _fix, so an error in the fix steps returns an ERROR report that keeps the evaluated findings and diffs (via dataclasses.replace). README exit code 2 now covers unexpected errors.

Tests: engine regression for the 'runs-on: !foo bar' workflow (ConstructorError -> error, traceback on stderr), fix-step error keeps findings/diffs (GitHubError and KeyError), KeyboardInterrupt propagates; CLI tests for a two-repo run with an unexpected error (second repo processed, summary line, step summary table, exit 2) and for findings printed under a fix-step error.

Verification: ruff format clean, targeted tests 87 passed, task verify exit 0 (491 passed, 99.41% coverage).

Risk: a blanket except turns programming bugs into per-repo errors; mitigated by the traceback and exception type in the detail. Out of scope follow-ups stay as planned (_json() unknown YAML tag as manual finding, retries/timeouts in github.py).
<!-- SECTION:FINAL_SUMMARY:END -->
