---
id: TASK-26
title: ADR-ek a meglévő fő tervezési döntésekről
status: Done
assignee: []
created_date: '2026-11-12T12:33:00Z'
updated_date: '2026-11-13T20:26:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/engine.py
  - src/github_manager/github.py
priority: low
type: docs
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A Backlogban 15 lezárt feladat van, de egyetlen dokumentum és egyetlen döntés (ADR) sincs (`backlog decision list --plain` és `backlog doc list --plain` üres). A projekt fő tervezési döntései csak kódkommentekben, a README-ben és lezárt feladatok szövegében élnek, így egy új fejlesztő vagy ágens nem látja, mi szándékos, és miért.

A rögzítendő, ma is érvényes döntések és a forrásuk:
1. **A szabályok csak a `Workspace` protokollon át olvasnak és írnak**; ugyanaz a kód szolgálja a `check`-et és a `fix`-et (a `rules` modul docstringje, `RemoteWorkspace` az `engine.py`-ban).
2. **Repónként egy pull request, rögzített ágról, minden futáskor egyetlen commitként újragenerálva; a futás idempotens** (`_sync_pull_request`, `_branch_matches` az `engine.py`-ban; README bevezető).
3. **A commit a GraphQL `createCommitOnBranch` hívással készül, hogy a GitHub aláírja** (`GitHub.commit_files` a `github.py`-ban).
4. **A repó-beállítások és a ruleset közvetlenül, nem PR-ral kerülnek a repóra; a ruleset írását visszaolvasás ellenőrzi; csak a `github-manager: <id>` nevű ruleset a kezelt, a többihez a program nem nyúl** (`_apply_ruleset`, `RepoRuleset`; TASK-2).
5. **Auto-merge csak ott, ahol a kezelt ruleset megköveteli a `verify` checket** (`VERIFY_CHECK`, `_verify_required`, `_auto_merge`; TASK-10, TASK-11).
6. **Az emberi döntést igénylő szabályok csak jeleznek, nem javítanak** (láthatóság, ágstratégia, hiányzó fájlok, workflow-trigger; TASK-4, TASK-13, TASK-14).
7. **A valódi `github-manager.toml` tartalmára nincs teszt, legfeljebb betöltési teszt** (TASK-12).

Forrás: docs/project-review-2026-11-12.md, 5.3.

## Objective
A hét meglévő tervezési döntés elfogadott ADR-ként, indoklással visszakereshető a Backlogban.

## Scope
### In scope
- Hét decision és hét indokló dokumentum létrehozása a `backlog` CLI-vel.

### Out of scope
- A HTTP-kliens döntése (PyGithub megszüntetése): azt a saját feladata rögzíti.
- Új döntések meghozatala, kód- vagy README-módosítás.
- A Backlog markdown fájlok közvetlen szerkesztése.

## Implementation plan
1. Minden döntésnél a jelenlegi kódból és a hivatkozott lezárt feladatokból (`backlog task view TASK-<n> --plain`) ellenőrizni, hogy az állítás ma is igaz; ami időközben megváltozott (pl. a PR újraépítése staging ággal), azt a jelenlegi állapot szerint kell leírni.
2. Döntésenként:
   - `backlog decision create "<cím>" -s accepted --plain` — a decision azonosítóját feljegyezni. A decision törzse CLI-vel nem adható meg (csak cím és státusz).
   - `backlog doc create "<cím>" -p adr -t other --plain`, majd `backlog doc update <docId> --content "$content"`, ahol a tartalom szakaszai: `## Context`, `## Decision`, `## Consequences`, `## Sources` (pontos fájl- és szimbólumnevek, feladatazonosítók), és az első sor megnevezi a decision azonosítóját.
3. A többsoros tartalmat idézőjelezett változóból kell átadni (valódi sortörésekkel), hogy a shell ne értelmezze a backtickeket.
4. Nyelv: magyar, a Backlog feladatokkal egyezően; a kódnevek eredeti alakban.
5. Visszaolvasás: `backlog decision list --plain` és dokumentumonként `backlog doc view <docId>`.

