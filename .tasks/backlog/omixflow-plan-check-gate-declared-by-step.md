---
id: omixflow-plan-check-gate-declared-by-step
title: plan.py check не видит гейт, который объявляет шаг самого плана — «gate the project does not declare» у следующих шагов
status: draft
type: bug
created: 2026-10-21
updated: 2026-10-21
origin: Swarga AI Studio T-21 (G-116 лида swais-lead, 2026-10-21), сверено по log.md и spec.md T-21 и воспроизведено plan.py check на копии плана
target: omixflow
external:
links: [omixflow-plan-check-done-steps]
---

**Контекст.** `plan.py check` сверяет гейты чекпоинтов с объявленными: гейт в обратных кавычках,
которого нет в `verify` текущего `flow.yaml` (с командой), — «checkpoint names gate `{g}` the
project does not declare in `verify`». Набор берётся из конфига на момент проверки. Во время
Implement `resolve.py verify` читает `flow.yaml` заново, так что гейт, объявленный шагом, на шагах
после него работает; ложь только в статической проверке плана.

**Проблема.**
- T-21 «Гейт structure: слои пакетов на dependency-cruiser» (тир S, профиль full, `specs.mode:
  adr`): шаг 1 — `MODIFY: .claude/omixflow/flow.yaml — verify.structure: pnpm structure`, шаги 2–3
  называют гейт `structure` в чекпоинтах.
- `plan.py check`: «кругов 1 (шаг 1 называет команду `pnpm structure`, а не гейт), остаток 3 — шаги
  2–3 называют гейт `structure`, который объявляет шаг 1» (log.md T-21, «Plan ✅ (combined)»);
  сессия обошла строкой в log.md и аспектом ревью.
- Воспроизведено на копии плана с `flow.yaml` основного дерева Swarga AI Studio: «step 2: … gate
  `structure` …», «step 3: …» дважды — одна строка на каждое упоминание гейта в чекпоинте, дубли не
  схлопываются.
- Шаг 1 свой гейт в чекпоинте назвать тоже не может (тот же отказ), отсюда команда вместо гейта.

**Предложение.**
1. Шаг, у которого в Files правка `flow.yaml` с `verify.{gate}` в описании (`MODIFY: …/flow.yaml —
   verify.structure: …`), объявляет гейт: для его собственного чекпоинта и для всех следующих шагов
   гейт объявлен. Явная форма — по желанию: пометка в описании файла «объявляет гейт `{name}`».
2. Гейт, которого нет ни в `flow.yaml`, ни в объявлении шагов, — по-прежнему строка.
3. Одна строка на гейт в шаге, без дублей.
4. Сделанные шаги (`steps_done`, 0.9.6) объявление тоже дают.

**Критерии приёмки.** План, где шаг N добавляет `verify.{gate}` в `flow.yaml`, а шаги ≥ N его
называют, проходит `plan.py check` без строк о гейте; гейт, который не объявляет ни шаг, ни
`flow.yaml`, ловится; тест в `tests/test_plan.py`.
