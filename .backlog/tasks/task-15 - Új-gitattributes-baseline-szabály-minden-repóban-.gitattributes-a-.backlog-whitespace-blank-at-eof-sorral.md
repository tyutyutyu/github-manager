---
id: TASK-15
title: >-
  Új gitattributes-baseline szabály: minden repóban .gitattributes a .backlog/**
  whitespace=-blank-at-eof sorral
status: Done
assignee: []
created_date: '2026-11-05T22:54:00Z'
updated_date: '2026-11-05T23:11:00Z'
labels: []
dependencies: []
references:
  - src/github_manager/rules.py
  - tests/test_rules.py
modified_files:
  - github-manager.toml
priority: medium
type: feature
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Minden kezelt repóban legyen `.gitattributes` fájl ezzel a sorral:

```
.backlog/** whitespace=-blank-at-eof
```

(A Backlog.md által írt `.backlog/` fájloknál a git ne jelezze hibának a fájlvégi üres sort.)

Új kód nem kell: a meglévő `required_lines` szabálytípus (`RequiredLines` a `src/github_manager/rules.py`-ban) pontosan ezt tudja:
- hiányzó fájlt létrehoz, amely csak a managed blokkot tartalmazza (`test_required_lines_creates_missing_file` a `tests/test_rules.py`-ban);
- létező fájl végére egy üres sor után hozzáfűzi a blokkot, a fájl többi tartalmát (repóspecifikus attribútumok) érintetlenül hagyja;
- a blokkot `# >>> github-manager: <id>` és `# <<< github-manager: <id>` jelöli; a `#` a `.gitattributes`-ban érvényes komment, így az alapértelmezett `comment = "#"` megfelel.

Döntés: `required_lines`, nem `file_sync`. A `file_sync` a teljes fájlt felülírná, és törölné a repók saját `.gitattributes` sorait. Ezért a fájl tartalma a blokkjelölőkkel együtt három sor lesz (lásd Acceptance criteria).

Minta: a `gitignore-baseline` szabály a `github-manager.toml`-ban (`type = "required_lines"`, `path`, `lines = '''…'''`, `exclude = []`, magyarázó kommenttel).

## Objective
A `github-manager.toml`-ban egy új `required_lines` szabály biztosítja, hogy minden hatókörbe eső repó `.gitattributes` fájljában benne legyen a `.backlog/** whitespace=-blank-at-eof` sor egy managed blokkban; `fix` a compliance PR-ban hozza létre vagy frissíti.

## Scope
### In scope
- Új `[[rules]]` blokk a `github-manager.toml`-ban, a `gitignore-baseline` szabály után:
  - `id = "gitattributes-baseline"`
  - `type = "required_lines"`
  - `path = ".gitattributes"`
  - `lines = '''` + új sor + `.backlog/** whitespace=-blank-at-eof` + új sor + `'''`
  - `exclude = []`
  - rövid angol komment a blokk fölött (managed blokk, a fájl többi része érintetlen marad).

### Out of scope
- Bármilyen változás a `src/` alatt vagy új szabálytípus.
- A github-manager repó saját `.gitattributes` fájljának kézi létrehozása (a szabály a `fix` futáskor PR-ban hozza létre, mint minden más repóban).
- Írás bármelyik kezelt repóba (a kezelt repókba csak a meglévő `fix`/ütemezett `enforce.yml` futás ír).
- Teszt a valódi `github-manager.toml` tartalmára (a projekt szabálya: legfeljebb a betölthetőségét ellenőrző meglévő teszt marad, `tests/test_config.py`).
- README változás: a README a szabálytípusokat írja le, nem a konfigurált szabályokat; a `required_lines` sora már leírja ezt a viselkedést.

## Implementation plan
1. `github-manager.toml`: a `gitignore-baseline` `[[rules]]` blokk után illeszd be az új blokkot a Scope szerint. A `lines` értéke `'''` literál string legyen (ugyanúgy, mint a `gitignore-baseline`-nál), a sor behúzás nélkül, mert a `Options.text_block` a behúzott sort config-hibának veszi.
2. `uv run github-manager repos` — a config betölthető (csak olvasó parancs).
3. `uv run ruff format -q . && task verify` — a teljes ellenőrzés zöld (a `tests/test_config.py` betöltési tesztje lefut a valódi configon).
4. Opcionális, csak olvasó ellenőrzés (tokent igényel): `uv run github-manager check -r tyutyutyu/github-manager --diff` — a kimenetben `fix  gitattributes-baseline  .gitattributes: managed block is missing` és a diffben a három soros új fájl látszik. Ne futtasd a `fix`-et.

## Dependencies and risks
- Nincs előfeltétel.
- Hatás: a következő `fix` futás minden hatókörbe eső repó compliance PR-jába bekerül a `.gitattributes` változás (a `.backlog/` nélküli repókba is; ez szándékos, a sor ott hatástalan).
- A `whitespace=-blank-at-eof` csak a `blank-at-eof` whitespace-hibát kapcsolja ki a `.backlog/**` alatti fájlokra; a többi `core.whitespace` ellenőrzés változatlan.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A github-manager.toml-ban van egy gitattributes-baseline szabály: type = "required_lines", path = ".gitattributes", lines egyetlen sora ".backlog/** whitespace=-blank-at-eof", exclude = []
- [x] #2 Egy .gitattributes nélküli repón a check "fix  gitattributes-baseline  .gitattributes: managed block is missing" findingot ad, és a tervezett fájl pontosan ez a három sor: "# >>> github-manager: gitattributes-baseline", ".backlog/** whitespace=-blank-at-eof", "# <<< github-manager: gitattributes-baseline"
- [x] #3 Meglévő .gitattributes esetén a fájl korábbi sorai megmaradnak, a blokk egy üres sor után a végére kerül
- [x] #4 uv run github-manager repos hiba nélkül betölti a configot
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 uv run ruff format -q . és task verify sikeres
- [x] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [x] #3 A diff csak a github-manager.toml-t érinti, és nem tartalmaz kapcsolódó változáson kívüli módosítást
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Easy GitHub started implementation on feature/TASK-15-uj-gitattributes-baseline-szabaly-minden-repoban.

Validation: `uv run github-manager repos` exit 0; read-only `check -r tyutyutyu/github-manager --diff` reports `fix gitattributes-baseline .gitattributes: managed block is missing` and plans the exact 3-line file (marker, `.backlog/** whitespace=-blank-at-eof`, marker); applying the loaded rule to an in-memory existing .gitattributes kept prior lines and appended the block after one blank line; `ruff format --check .` and `task verify` green. The Backlog task file change is workflow lifecycle bookkeeping, not implementation.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the `gitattributes-baseline` `required_lines` rule to github-manager.toml (after `gitignore-baseline`): path `.gitattributes`, single line `.backlog/** whitespace=-blank-at-eof`, `exclude = []`, with an English comment. `required_lines` was chosen over `file_sync` so repository-specific attributes are preserved. No src/ or test changes.

Verification: `github-manager repos` loads the config; live read-only `check --diff` on tyutyutyu/github-manager shows the missing-block finding and the exact 3-line planned file; in-memory apply on an existing file preserves prior lines and appends the block after a blank line; `ruff format --check` and `task verify` (lint, ty, deptry, tests, audit, build) pass.

Impact: the next `fix` run adds `.gitattributes` to every in-scope repo's compliance PR, including repos without `.backlog/` (intended, harmless).
<!-- SECTION:FINAL_SUMMARY:END -->
