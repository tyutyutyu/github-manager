---
id: TASK-5
title: >-
  Új self_hosted_runners szabálytípus: privát és internal repók csak self-hosted
  runnert használhatnak (jelzés)
status: To Do
assignee: []
created_date: '2026-10-17 19:39'
labels: []
dependencies: []
references:
  - src/github_manager/rules.py
  - src/github_manager/engine.py
  - tests/conftest.py
  - github-manager.toml
documentation:
  - README.md
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A privát (és internal) repók GitHub Actions jobjai ne fogyasszanak GitHub-hosted perceket, csak a saját self-hosted runneren fussanak. Egyetlen self-hosted gép van (zhukov), org szinten regisztrálva a `tyutyutyu-org` alatt; a címkéi: `self-hosted`, `Linux`, `X64`, `zhukov`. Privát repó csak a `tyutyutyu-org` alatt lehet (ezt a `repo_visibility` szabály jelzi; a `tyutyutyu` alatti privát repók ma mind a globális `exclude` listában vannak). GitHub-on nincs olyan repó- vagy org-beállítás, ami tiltaná a GitHub-hosted runnert, ezért a workflow-fájlok `runs-on` értékét kell vizsgálni.

A felhasználó döntései (2026-10-17):
- Hatókör: `private` és `internal` láthatóságú repók; a `public` repókat a szabály nem vizsgálja.
- Engedélyezett címkék: **pontos egyezés** egy konfigurált címkehalmazzal; a központi érték `allowed_runs_on = [["self-hosted"]]`.
- Statikusan el nem dönthető esetek (kifejezés, mátrix, külső reusable workflow) nem javítható findingot adnak, nem csúsznak át csendben.
- YAML-olvasás PyYAML-lal (`yaml.compose`, hogy a későbbi javító feladat ugyanazt a node-fát és pozíciókat használhassa).
- Nincs API-alapú runner-ellenőrzés; a tokenek rendben vannak.
- Ez a feladat **csak jelez**; az automatikus javítás (PR) a külön, erre épülő feladat.

Kódbeli kiindulópontok:
- Minta a report-only szabályra: `RepoVisibility` (`src/github_manager/rules.py`): `workspace.setting("visibility")`, `None` esetén `Finding(self.id, f"setting visibility {NOT_READABLE}", fixable=False)`.
- A `Workspace` Protocol (`rules.py` eleje) ma csak ismert útvonalat olvas (`read`), könyvtárat nem listáz. A `RemoteWorkspace` (`src/github_manager/engine.py`) a konstruktorban már lekéri a teljes fát: `self._paths = api.tree_paths(repo, sha)` (`set[str]`, vagy `None`, ha a lista nem elérhető vagy csonka), a rule-ok írásai a `self._written`-ben vannak. Ebből új API-hívás nélkül listázható a `.github/workflows/`.
- Test fake-ek: `MemoryWorkspace` és `FakeGitHub` (`tests/conftest.py`); a `FakeGitHub.tree_paths` mindig halmazt ad vissza.
- Opciók olvasása: `Options` (`rules.py`) — listák listájához nincs kész metódus, a `_take`-re vagy egy új típusos metódusra kell építeni; az ismeretlen kulcsot a `finish()` utasítja el.
- Szabálytípus regisztráció: `RULE_TYPES` (`rules.py` vége).
- Függőségek: `pyproject.toml` `dependencies` (ma csak `pygithub==2.10.0`, pontos rögzítéssel); a `deptry` a gate része.
- A `fixable=False` finding a CLI-ben `[manual]`, a PR törzsében a „Needs manual action” részbe kerül (`_pr_body`, `engine.py`), és `fix` módban is 1-es kilépési kódot ad.

## Objective
Új `self_hosted_runners` szabálytípus, ami a privát és internal repók minden workflow-jobjánál ellenőrzi, hogy a `runs-on` pontosan egy engedélyezett self-hosted címkehalmaz, és minden eltérést `fixable=False` findingként jelez. Semmit nem ír.

## Scope
### In scope
- PyYAML futásidejű függőség pontos verzióval; ha a `ty check` hiányzó típusokat jelez, `types-pyyaml` a `dev` csoportba, szintén pontos verzióval.
- Új `Workspace` metódus a fájlútvonalak listázására (Protocol, `RemoteWorkspace`, `MemoryWorkspace`), és a `FakeGitHub`-ban a nem elérhető fa (`tree_paths` → `None`) szimulálhatósága.
- `SelfHostedRunners` szabály (`type_name = "self_hosted_runners"`), `allowed_runs_on` opcióval és validálással, regisztrálva a `RULE_TYPES`-ban.
- `github-manager.toml`: új szabály utolsóként.
- Tesztek, README, projektskill.

### Out of scope
- Bármilyen automatikus javítás vagy fájlírás (a `runs_on` célérték és a PR-es csere a következő feladat).
- Runner-elérhetőség lekérdezése API-n.
- Publikus repókra vonatkozó fordított szabály (publikus repó ne használjon self-hosted runnert).
- `.github/actions/**` composite actionök és alkönyvtárak a `.github/workflows/` alatt (a GitHub csak a közvetlen fájlokat futtatja).
- A globális `exclude`, fork-, archivált- és üresrepó-szűrés.

