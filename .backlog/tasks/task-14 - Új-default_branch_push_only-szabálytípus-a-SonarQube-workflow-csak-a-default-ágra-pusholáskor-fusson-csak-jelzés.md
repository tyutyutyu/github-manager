---
id: TASK-14
title: >-
  Új default_branch_push_only szabálytípus: a SonarQube workflow csak a default
  ágra pusholáskor fusson (csak jelzés)
status: Done
assignee: []
created_date: '2026-11-03T21:18:00Z'
updated_date: '2026-11-03T22:42:00Z'
labels: []
dependencies:
  - TASK-13
modified_files:
  - src/github_manager/rules.py
  - github-manager.toml
  - README.md
  - tests/test_rules.py
  - tests/test_engine.py
priority: medium
type: feature
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A tyutyutyu-org repóiban a `.github/workflows/sonarqube.yml` workflow (létezését a TASK-13 `required_files` szabálya jelzi) a zhukovon futó SonarQube Community Buildre (26.10, `http://zhukov:9000`) küld elemzést. A Community Build csak egy ágat elemez: PR-, Renovate- vagy más ágról futtatott elemzés felülírja a main eredményét. Ezért a workflow csak a default ágra (main) pusholáskor futhat. A workflow tartalma egyébként projektenként szabad (build, tesztfuttatás, scanner), a github-manager ezen kívül semmit nem ellenőriz benne.

Döntések (2026-11-03): egyetlen megengedett trigger a `push` a default ágra; Renovate- és más ágakról nem fut; `pull_request`, `pull_request_target`, `workflow_dispatch` (a UI-ban bármely ágon indítható), `schedule`, `workflow_call` és minden más trigger tilos. Csak jelez, nem javít.

Meglévő építőelemek a `src/github_manager/rules.py`-ban (TASK-11): `yaml.compose(text, Loader=yaml.SafeLoader)` node-fa; `_entry(root, "on")` (a PyYAML YAML 1.1 az `on` kulcsot `True`-ként tölti be, a node-fán viszont `on` a skalár), `_mapping`, `_patterns`, `_text`, `_branch_listed`. A futtató runner self-hosted kényszerét a meglévő `private-self-hosted-runners` szabály adja, ezt nem kell ismételni.

## Objective
Új `default_branch_push_only` szabálytípus: a `path` opcióban megadott workflow-fájl `on` triggere csak `push` lehet, amelynek `branches` szűrője pontosan a repó default ágát tartalmazza; minden eltérés `fixable=False` finding, a hiányzó fájl nem finding.

## Scope
### In scope
- `DefaultBranchPushOnly` szabályosztály, `RULE_TYPES` bejegyzés, `path` opció.
- Statikus trigger-elemzés a fájl szövegéből.
- `github-manager.toml` új `[[rules]]` blokk: `id = "sonarqube-main-only"`, `type = "default_branch_push_only"`, `path = ".github/workflows/sonarqube.yml"`, `exclude = ["tyutyutyu/*"]`, magyarázó kommenttel (Community Build csak egy ágat elemez).
- Tesztek szintetikus configgal, README, github-manager-rules skill.

### Out of scope
- A fájl létezésének ellenőrzése (TASK-13).
- A workflow tartalmának bármely más része (jobok, lépések, tesztfuttatás, `runs-on`, job-szintű `if:`).
- Javítás vagy írás a kezelt repókban.
- SonarQube szerver, token, org secret/változó.
- Teszt a valódi `github-manager.toml` tartalmára.

## Implementation plan
1. `src/github_manager/rules.py`: `DefaultBranchPushOnly(Rule)` frozen, kw_only dataclass, `type_name = "default_branch_push_only"`, mező `path: str`. `_build`: `options.text("path", REQUIRED)`; config-hiba, ha nem a `WORKFLOWS_DIR` közvetlen `.yml`/`.yaml` gyereke.
2. `apply`: `text = workspace.read(self.path)`; `None` → `[]`. Különben egy problémaszöveget számol, és ha van, `[Finding(self.id, f"{self.path}: {problem}", fixable=False)]`.
3. Érvényes, ha mind teljesül (különben a legelső hibát nevezze meg az üzenet):
   - érvényes, egydokumentumos YAML, mapping gyökérrel (különben `invalid YAML (...)`);
   - van `on` kulcs (node-fán `_entry(root, "on")`), és mapping; string (`on: push`) vagy lista (`on: [push]`) → hiba: a push szűrő nélkül minden ágon fut;
   - az `on` mapping egyetlen kulcsa `push`; minden más kulcsot rendezve nevezzen meg (`other triggers: pull_request, workflow_dispatch`);
   - a `push` értéke mapping, benne `branches` (`_patterns`-szel olvasva) pontosan egy elem, amely betű szerint egyenlő `workspace.default_branch`-csel (glob, `!` negálás, más ág → hiba);
   - nincs `branches-ignore`, `tags`, `tags-ignore` kulcs a `push` alatt (`tags` mellett tag-pusholásra is futna); `paths`/`paths-ignore` megengedett, mert csak szűkít.
