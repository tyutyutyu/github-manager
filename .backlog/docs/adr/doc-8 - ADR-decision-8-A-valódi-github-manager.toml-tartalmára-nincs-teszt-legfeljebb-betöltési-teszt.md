---
id: doc-8
title: >-
  ADR decision-8: A valódi github-manager.toml tartalmára nincs teszt,
  legfeljebb betöltési teszt
type: other
created_date: '2026-11-13T20:22:00Z'
updated_date: '2026-11-13T20:22:00Z'
---
Decision: decision-8 (accepted).

## Context
A `github-manager.toml` éles konfiguráció, gyakran változik. A tartalmát rögzítő tesztek minden konfigurációváltozásnál eltörnének, és nem a kód helyességét mérnék.

## Decision
A valódi `github-manager.toml` tartalmára nem készül teszt; legfeljebb az ellenőrizhető, hogy hibátlanul betöltődik. A szabályok és a konfiguráció viselkedését a tesztek saját, ideiglenes konfigurációval ellenőrzik.

## Consequences
- A konfiguráció tesztmódosítás nélkül változtatható.
- A konfiguráció szándékolt tartalmát a review ellenőrzi, nem a tesztek.

## Sources
- `tests/test_config.py` — a valódi `github-manager.toml` betöltési tesztje (`load_config`), a többi teszt `tmp_path` alatti fájlokkal.
- `src/github_manager/config.py` — `load_config`.
- Feladat: TASK-12.