## Implementation plan
1. **Függőség**: `uv add pyyaml==<legfrissebb stabil>` (a pin formája egyezzen a `pygithub==2.10.0`-val), majd `uv lock`. Csak akkor vegyél fel `types-pyyaml`-t a `dev` csoportba, ha a `uv run ty check` enélkül hibát ad.
2. **Útvonal-listázás**: a `Workspace` Protocolba új metódus, pl. `paths(self, prefix: str) -> list[str] | None`: a `prefix`-szel kezdődő fájlútvonalak rendezve, a rule-ok által írt fájlokkal együtt; `None`, ha a fa nem listázható.
   - `RemoteWorkspace`: `self._paths` ∪ `self._written` kulcsai; ha `self._paths is None`, `None`.
   - `MemoryWorkspace`: a `files` kulcsai; legyen egy konstruktorparaméter, amivel `None` kényszeríthető.
   - `FakeGitHub.add_repo`: opcionális paraméter, amivel a `tree_paths` `None`-t ad.
3. **Szabály** (`rules.py`, a `RepoVisibility` után): `SelfHostedRunners(Rule)`, mezője `allowed_runs_on: list[list[str]]`.
   - `_build`: `allowed_runs_on` kötelező, nem üres lista; minden eleme nem üres, nem üres stringekből álló lista; minden halmaz tartalmazza a `self-hosted` címkét (kis- és nagybetűtől függetlenül); két, kisbetűsítve azonos halmaz `ValueError` (duplikátum). Hibánál `ValueError` beszédes üzenettel, a meglévő szabályok stílusában.
   - `apply`:
     - `visibility = workspace.setting("visibility")`; `None` → egy `NOT_READABLE` finding (`fixable=False`); `"public"` → `[]`, és ilyenkor ne listázzon fájlt.
     - `workspace.paths(".github/workflows/")` → `None` esetén egy `fixable=False` finding (a workflow-k nem listázhatók), nem csendes átengedés. A vizsgált fájlok: közvetlenül a könyvtárban lévő `*.yml` és `*.yaml`, rendezve.
     - Fájlonként `yaml.compose(text, Loader=yaml.SafeLoader)`; `yaml.YAMLError` vagy több dokumentum → egy `fixable=False` finding a fájlra. A gyökér nem mapping, vagy nincs mapping típusú `jobs` → `fixable=False` finding.
     - Jobonkénti döntés (címke-összehasonlítás `casefold()`-dal, halmazként):
       | `runs-on` / job | eredmény |
       |---|---|
       | string vagy stringlista, a halmaz pontosan egyezik egy `allowed_runs_on` halmazzal | nincs finding |
       | string vagy stringlista, nem egyezik (pl. `ubuntu-latest`, `windows-latest`, `[self-hosted, Linux, X64, zhukov]`) | `fixable=False` finding |
       | bármely címke tartalmaz `${{` kifejezést | `fixable=False` finding (kézi ellenőrzés) |
       | mapping (`group:` / `labels:`), nem string listaelem, egyéb típus | `fixable=False` finding |
       | nincs `runs-on`, de `uses: ./...` (helyi reusable workflow) | nincs finding (a hívott fájlt a szabály külön vizsgálja) |
       | nincs `runs-on`, `uses` mással kezdődik (`owner/repo/...@ref`) | `fixable=False` finding (a hívott workflow dönti el a runnert) |
       | se `runs-on`, se `uses`, vagy a job nem mapping | `fixable=False` finding |
     - Az üzenet nevezze meg a fájlt, a jobot, a tényleges értéket (`json.dumps`) és az engedélyezett halmazokat, pl. `.github/workflows/ci.yml: job test: runs-on ["ubuntu-latest"] is not an allowed self-hosted runner (allowed: ["self-hosted"])`.
     - Soha nem hív `write`, `change_setting` vagy `change_ruleset` metódust.
   - Docstring a többi szabály stílusában.
4. **`github-manager.toml`**: a `repo-visibility` után, utolsóként:
   ```toml
   [[rules]]
   id = "private-self-hosted-runners"
   type = "self_hosted_runners"
   # Private and internal repositories: every job must run on exactly one of these label
   # sets. Mismatches are reported ([manual]).
   allowed_runs_on = [["self-hosted"]]
   exclude = []
   ```
