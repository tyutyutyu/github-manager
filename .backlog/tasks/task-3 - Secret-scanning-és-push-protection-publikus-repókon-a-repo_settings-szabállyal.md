---
id: TASK-3
title: Secret scanning és push protection publikus repókon a repo_settings szabállyal
status: Done
assignee: []
created_date: '2026-10-14 21:39'
updated_date: '2026-10-16 12:37'
labels: []
dependencies: []
references:
  - 'https://docs.github.com/en/rest/repos/repos#update-a-repository'
documentation:
  - README.md
modified_files:
  - src/github_manager/rules.py
  - src/github_manager/engine.py
  - tests/test_rules.py
  - tests/test_engine.py
  - tests/test_github.py
  - github-manager.toml
  - README.md
priority: medium
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A publikus repókban a secret scanning és a push protection ingyenes, és megakadályozza, hogy véletlenül kiszivárgott token a repóba kerüljön. 2026-10-14-i állapot a két publikus, hatókörbe eső repón (`GET repos/{owner}/{repo}` → `security_and_analysis`):
- `tyutyutyu/github-manager`: `secret_scanning`, `secret_scanning_push_protection`: `disabled`.
- `tyutyutyu/just-enough-quota-bar`: mindkettő `enabled`.

A privát repókban ezek a funkciók fizetősek (GitHub Secret Protection), ezért a felhasználó döntése (2026-10-14): csak publikus repókra vonatkozzon. A privát `tyutyutyu/agent-skills` válaszában a `security_and_analysis` mező hiányzik.

Kódbeli kiindulópontok:
- A `repo_settings` rule type (`RepoSettings` a `src/github_manager/rules.py`-ban) jelenleg csak a `REPO_BOOL_SETTINGS` logikai kulcsait fogadja el.
- Az olvasás a `GitHub.repo_settings` (a PyGithub `get_repo(...).raw_data`, ebben a `visibility` és a `security_and_analysis` is benne van), az írás a `GitHub.update_repo_settings` (`get_repo(...).edit(**settings)`).
- A PyGithub 2.10.0 `Repository.edit` elfogad egy `security_and_analysis: dict` paramétert (ellenőrizve). A REST formátum: `{"secret_scanning": {"status": "enabled"}, "secret_scanning_push_protection": {"status": "enabled"}}`.
- A változások gyűjtése: `RemoteWorkspace.change_setting` / `setting_changes` (`src/github_manager/engine.py`).

## Objective
A `repo_settings` szabály opcionálisan előírhatja a `secret_scanning` és `secret_scanning_push_protection` állapotát. Publikus repón a `check` jelzi az eltérést, a `fix` beállítja; privát és internal repón a szabály ezt a részt finding nélkül kihagyja.

## Scope
### In scope
- Új opcionális kulcs a `repo_settings` szabály táblájában: `security_and_analysis = { secret_scanning = "enabled", secret_scanning_push_protection = "enabled" }`. Kizárólag ez a két alkulcs, értéke `"enabled"` vagy `"disabled"`.
- Az összehasonlítás és az írás a meglévő settings-útvonalon (`change_setting` → `update_repo_settings` → PyGithub `edit`).
- `github-manager.toml`: a `repo-settings` szabály bővítése mindkét alkulccsal, `"enabled"` értékkel.
- README: a `repo_settings` sor kiegészítése.

### Out of scope
- Privát vagy internal repók biztonsági beállításai, GitHub Advanced Security / Secret Protection licenc.
- `secret_scanning_non_provider_patterns`, `secret_scanning_validity_checks`, Dependabot alerts és security updates (a függőségfrissítést a Renovate végzi).
- Logikai beállítások bővítése és rulesetek (külön feladatok).

## Implementation notes
1. **Validálás** (`RepoSettings._build`):
   - A `settings` tábla mellett elfogadja a `security_and_analysis` táblát. Ismeretlen alkulcs vagy nem `"enabled"`/`"disabled"` érték `ValueError`, ami a `ConfigError`-on át jelenik meg.
   - Ha csak `security_and_analysis` van megadva, a `settings` üres vagy hiányzó lehet.
   - Ha mindkettő hiányzik vagy üres: `ValueError`.
