---
id: doc-9
title: 'ADR: GitHub App hitelesítés a PAT-ek helyett'
type: other
created_date: '2026-11-14T09:14:00Z'
updated_date: '2026-11-14T09:18:00Z'
---
# ADR: GitHub App hitelesítés a PAT-ek helyett

Decision: decision-9 (státusz: accepted). Feladat: TASK-38. Követő feladatok: TASK-40, TASK-41, TASK-42, TASK-43.

## Állapot és bizonyítottság

A kísérleti GitHub App és a homokozó repó elérése (App azonosító, telepítés azonosítója, privát kulcs, `GITHUB_MANAGER_SANDBOX_REPO`) a spike futásakor nem állt rendelkezésre: a környezetben egyik változó sem volt beállítva, az App létrehozása pedig a tulajdonos kézi lépése. Ezért **egyetlen feltevést sem próbáltunk ki**, és nem írtunk semmilyen repóba. Minden állítás a GitHub dokumentációján alapul; a dokumentált tényt és a bizonyítatlan következtetést külön jelöljük.

A döntés ennek ellenére `accepted`, mert a dokumentált tények az átállás irányát támasztják alá, a kísérletileg nem igazolt pontok pedig **a megvalósítás előfeltételei**: a TASK-40 igazolja az a–g feltevéseket a homokozón, és a TASK-41, TASK-42 és TASK-43 csak utána indulhat (függőséglánc: TASK-40 → TASK-41 → TASK-42 → TASK-43). Ha a TASK-40-ben egy feltevés megdől, ez az ADR és a decision-9 frissítendő vagy visszavonandó.

## Context

Az `enforce` workflow ownerenként egy hosszú életű finomhangolt PAT-tel fut (`GH_MANAGER_TOKEN` a `tyutyutyu`, `GH_MANAGER_ORG_TOKEN` a `tyutyutyu-org` ownerhez). Kézzel kell megújítani őket, lejáratkor a futás leáll, és a publikus repó titkai közt vannak. A GitHub App telepítési tokent ad, amely 1 órán át érvényes (https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation); az `enforce` job időkorlátja 30 perc, tehát egy token egy jobhoz elég.

Az átállás nem csak workflow-kérdés: a `GitHub.list_repos` (`src/github_manager/github.py`) a `GET /user` hívással állapítja meg a felhasználót, majd `GET /user/repos`-t vagy `GET /orgs/{owner}/repos`-t hív, amelyek a felhasználói végpontok miatt telepítési tokennel nem használhatók.

## A feltevések (a–g)

Mindegyik **nem kipróbálva**; a kísérletet a TASK-40 végzi (`GITHUB_MANAGER_SANDBOX_REPO=<owner>/<name> GH_TOKEN=<telepítési token> task dev:test-integration` és célzott hívások a kliens meglévő metódusaival).

- **a. App-tokennel nyitott PR elindítja a `pull_request` workflow-kat.**
  - Dokumentált: a `GITHUB_TOKEN`-nel kiváltott események (a `workflow_dispatch` és `repository_dispatch` kivételével) nem indítanak új workflow-futást, és a dokumentáció a továbbiakban GitHub App telepítési tokent vagy PAT-et ajánl (https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication).
  - Bizonyítatlan következtetés: ebből következik, hogy a telepítési tokennel nyitott PR a kötelező `verify` checket elindítja. Nem kipróbálva.