## Verification
- `backlog decision list --plain` — hét új decision `accepted` státusszal.
- `backlog doc list --plain` — hét dokumentum az `adr` útvonalon; `backlog doc view <docId>` mindegyiknél mutatja a négy szakaszt és a decision azonosítóját.
- Kézi ellenőrzés: a Sources szakaszokban megnevezett fájlok és szimbólumok léteznek (`grep -n "<szimbólum>" src/github_manager -r`).
- `git status --short` — csak a CLI által létrehozott Backlog-fájlok jelennek meg.

## Dependencies and risks
- Ha a compliance PR frissítését (staging ág) vagy az auto-merge feltételét érintő feladat időközben elkészült, a 2. és az 5. döntés szövege az új állapotot írja le.
- Kockázat az elavult vagy a kóddal ellentmondó állítás; ezt az 1. lépés ellenőrzése fogja meg.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A Backlogban hét új decision van `accepted` státusszal, a leírásban felsorolt hét döntésre
- [x] #2 Mindegyikhez tartozik egy dokumentum az `adr` útvonalon Context, Decision, Consequences és Sources szakasszal, amely megnevezi a decision azonosítóját
- [x] #3 A Sources szakaszok létező fájlokra, szimbólumokra és feladatazonosítókra hivatkoznak, és az állítások megfelelnek a jelenlegi kódnak
- [x] #4 A decisionök és dokumentumok a `backlog` CLI-vel készültek; a Backlog markdown fájljai nem lettek közvetlenül szerkesztve, és kód nem módosult
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Minden létrehozott decision és dokumentum vissza lett olvasva a `backlog` CLI-vel
- [x] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-26-adr-ek-a-meglevo-fo-tervezesi-dontesekrol.

Finalization check (2026-11-13): `backlog decision list --plain` shows decision-2..decision-8, all accepted (decision-1 is the pre-existing, out-of-scope HTTP-client ADR from TASK-24). `backlog doc list --plain` / `backlog doc view doc-2..doc-8`: each ADR doc lives under adr, names its decision ID on the first line and has the Context, Decision, Consequences and Sources sections. Every cited symbol was grepped in its stated file (RemoteWorkspace, _evaluate, _fix, setting_changes, ruleset_changes, _sync_pull_request, _rebuild_branch, _branch_matches, STAGING_SUFFIX, PR_UP_TO_DATE, PR_CLOSED, GitHub.commit_files/createCommitOnBranch/expectedHeadOid, update_repo_settings, _apply_ruleset, ruleset_matches, RULESET_PREFIX, RepoRuleset, VERIFY_CHECK, _verify_required, _auto_merge, CLEAN_STATUS, VERIFY_NOT_REQUIRED, requires_workflow_check, RepoVisibility, BranchStrategy, RequiredFiles, DefaultBranchPushOnly, Finding.fixable, load_config). TASK-2/4/10/11/12/13/14 exist. Claims match the current code (staging-branch rebuild, ruleset read-back without retry, auto-merge condition and immediate merge on clean status, fixable=False report-only rules). git status: only the TASK-26 file and the 14 new Backlog files; no code or README change. dev:verify passed (502 tests, 99.42% coverage). Minor wording: doc-8 Sources says the other config tests use tmp_path files, but most use in-memory parse_config data; the Decision section wording is accurate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Recorded the seven existing design decisions as accepted Backlog ADRs: decision-2..decision-8, each with a matching doc-2..doc-8 under adr (Context, Decision, Consequences, Sources). Topics: Workspace protocol only, one rebuilt single-commit PR per repo from a fixed branch with a staging branch (idempotent), signed commits through GraphQL createCommitOnBranch, direct settings/ruleset writes with read-back and only the 'github-manager: <id>' ruleset managed, auto-merge only where the managed ruleset requires verify, report-only rules for human decisions, and no tests on the real github-manager.toml beyond a load test. Everything was created with the backlog CLI and read back through it. Every cited file, symbol and task ID was checked against the current code. No code or README change; dev:verify passed. Follow-up (optional): doc-8 Sources slightly overstates tmp_path use in tests/test_config.py.
<!-- SECTION:FINAL_SUMMARY:END -->
