---
id: TASK-6
title: >-
  self_hosted_runners: ubuntu-* és nem pontos self-hosted runs-on automatikus
  cseréje self-hosted-re a compliance PR-ban
status: To Do
assignee: []
created_date: '2026-10-17 19:39'
labels: []
dependencies:
  - TASK-5
references:
  - src/github_manager/rules.py
  - src/github_manager/engine.py
  - .github/workflows/enforce.yml
  - github-manager.toml
documentation:
  - README.md
priority: medium
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `self_hosted_runners` szabály (TASK-5) a privát és internal repók workflow-jobjainál minden nem engedélyezett `runs-on` értéket `fixable=False` findingként jelez. A felhasználó döntése (2026-10-17): a biztonságosan átírható eseteket a szabály **javítsa a compliance PR-ban**, egyetlen központi célértékre (`runs-on: self-hosted`).

Miért biztonságos a csere: egyetlen self-hosted gép van (zhukov, org szinten a `tyutyutyu-org` alatt, címkéi `self-hosted`, `Linux`, `X64`, `zhukov`), így bármely `self-hosted`-et tartalmazó címkehalmaz ugyanarra a gépre fut, mint a puszta `self-hosted`. A `ubuntu-*` GitHub-hosted Linux runner is erre a Linux gépre cserélhető. A `windows-*` és `macos-*` nem cserélhető (más OS), ezek kézi döntést igényelnek. A tokenek Workflows: Read and write jogosultsága a felhasználó szerint megvan (a GitHub enélkül elutasítja a `.github/workflows/` alatti fájlok pusholását).

Kódbeli kiindulópontok:
- `SelfHostedRunners` (`src/github_manager/rules.py`, TASK-5): YAML-olvasás `yaml.compose(..., Loader=yaml.SafeLoader)`-rel; a node-ok `start_mark` / `end_mark` mezői (`line`, `column`, 0-tól) adják az érték pontos helyét a szövegben.
- Minta a fájlt író, PR-be kerülő javításra: `RequiredLines` és `RenovatePreset` (`rules.py`): `workspace.read` → módosított szöveg → `workspace.write`, a finding alapértelmezésben `fixable=True`. A fájlváltozásokból az engine egy commitot és egy PR-t készít (`_process`, `_pr_body`, `commit_files` a `src/github_manager/engine.py`-ban és a `src/github_manager/github.py`-ban).
- A rule-ok nem dobnak kivételt adathibára; az engine csak a `GitHubError`-t kezeli (`ERROR` outcome). Ha a javítás nem biztonságos, a szabály ne írjon, hanem `fixable=False` findingot adjon.
- A README token-táblájában és a `.github/workflows/enforce.yml` fejléc-kommentjében a Workflows jog ma „csak ha egy szabály a `.github/workflows` fájljait írja” megjegyzéssel szerepel.

## Objective
A `self_hosted_runners` szabály `fix` módban az átírható `runs-on` értékeket a konfigurált `runs_on` értékre cseréli a compliance PR-ban, a workflow-fájl többi részét (behúzás, kommentek, sorvégek, többi sor) bájtra változatlanul hagyva; minden más eset nem javítható finding marad.

## Scope
### In scope
- Új kötelező `runs_on` opció a szabályban, validálással.
- Az átírható esetek javítása és a javítás utáni önellenőrzés.
- `github-manager.toml`, README (szabálytábla, „Not fixed automatically”, token-tábla), az `enforce.yml` fejléc-kommentje, tesztek, projektskill.

### Out of scope
- `windows-*`, `macos-*`, ismeretlen címkék, kifejezések (`${{ }}`), mátrix, `group:`/`labels:` mapping, külső reusable workflow: ezek továbbra is `fixable=False` findingok (TASK-5 viselkedése).
- A workflow-k egyéb tartalmának (lépések, eszközök, cache) igazítása a self-hosted gépre.
- Runner-elérhetőség lekérdezése API-n; a token-jogosultságok beállítása.

## Implementation plan
1. **Opció**: `runs_on: list[str]` kötelező, nem üres, nem üres stringek listája. `_build`-ben `ValueError`, ha a `runs_on` kisbetűsített halmaza nem egyezik egyik `allowed_runs_on` halmazzal sem (különben a javítás után is finding maradna).
2. **Átírhatóság** (TASK-5 osztályozására építve, kizárólag string vagy stringlista `runs-on` esetén, kifejezés nélkül):
   - javítható, ha a halmaz pontosan egy elemű és az elem `fnmatch`-szel illeszkedik `ubuntu-*`-ra (kis- és nagybetűtől függetlenül);
   - javítható, ha a halmaz tartalmazza a `self-hosted` címkét, de nem engedélyezett (pl. `[self-hosted, Linux, X64, zhukov]`);
   - minden más eset változatlanul `fixable=False`.
3. **Biztonságos csere**: csak akkor írj, ha az érték node-ja egy soron belül van (`start_mark.line == end_mark.line`), ugyanazon a soron kezdődik, mint a `runs-on` kulcs node-ja (ez kiszűri az aliasokat és a több soros block listát), és scalar vagy flow sequence. Különben `fixable=False` finding („cannot rewrite safely”), írás nélkül.
   - A csere a `start_mark.column` és `end_mark.column` közötti szakaszt helyettesíti: egyelemű `runs_on` → a címke puszta scalarként (`self-hosted`), több elem → flow lista (`[a, b]`). A sor többi része (a kulcs előtti behúzás, a záró komment) megmarad.
   - Egy fájlon belül az összes cserét egy menetben végezd, hátulról előre, hogy a pozíciók ne csússzanak el. A sorvégek (`\n` / `\r\n`) és a fájl végi újsor maradjon az eredeti.
