---
id: TASK-13
title: >-
  Új required_files szabálytípus: megadott fájlok létezésének ellenőrzése (csak
  jelzés)
status: Done
assignee: []
created_date: '2026-11-03T21:17:00Z'
updated_date: '2026-11-03T22:11:00Z'
labels: []
dependencies: []
modified_files:
  - src/github_manager/rules.py
  - github-manager.toml
  - README.md
  - tests/test_rules.py
  - tests/test_engine.py
priority: medium
type: feature
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A tyutyutyu-org minden repójában legyen SonarQube-elemzés, amely a zhukovon futó SonarQube Community Buildre (26.10, `http://zhukov:9000`, csak LAN/Tailscale) küld. A workflow tartalma projektenként eltér (nyelv, build, tesztfuttatás), ezért nem `file_sync`-kel kezeljük: a github-manager csak azt ellenőrzi, hogy a fix nevű `.github/workflows/sonarqube.yml` létezik. A „fájl létezik” ellenőrzésre később más szabályoknak is szükségük lesz, ezért általános szabálytípus kell, nem SonarQube-specifikus.

Döntések (2026-11-03): fix fájlnév; `sonar-project.properties` NEM kötelező (Maven/Gradle scanner nem olvassa); a szabály csak jelez, semmit nem ír (a fájl tartalma projektenként más, nem generálható).

Meglévő minták: `RepoVisibility` (`src/github_manager/rules.py`) a csak jelző szabály mintája (`Finding(..., fixable=False)`); `FileSync` a `path`-alapú opcióolvasás mintája; `Options.text_list` és `Options.finish` (ismeretlen kulcs config-hiba); `RULE_TYPES` regisztráció. `Workspace.read(path)` a függő PR-írásokkal együtt adja a fájlt (`RemoteWorkspace.read` a `src/github_manager/engine.py`-ban, `MemoryWorkspace.read` a `tests/conftest.py`-ban), `None`, ha nincs.

## Objective
Új `required_files` szabálytípus: a `paths` listában szereplő minden fájlnak léteznie kell a repóban; minden hiányzó fájl egy `fixable=False` (manual) finding, és a szabály semmit nem ír.

## Scope
### In scope
- `RequiredFiles` szabályosztály és `RULE_TYPES` bejegyzés.
- `paths` opció validálása.
- `github-manager.toml` új `[[rules]]` blokk: `id = "sonarqube-workflow"`, `type = "required_files"`, `paths = [".github/workflows/sonarqube.yml"]`, `exclude = ["tyutyutyu/*"]` (csak tyutyutyu-org), magyarázó kommenttel.
- Tesztek szintetikus configgal, README, github-manager-rules skill.

### Out of scope
- A SonarQube workflow trigger-ellenőrzése (külön task, ettől függ).
- Workflow-k vagy bármilyen fájl írása/generálása a kezelt repókban; javítás.
- `sonar-project.properties` megkövetelése.
- SonarQube szerver, analysis token, `SONAR_TOKEN` org secret, `SONAR_HOST_URL` org változó (kézi előfeltételek a github-manageren kívül).
- Teszt a valódi `github-manager.toml` tartalmára (csak a betölthetőségét ellenőrző meglévő teszt marad).

