---
id: doc-10
title: >-
  ADR decision-10: A repóprofilok kizáróak és névalapúak; a szabályok
  profilokhoz rendelhetők (common az alapértelmezés)
type: other
created_date: '2026-11-17T00:13:00Z'
updated_date: '2026-11-17T00:13:00Z'
---
Decision: decision-10 (accepted).

## Context
Eddig minden `[[rules]]` szabály minden kiválasztott repóra vonatkozott. Két új repófajta érkezik (`*-workspace`, `*-backlog`), amelyekre részben más szabályok kellenek: a SonarQube szabályok nem, és az owner szerinti `repo-visibility` (public) rájuk hibás lenne, mert jellemzően privátak.

## Decision
- A profilok kizáróak: minden repó pontosan egy profilba tartozik.
- A besorolás a repónév alapján történik: a felső szintű `profiles` tábla profilnév → nem üres glob-lista, a repónévre és az OWNER/NAME-re illesztve, ugyanúgy, mint az `exclude`.
- A `common` foglalt, implicit alapértelmezés: nem definiálható a `profiles` táblában, és ez a profilja minden repónak, amelyre egyik definiált profil sem illeszkedik.
- Minden szabálytípus közös `profiles` kulcsa felsorolja, mely profilokra vonatkozik; alapértelmezése `["common"]`. A szabály csak a repó profiljában fut (az `exclude` mellett), és az auto-merge döntésben is csak az ilyen `repo_ruleset` szabályok számítanak.
- Nem definiált profil a szabály `profiles` listájában config-hiba (üres lista és ismétlődő elem is).
- Ha egy repóra több profil illeszkedik, a repó `ERROR` riportot kap az ütköző profilok nevével, a futás a többi repóval folytatódik.
- A repó profilja megjelenik a konzolriportban és a step summaryben.

## Consequences
- Ha egy meglévő repó neve véletlenül `-workspace` vagy `-backlog` végű, profilt vált; ezt a riportban kiírt profil jelzi, és a repó az `exclude`-dal kizárható.
- A SonarQube szabályok és az owner szerinti `repo-visibility` csak `common` profilú; a workspace és backlog profilban a `profile-visibility` szabály mindkét ownerre privátot vár.
- Nincs profil-öröklés és szabály-felülírás profilonként; tartalomalapú besorolás (pl. `workspace.yaml`), topic és custom property sem része a döntésnek.

## Sources
- `src/github_manager/config.py` — a `profiles` tábla és a szabályok profiljainak ellenőrzése.
- `src/github_manager/engine.py` — `resolve_profile`, `_rule_applies`.
- `src/github_manager/rules/base.py` — `Rule.profiles`.
- Feladat: TASK-44.
