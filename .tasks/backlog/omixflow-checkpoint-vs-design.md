---
id: omixflow-checkpoint-vs-design
title: Чекпоинт «прежние тесты без правок» противоречит Design своего шага, который меняет поведение под этими тестами
status: draft
type: improvement
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-14, шаг 3 (G-86 лида swais-lead, 2026-10-18), сверено по plan.md и reports/implement-step3.md T-14
target: omixflow
external:
links: [omixflow-architect-plan-quality, omixflow-architect-plan-goal]
---

**Контекст.** Шаг плана (0.9.0): Design — как шаг меняет код, Test checkpoint — чем шаг
проверяется. `plan.py check` сверяет поля и гейты; согласованность чекпоинта с Design — суждение
ревьюера плана.

**Проблема.**
- T-14, шаг 3: Design — «`transitionVariable` принимает источник `decision`»; чекпоинт —
  «Прежние тесты `chooseDone` зелёные без правок». Прежний тест проверял, что значение с
  источником `decision` — ошибка; по Design он обязан измениться. coder пошёл по Design: в тесте
  источник `decision` → `system` и новое сообщение, объяснение в NOTES
  (reports/implement-step3.md, стр. 6).
- Ревью плана противоречия не нашло; решать пришлось coder'у по ходу шага.

**Предложение.**
1. Аспект ревью плана (`agents/reviewer.md`, «Aspects by phase», Plan): чекпоинт «без правок»
   / «unchanged» у шага, чей Design меняет поведение, которое закрепляют прежние тесты, —
   finding `plan`.
2. `agents/architect.md`: чекпоинт называет прежние тесты, которые шаг меняет, и как («тест X —
   источник `decision` теперь допустим»), а «без правок» — только о тестах, поведение которых
   Design не трогает.
3. Эвристика `plan.py check` (по желанию): чекпоинт с «без правок»/«unchanged» в шаге, Design
   которого называет функцию из того же чекпоинта, — строка ревьюеру, не дефект.

**Критерии приёмки.** Ревью плана помечает чекпоинт, противоречащий Design своего шага; правило
architect'а записано.
