---
id: TASK-44
title: >-
  Repóprofilok: kizáró, névalapú profilok (common, workspace, backlog) és a
  szabályok profilhoz rendelése
status: To Do
assignee: []
created_date: '2026-11-16T23:56:00Z'
labels: []
dependencies: []
modified_files:
  - src/github_manager/config.py
  - src/github_manager/rules/base.py
  - src/github_manager/engine.py
  - src/github_manager/cli.py
  - github-manager.toml
  - README.md
priority: high
type: feature
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Ma minden `[[rules]]` szabály minden kiválasztott repóra vonatkozik (`_evaluate` és `_verify_required` a `src/github_manager/engine.py`-ban csak a `Rule.applies_to` exclude-globot nézi). Ezt hívjuk „common” profilnak. Két új repófajta érkezik, amelyekre részben más szabályok kellenek:
- **workspace** repó: a repónév `-workspace` utótagú (pl. `zenget-workspace`); egy `workspace.yaml` manifestet és gyökérfájlokat tartalmaz, alkalmazást nem.
- **backlog** repó: a repónév `-backlog` utótagú; egy workspace Backlog.md tervező repója (`.backlog/`).
Mindkettő jellemzően privát, a többi tagrepó publikus, ezért a mostani `repo-visibility` szabály (owner szerint: `tyutyutyu` = public) hibásan jelezne rájuk.

Döntések (2026-11-17, a tulajdonossal egyeztetve):
- A profilok kizáróak: minden repó pontosan egy profilba tartozik. A besorolás a repónév alapján történik (glob), a `common` az implicit alapértelmezés.
- Minden szabály felsorolja, mely profilokra vonatkozik; ha nem adja meg, akkor csak `common`.
- A workspace és a backlog profil minden mostani common szabályt megkap, kivéve a SonarQube szabályokat (`sonarqube-workflow`, `sonarqube-main-only`). A `repo-visibility` a common profilban marad. A workspace és backlog profilban egy külön `repo_visibility` szabály mindkét ownerre privátot vár.

Meglévő minták: `Options` (`src/github_manager/rules/base.py`, ismeretlen kulcs hiba), `parse_config` / `_check_visibility_owners` (`src/github_manager/config.py`) a config-szintű keresztellenőrzés mintája, `Repo` (`src/github_manager/github.py`), `RepoReport` és `Outcome` (`engine.py`), konzol- és step summary riport (`_print_report`, `_write_step_summary` a `src/github_manager/cli.py`-ban). A tesztfakék: `FakeGitHub.add_repo`, `MemoryWorkspace` (`tests/conftest.py`).

## Objective
A konfigurációban profilok definiálhatók repónév-mintákkal, a szabályok profilokhoz rendelhetők, és a github-manager minden repóra csak a saját profiljának szabályait alkalmazza.

## Scope
### In scope
- Felső szintű `profiles` tábla a TOML-ban: profilnév → nem üres glob-lista, a repónévre és az OWNER/NAME-re illesztve, ugyanúgy, mint az `exclude`.
- `common` foglalt profilnév: implicit, nem definiálható a `profiles` táblában.
- Új, minden szabálytípusra közös `profiles` kulcs a `Rule`-on (lista, alapértelmezés `["common"]`).
- A szabályok kiértékelése, az auto-merge döntés (`_verify_required`) és minden más szabályszűrés a repó profilja szerint.
- A repó profilja megjelenik a konzolriportban és a step summaryben.
- `github-manager.toml`: `profiles = { workspace = ["*-workspace"], backlog = ["*-backlog"] }`. A meglévő szabályok profil-hozzárendelése a fenti döntések szerint. Új `profile-visibility` szabály (`type = "repo_visibility"`, `visibility = { "tyutyutyu" = "private", "tyutyutyu-org" = "private" }`, `profiles = ["workspace", "backlog"]`), magyarázó kommentekkel.
- README: új „Profiles” szakasz és a `profiles` kulcs leírása a közös opciók között.
- Backlog decision az új tervezési döntésről (kizáró, névalapú profilok), a `backlog decision` CLI-vel.

### Out of scope
- A workspace és backlog verify workflow-sablonok, a séma-szinkron és a tagrepó-ellenőrző szabály (külön feladatok).
- Tartalomalapú besorolás (pl. `workspace.yaml` jelenléte), topicok, custom property-k.
- Profil-öröklés vagy szabály-felülírás profilonként.
- Teszt a valódi `github-manager.toml` tartalmára (csak a meglévő betöltési teszt marad).

