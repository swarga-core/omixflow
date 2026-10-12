---
id: omixflow-agent-resume-by-id
title: После перезапуска сессии имена её прежних субагентов не резолвятся — продолжать по agentId
status: draft
type: bug
created: 2026-10-12
updated: 2026-10-12
origin: Swarga AI Studio T-7 (G-54 лида swais-lead) и mewria MEW-25 (G-57 лида mewria-lead), 2026-10-12, сессии подняты sessions.py respawn после сбоя сети; сверено по транскриптам обеих сессий
target: omixflow
external:
links: [omixflow-agent-failed-resume, omixflow-rotation-context-teammates]
---

**Контекст.** `runtime.md`, «Спавн агентов»: каждый спавн architect, coder, tester и
reviewer обязан иметь `name`, дальше общение — SendMessage по имени; имя живого агента
хранится в `state.yaml` (`agents.*`). `review-cycle.md`, «Continuation» — так же. С 0.7.0
лид поднимает остановленную фоновую сессию `sessions.py respawn` (разговор сохраняется).
`scripts/agent_ctx.py` находит транскрипт агента по `name` в `subagents/*.meta.json`; имя
файла несёт agentId (`agent-a0404b9ba02c66b78.meta.json` → `a0404b9ba02c66b78`).

**Проблема.** T-7 остановилась от сбоя API, лид поднял её `respawn` (сессия и id те же).
В 07:28 оркестратор послал `reviewer-T-7` по имени: «No agent named 'reviewer-T-7' is
reachable». Через три секунды тот же агент продолжился по agentId (`aa1c990a52da5a28a`,
«Resuming agent aa1c990»), дальше оркестратор продолжал прежних агентов только по id
(log.md T-7, Spec: «имена агентов после перезапуска не резолвятся — агенты продолжены по
id»). Агенты, заспавненные после подъёма (`coder-T-7`, `coder-T-7-2`, `coder-T-7-3`), по
имени резолвятся. Имя теряют только агенты, заспавненные до перезапуска; id оркестратор
нашёл вручную.

T-11 (дополнение swais-lead): то же — «No agent named 'architect-T-11' is reachable»,
продолжение по agentId; агент заспавнен до подъёма сессии.

MEW-25 (G-57 mewria-lead): то же после `respawn` (ENOTFOUND). В 07:29 и 07:40 SendMessage
`reviewer-MEW-25` и `architect-MEW-25` — «not reachable»; по id сессия не пробовала,
а заспавнила reviewer'а заново с тем же именем и ротировала architect'а в
`architect-MEW-25-2` с `PREVIOUS_REPORTS`. Это сработало, но контекст обоих агентов
пропал. `review-cycle.md` («При обрыве агента SendMessage возобновляет его из
транскрипта») покрывает только обрыв внутри живой сессии.

**Предложение.**
- `agent_ctx.py NAME` печатает и `id` (из имени файла транскрипта); тот же поиск —
  «последний транскрипт с этим именем в сессии».
- `runtime.md`, «Спавн агентов»: SendMessage по имени не доставлен («No agent named … is
  reachable») агенту, который жив в `state.yaml` — после перезапуска сессии; продолжить
  по id из `agent_ctx.py {имя}`, не спавнить нового. Хранить id в `state.yaml` не нужно:
  транскрипт его даёт, и правило работает и для агентов, заспавненных до выпуска.
- `review-cycle.md`, «Continuation» — ссылка на это правило; новый спавн с отчётами
  предшественника и ротационным суффиксом (как в MEW-25) — только если продолжить по id
  не вышло.
- `lead.md`, «Остановленная сессия»: `advisory` «продолжить» после `respawn` напоминает,
  что прежних агентов продолжают по id.

**Критерии приёмки.** `agent_ctx.py` печатает `id`, тест на фикстуре; правило в runtime.md;
после `respawn` оркестратор продолжает прежних агентов без ручного поиска id.
