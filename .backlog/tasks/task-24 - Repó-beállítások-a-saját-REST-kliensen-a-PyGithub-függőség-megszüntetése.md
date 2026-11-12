---
id: TASK-24
title: 'Repó-beállítások a saját REST-kliensen: a PyGithub függőség megszüntetése'
status: To Do
assignee: []
created_date: '2026-11-12T12:33:00Z'
labels: []
dependencies: []
references:
  - docs/project-review-2026-11-12.md
  - src/github_manager/github.py
  - tests/test_github.py
  - pyproject.toml
  - https://docs.github.com/en/rest/repos/repos#update-a-repository
priority: medium
type: enhancement
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Context
A `GitHub` kliens (`src/github_manager/github.py`) mindent a saját, standard könyvtárra épülő transporton ér el (`_request`, `call`, `paginate`, `graphql`), két hívás kivételével, amelyek a PyGithubon mennek:
- `repo_settings`: `dict(self._client.get_repo(repo).raw_data)`;
- `update_repo_settings`: `self._client.get_repo(repo).edit(**settings)`.

Ehhez tartozik a `from github import Auth, Github, GithubException` import, a `self._client = Github(auth=Auth.Token(token), base_url=self._api_url)` példány és a `_settings_error` segéd. A PyGithubot a `86ada10` commit (2026-10-15) vezette be a `repo_settings` szabályhoz.

Gondok: a PyGithub hozza a futásidejű függőségi fa nagyobb részét (kb. 20 csomagból mintegy kétharmadot) két hívásért; a két réteg hibakezelése, időkorlátja és újrapróbálkozása eltér; minden beállítás-írás előtt felesleges plusz `GET` megy (`get_repo`).

Döntés (2026-11-12, tulajdonos): a PyGithub megszűnik, a két hívás a saját kliensre kerül.

Forrás: docs/project-review-2026-11-12.md, 5.2.

## Objective
A repó-beállítások olvasása és írása a kliens saját REST-transportján megy, és a projektnek nincs PyGithub függősége.

## Scope
### In scope
- `repo_settings` és `update_repo_settings` átírása `GET` / `PATCH /repos/{owner}/{repo}` hívásra.
- A PyGithub import, kliens és `_settings_error` törlése; a függőség eltávolítása, `uv.lock` frissítése.
- A három PyGithub-alapú teszt cseréje `FakeHttp`-alapúra.
- Kommentek és README igazítása; a döntés rögzítése ADR-ként.

### Out of scope
- Újrapróbálkozás, rate limit kezelés, időkorlát-változtatás a transportban.
- A `GitHubApi` protokoll (`engine.py`), a `RepoSettings` szabály és a `REPO_BOOL_SETTINGS` lista viselkedése.
- A `github-manager.toml` szabályainak módosítása (csak a PyGithubot említő komment igazítható).

## Implementation plan
1. A https://docs.github.com/en/rest/repos/repos#update-a-repository oldalon ellenőrizni, hogy a `REPO_BOOL_SETTINGS` (a `rules` modulban) minden neve és a `security_and_analysis` a `PATCH /repos/{owner}/{repo}` törzsparamétere. Eltérés esetén a feladat jegyzetében jelezni, a listát nem módosítani.
2. `src/github_manager/github.py`:
   - `repo_settings`: `return dict(self.call("GET", f"/repos/{repo}"))`;
   - `update_repo_settings`: `self.call("PATCH", f"/repos/{repo}", settings)` — a kapott szótár változatlanul a törzs (logikai értékek, illetve `security_and_analysis = {<feature>: {"status": ...}}`);
   - törölni: a `github` importot, a `self._client`-et, a `_settings_error`-t; a modul docstringjét és a szakaszkommenteket igazítani.
   A hibák így a transport formátumát kapják (`<METHOD> <abszolút URL>: HTTP <kód>: <üzenet>`), a `GitHubError.status` megmarad.