4. `RULE_TYPES`-be felvenni; `github-manager.toml` blokk a TASK-13 `sonarqube-workflow` szabálya után.
5. Tesztek (`tests/test_rules.py` `MemoryWorkspace`-szel, egy engine-teszt `tests/test_engine.py`-ban `FakeGitHub.add_repo`-val, write-prefix ellenőrzéssel): érvényes `push: branches: [main]` és `branches: main`; `paths` szűrővel érvényes; más default ág (pl. `master`) a workspace-ből; hiányzó fájl → nincs finding; `on: push` string és lista; `pull_request`, `workflow_dispatch`, `schedule` mellé téve; `branches: ["main", "renovate/**"]`; `branches: ["*"]`; `branches-ignore`; `tags`; hiányzó `branches`; hiányzó `on`; YAML-hiba; mindegyiknél a teljes üzenet szövegét ellenőrizve; config-hiba rossz `path`-ra.
6. `README.md` Rule types tábla új sora és a „Not fixed automatically” lista; `.claude/skills/github-manager-rules/SKILL.md` rövid szakasz (gitignore-olt, nem jelenik meg a diffben).

## Verification
- `uv run ruff format -q . && task verify` — format, lint, ty, pytest ≥80% branch coverage, audit, build sikeres.
- `uv run github-manager repos` — a valódi config betölthető (csak olvasó parancs).

## Dependencies and risks
- TASK-13: a hiányzó fájlt az jelzi; e nélkül a hiányzó workflow észrevétlen maradna.
- A statikus elemzés nem látja a job-szintű `if:` feltételt (pl. `workflow_dispatch` + `if: github.ref == 'refs/heads/main'`); ezért tilos a `workflow_dispatch`, a szigorúság szándékos.
- Ha valaha más default ág lesz, a szabály a `workspace.default_branch`-et követi, nem a literál `main`-t.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A default_branch_push_only szabálytípus regisztrálva van; a path workflow-ra nincs finding, ha az on csak push, és a branches szűrő pontosan a default ág
- [x] #2 on: push string vagy lista, más trigger (pull_request, pull_request_target, workflow_dispatch, schedule, workflow_call stb.), hiányzó vagy többelemű branches, glob vagy negált minta, branches-ignore, tags, tags-ignore, hiányzó on és YAML-hiba esetén fixable=False finding nevezi meg az okot
- [x] #3 paths és paths-ignore szűrő mellett a workflow érvényes
- [x] #4 Hiányzó fájlra nincs finding; a szabály soha nem ír és nem nyit PR-t
- [x] #5 Nem a WORKFLOWS_DIR közvetlen .yml/.yaml gyerekét megadó path config-hiba
- [x] #6 A github-manager.toml-ban sonarqube-main-only szabály path = ".github/workflows/sonarqube.yml", exclude = ["tyutyutyu/*"]
- [x] #7 README Rule types tábla és a Not fixed automatically lista, valamint a github-manager-rules skill leírja a szabályt
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . és task verify sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-14-uj-default-branch-push-only-szabalytipus-a-sonar.

Finalization 2026-11-03: `uv run ruff format -q . && task verify` passed (format, lint, ty, deptry, 479 tests, 99.40% branch coverage, audit, build). `uv run github-manager repos` loads the real config. Review repair: non-mapping `on` is rendered by `_shown` without constructing the node (tags, aliases, numbers, empty value). tests/test_config.py only checks that the real config loads (pre-existing, not part of this diff).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the report-only `default_branch_push_only` rule type (`DefaultBranchPushOnly` in src/github_manager/rules.py, registered in RULE_TYPES). For the workflow at `path` (must be a direct .yml/.yaml child of .github/workflows/, else config error) it reports one fixable=False finding naming the first problem unless `on` is a mapping whose only trigger is `push` with `branches` exactly equal to the workspace default branch and no branches-ignore/tags/tags-ignore; paths/paths-ignore are allowed; a missing file yields no finding and nothing is ever written. github-manager.toml gained `sonarqube-main-only` (path .github/workflows/sonarqube.yml, exclude tyutyutyu/*) because the SonarQube Community Build analyses a single branch. README and the github-manager-rules skill describe the rule. Verification: `uv run ruff format -q . && task verify` green (479 tests, 99.40% coverage); real config loads via `uv run github-manager repos`. Risk: the static check ignores job-level `if:`, so workflow_dispatch is deliberately forbidden.
<!-- SECTION:FINAL_SUMMARY:END -->
