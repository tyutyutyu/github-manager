---
id: TASK-4
title: >-
  Új repo_visibility szabálytípus: publikus repók a tyutyutyu, privátak a
  tyutyutyu-org alatt (csak jelzés)
status: To Do
assignee: []
created_date: '2026-10-16 17:19'
updated_date: '2026-10-16 17:20'
labels: []
dependencies: []
documentation:
  - README.md
modified_files:
  - src/github_manager/rules.py
  - src/github_manager/config.py
  - github-manager.toml
  - tests/test_rules.py
  - tests/test_config.py
  - tests/test_engine.py
  - README.md
priority: medium
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A két owner szerepe szétválik: a `tyutyutyu` (személyes fiók) alatt csak publikus, a `tyutyutyu-org` szervezet alatt csak privát repó lehet. Ezt ma semmi nem ellenőrzi. A láthatóság megváltoztatása vagy a repó átvitele másik ownerhez (transfer) emberi döntés, ezért a felhasználó döntése (2026-10-16): **nincs automatikus javítás, csak hibajelzés**.

Kódbeli kiindulópontok:
- A minta a `BranchStrategy` (`src/github_manager/rules.py`): csak `Finding(..., fixable=False)` findingokat ad vissza, a workspace-be nem ír.
- A láthatóságot a `RepoSettings.apply` már olvassa: `workspace.setting("visibility")` (értéke `"public"`, `"private"` vagy `"internal"`). Ez a `GitHub.repo_settings` (`src/github_manager/github.py`, PyGithub `get_repo(...).raw_data`) válaszából jön, és a `RemoteWorkspace` (`src/github_manager/engine.py`) lustán, repónként egyszer olvassa. Új API-hívás és új token-jogosultság nem kell (a Metadata: read elég).
- Az owner a `workspace.full_name`-ből (`OWNER/NAME`) adódik.
- A szabálytípusok listája a `RULE_TYPES` (`rules.py` vége). Az opciók típusos olvasása az `Options` (`table`, `text`, ...), az ismeretlen kulcsot a `finish()` utasítja el.
- A `parse_config` (`src/github_manager/config.py`) először a szabályokat parse-olja, utána az `owners` listát (`_owners`). A szabály maga nem ismeri az `owners` listát.
- A `fixable=False` finding a CLI-ben `[manual]` jelöléssel jelenik meg (`src/github_manager/cli.py`), a PR törzsében a „Needs manual action” részbe kerül (`_pr_body`), és `fix` módban is 1-es kilépési kódot okoz.
- Korlát, amin nem kell változtatni: a globális `exclude`, az archivált repók, a forkok (`include_forks = false`) és az üres repók egyik szabályhoz sem jutnak el (`select_repos`, illetve `_process` „empty repository” skip), így ehhez sem.

## Objective
Új `repo_visibility` szabálytípus, ami ownerenként előírja a repók láthatóságát, és minden eltérést nem javítható (`[manual]`) findingként jelez. `fix` módban se PR-t, se beállítás-módosítást nem okoz.

## Scope
### In scope
- `repo_visibility` szabálytípus a `src/github_manager/rules.py`-ban, regisztrálva a `RULE_TYPES`-ban.
- Config-validálás, beleértve, hogy a `visibility` tábla kulcsai a `owners` listában szerepeljenek.
- `github-manager.toml`: új szabály, `id = "repo-visibility"`, `visibility = { "tyutyutyu" = "public", "tyutyutyu-org" = "private" }`, `exclude = []`, rövid angol kommenttel arról, hogy csak jelez.
- Tesztek és README.

### Out of scope
- Bármilyen automatikus javítás: láthatóság átállítása (`update_repo_settings`), transfer.
- A már meglévő eltérések rendezése egyes repókon.
- A globális `exclude`, a fork-, archivált- és üresrepó-szűrés megváltoztatása.
- `internal` láthatóság támogatása elvárt értékként (csak Enterprise szervezetben létezik).
- A `repo_settings` és a `repo_ruleset` szabályok viselkedése.

## Implementation plan
1. **Szabály** (`rules.py`, a `BranchStrategy` után vagy a `RepoRuleset` után):
   - `RepoVisibility(Rule)`, `type_name = "repo_visibility"`, mezője `visibility: dict[str, str]` (owner → elvárt láthatóság).
   - `_build`: `options.table("visibility", REQUIRED)`. Üres tábla → `ValueError("'visibility' must not be empty")`. Minden érték `"public"` vagy `"private"`, különben `ValueError`, ami felsorolja a hibás ownereket (pl. `visibility values must be public or private: x`). Ha két kulcs csak kis- és nagybetűben tér el, az is `ValueError` (duplikált owner).
   - `apply`: az owner a `workspace.full_name.split("/", 1)[0]`, a táblában kis- és nagybetűtől függetlenül keresve. Ha nincs a táblában: `[]`, és a `visibility`-t ilyenkor ne olvassa. Egyébként `current = workspace.setting("visibility")`:
     - ha `current is None`: `Finding(self.id, f"setting visibility {NOT_READABLE}", fixable=False)` (a meglévő `NOT_READABLE` konstans);
     - ha `current == wanted`: `[]`;
     - különben egy `fixable=False` finding, pl. `visibility is "private", expected "public" for owner tyutyutyu (change it or transfer the repository)`, a `json.dumps` idézési mintával, ahogy a `RepoSettings` üzenetei.
   - Soha nem hív `write`, `change_setting` vagy `change_ruleset` metódust.
   - Docstring a többi szabály stílusában.