4. **Önellenőrzés**: a módosított szöveget parse-old újra, és osztályozd a TASK-5 logikájával. Ha bármely javított job még mindig nem engedélyezett, vagy a parse hibát ad, a fájlt ne írd, és adj `fixable=False` findingot. Csak sikeres ellenőrzés után `workspace.write(path, new_text)`; a javított jobok findingja `fixable=True`.
5. **`github-manager.toml`**: a `private-self-hosted-runners` szabály kapja meg a `runs_on = ["self-hosted"]` kulcsot, a komment írja le, hogy az `ubuntu-*` és a nem pontos self-hosted halmazok PR-ben cserélődnek.
6. **Tesztek** (valódi API-hívás nélkül):
   - `tests/test_rules.py`: `runs-on: ubuntu-latest` → `self-hosted`, a záró komment és a behúzás marad, a többi sor bájtra azonos; `runs-on: [ubuntu-22.04]` és idézőjeles `"ubuntu-latest"`; `[self-hosted, Linux, X64, zhukov]` → `self-hosted`; két javítandó job egy fájlban; CRLF sorvégű fájl; több soros block lista és alias (`&`/`*`) → `fixable=False`, nincs írás; `windows-latest` és `macos-latest` → `fixable=False`; a javított fájlon újrafuttatva nincs finding; `_build` hiba: hiányzó vagy nem engedélyezett `runs_on`.
   - `tests/test_engine.py` (`fake_github`): privát repó `ubuntu-latest` workflow-val `fix` módban → PR nyílik a javított fájllal, a második futás `pull request up to date`/compliant; egy javítható és egy nem javítható job ugyanabban a repóban → PR a javítással, és a nem javítható finding a PR „Needs manual action” részében.
   - `tests/test_config.py`: a `test_repository_config_file_is_valid` ellenőrzi a `runs_on` értéket.
7. **Dokumentáció**:
   - README szabálytábla: a `self_hosted_runners` sor javítás oszlopa leírja a cserét (PR-ben, `runs_on` értékre); a „Not fixed automatically” lista csak a nem javítható eseteket sorolja.
   - README token-tábla: a Workflows sor „Needed for” oszlopa: `self_hosted_runners` (a `.github/workflows` fájlok javítása); ne legyen többé „only if”.
   - `.github/workflows/enforce.yml` fejléc-kommentje: a Workflows: read/write a felsorolt kötelező jogok közé kerül.
   - Projektskill (`.claude/skills/github-manager-rules/SKILL.md`): a `self_hosted_runners` szakasz kiegészül a javítási szabályokkal (mi javítható, egysoros csere, önellenőrzés). A fájl a `.gitignore` miatt nem jelenik meg a diffben; ezt az átadásnál jelezni kell.

## Dependencies and risks
- Függ: TASK-5 (a szabály, az osztályozás és a `paths` metódus).
- A javított PR saját checkjei már a self-hosted gépen futnak; a felhasználó szerint ez nem jelent problémát.
- Ha egy token mégsem kapta meg a Workflows jogot, a commit `GitHubError`-ral (`ERROR` outcome) bukik az adott ownernél; ez nem a szabály hibája.

## Verification
- `uv run pytest tests/test_rules.py tests/test_config.py tests/test_engine.py -q --no-cov`: az új esetek zöldek.
- `uv run ruff format -q .`, `uv run ruff check --fix .`, majd `task verify`: minden lépés sikeres (format, lint, ty, deptry, pytest ≥80% branch coverage, audit, build).
- Kézi, merge után: GitHub Actions → `enforce` → `mode = check`, majd egy repóra `mode = fix`, `repo = tyutyutyu-org/proxy-manager`. Várt: PR nyílik, amelyben a `deploy.yml` `runs-on` sora `self-hosted`-re változik, és a diff más sort nem érint.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Privát vagy internal repóban az egyelemű `ubuntu-*` és a `self-hosted`-et tartalmazó, de nem engedélyezett `runs-on` érték `fix` módban a `runs_on` értékre (`self-hosted`) cserélődik a compliance PR-ban, a finding `fixable=True`
- [ ] #2 A javított fájl csak a cserélt értékekben tér el: a behúzás, a záró kommentek, a sorvégek (LF/CRLF), a fájl végi újsor és minden más sor bájtra azonos
- [ ] #3 Egy fájlon belül több javítandó job egy írással javul, és a javított fájlon a második futás nem ad findingot
- [ ] #4 Több soros block lista, alias, vagy olyan érték, ami a cserével sem lenne engedélyezett, nem íródik át, hanem `fixable=False` finding marad; `windows-*`, `macos-*` és ismeretlen címkék továbbra is `fixable=False`
- [ ] #5 Ha egy repóban javítható és nem javítható job is van, a PR tartalmazza a javítást, a nem javítható finding a PR „Needs manual action” részébe kerül
- [ ] #6 Config-hiba (`ConfigError`): hiányzó, üres vagy olyan `runs_on`, ami nem egyezik egy `allowed_runs_on` halmazzal sem; a `github-manager.toml` `runs_on = ["self-hosted"]` értékét a `test_repository_config_file_is_valid` ellenőrzi
- [ ] #7 A README (szabálytábla, „Not fixed automatically”, token-tábla Workflows sora) és az `enforce.yml` fejléc-kommentje a javítást és a kötelező Workflows: Read and write jogot írja le
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 A `uv run ruff format -q .` és a `task verify` hiba nélkül lefut (formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build)
- [ ] #2 Az új tesztek egyike sem hív valódi GitHub API-t; éles fiókon legfeljebb a csak olvasó `github-manager repos` parancs fut
- [ ] #3 A `.claude/skills/github-manager-rules/SKILL.md` `self_hosted_runners` szakasza leírja a javítási szabályokat
<!-- DOD:END -->
