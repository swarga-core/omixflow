---
id: omixflow-agents-without-name
title: Харнесс 2.1.300+ спавнит субагентов без имени — протокол требует name, agent_ctx.py ищет только по имени
status: draft
type: bug
created: 2026-10-16
updated: 2026-10-16
origin: Swarga AI Studio T-10 (G-65 лида swais-lead, 2026-10-16, сессия на 0.9.0), сверено по транскриптам T-10, T-8, T-9, T-11 и scripts/agent_ctx.py
target: omixflow
external:
links: [omixflow-agent-resume-by-id, omixflow-rotation-context-teammates, omixflow-agent-rotation-context]
---

**Контекст.** `protocol/runtime.md:125-127`: каждый спавн architect, coder, tester и reviewer
«обязан иметь `name`» (`{role}-{id}`), продолжение — SendMessage по имени; после
перезапуска — по `id` из `agent_ctx.py {имя}` (0.7.3). Ротация (`protocol/tiers.md:131-137`)
берёт объём контекста из `agent_ctx.py {имя агента}`; `context: null` — из usage
уведомления о завершении, иначе строка «контекст {имя} неизвестен» и coder сменяется только
по шагам. `agent_ctx.py` ищет транскрипт по полю `name` в
`{projects}/*/{session}/subagents/*.meta.json` (`scripts/agent_ctx.py:52-63`).

**Проблема.**
- Харнесс сменил инструмент Agent: в 2.1.296 параметр `name` был — в `.meta.json`
  субагентов SwAIS T-8, T-9, T-11 есть `"name": "coder-T-8"` и т. п. Сессия T-10 шла на
  2.1.300–2.1.301: у Agent нет параметра `name` (у сессии omixflow-lead на 2.1.301 — тоже),
  во всех 8 `.meta.json` T-10 поля `name` нет (`agentType`, `description`, `toolUseId`,
  `model`). Продолжение — только по agentId; T-10 так и делала, хранила id в
  `state.yaml` `agents.*`.
- Оркестратор T-10 вызвал `agent_ctx.py a6a303d678e606a77` (id вместо имени) — код 3,
  `"reason": "транскрипт агента не найден: …/84ebdefc-…/subagents"`. Каталог `subagents`
  при этом был (8 транскриптов, `agent-a6a303d678e606a77.jsonl` среди них): скрипт не
  нашёл совпадения по `name`, а текст причины читается как «каталога нет» — так гоча
  и записана.
- Ротация пошла по запасному пути tiers.md: «контекст ~498k по usage уведомления (порог
  350k; `agent_ctx.py` транскрипт не находит)», coder сменён после третьего шага.
- Всё, что держится на имени, разошлось с харнессом: «обязан иметь `name`», суффиксы
  ротации (`coder-{id}-2`), `state.py set agents.{ключ}={имя}`, `agent_ctx.py {имя}`,
  поиск по id после respawn через имя.

**Предложение.**
1. `agent_ctx.py` принимает и id: аргумент вида `a[0-9a-f]{16}` ищется по имени файла
   `agent-{id}.jsonl`, иное — по `name` в `.meta.json`. Причина кода 3 различает «нет
   каталога subagents у сессии», «нет транскрипта с именем/id {X}» и «нет ответа модели».
2. `runtime.md`, «Спавн агентов»: адрес агента — agentId из результата спавна, его
   хранит `state.yaml` `agents.*` (`state.py set TASK_DIR agents.{ключ}={id}`); `name` —
   когда харнесс его принимает, тогда SendMessage по имени. Ротационный суффикс — в
   `description` спавна, а не в адресе.
3. `tiers.md`, ротация: `agent_ctx.py {id или имя}`; запасной путь — usage уведомления
   о завершении (как в T-10) — назван явно, с оговоркой, что его поле — объём контекста
   последнего ответа, а не сумма за агента (проверить на транскрипте и записать).
4. `doctor`: проверка, что `agent_ctx.py` находит транскрипт хотя бы одного субагента
   текущей сессии по id (если они есть) — по образцу пробы `sessions.py probe`.

**Критерии приёмки.** Оркестратор продолжает агента по agentId из `state.yaml` без имени;
`agent_ctx.py {id}` отдаёт контекст субагента без поля `name` в `.meta.json`; причина кода 3
различает отсутствие каталога и отсутствие транскрипта; тесты на поиск по id и по имени.
