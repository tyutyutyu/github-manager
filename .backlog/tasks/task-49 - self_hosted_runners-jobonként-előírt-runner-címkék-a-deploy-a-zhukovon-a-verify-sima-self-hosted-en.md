---
id: TASK-49
title: >-
  self_hosted_runners: jobonként előírt runner címkék (a deploy a zhukovon, a
  verify sima self-hosted-en)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-27T00:20:33Z'
updated_date: '2026-11-27T00:22:56Z'
labels: []
dependencies: []
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A tyutyutyu-org repókban a verify és minden más job bármelyik org szintű self-hosted runneren futhat (`[self-hosted]`), a deploy job viszont csak a zhukov runneren (`[self-hosted, zhukov]`), mert ott építi és indítja a docker compose stacket. Eddig a szabály csak repószintű `allowed_runs_on` halmazokat ismert, így vagy a zhukov címkét írta ki a deploy jobból, vagy bármelyik job futhatott volna a zhukovon.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Az új, opcionális `job_runs_on` tábla job-azonosítóhoz (pontos egyezés, a kis- és nagybetű számít) egy címkekészletet rendel; az ilyen jobnak pontosan ezt kell használnia (halmazként, kis- és nagybetű nélkül)
- [ ] #2 A `job_runs_on`-ban nem szereplő jobok változatlanul az `allowed_runs_on` halmazok egyikét használhatják, a csere értéke a `runs_on`
- [ ] #3 Egy `job_runs_on`-beli job ubuntu-* vagy más self-hosted címkekészletét a fix a job saját készletére írja át; a többi esetet (expression, mátrix stb.) manuálisként jelzi, mint eddig
- [ ] #4 Érvénytelen `job_runs_on` (nem tábla, üres kulcs, üres vagy nem szöveges lista, `self-hosted` nélküli készlet) konfigurációs hiba
- [ ] #5 Unit tesztek a tests/test_rules_workflows.py-ban és engine teszt a tests/test_engine.py-ban; a README szabályleírása dokumentálja az opciót
- [ ] #6 A github-manager.toml private-self-hosted-runners szabálya: `allowed_runs_on = [["self-hosted"]]`, `job_runs_on = { deploy = ["self-hosted", "zhukov"] }`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. SelfHostedRunners: új job_runs_on mező (job id -> címkekészlet), validálás a _build-ben.
2. Jobonkénti cél (_Target: engedett halmazok + csere érték); _job_problem, _rewritable, _replacement, _verified ezt kapja.
3. Unit és engine tesztek, README, github-manager.toml.
4. uv run ruff format -q . && task verify
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Megvalósítva: job_runs_on mező és validálás, jobonkénti _Target; unit, config és engine tesztek; README; github-manager.toml. task verify zöld (776 passed, 99% coverage). A zhukov-deployment skill (~/.claude/skills) deploy.yml példája és leírása is frissítve.
<!-- SECTION:NOTES:END -->
