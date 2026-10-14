---
id: TASK-2
title: 'Új repo_ruleset szabálytípus: központi branch ruleset a default ágon'
status: To Do
assignee: []
created_date: '2026-10-14 21:39'
labels: []
dependencies:
  - TASK-1
references:
  - 'https://docs.github.com/en/rest/repos/rules'
documentation:
  - README.md
modified_files:
  - src/github_manager/rules.py
  - src/github_manager/engine.py
  - src/github_manager/github.py
  - tests/conftest.py
  - tests/test_rules.py
  - tests/test_engine.py
  - tests/test_github.py
  - tests/test_config.py
  - github-manager.toml
  - README.md
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A default ágakon jelenleg alig van védelem. 2026-10-14-i állapot a 7 érintett repón:
- Klasszikus branch protection sehol nincs.
- Repó-szintű ruleset csak két org-repóban van, kézzel létrehozva:
  - `tyutyutyu-org/ph_toolbox`: „Protect default branch” (id 25033035), `deletion`, `non_fast_forward` és kötelező `verify` check.
  - `tyutyutyu-org/youtube-mirror`: „Protect main” (id 24051863), `deletion`, `non_fast_forward`, `pull_request` és kötelező `test` check.
- A `tyutyutyu/agent-skills` privát repó a személyes fiók Free csomagján van; a `GET repos/{owner}/{repo}/rulesets` válasza HTTP 403: „Upgrade to GitHub Pro or make this repository public to enable this feature.” A `tyutyutyu-org` szervezet Team csomagon van, ott privát repóban is működnek a rulesetek.

Döntés (felhasználó, 2026-10-14):
- Minden érintett repó default ágára egy központi branch ruleset kerül: törlés tiltása, force push tiltása, kötelező pull request, **bypass nélkül**.
- A kötelező status checkek repónként konfigurálhatók.

A ruleset-kezelés módját a `github-settings` skill írja le (`~/.claude/skills/github-settings/SKILL.md` és `references/repository-rulesets.md`):
- csak repó-szintű `repos/{owner}/{repo}/rulesets` végpontok;
- kiválasztás `includes_parents=false` lekéréssel, `source_type == "Repository"` alapján;
- teljes, csak írható mezőket tartalmazó payload;
- `POST`/`PUT` után visszaolvasás, vak újrapróbálás nélkül.

Kódbeli kiindulópontok:
- A szabályok a `Workspace` protokollon át dolgoznak (`src/github_manager/rules.py`).
- A közvetlenül alkalmazott (nem PR-es) változásokra már van minta: `Workspace.setting`/`change_setting`, `RemoteWorkspace.setting_changes` (`src/github_manager/engine.py`), `Finding.setting`, a `_process` a PR-szinkron után hívja az `api.update_repo_settings`-t, valamint `Outcome.SETTINGS_UPDATED`, és a `_pr_body` „Repository settings (applied directly)” szakasza.
- A PyGithub 2.10.0 `Repository` osztályában nincs ruleset-metódus (ellenőrizve), ezért a ruleset hívások a meglévő stdlib REST transzporton (`GitHub.call`, `GitHub.paginate` a `src/github_manager/github.py`-ban) menjenek.

## Objective
Új `repo_ruleset` rule type, amely minden hatókörbe eső repón fenntart egy github-manager által birtokolt branch rulesetet a default ágon (deletion, non_fast_forward, pull_request, opcionálisan repónként megadott required_status_checks). A `check` jelzi az eltérést, a `fix` létrehozza vagy frissíti a rulesetet.

## Scope
### In scope
- `RepoRuleset` szabály a `RULE_TYPES`-ban, típusnév `repo_ruleset`, opcióvalidálással.
- Workspace- és API-protokoll bővítés ruleset olvasásra és írásra; `RemoteWorkspace`, `GitHub`, valamint a tesztes `FakeGitHub` és `MemoryWorkspace` (`tests/conftest.py`) bővítése.
- Engine: a ruleset-változások alkalmazása `fix` módban, a PR-szinkron után, a settings mintájára; PR-leírás és kimenet.
- `github-manager.toml`: a központi szabály felvétele; README szabálytípus-táblázat és dokumentáció.

### Out of scope
- A kézi rulesetek (pl. „Protect default branch”, „Protect main”) módosítása, törlése vagy átvétele. Ezeket a szabály figyelmen kívül hagyja.
- Szervezeti vagy enterprise rulesetek, tag- és push-rulesetek.
- Bypass actorok kezelése (a payload mindig `"bypass_actors": []`).
- Klasszikus branch protection API.
- `allow_auto_merge` és a többi logikai repó-beállítás (függőségként külön feladat), `security_and_analysis` (külön feladat).

