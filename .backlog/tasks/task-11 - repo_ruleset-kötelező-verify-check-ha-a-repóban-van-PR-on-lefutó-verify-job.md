---
id: TASK-11
title: 'repo_ruleset: kötelező verify check, ha a repóban van PR-on lefutó verify job'
status: Done
assignee: []
created_date: '2026-10-21T18:14:00Z'
updated_date: '2026-10-21T22:48:00Z'
labels: []
dependencies: []
modified_files:
  - src/github_manager/rules.py
  - github-manager.toml
  - tests/test_rules.py
  - tests/test_engine.py
  - tests/test_config.py
  - README.md
priority: high
type: feature
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Elvárás: minden kezelt repóban legyen `verify` workflow, és a `verify` check legyen kötelező a PR-merge-hez. Erre épül a compliance PR-ok auto-merge-e (TASK-10): auto-merge csak ott lehet, ahol a `verify` kötelező.

A kötelező check neve a GitHubon a check run neve: a job `name:` mezője, ennek hiányában a job id; nem a workflow neve vagy fájlneve. Mátrixos job neve `verify (<érték>)`, reusable hívásé `verify / <job>`, ezek nem teljesítik a `verify` checket. Kis- és nagybetű számít.

Kockázat: ha a ruleset olyan checket tesz kötelezővé, amely a PR-on sosem fut le, egyetlen PR sem mergelhető (az sem, amely javíthatná). Ezért a `verify` csak akkor kerülhet a rulesetbe, ha a default ágon lévő workflow-k alapján a check biztosan lefut a default ágra nyitott PR-okon.

Meglévő építőelemek a `src/github_manager/rules.py`-ban: `RepoRuleset` (`checks_for`, `payload`, `apply`), `SelfHostedRunners` workflow-listázása (`workspace.paths(WORKFLOWS_DIR)`, csak közvetlen `.yml`/`.yaml` gyerekek) és YAML-segédek (`_jobs`, `_mapping`, `_entry`; `yaml.compose(..., Loader=yaml.SafeLoader)`). A PyYAML YAML 1.1: az `on:` kulcs `True`-ként töltődik be, a node-fán viszont a kulcs skalár értéke `on`.

## Objective
A `repo_ruleset` szabály egy új opcióval (`required_workflow_check = "verify"`) a menedzselt rulesetbe kötelező checkként felveszi a `verify`-t, ha a repó default ágán van érvényes, PR-on lefutó `verify` job; különben manuális findingot ad, amely megmondja, mi hiányzik, és a `verify`-t nem teszi kötelezővé. A szabály lekérdezhetővé teszi, hogy egy repóban a `verify` kötelező-e (ezt használja TASK-10).

## Scope
### In scope
- `RepoRuleset` új opcionális kulcsa (`required_workflow_check`, nem üres string; hiányában a viselkedés változatlan).
- Statikus workflow-elemzés a default ágon.
- A rulesetbe kerülő checklista: a `required_status_checks` globok uniója + a `verify`, ha érvényes (rendezve, duplikáció nélkül).
- Lekérdezés (pl. `RepoRuleset.requires_workflow_check(workspace) -> bool` vagy a workspace-függő checklista), amelyből TASK-10 eldönti az auto-merge jogosultságot.
- `github-manager.toml`: `required_workflow_check = "verify"`; a `required_status_checks` globok közül a csak `verify`-t előíró bejegyzések feleslegessé válnak és törlendők.
- Tesztek, README, a github-manager-rules skill.

### Out of scope
- `verify` workflow-k írása vagy generálása repókban; bármilyen írás más repókba ezen a kódon kívül.
- Check run-ok élő lekérdezése a GitHubról (a döntés statikus a default ág fájljaiból).
- Az auto-merge (TASK-10).
- Új szabálytípus: a logika a `repo_ruleset`-ben marad, hogy a „kötelező-e” döntés és a ruleset payload egy helyen legyen.

## Implementation plan
1. `RepoRuleset._build`: új `required_workflow_check` opció; üres string config-hiba.
2. Új függvény (pl. `_workflow_check_problem(workspace, check, default_branch) -> str | None`), amely a `.github/workflows/` közvetlen `.yml`/`.yaml` fájljait végignézi, és akkor érvényes (None), ha legalább egy fájlban:
   - a trigger tartalmazza a `pull_request`-et (`on` lehet string, lista vagy mapping; a node-fán az `on` kulcsot keresd);
   - a `pull_request` `branches` szűrője (ha van) illeszkedik a default ágra (`fnmatchcase`), a `branches-ignore` (ha van) nem; `paths` vagy `paths-ignore` szűrő esetén érvénytelen (a check függőben maradna);
   - van job, amelynek check-neve pontosan a `check`: `name:` skalár = `check`, vagy `name` nélkül a job id = `check`; a `name` nem tartalmaz `${{`-t;
   - a job nem reusable hívás (`uses:`) és nincs `strategy.matrix`-a.
   Ha nincs érvényes fájl, a szöveg nevezze meg a legközelebbi okot (nincs `verify` job; mátrix; reusable; nincs `pull_request` trigger; path-szűrő; branch-szűrő; listázhatatlan fa; YAML-hiba).