5. **Tesztek** (valódi API-hívás nélkül):
   - `tests/test_rules.py` (`make_workspace`): publikus repó → nincs finding és nincs fájlolvasás; hiányzó `visibility` → `NOT_READABLE`; `private` és `internal` repó egyező `self-hosted` értékkel (string, egyelemű lista, `Self-Hosted`) → nincs finding; a táblázat minden sora; `.yaml` kiterjesztés; alkönyvtár és nem YAML fájl figyelmen kívül; érvénytelen YAML; több dokumentum; hiányzó `jobs`; nem listázható fa; `_build` hibák (hiányzó, üres, nem lista, üres string, `self-hosted` nélküli halmaz, duplikált halmaz, ismeretlen kulcs).
   - `tests/test_engine.py` (`fake_github`): egy privát repó `ubuntu-latest` workflow-val `fix` módban → `needs fix`, a finding a `manual_findings` között, nincs commit, PR és beállítás-írás (a `calls` write-prefix ellenőrzésével, ne a teljes listával); a `paths` a `RemoteWorkspace`-ben látja a más szabály által írt fájlt is.
   - `tests/test_config.py`: a `test_repository_config_file_is_valid` típuslistája kiegészül a `SelfHostedRunners`-szel (utolsó), és ellenőrzi az `id`-t és az `allowed_runs_on` értéket.
6. **README**: a „Rule types” táblázat új sora (`self_hosted_runners`: ellenőrzés leírása, javítás: *none: reported as manual*), és a „Not fixed automatically” felsorolás kiegészítése. A token-tábla nem változik.
7. **Projektskill** (`.claude/skills/github-manager-rules/SKILL.md`): a „Verification” rész a valódi config tesztjénél az új sorrendet írja (`self_hosted_runners` az utolsó), és egy rövid `self_hosted_runners rule` szakasz a fenti döntésekkel. A fájl a `.gitignore` miatt nem jelenik meg a diffben; ezt az átadásnál jelezni kell.

## Dependencies and risks
- Élesítés után a napi `enforce` futás (`.github/workflows/enforce.yml`) 1-es kóddal zárul, amíg van hatókörbe eső eltérő workflow. Ez szándékos jelzés; egyedi kivétel a szabály `exclude` listájával adható.
- PyYAML YAML 1.1: az `on:` kulcs `True`-ként olvasódik be. A szabály csak a `jobs` kulcsot használja, ez nem érinti, de ne építs az `on` kulcsra.
- A következő feladat (PR-es javítás) erre a szabályra és a `paths` metódusra épül.

## Verification
- `uv run pytest tests/test_rules.py tests/test_config.py tests/test_engine.py -q --no-cov`: az új esetek zöldek, a valódi `github-manager.toml` betöltődik.
- `uv run ruff format -q .`, `uv run ruff check --fix .`, majd `task verify`: minden lépés sikeres (format, lint, ty, deptry, pytest ≥80% branch coverage, audit, build).
- Kézi, merge után: GitHub Actions → `enforce` → `mode = check`. Várt: a `tyutyutyu-org` repóknál minden nem `self-hosted` jobra egy `[manual] private-self-hosted-runners: ...` sor (pl. `proxy-manager` `deploy.yml` a `[self-hosted, Linux, X64, zhukov]` értékkel); publikus repóknál nincs ilyen sor; `fix` módban sem változik workflow-fájl.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Privát és internal repóban minden `.github/workflows/*.yml|*.yaml` job, amelynek `runs-on` címkehalmaza (kis- és nagybetűtől függetlenül) nem egyezik pontosan egy `allowed_runs_on` halmazzal, pontosan egy `fixable=False` findingot ad, ami megnevezi a fájlt, a jobot, a tényleges és az engedélyezett értéket
- [ ] #2 Publikus repón nincs finding, és a szabály nem olvas workflow-fájlt; hiányzó `visibility` `NOT_READABLE` findingot ad
- [ ] #3 `${{ }}` kifejezés, mapping alakú `runs-on`, külső `uses` reusable workflow, hiányzó `runs-on`/`uses`, érvénytelen vagy több dokumentumos YAML, hiányzó `jobs` és nem listázható fa mind `fixable=False` findingot ad; a `uses: ./...` helyi hívás nem ad findingot
- [ ] #4 A szabály `check` és `fix` módban sem ír fájlt, beállítást vagy rulesetet, és egyedül nem nyit PR-t
- [ ] #5 Config-hiba (`ConfigError`): hiányzó, üres vagy rossz típusú `allowed_runs_on`, üres címke, `self-hosted` nélküli halmaz, kisbetűsítve duplikált halmaz, ismeretlen kulcs
- [ ] #6 A `github-manager.toml` utolsó szabálya a `private-self-hosted-runners` (`allowed_runs_on = [["self-hosted"]]`), és a `test_repository_config_file_is_valid` ezt ellenőrzi
- [ ] #7 A PyYAML pontos verzióval szerepel a `pyproject.toml` függőségei között és a `uv.lock`-ban; a README szabálytáblája és a „Not fixed automatically” lista leírja az új szabályt
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 A `uv run ruff format -q .` és a `task verify` hiba nélkül lefut (formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build)
- [ ] #2 Az új tesztek egyike sem hív valódi GitHub API-t; éles fiókon legfeljebb a csak olvasó `github-manager repos` parancs fut
- [ ] #3 A `.claude/skills/github-manager-rules/SKILL.md` leírja a `self_hosted_runners` szabályt és az új szabálysorrendet
<!-- DOD:END -->