- **b. A `createCommitOnBranch` App-tokennel aláírt („Verified") commitot ad.**
  - Dokumentált: a botok és GitHub Appok által készített, ellenőrizhető aláírású commitot a GitHub Verified-nek jelöli (https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification#signature-verification-for-bots); a mutáció leírása: https://docs.github.com/en/graphql/reference/mutations#createcommitonbranch.
  - Bizonyítatlan következtetés: a decision-4 PAT-es működése (a GitHub írja alá a GraphQL-lel készült commitot) telepítési tokennel is érvényes. Nem kipróbálva.
- **c. Az `enablePullRequestAutoMerge` és a squash merge App-tokennel működik.**
  - Dokumentált: a mutáció (https://docs.github.com/en/graphql/reference/mutations#enablepullrequestautomerge) és a merge végpont (https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request) a `Pull requests: write` (merge-nél a `Contents: write` is) jogosultságot kéri; a teljes lista: https://docs.github.com/en/rest/overview/permissions-required-for-github-apps.
  - Bizonyítatlan következtetés: a két hívás App-tokennel is lefut a kezelt ruleset mellett. Nem kipróbálva.
- **d. A `PATCH /repos/{repo}` (benne a `security_and_analysis`) és a ruleset-végpontok `Administration: write` jogosultsággal működnek.**
  - Dokumentált: a repó módosítása (https://docs.github.com/en/rest/repos/repos#update-a-repository) és a ruleset-végpontok (https://docs.github.com/en/rest/repos/rules) az `Administration` repó-jogosultságot kérik.
  - Bizonyítatlan, kockázat: a `security_and_analysis` egyes elemei (például secret scanning, push protection) további jogosultságot vagy tulajdonosi beállítást igényelhetnek; ezt a TASK-40 egyenként ellenőrzi. Nem kipróbálva.
- **e. A `.github/workflows/` alatti fájl módosítása `Workflows: write` jogosultsággal működik.**
  - Dokumentált: a `Workflows` jogosultság a workflow-fájlok módosítását engedi (https://docs.github.com/en/rest/overview/permissions-required-for-github-apps és https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
  - Bizonyítatlan következtetés: a `createCommitOnBranch` hívás workflow-fájlra is lefut App-tokennel. Nem kipróbálva.
- **f. A repók listázása telepítési tokennel visszaadja a privát és az archivált repókat, a `Repo` mezőivel.**
  - Dokumentált: a `GET /installation/repositories` a telepítéshez rendelt repókat adja vissza repository objektumként (`name`, `full_name`, `default_branch`, `archived`, `fork`) (https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation); a felhasználói végpontok (`GET /user`, `GET /user/repos`) telepítési tokennel nem használhatók.
  - Bizonyítatlan: hogy a privát és az archivált repók is szerepelnek-e a válaszban. Nem kipróbálva.
- **g. A kezelt ruleset (nincs bypass actor, PR kötelező, 0 jóváhagyás) mellett az App által nyitott PR merge-elhető.**
  - Dokumentált: a ruleset szabályai mindenkire vonatkoznak, akit a bypass lista nem vesz ki (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).
  - Bizonyítatlan következtetés: mivel a PAT-es működés is bypass nélküli PR-t használ és nulla jóváhagyást kér, az App-os PR ugyanúgy merge-elhető. Nem kipróbálva.

Owner-típus: a homokozó típusa nem ismert, ezért a felhasználóra és a szervezetre vonatkozó minden állítás dokumentációs.

## Options

1. Maradás a PAT-eknél.
2. Egy publikus App két telepítéssel (`tyutyutyu` felhasználó, `tyutyutyu-org` szervezet).
3. Ownerenként külön privát App. Egy privát App csak a saját tulajdonosára telepíthető (https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/making-a-github-app-public-or-private), tehát két App, két kulcs és két secret kellene.

## Decision

Átállás **egy publikus App két telepítéssel** (2. opció). Indok: egy kulcs és egy secret kell a két PAT secret helyett, és a hosszú életű, kézzel megújított titok megszűnik; az App azonosítója nem titok, a privát kulcs nem hagyja el a secretet. A publikus App kockázata, hogy mások is telepíthetik, de ehhez nem kapnak hozzáférést a kulcshoz. Nem választott opció: a PAT-eknél maradás (a kézi megújítás és a lejárati leállás marad), és a két App (kétszeres kulcskezelés).

### Jogosultságok

Contents, Pull requests, Administration és Workflows: read/write; Metadata: read. Telepítés minden repóra ownerenként; a workflow-ban a `permission-*` bemenetekkel szűkíthető.

### Token kiállítása a workflow-ban

- Action: `actions/create-github-app-token`, v3.3.0, commit SHA `64ab729a6294000f5aa4a4bc0b73d1f32bc45510` (a többi action-höz hasonlóan SHA-ra pinelve, verziókommenttel: `# v3.3.0`).
- Bemenetek (az action.yml szerint): `client-id` (az `app-id` elavult), `private-key` (kötelező), `owner`; a `repositories` elmarad, így a token a telepítés összes repójára szól. A kimenet a `token`; az action a job végén visszavonja.
- Konfiguráció: `GH_MANAGER_APP_CLIENT_ID` repó-változó (nem titok) és `GH_MANAGER_APP_PRIVATE_KEY` secret.
- Mátrix: a `matrix.secret` kulcs megszűnik; az `include` csak `owner` elemeket tartalmaz (`tyutyutyu`, `tyutyutyu-org`), és minden job egy ilyen lépéssel indul:

```yaml
- id: app-token
  uses: actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0
  with:
    client-id: ${{ vars.GH_MANAGER_APP_CLIENT_ID }}
    private-key: ${{ secrets.GH_MANAGER_APP_PRIVATE_KEY }}
    owner: ${{ matrix.owner }}
```

Az "Apply rules" lépésben a `GH_TOKEN: ${{ steps.app-token.outputs.token }}` váltja a `${{ secrets[matrix.secret] }}` értéket.

### Repólistázás

A `GitHub.list_repos` telepítési tokennél a lapozott `GET /installation/repositories` végpontot használja, `GET /user` nélkül; személyes tokennel és `gh` CLI-vel marad a mostani ág. A megvalósítás a TASK-41.

### Helyi futtatás

Marad a `resolve_token` (`GH_TOKEN` / `GITHUB_TOKEN` / `gh` CLI); a telepítési token `GH_TOKEN`-ként adható.

### A PR-ok szerzője

Az új compliance PR-ok szerzője a bot (`<app>[bot]`) lesz, az értesítések a bot nevén jönnek. A már nyitott PR-ok szerzője nem változik: az `engine._sync_pull_request` a meglévő nyitott PR-t megtartja, csak a címét és a törzsét frissíti (`update_pr`), és ha az ág eltér, újraépíti; az újraépített commit az App nevén készül, de a PR szerzője a korábbi marad. Új PR-t (`create_pr`) csak akkor nyit, ha nincs nyitott PR. A régi PR-ok lezárására nincs szükség; ha mégis kellene, az külön feladat.

### Kivezetés és visszaállás

- Kivezetés: az App-os futás igazolt sikere után a két PAT secret törlése (TASK-43); a tokenek visszavonása a tulajdonos kézi lépése.
- Visszaállás: a PAT secretek a kivezetésig megmaradnak, a workflow a TASK-42 előtti állapotra (git revert) visszaállítható. A kivezetés után új PAT kiállítása a visszaút.

## Consequences

- Nincs kézi tokenmegújítás és nincs lejárati leállás; a titok (a privát kulcs) csak egy secret, a tokenek 1 órán belül lejárnak.
- A PR-ok szerzője bot; ha a bot nem tudja elindítani a `verify` checket (a feltevés cáfolata), az átállás nem folytatható.
- A kulcs kiszivárgása az App összes telepítésére hatna; a kulcs a repón kívül, secretben tárolandó.
- Kód, workflow és README módosul (TASK-41, TASK-42), a kivezetés külön lépés (TASK-43).
- Az a–g feltevések igazolása a megvalósítás előfeltétele (TASK-40).

## Takarítás

A spike nem hozott létre ágat, PR-t, rulesetet vagy kísérleti kódot; a `src/`, `.github/` és a README nem változott, a homokozóba nem írtunk. A kísérleti App sorsáról (megtartás vagy törlés) a tulajdonos dönt; a TASK-40 kezdetén rögzítendő.