3. `RepoRuleset`: a checklista workspace-függő lesz; a `payload` ezt használja; az `apply` érvénytelen workflow esetén `fixable=False` findingot ad (`required check verify is not added: <ok>` jellegű üzenettel), a ruleset többi része ettől még fix-elődik.
4. `github-manager.toml`: a fenti módosítások, megjegyzéssel (a check neve a job neve; mátrix/reusable nem jó; path-szűrő tilos).
5. Tesztek (`tests/test_rules.py`, `tests/test_engine.py`; config-parse esetek a `tests/test_config.py`-ban, de NEM a valódi `github-manager.toml` tartalmára): érvényes egyszerű workflow; `name: verify` más job id-val; mátrix; reusable `uses`; `on: pull_request` string/lista/mapping; `branches` illeszkedik/nem; `paths` szűrő; nincs workflow; listázhatatlan fa (`MemoryWorkspace(listable=False)`); YAML-hiba; `Verify` nagybetűvel nem érvényes; a payload checklistája a glob-unióval együtt rendezett és duplikációmentes; az opció hiányában a payload változatlan; a lekérdezés igaz/hamis értéke.
6. `README.md` Rule types `repo_ruleset` sora és a kötelező checkekről szóló figyelmeztetés; `.claude/skills/github-manager-rules/SKILL.md` „repo_ruleset rule” szakasza.

## Verification
- `uv run ruff format -q . && task verify` — sikeres.
- `uv run github-manager repos` — a valós config betölthető (csak olvasó parancs).

## Dependencies and risks
- Nincs előfeltétel. TASK-10 erre épül.
- A statikus elemzés nem látja, ha a job `if:` feltétellel skipel; a skipelt job a GitHubon teljesíti a kötelező checket, ez elfogadható.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 required_workflow_check opcionális repo_ruleset kulcs; hiányában a payload változatlan, üres string config-hiba
- [x] #2 Érvényes verify job esetén a menedzselt ruleset required_status_checks listája tartalmazza a verify-t a glob-unióval együtt, rendezve, duplikáció nélkül
- [x] #3 Mátrix, reusable uses, hiányzó pull_request trigger, paths szűrő, nem illeszkedő branches szűrő, nagybetűs Verify, hiányzó workflow, listázhatatlan fa és YAML-hiba esetén a verify nem kerül a rulesetbe, és fixable=False finding nevezi meg az okot
- [x] #4 A szabályból lekérdezhető, hogy egy repóban a verify kötelező-e; tesztelve igaz és hamis esetre
- [x] #5 A github-manager.toml-ban required_workflow_check = verify, a csak verify-t előíró glob bejegyzések törölve
- [x] #6 README és a github-manager-rules skill leírja a verify check feltételeit
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . és task verify sikeres
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-11-repo-ruleset-kotelezo-verify-check-ha-a-repoban.

Finalization: uv run ruff format -q . exit 0 and task verify exit 0 (390 passed, coverage 99.28%, ruff/ty/deptry/audit/build ok). Format run changed no tracked/untracked path (git status identical before/after). Files changed: rules.py, engine.py, conftest.py, test_rules.py, test_engine.py, test_config.py, README.md, github-manager.toml, this task file; the github-manager-rules SKILL.md is git-ignored (.gitignore:265 .claude/) but read and describes the conditions. Correction: the earlier Modified files list omitted engine.py and tests/conftest.py (original_paths/original default-branch accessors).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
required_workflow_check option added to repo_ruleset. rules.py statically analyses default-branch workflows (pull_request trigger, branches/types/paths filters, exact job check name, no matrix/reusable) and adds verify to the sorted, de-duplicated check union only when valid; otherwise a fixable=False finding names the cause. RepoRuleset.requires_workflow_check answers whether verify is required (for TASK-10). The analysis reads only the default-branch commit (new original/original_paths accessors in engine.py). github-manager.toml now sets required_workflow_check = verify and drops the verify-only globs. README and the skill document the conditions. Verified: ruff format exit 0 and task verify exit 0 in this session (390 tests, 99.28% coverage). Not run: uv run github-manager repos (live-config load). Risk: static analysis does not see job if: skips.
<!-- SECTION:FINAL_SUMMARY:END -->
