---
id: omixflow-state-split-steps
title: state.py step не принимает шаг с буквой (3a) — steps_done только числа, plan.py check для таких шагов шумит
status: draft
type: bug
created: 2026-10-20
updated: 2026-10-20
origin: ревью выпуска 0.9.6 (F3), сверено по scripts/state.py и scripts/plan.py
target: omixflow
external:
links: [omixflow-plan-check-done-steps]
---

**Контекст.** `plan.py` распознаёт шаг с буквой (`### Step 5a`, T-8: шаг, разбитый по ходу
Implement), `stats.py` считает 3a/3b двумя шагами. `state.py step DIR start|done N` приводит N к
`int` (`cmd_step`), `steps_done` хранит числа, `step` после `done` — `N + 1`.

**Проблема.**
- `state.py step DIR done 3a` → `ValueError: invalid literal for int()`: сделанный шаг с буквой в
  `steps_done` не попадает.
- `plan.py check` с 0.9.6 не сверяет с деревом пути сделанных шагов по `steps_done` (G-97); у шага
  `3a` это не работает — после него снова ложные «CREATE … already exists».

**Предложение.**
1. `state.py step` принимает `\d+[a-z]?`: числа — числами, с буквой — строкой; `steps_done` в
   порядке плана (сортировка по числу, затем по букве).
2. `step` после `done 3a` — следующий шаг плана, а не `int + 1` (читать план или оставлять `null`
   до `start`).
3. Потребители `steps_done` (`lead.py`, скилы implement и review, `stats.py`) — сверить со
   строковыми номерами.

**Критерии приёмки.** `state.py step DIR done 3a` записывает `3a`; `plan.py check` после него не
сверяет пути шага 3a с деревом; тесты в `tests/test_state_multitask.py` и `tests/test_plan.py`.