## Implementation notes
1. **Konfiguráció** (`RepoRuleset._build`), példa:
   ```toml
   [[rules]]
   id = "default-branch-ruleset"
   type = "repo_ruleset"
   required_status_checks = { "tyutyutyu/github-manager" = ["verify"], "tyutyutyu-org/ph_toolbox" = ["verify"], "tyutyutyu-org/youtube-mirror" = ["test"] }
   strict_required_status_checks = false
   exclude = []
   ```
   - `required_status_checks`: opcionális tábla. A kulcs ugyanúgy illesztett shell glob, mint az `exclude` (repónév vagy OWNER/NAME, `fnmatchcase`), az érték nem üres check-context nevek listája. Egy repóra az összes illeszkedő minta listájának rendezett, duplikátummentes uniója vonatkozik. Ha nincs illeszkedés, a payloadban nincs `required_status_checks` szabály.
   - `strict_required_status_checks`: bool, alapértelmezés `false`.
   - Ismeretlen kulcs, üres lista vagy üres string legyen `ValueError`, ugyanúgy, ahogy az `Options` ma kezeli.
   - A szabálynak ismernie kell a repó nevét; ehhez a Workspace-nek ki kell tennie a teljes repónevet (a `RemoteWorkspace` már tárolja `_repo`-ként).
2. **Kezelt ruleset azonosítása:** a neve `github-manager: <rule id>`. A `GET repos/{owner}/{repo}/rulesets?includes_parents=false&per_page=100` (lapozva) listából csak a `source_type == "Repository"` és ilyen nevű elemet tekinti a magáénak. Ha több ilyen van, az `fixable=False` finding, nincs írás.
3. **Kívánt payload**, csak írható mezőkkel:
   - `name`, `"target": "branch"`, `"enforcement": "active"`, `"bypass_actors": []`;
   - `"conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}`;
   - `rules` ebben a sorrendben:
     - `{"type": "deletion"}`;
     - `{"type": "non_fast_forward"}`;
     - `{"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false, "require_last_push_approval": false, "required_review_thread_resolution": true, "allowed_merge_methods": ["merge", "squash", "rebase"]}}`;
     - ha van check: `{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": <strict>, "do_not_enforce_on_create": false, "required_status_checks": [{"context": "<név>"}, ...]}}`.
4. **Összehasonlítás:** a meglévő kezelt rulesetet a `GET .../rulesets/{id}?includes_parents=false` teljes válaszával kell összevetni. Csak a payloadban megadott kulcsokat szabad nézni: a GitHub a `pull_request` paraméterekhez saját alapértelmezett mezőket ad (pl. `required_reviewers`, `dismissal_restriction`, `require_extra_approval_for_unattributed_changes`), a check-elemekhez `integration_id`-t. Ha ezeket is összevetné, minden futás örök eltérést jelezne. A szabálytípusok sorrendje nem számít.
5. **Findingok:**
   - hiányzó ruleset: fixable, közvetlenül alkalmazott (`Finding.setting=True` vagy azonos szerepű jelző), pl. `ruleset github-manager: <id> is missing`;
   - eltérő ruleset: ugyanígy, pl. `ruleset github-manager: <id> is outdated`;
   - a 403 „Upgrade to GitHub Pro…” válasz és a több azonos nevű kezelt ruleset `fixable=False`; ezek nem `Outcome.ERROR`-ok.
   - Más HTTP hiba `GitHubError` marad, így a repó `ERROR` lesz.
6. **Alkalmazás `fix` módban** a settings mintájára, a PR-szinkron után:
   - hiányzó ruleset: `POST repos/{owner}/{repo}/rulesets`; meglévő: `PUT repos/{owner}/{repo}/rulesets/{id}` a teljes payloaddal;
   - időtúllépés vagy kétértelmű hiba után nincs automatikus újrapróbálás;
   - az írás után a szerver állapotát vissza kell olvasni, és ha a kezelt kulcsok nem egyeznek a kívánt payloaddal, `GitHubError`;
   - ha csak ruleset vagy settings változott, a repó kimenete `settings updated` (vagy egy azonos szerepű új `Outcome`); a PR-leírásban a közvetlenül alkalmazott szakaszba kerül;
   - `check` módban semmilyen írás nem történhet.
7. **Tesztek:** a `tests/test_rules.py` és `tests/test_engine.py` a `FakeGitHub` / `MemoryWorkspace` fake-ekkel, valódi API-hívás nélkül. Lefedendő:
   - opcióvalidálás;
   - glob-unió;
   - hiányzó, naprakész és eltérő (extra szerveroldali mezőkkel is naprakésznek minősülő) ruleset;
   - kézi ruleset érintetlensége;
   - duplikált kezelt név;
   - 403 Free csomag;
   - `check` írás nélkül;
   - `fix` utáni második futás `compliant`.

   A `tests/test_github.py` a meglévő `FakeHttp` openerrel teszteli az új REST metódusokat, lapozással és 403-mal.
8. **Dokumentáció és konfiguráció:**
   - `github-manager.toml`: a fenti szabály, a check-nevekkel. Ezek a default ág utolsó commitján 2026-10-14-én ténylegesen futó checkek voltak: github-manager → `verify` (és `SonarCloud Code Analysis`, ami nem kell), ph_toolbox → `verify`, youtube-mirror → `test`.
   - README „Rule types” táblázat: új sor; a „Tokens” szakasz Administration-indoklása említse a rulesetet is.
   - A `tests/test_config.py::test_repository_config_file_is_valid` várt típuslistája bővüljön.