## Implementation plan
1. `src/github_manager/config.py`: a `Config` kapjon `profiles: dict[str, list[str]]` mezőt (alapértelmezés üres). A `parse_config` validálja:
   - a tábla értékei nem üres stringlisták;
   - a `common` név foglalt;
   - a profilnevek nem üresek, és kis- és nagybetűtől függetlenül sem ismétlődnek.
   Config-hiba legyen, ha egy szabály `profiles` listájában nem definiált profil szerepel; ezt a `_check_visibility_owners` mintájára ellenőrizze.
2. `src/github_manager/rules/base.py`: a `Rule` kapjon `profiles: list[str]` mezőt, alapértelmezés `["common"]`. A `from_options` olvassa a közös `id` és `exclude` mellett. Üres lista vagy ismétlődő elem config-hiba.
3. Profilfeloldás egy helyen (pl. függvény a `config.py`-ban vagy az `engine.py`-ban): egy `Repo` profilja az a definiált profil, amelynek valamelyik mintája illeszkedik a `name`-re vagy a `full_name`-re. Ha egy sem illeszkedik: `common`. Ha több profil illeszkedik, a repó `Outcome.ERROR` riportot kap, a detail megnevezi az ütköző profilokat, és a futás a többi repóval folytatódik.
4. `engine.py`: a `_evaluate` és a `_verify_required` csak azokat a szabályokat vegye figyelembe, amelyek profiljai tartalmazzák a repó profilját, és amelyekre az `applies_to` igaz. A `RepoReport` kapjon `profile` mezőt.
5. `cli.py`: a `_print_report` és a `_write_step_summary` jelenítse meg a profilt.
6. Tesztek:
   - `tests/test_config.py`: a profilok és a `profiles` kulcs validálása.
   - `tests/test_engine.py`, `FakeGitHub`-bal:
     - besorolás név és OWNER/NAME szerint;
     - nem illeszkedő repó → `common`;
     - ütköző profilok → ERROR, a többi repó feldolgozva;
     - egy csak workspace profilú szabály nem fut common repón, és fordítva;
     - auto-merge döntés profil szerint.
   - `tests/test_cli.py`: a profil látszik a riportban és a step summaryben.
7. `github-manager.toml` frissítése (In scope szerint). README „Profiles” szakasz. Backlog decision rögzítése.

## Verification
- `uv run ruff format -q . && task verify` — formázás, lint, típusellenőrzés, tesztek ≥80% branch coverage-dzsel, audit, build sikeres.
- `uv run github-manager repos` — a valódi config betölthető (csak olvasó parancs).
- `uv run github-manager check -o tyutyutyu --repo zenget-workspace` (csak olvasó) — a riport a `workspace` profilt mutatja, SonarQube és owner szerinti visibility finding nincs.

## Dependencies and risks
- Nincs előfeltétel. A backlog verify, a workspace verify és a tagrepó-szabály feladatai erre épülnek.
- Kockázat: ha egy meglévő repó neve véletlenül `-workspace` vagy `-backlog` végű, profilt vált. Mitigáció: a riport kiírja a profilt, és a repó az `exclude`-dal kizárható.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A felső szintű profiles tábla profilnév → glob-lista párokat fogad; a common név foglalt, az üres lista, az ismétlődő profilnév és a nem string elem config-hiba
- [ ] #2 Minden szabálytípus elfogad egy profiles listát (alapértelmezés ["common"]); nem definiált profilnév, üres lista vagy ismétlődő elem config-hiba
- [ ] #3 Egy repó a repónévre vagy OWNER/NAME-re illeszkedő egyetlen profilba kerül, illeszkedés nélkül a common-ba; több illeszkedő profilnál a repó ERROR riportot kap az ütköző profilok nevével, a többi repó feldolgozása folytatódik
- [ ] #4 Egy repóra csak azok a szabályok futnak, és az auto-merge döntésben csak azok a repo_ruleset szabályok számítanak, amelyek profiles listája tartalmazza a repó profilját
- [ ] #5 A konzolriport és a step summary minden repónál kiírja a profilt
- [ ] #6 A github-manager.toml definiálja a workspace (*-workspace) és backlog (*-backlog) profilt; a SonarQube szabályok és a repo-visibility csak common, a többi meglévő szabály mindhárom profilra vonatkozik, és egy profile-visibility szabály mindkét ownerre privátot vár a workspace és backlog profilban
- [ ] #7 README Profiles szakasza és egy Backlog decision leírja a kizáró, névalapú profilokat
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 uv run ruff format -q . && task verify sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz a feladathoz nem tartozó változást
<!-- DOD:END -->
