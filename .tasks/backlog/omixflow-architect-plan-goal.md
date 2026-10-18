---
id: omixflow-architect-plan-goal
title: architect в режиме spec+plan пропускает **Goal:** в шагах — круг fix ловит plan.py check
status: draft
type: improvement
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-13, Plan (G-79 лида swais-lead, 2026-10-18), сверено по log.md и plan.md T-13 и agents/architect.md
target: omixflow
external:
links: [omixflow-architect-plan-quality]
---

**Контекст.** Шаблон шага в `agents/architect.md:134-140`: `**Goal:**`, `**Covers:**`,
`**Design:**`, Files, Test checkpoint. `plan.py check` (0.9.0) проверяет поля шагов; скилы spec
(M) и plan (L) дают architect'у до двух кругов фиксов по выводу check.

**Проблема.**
- T-13: у шагов 2–8 первого плана не было `**Goal:**`; log.md: «plan.py check: кругов 1,
  остаток 0 (нет **Goal:** у шагов 2–8 — исправлено architect)». Механизм сработал как задуман,
  цена — один круг architect'а (запрос на полном контексте spec+plan).
- Самопроверку architect сделать не может: у него нет Bash (`tools: Read, Write, Edit, Glob,
  Grep, mcp__serena__*`), `plan.py check` ему не запустить.

**Предложение.**
1. В `agents/architect.md` перед ответом — самопроверка по списку полей: каждый `### Step N`
   имеет `**Goal:**`, `**Covers:**`, `**Design:**`, Files, Test checkpoint (текстом, без
   скрипта); шаблон шага — с пометкой «все поля в каждом шаге, не только в первом».
2. Сколько кругов `plan.py check` уходит на поля шагов — по log.md задач 0.9 (`stats.py`,
   строка «plan.py check: кругов N»): если у большинства планов круг ровно этот — пункт 1
   окупается, иначе оставить как есть.

**Критерии приёмки.** План от architect'а проходит `plan.py check` по полям шагов с первого раза
на следующих прогонах; или данные `stats.py` показывают, что круг редок, и заметка закрывается.
