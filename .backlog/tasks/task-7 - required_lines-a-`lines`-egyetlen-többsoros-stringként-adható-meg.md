---
id: TASK-7
title: 'required_lines: a `lines` egyetlen többsoros stringként adható meg'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 00:31'
updated_date: '2026-10-18 00:33'
labels: []
dependencies: []
documentation:
  - README.md
priority: medium
type: enhancement
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `required_lines` szabály (`RequiredLines` a `src/github_manager/rules.py`-ban) a managed blokkot egyben írja a fájlba, a configban viszont a `lines` ma egy stringlista (`lines = [".DS_Store", ".idea/", ...]`). Egy blokkot egyszerűbb egyben, többsoros TOML literal stringként (`'''...'''`) megadni, úgy, ahogy a fájlban is megjelenik. Ráadásul így üres sorral csoportosítani is lehet.

A felhasználó döntései (2026-10-18):
- Literal stringet (`'''`) használunk, így a gitignore backslash-ei (pl. `\#file`) szó szerint maradnak.
- Belső üres sor megengedett; az elején és a végén lévő üres sorokat levágjuk. A sorvégi szóközt is levágjuk.
- A sor eleji behúzás (szóköz vagy tab) config-hiba.
- Nincs más config, ezért a listás formát nem kell megtartani: a `lines` csak string lehet. A `remove_lines` lista marad.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `lines` egy nem üres string; a sorai sorrendben kerülnek a managed blokkba
- [x] #2 Az elején és a végén lévő üres sorok, valamint a sorvégi szóközök nem kerülnek a blokkba; a belső üres sorok megmaradnak
- [x] #3 Behúzott (szóközzel vagy tabbal kezdődő) sor esetén a config betöltése hibát ad, ami megnevezi a `lines` kulcsot és a sort
- [x] #4 Lista, illetve csak üres vagy whitespace sorokból álló `lines` esetén a config betöltése hibát ad
- [x] #5 A `github-manager.toml` gitignore-baseline szabálya `'''` többsoros stringet használ, és ugyanazt a blokkot adja, mint korábban
- [x] #6 A README `required_lines` sora leírja a string formát; a tesztek lefedik a belső üres sort, a backslash-t, a levágást és a hibás eseteket
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Options.text_block: string kötelező, splitlines + rstrip, külső üres sorok levágása, behúzás és üres tartalom hiba (sorszámmal).
2. RequiredLines._build a text_block-ot használja a lines-ra; remove_lines lista marad.
3. github-manager.toml gitignore-baseline: lines ''' blokk.
4. Tesztek (test_rules, test_engine, test_config, test_cli) átállítása stringre + új esetek.
5. README required_lines sor, projekt skill frissítése.
6. uv run ruff format -q . és task verify.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Options.text_block (rules.py) parse-olja a lines-t; RequiredLines._build ezt használja. A remove_lines lista maradt. A projekt skill (.claude/skills/github-manager-rules/SKILL.md) required_lines szerződése frissítve; ez a fájl gitignore-olt (.gitignore:271 .claude/), nem kerül a PR-ba.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A required_lines szabály `lines` opciója mostantól egyetlen többsoros string (a toml-ban `'''` literal), lista helyett. Az `Options.text_block` soronként bont, levágja a sorvégi szóközöket és a külső üres sorokat, a belső üres sorokat megtartja; behúzott sor, lista vagy üres tartalom config-hiba (a hiba a kulcsot és a sor számát is megadja). A github-manager.toml gitignore-baseline szabálya átállt az új formára, ugyanazzal a blokkal (test_repository_config_file_is_valid ellenőrzi). README és tesztek frissítve: új teszt a belső üres sorra, a backslash-re és a levágásra, plusz a hibás esetekre. Ellenőrzés: `task verify` exit 0, 249 teszt, 99% coverage. Kockázat: a lista forma megszűnt; a felhasználó szerint más config nem használja.
<!-- SECTION:FINAL_SUMMARY:END -->