## Verification
- `uv run ruff format -q .` majd `task verify`: formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build; mind sikeres.
- `uv run pytest tests/test_rules.py tests/test_engine.py tests/test_github.py -q --no-cov`: az új ruleset-tesztek zöldek.
- Kézi, a merge után: GitHub Actions → `enforce` → `mode = check`. Várt:
  - minden érintett repónál `ruleset github-manager: default-branch-ruleset is missing` jellegű `[fix]` sor;
  - a `tyutyutyu/agent-skills` repónál `[manual]` sor a 403 miatt;
  - a futás `ERROR` nélkül zárul.
- Kézi, a `fix` futás után, egy repón: `gh api -H 'X-GitHub-Api-Version: 2026-03-10' 'repos/tyutyutyu/github-manager/rulesets?includes_parents=false'` listázza a `github-manager: default-branch-ruleset` rulesetet `active` enforcementtel. Egy második `check` futás erre a repóra `compliant`.

## Dependencies and risks
- Előfeltétel: a `repo_settings` rule type (és a `Finding.setting` / `update_repo_settings` minta) a `main`-en van; a feladat létrehozásakor csak commitolatlan munka volt.
- Előfeltétel: a `GH_MANAGER_TOKEN` és `GH_MANAGER_ORG_TOKEN` tokenek Administration: Read and write joggal (README „Tokens”).
- Kockázat: bypass nélküli kötelező PR. Élesítés után a tulajdonos sem pusholhat közvetlenül egyik érintett repó default ágára sem. A github-manager saját működését nem érinti (csak a `feature/github-manager-compliance` ágra pushol, a PR-t a felhasználó mergeli). Élesítés előtt `check` futás és a felhasználó tájékoztatása szükséges.
- Kockázat: rossz vagy nem létező check-név a `required_status_checks`-ban minden PR-t mergelhetetlenné tesz az adott repóban. Csak a default ágon ténylegesen riportoló check-neveket szabad felvenni (`gh api repos/{owner}/{repo}/commits/{default}/check-runs --jq '.check_runs[].name'`).
- Kockázat: a Renovate automerge kötelező checkekkel csak `allow_auto_merge = true` mellett megy a platform-automerge-en át; ezt a függőségként megadott feladat állítja be.
- A kézi rulesetek a kezelt mellett megmaradnak; a GitHub a szabályokat összegzi, ez nem okoz ütközést.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `repo_ruleset` típus szerepel a `RULE_TYPES`-ban; a `required_status_checks` (glob → nem üres check-lista tábla) és a `strict_required_status_checks` (bool) opciót validálja, ismeretlen kulcsra, üres listára vagy üres stringre konfigurációs hibát ad
- [ ] #2 `check` módban egy hiányzó vagy eltérő `github-manager: <rule id>` nevű ruleset fixable findinget ad, és semmilyen írás nem történik GitHubon
- [ ] #3 `fix` módban a hiányzó ruleset `POST`-tal létrejön, az eltérő `PUT`-tal frissül a teljes payloadra (deletion, non_fast_forward, pull_request 0 jóváhagyással és kötelező szálfeloldással, bypass nélkül, `~DEFAULT_BRANCH`), és a visszaolvasott állapot egyezik
- [ ] #4 Egy repó csak akkor kap `required_status_checks` szabályt, ha a neve illeszkedik a konfigurált mintákra; több illeszkedésnél a check-nevek rendezett, duplikátummentes uniója kerül bele
- [ ] #5 Egy naprakész kezelt ruleset, amelynek szerveroldali válasza extra alapértelmezett mezőket (pl. `required_reviewers`, `integration_id`) is tartalmaz, `compliant`; a `fix` utáni második futás nem jelez eltérést
- [ ] #6 A nem github-manager nevű (kézi) rulesetek változatlanok maradnak
- [ ] #7 A Free csomagos privát repó 403-as válasza és a több azonos nevű kezelt ruleset `[manual]` finding, nem `ERROR`; minden más API-hiba `ERROR`
- [ ] #8 Csak ruleset- vagy settings-változásnál nem nyílik PR; ha PR is nyílik, a ruleset-változás a „Repository settings (applied directly)” szakaszban szerepel, a commit üzenetben nem
- [ ] #9 A `github-manager.toml` tartalmazza a központi szabályt a github-manager, ph_toolbox (`verify`) és youtube-mirror (`test`) check-nevekkel, a README szabálytípus-táblázata és a „Tokens” szakasza leírja az új típust
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 A `task verify` sikeres, az új kód branch-lefedettsége a tesztekben teljes
- [ ] #2 Az élesítés (első `fix` futás) előtt a felhasználó tudomásul vette, hogy a default ágakra bypass nélkül csak PR-en át lehet bejutni
<!-- DOD:END -->