3. `pyproject.toml`: a `"pygithub==2.10.0"` sor törlése; `uv lock`; ellenőrzés: `uv tree --no-dev`.
4. `tests/test_github.py`: a `test_repo_settings_use_pygithub`, `test_update_repo_settings_passes_security_and_analysis` és `test_repo_settings_errors_are_wrapped` tesztek cseréje a meglévő `http`/`client` fixture-rel (`FakeHttp.queue`): a `GET` a sorba tett szótárt adja vissza; a `PATCH` kérés `("PATCH", f"{API}/repos/o/r", <settings>)` alakban rögzül; a `security_and_analysis` törzs változatlan; `403` válaszra mindkét hívás `GitHubError`-t dob `status == 403`-mal. A `FakeRepository` osztály és a `GithubException` import törlendő.
5. Szövegek: a `rules` modul két kommentje („accepted by PyGithub's `Repository.edit`", „through PyGithub"), a `README.md` bevezető felsorolásának utolsó pontja és a `repo_settings` leírása, valamint a `github-manager.toml` `repo-settings` szabálya fölötti komment.
6. ADR: `backlog decision create "<cím>" -s accepted --plain`. A decision törzse CLI-vel nem adható meg (csak cím és státusz), ezért az indoklás (Context / Decision / Consequences) Backlog dokumentumba kerül: `backlog doc create "<cím>" -p adr -t other --plain`, majd `backlog doc update <docId> --content "$content"`; a dokumentum nevezze meg a decision azonosítóját. A Backlog markdown fájlokat közvetlenül szerkeszteni tilos.

## Verification
- `uv run pytest tests/test_github.py --no-cov` — az új kliens-tesztek zöldek.
- `grep -rn -i "pygithub\|from github import" src tests README.md github-manager.toml pyproject.toml` — nincs találat.
- `uv tree --no-dev` — a futásidejű fa csak a `pyyaml` és a `rich` ágát tartalmazza.
- `uv run ruff format -q . && task verify` — minden minőségkapu zöld (a `deptry` is).
- `uv run github-manager check` a változtatás előtt és után, ugyanazon a napon (csak olvasó): a `repo_settings` és `repo_visibility` szabályok leletei megegyeznek.
- `backlog decision list --plain` és `backlog doc view <docId>` — az ADR visszaolvasható.

## Dependencies and risks
- A PyGithub beépített újrapróbálkozása megszűnik a két hívásnál; innentől ugyanúgy viselkednek, mint a kliens többi hívása (nincs újrapróbálkozás).
- Ha a `rules.py` csomaggá bontása előbb készül el, az érintett kommentek a `src/github_manager/rules/settings.py`-ban vannak.
- Az `enforce` jobot érintő Renovate-szabály (`[project].dependencies`) a rövidebb függőségi listára is érvényes, teendő nincs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A `repo_settings` egy `GET /repos/{owner}/{repo}` hívással, a kliens saját transportján olvas, és a GitHub válaszát adja vissza szótárként
- [ ] #2 Az `update_repo_settings` pontosan egy `PATCH /repos/{owner}/{repo}` hívást küld, amelynek törzse a kapott beállítás-szótár változatlanul (logikai értékek és `security_and_analysis`)
- [ ] #3 HTTP-hibánál mindkét hívás `GitHubError`-t dob, amelynek `status` mezője a HTTP-kód
- [ ] #4 A `pyproject.toml` és a `uv.lock` nem tartalmazza a PyGithubot, és a `src/` és `tests/` sehol nem importálja a `github` csomagot
- [ ] #5 A README, a forráskommentek és a `github-manager.toml` kommentje nem említi a PyGithubot
- [ ] #6 A valódi flottán futtatott `check` a változtatás előtt és után ugyanazokat a `repo_settings` és `repo_visibility` leleteket adja
- [ ] #7 A döntés ADR-ként rögzítve van a Backlogban (decision `accepted` státusszal és indokló dokumentum az `adr` útvonalon)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run ruff format -q .` és `task verify` sikeres
- [ ] #2 Nincs teszt a valódi github-manager.toml tartalmára
- [ ] #3 A diff nem tartalmaz kapcsolódó változáson kívüli módosítást, ideiglenes fájlt vagy titkot
<!-- DOD:END -->