2. **Alkalmazás** (`RepoSettings.apply`):
   - A `workspace.setting("visibility")` alapján: ha nem `"public"`, a biztonsági rész kimarad, finding nincs.
   - Publikus repón minden alkulcsra a `workspace.setting("security_and_analysis")[<alkulcs>]["status"]` értéket veti össze.
   - Eltérésnél egy fixable, `setting=True` finding, pl. `setting security_and_analysis.secret_scanning is "disabled", expected "enabled"`.
   - Ha a `security_and_analysis` mező hiányzik a válaszból: `fixable=False` finding, ugyanazzal a „not readable (the token needs Administration access)” szöveggel, mint a logikai beállításoknál.
3. **Írás:**
   - Az összes biztonsági változás egyetlen `change_setting("security_and_analysis", {<alkulcs>: {"status": <érték>}, ...})` hívásba kerül, így `fix` módban egy PATCH megy ki.
   - A `RemoteWorkspace.setting_changes` jelenleg teljes értékegyenlőséget néz; a beágyazott dictnél csak a kért alkulcsok `status`-ának eltérése számítson változásnak.
   - A `secret_scanning_push_protection` engedélyezéséhez a `secret_scanning`-nek is engedélyezve kell lennie; mindkettő ugyanabban a payloadban menjen.
4. **Tesztek:**
   - `tests/test_rules.py`: validálás, publikus eltérés, publikus naprakész, privát kihagyás, hiányzó mező.
   - `tests/test_engine.py`: `check` írás nélkül; `fix` egyetlen `update_repo_settings` hívás a beágyazott payloaddal; a második futás `compliant`.
   - `tests/test_github.py`: a meglévő `FakeRepository` mintával ellenőrzi, hogy az `edit` a `security_and_analysis` kulcsot kapja.
   - Valódi API-hívás egyik tesztben sem lehet.

## Verification
- `uv run ruff format -q .` majd `task verify`: formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build; mind sikeres.
- `uv run pytest tests/test_rules.py tests/test_engine.py tests/test_config.py -q --no-cov`: az új esetek és a valódi konfiguráció betöltése zöld.
- Kézi, a merge után: GitHub Actions → `enforce` → `mode = check`. Várt:
  - `tyutyutyu/github-manager`: `[fix]` sor mindkét alkulcsra;
  - `tyutyutyu/just-enough-quota-bar`: ezekre nincs finding;
  - privát repók: ezekre nincs finding.
- Kézi, `fix` után: `gh api repos/tyutyutyu/github-manager --jq '.security_and_analysis'` szerint mindkét alkulcs `enabled`.

## Dependencies and risks
- Előfeltétel: a `repo_settings` rule type a `main`-en van; a feladat létrehozásakor csak commitolatlan munka volt.
- Előfeltétel: a tokenek Administration: Read and write joggal (README „Tokens”).
- Kockázat: a push protection a már bent lévő titkokat nem távolítja el. A bekapcsolás után a GitHub a meglévő commitokat is szkenneli, és secret scanning alertek jelenhetnek meg, amiket kézzel kell kezelni.
- Ha egy repó később privátra vált, a szabály nem kapcsolja ki a beállítást, csak nem ellenőrzi tovább.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `repo_settings` szabály elfogad egy opcionális `security_and_analysis` táblát pontosan a `secret_scanning` és `secret_scanning_push_protection` alkulccsal, `"enabled"`/`"disabled"` értékkel; más alkulcsra vagy értékre konfigurációs hibát ad
- [x] #2 Publikus repón az eltérő állapot fixable findinget ad; `fix` módban egyetlen PATCH (PyGithub `edit(security_and_analysis=...)`) állítja be mindkettőt, és a második futás `compliant`
- [x] #3 Privát és internal repón a biztonsági rész nem ad findinget és nem ír semmit
- [x] #4 Ha a válaszból hiányzik a `security_and_analysis` egy publikus repón, `[manual]` „not readable” finding keletkezik
- [x] #5 A logikai beállítások eddigi viselkedése és tesztjei változatlanok
- [x] #6 A `github-manager.toml` `repo-settings` szabálya mindkét alkulcsot `"enabled"`-re írja elő, a README `repo_settings` sora leírja az opciót és a csak-publikus korlátot
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 A `task verify` sikeres
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-3-secret-scanning-es-push-protection-publikus-repo.

Validation: ruff format check and pytest (114 passed, 99.26% branch coverage) rerun; workflow task verify exited 0. Nested security_and_analysis payloads merge across rules in RemoteWorkspace (single PATCH).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added optional security_and_analysis (secret_scanning, secret_scanning_push_protection) to repo_settings: validated, public-only, one merged PATCH via change_setting; config and README updated. Verified with task verify (exit 0) and pytest 114 passed, 99.26% coverage.
<!-- SECTION:FINAL_SUMMARY:END -->