## Implementation plan
1. `src/github_manager/rules.py`: `RequiredFiles(Rule)` frozen, kw_only dataclass, `type_name = "required_files"`, mező `paths: list[str]`. `_build`: `options.text_list("paths", REQUIRED)`; config-hiba (`ValueError`), ha a lista üres, ha egy elem `/`-rel kezdődik vagy `/`-re végződik, ha `..` szegmenst tartalmaz, vagy ha duplikált.
2. `apply`: a `paths` sorrendjében `workspace.read(path) is None` esetén `Finding(self.id, f"{path}: missing", fixable=False)`; egyébként nincs finding. Nem hív `write`, `change_setting`, `change_ruleset` metódust.
3. `RULE_TYPES` tuple-be felvenni.
4. `github-manager.toml`: a fenti blokk a `private-self-hosted-runners` után, kommenttel (csak létezést néz, tartalmat nem; csak jelez).
5. Tesztek a `tests/test_rules.py`-ban (`MemoryWorkspace`) és egy engine-szintű a `tests/test_engine.py`-ban (`FakeGitHub.add_repo`): létező fájl → nincs finding; hiányzó → pontos üzenet, `fixable=False`; több hiányzó → sorrendben; config-hibák (üres lista, abszolút út, `..`, duplikátum, ismeretlen kulcs); `fix` módban a hiány nem nyit PR-t és nem ír (`fake_github.calls` write-prefix ellenőrzés, nem teljes lista).
6. `README.md`: Rule types tábla új sora (`required_files` | a `paths` fájljai léteznek | none: reported as *manual*) és a „Not fixed automatically” lista bővítése. `.claude/skills/github-manager-rules/SKILL.md`: rövid `required_files rule` szakasz (gitignore-olt fájl, nem jelenik meg a diffben).

## Verification
- `uv run ruff format -q . && task verify` — format, lint, ty, pytest ≥80% branch coverage, audit, build sikeres.
- `uv run github-manager repos` — a valódi config betölthető (csak olvasó parancs).

## Dependencies and risks
- Nincs előfeltétel. A trigger-ellenőrző task erre épít (a hiányzó fájlt csak ez a szabály jelzi).
- Kockázat: amíg a repók nem kapnak kézzel írt `sonarqube.yml`-t, minden tyutyutyu-org repó manual findingot mutat; ez szándékos.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A required_files szabálytípus regisztrálva van; a paths lista minden hiányzó fájljára fixable=False finding „<path>: missing” üzenettel, létező fájlra nincs finding
- [x] #2 A szabály check és fix módban sem ír a repóba, nem nyit PR-t és nem módosít beállítást vagy rulesetet
- [x] #3 Üres paths, abszolút vagy / végű út, .. szegmens, duplikált elem és ismeretlen kulcs config-hiba
- [x] #4 A github-manager.toml-ban sonarqube-workflow szabály: paths = [".github/workflows/sonarqube.yml"], exclude = ["tyutyutyu/*"]
- [x] #5 README Rule types tábla és a Not fixed automatically lista, valamint a github-manager-rules skill leírja a szabályt
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . és task verify sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-13-uj-required-files-szabalytipus-megadott-fajlok-l.

Finalization verification (2026-11-03): uv run ruff format -q . && task verify passed (431 tests, 99.31% branch coverage, ruff/ty/deptry/audit/build OK). uv run github-manager repos loaded the real config and listed repos (exit 0). .claude/skills/github-manager-rules/SKILL.md has a 'required_files rule' section; git check-ignore: '.gitignore:265:.claude/', so it is not in the diff (as planned). exclude = ["tyutyutyu/*"] matches OWNER/NAME via Rule.applies_to, so only tyutyutyu-org repos are checked.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the generic report-only required_files rule type (RequiredFiles in src/github_manager/rules.py, registered in RULE_TYPES). Every missing file in 'paths' yields Finding(id, '<path>: missing', fixable=False) in paths order; existing (even empty or pending-written) files yield nothing; the rule never writes, opens PRs or changes settings/rulesets. Config errors: missing/empty paths, non-string/empty items, leading/trailing '/', '..' segment, duplicates, unknown keys. github-manager.toml got the sonarqube-workflow rule (paths = [".github/workflows/sonarqube.yml"], exclude = ["tyutyutyu/*"]) with a comment; README Rule types table and 'Not fixed automatically' list and the (git-ignored) github-manager-rules skill document it. Tests: unit tests in tests/test_rules.py and engine tests in tests/test_engine.py (check+fix mode, no write calls, no PR) using synthetic config. Verification: ruff format + task verify green (431 passed, 99.31% coverage); github-manager repos loads the real config. Risk (intentional): every tyutyutyu-org repo reports a manual finding until a hand-written sonarqube.yml is added; trigger check is a separate follow-up task.
<!-- SECTION:FINAL_SUMMARY:END -->