2. **Config-ellenőrzés** (`config.py`, `parse_config`): miután az `owners` megvan, minden `RepoVisibility` szabálynál, ha a `visibility` táblában olyan kulcs van, ami (kis- és nagybetűtől függetlenül) nincs az `owners`-ben, legyen `ConfigError(f"rule {id}: visibility owners not in 'owners': ...")`. Enélkül egy elgépelt owner csendben kikapcsolná az ellenőrzést. Owner, ami az `owners`-ben van, de a táblában nincs, megengedett: az ő repóit a szabály nem ellenőrzi.
3. **`github-manager.toml`**: az új szabály a `default-branch-ruleset` után, utolsóként.
4. **Tesztek** (valódi API-hívás nélkül):
   - `tests/test_rules.py`, a `make_workspace` fixture-rel (`MemoryWorkspace(settings=..., full_name=...)`):
     - egyező láthatóság → nincs finding;
     - eltérő láthatóság mindkét irányban (`tyutyutyu/x` private, `tyutyutyu-org/y` public) → egy `fixable=False` finding, a `workspace.settings` és `files` változatlan;
     - owner kis- és nagybetűs eltéréssel (`Tyutyutyu/x`);
     - a táblában nem szereplő owner → nincs finding;
     - hiányzó `visibility` → `NOT_READABLE` finding;
     - `internal` tényleges érték → eltérésként jelenik meg;
     - `_build` hibák: hiányzó vagy üres tábla, ismeretlen érték, kis- és nagybetűs duplikátum, ismeretlen kulcs a szabályban.
   - `tests/test_config.py`: a `visibility` kulcs, ami nincs az `owners`-ben, `ConfigError`. A `test_repository_config_file_is_valid` típuslistája kiegészül a `RepoVisibility`-vel (utolsó elem), és ellenőrzi a valódi `visibility` táblát.
   - `tests/test_engine.py`: a `FakeGitHub`-bal egy eltérő láthatóságú repó `fix` módban: a riport `needs fix`, a `manual_findings` tartalmazza a findingot, nincs `update_repo_settings` hívás, és nem nyílik PR. Ha más szabály PR-t nyit ugyanazon a repón, a finding a PR „Needs manual action” részében szerepel.
   - `tests/test_cli.py`, ha a meglévő minta lehetővé teszi: a finding `[manual]` jelöléssel jelenik meg, és a `fix` kilépési kódja 1.
5. **README**:
   - A „Rule types” táblázat új sora: `repo_visibility`, ellenőrzi a `visibility = { "<owner>" = "public" | "private" }` szerinti láthatóságot, javítás: *none: reported as manual*.
   - A „Not fixed automatically” felsorolás kiegészítése a láthatósággal.
   - A token-tábla nem változik (nem kell új jogosultság).
6. **Projektskill**: a `.claude/skills/github-manager-rules/SKILL.md` „Verification” részében a `test_repository_config_file_is_valid` leírása (`repo_ruleset` is last) frissüljön az új sorrendre.

## Dependencies and risks
- Kockázat: élesítés után a napi `enforce` futás (`.github/workflows/enforce.yml`, `fix`) 1-es kóddal ér véget, amíg van hatókörbe eső eltérő repó. Ez szándékos jelzés. A szabály saját `exclude` listájával egyedi kivétel adható.
- A globálisan kizárt repókat a szabály nem látja (lásd Context).

## Verification
- `uv run pytest tests/test_rules.py tests/test_config.py tests/test_engine.py -q --no-cov`: az új esetek zöldek, a valódi `github-manager.toml` betöltődik az új szabállyal.
- `uv run ruff format -q .`, majd `task verify`: minden lépés sikeres (≥80% branch coverage).
- Kézi, merge után: GitHub Actions → `enforce` → `mode = check`. Várt: minden hatókörbe eső, eltérő láthatóságú repónál egy `[manual] repo-visibility: visibility is ...` sor; az egyező repóknál nincs `repo-visibility` sor; `fix` módban sem változik láthatóság (`gh repo list <owner> --json nameWithOwner,visibility` futás előtt és után azonos).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `repo_visibility` szabály eltérő láthatóság esetén ownerenként pontosan egy `fixable=False` findingot ad, ami megnevezi a tényleges és az elvárt értéket és az ownert; egyezésnél nincs finding
- [ ] #2 A szabály `check` és `fix` módban sem ír fájlt, nem módosít beállítást vagy rulesetet, és nem nyit PR-t (a `fix` riport `needs fix` marad)
- [ ] #3 Az owner-egyeztetés kis- és nagybetűtől független; a `visibility` táblában nem szereplő owner repóira nincs finding
- [ ] #4 A válaszból hiányzó `visibility` `fixable=False` findingot ad a `NOT_READABLE` szöveggel, nem megy át csendben
- [ ] #5 Config-hiba (`ConfigError`): hiányzó vagy üres `visibility` tábla, `public`/`private`-tól eltérő érték, kis- és nagybetűs duplikált owner, illetve olyan owner-kulcs, ami nincs az `owners` listában
- [ ] #6 A `github-manager.toml` tartalmazza a `repo-visibility` szabályt (`tyutyutyu` = `public`, `tyutyutyu-org` = `private`) utolsóként, és a `test_repository_config_file_is_valid` ezt ellenőrzi
- [ ] #7 A README szabálytáblája és a „Not fixed automatically” felsorolás leírja az új szabályt; a token-tábla változatlan
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 A `uv run ruff format -q .` és a `task verify` hiba nélkül lefut (formázás, lint, ty, deptry, pytest ≥80% branch coverage, audit, build)
- [ ] #2 Az új tesztek egyike sem hív valódi GitHub API-t; éles fiókon legfeljebb a csak olvasó `github-manager repos` parancs fut
- [ ] #3 A `.claude/skills/github-manager-rules/SKILL.md` leírása a valódi config tesztjéről az új szabálysorrendhez igazodik
<!-- DOD:END -->
