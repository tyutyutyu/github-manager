---
id: TASK-38
title: >-
  Spike: GitHub App hitelesítés a PAT-ek helyett – megvalósíthatóság a homokozó
  repón és döntés (ADR)
status: To Do
assignee: []
created_date: '2026-11-12T23:54:00Z'
labels: []
dependencies:
  - TASK-28
references:
  - docs/project-review-2026-11-12.md
  - .github/workflows/enforce.yml
  - src/github_manager/github.py
  - README.md
  - >-
    https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
  - >-
    https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation
  - https://github.com/actions/create-github-app-token
priority: low
type: spike
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
Az `enforce` workflow (`.github/workflows/enforce.yml`) ownerenként egy finomhangolt személyes tokennel fut (`GH_MANAGER_TOKEN` a `tyutyutyu`, `GH_MANAGER_ORG_TOKEN` a `tyutyutyu-org` ownerhez). Mindkettő az owner összes repójára szól: Contents, Pull requests, Administration és Workflows írás, Metadata olvasás (README, „Tokens"). A tokenek hosszú életűek, kézzel kell megújítani őket, lejáratkor a futás leáll, és ennek a publikus repónak a titkai között vannak.

A GitHub App rövid életű telepítési tokent ad, kézi megújítás nélkül. Az átállás nem csak workflow-kérdés. Kódolvasás alapján ismert akadályok:
- A `GitHub.list_repos` (`src/github_manager/github.py`) a `GET /user` hívással állapítja meg a bejelentkezett felhasználót, majd `GET /user/repos?affiliation=owner`-t vagy `GET /orgs/{owner}/repos?type=all`-t hív. A felhasználói végpontok telepítési tokennel nem használhatók; a megfelelő végpont várhatóan a `GET /installation/repositories`.
- Két owner van (egy felhasználó és egy szervezet). Egy privát App csak a saját tulajdonosára telepíthető, tehát vagy egy publikus App kell két telepítéssel, vagy ownerenként külön App.
- A `resolve_token` (`GH_TOKEN` / `GITHUB_TOKEN` / `gh` CLI) helyi futtatásnál megmarad; a workflow-ban a tokent egy lépésnek kell kiállítania (pl. `actions/create-github-app-token`, SHA-ra pinelve, ahogy a többi action).

Ellenőrizendő feltevések (egyiket sem próbáltuk ki):
- a. App-tokennel nyitott PR elindítja a `pull_request` workflow-kat (a kötelező `verify` check miatt elengedhetetlen).
- b. A `createCommitOnBranch` App-tokennel aláírt („Verified") commitot ad.
- c. Az `enablePullRequestAutoMerge` és a squash merge App-tokennel működik.
- d. A `PATCH /repos/{repo}` (benne a `security_and_analysis`) és a ruleset-végpontok `Administration: write` App-jogosultsággal működnek.
- e. A `.github/workflows/` alatti fájl módosítása `Workflows: write` jogosultsággal működik.
- f. A repók listázása telepítési tokennel visszaadja a privát és az archivált repókat is, a `Repo` mezőihez szükséges adatokkal (`name`, `full_name`, `default_branch`, `archived`, `fork`).
- g. A kezelt ruleset (nincs bypass actor, PR kötelező, 0 jóváhagyás) mellett az App által nyitott PR ugyanúgy merge-elhető.

A kísérletekhez írni kell egy repóba; erre kizárólag a homokozó repó használható (`GITHUB_MANAGER_SANDBOX_REPO`; integrációs teszt: `tests/test_integration_github.py`, futtatás: `task dev:test-integration`).

Forrás: docs/project-review-2026-11-12.md, 2.5 és 6.5.

## Objective
Bizonyítékokon alapuló, ADR-ben rögzített döntés arról, hogy a program átáll-e GitHub App hitelesítésre és milyen felépítésben, valamint — átállás esetén — a megvalósítási feladatok a Backlogban.

## Scope
### In scope
- Kísérletek a homokozó repón App telepítési tokennel; a fenti feltevések igazolása vagy cáfolata.
- ADR (decision és indokló dokumentum).
- A követő megvalósítási feladatok felvétele, ha a döntés az átállás.

### Out of scope
- Bármilyen változtatás a `main` ágon a `src/`, a `.github/workflows/` és a README alatt (a megvalósítás a követő feladatoké).
- Írás a homokozón kívüli bármely repóba; a kísérleti App telepítése a homokozón kívüli repóra.
- A meglévő tokenek visszavonása vagy módosítása.
- Más hitelesítési módok vizsgálata.

## Implementation plan
1. **Tulajdonosi előfeltétel (kézi lépés; az ágens nem tudja elvégezni):** kísérleti GitHub App létrehozása a homokozó repó tulajdonosa alatt. Jogosultságok: Contents, Pull requests, Administration, Workflows — read/write; Metadata — read. Telepítés „Only select repositories" módon, kizárólag a homokozó repóra. Az App azonosítója és privát kulcsa a repón kívül áll rendelkezésre (helyi környezeti változó vagy fájl). Amíg ez nincs meg, a feladat nem kezdhető el.
2. Telepítési token kiállítása helyben: az App privát kulcsával aláírt JWT → `POST /app/installations/{installation_id}/access_tokens`. A token `GH_TOKEN`-ként adható a programnak. A kulcs és a token nem kerülhet a repóba, a logba, a feladat jegyzetébe vagy az ADR-be.
3. A feltevések ellenőrzése a homokozón; mindegyikhez rögzíteni kell a futtatott parancsot és a megfigyelt eredményt:
   - `GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> GH_TOKEN=<telepítési token> task dev:test-integration` — a PR életciklusa App-tokennel (a, b); az aláírás a `GET /repos/{repo}/commits/{sha}` válaszának `commit.verification.verified` mezőjéből olvasható; a workflow-indulást `gh run list --repo <homokozó>` mutatja, ha a homokozóban van `pull_request` workflow;
   - `GET /user`, `GET /user/repos` és `GET /installation/repositories` telepítési tokennel (f);
   - a c, d, e és g ponthoz célzott hívások a kliens meglévő metódusaival (`enable_auto_merge`, `merge_pr`, `repo_settings` / `update_repo_settings`, `create_ruleset` / `update_ruleset` / `get_ruleset`, workflow-fájl commitolása), mind a homokozón; a végén a homokozó visszaállítása (kísérleti ruleset törlése, beállítások vissza);
   - ha a homokozó csak az egyik owner-típus alatt van, a másik típusra (felhasználó, illetve szervezet) vonatkozó állításokat a dokumentációból kell alátámasztani, és az ADR-ben „nem kipróbálva" jelöléssel szerepeltetni.
4. A tervezési kérdések megválaszolása: egy publikus App két telepítéssel, vagy ownerenként külön App; a jogosultságok listája; a token kiállítása a workflow-ban (az action neve, pinelt SHA-ja, bemenetei, az ownerenkénti mátrix); a `list_repos` szükséges módosítása; a helyi futtatás módja; a PR-ok szerzőjének megváltozása (bot) és hatása (értesítések, a már nyitott compliance PR-ok átmenete); a tokenek kivezetése és a visszaállás módja.
5. ADR a Backlogban: `backlog decision create "<cím>" -s accepted --plain` (előtte `backlog decision create --help`; elutasító döntésnél a megfelelő státusszal). Az indoklás (Context / Options / Decision / Consequences, benne a 3. lépés bizonyítékai) Backlog dokumentumba kerül: `backlog doc create "<cím>" -p adr -t other --plain`, majd `backlog doc update <docId> --content "$content"`; a dokumentum nevezze meg a decision azonosítóját. Backlog markdown fájl közvetlenül nem szerkeszthető.
6. Ha a döntés az átállás: a megvalósítási feladatok felvétele a `backlog instructions task-creation` szerint (legalább: telepítési token támogatása a kliensben; az `enforce` workflow átállítása és a README „Tokens" szakaszának átírása; a tokenek kivezetése), függőségekkel, erre a feladatra hivatkozva.
7. Takarítás: a kísérleti ágak, PR-ok, rulesetek és a kísérleti kód eltávolítása. A kísérleti App sorsáról (megtartás vagy törlés) a tulajdonos dönt; az ADR rögzíti.

## Verification
- `backlog decision list --plain` és `backlog doc view <docId>` — az ADR visszaolvasható, és mind a hét feltevéshez (a–g) tartalmaz eredményt bizonyítékkal vagy „nem kipróbálva" jelöléssel.
- `backlog task list --plain` — a követő feladatok léteznek (vagy az ADR döntése: nem állunk át).
- `git diff --stat main -- src .github README.md` — üres.
- `gh pr list --repo <homokozó> --state open` — nincs a spike-ból maradt nyitott PR.

## Dependencies and risks
- Előfeltétel a homokozó repón futó integrációs teszt (és maga a homokozó repó).
- Előfeltétel a tulajdonos kézi lépése (1. lépés).
- Kockázat: a privát kulcs kiszivárgása. A kulcs csak a repón kívül tárolható, a kísérleti App pedig csak a homokozóra van telepítve.
- Kockázat: a homokozó csak az egyik owner-típust fedi; a másikra a bizonyíték gyengébb, ezt az ADR jelöli.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A Backlogban ADR rögzíti a döntést (átállás vagy maradás; egy publikus App vagy ownerenként külön App) indoklással és következményekkel
- [ ] #2 Az ADR mind a hét feltevéshez (a–g) megadja a megfigyelt eredményt a futtatott paranccsal, vagy „nem kipróbálva" jelölést dokumentációs hivatkozással
- [ ] #3 Az ADR megválaszolja a tervezési kérdéseket: jogosultságok, token-kiállítás a workflow-ban, a repólistázás módosítása, helyi futtatás, a tokenek kivezetése és a visszaállás
- [ ] #4 Átállási döntés esetén a megvalósítási feladatok fel vannak véve a Backlogba, függőségekkel
- [ ] #5 A spike csak a homokozó repóba írt; a `main` ágon a `src/`, a `.github/` és a README nem változott; a homokozóban nem maradt nyitott PR, kísérleti ág vagy kísérleti ruleset
- [ ] #6 Az App privát kulcsa és a kiállított tokenek sem a repóba, sem a feladat jegyzetébe, sem az ADR-be nem kerültek
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 A decision, a dokumentum és a követő feladatok a `backlog` CLI-vel készültek, és visszaolvashatók
- [ ] #2 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
