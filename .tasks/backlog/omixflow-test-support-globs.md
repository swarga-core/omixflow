---
id: omixflow-test-support-globs
title: plan.py files считает тестовую поддержку (test/, fixtures/) нетестовыми файлами — порог тира срабатывает зря
status: draft
type: bug
created: 2026-10-16
updated: 2026-10-16
origin: Swarga AI Studio T-10 (G-67 лида swais-lead, 2026-10-16, сессия на 0.9.0; E-42, D-254), сверено по scripts/plan.py, adapters/lang/ts.md, protocol/review-cycle.md и log.md T-10
target: omixflow
external:
links: [omixflow-tier-ceiling, omixflow-tier-from-statement]
---

**Контекст.** `protocol/tiers.md:15`: пороги тира считают нетестовые файлы — тесты идут
парой к коду. `plan.py files` отличает тесты по `tests.files` всех адаптеров lang и их
расширений (`scripts/plan.py:94-110`). В адаптере ts `tests.files` — только
`**/*.test.ts`, `**/*.test.tsx` и варианты (`adapters/lang/ts.md:10`). Проза того же
адаптера (`ts.md:46-48`, `test_conventions`) называет тестовой поддержкой `__mocks__/`,
`fixtures/`, `test/`, `test-utils/` пакета и `setupFiles` vitest; по ней же
`review-cycle.md`, шаг 3, отдаёт правки тестовой поддержки tester'у.

**Проблема.**
- SwAIS T-10, Plan: `plan.py files` — 31 нетестовый при пороге 30 (`tiers.m_max_files`,
  поднят до 30 разработчиком). Сверх порога — хелперы `packages/server/test/task-fixtures.ts`
  и `test/actions.ts`; фактически кода и документации 29 (22 + 7 ADR). Вопрос ушёл
  разработчику как исключение (E-42 → D-254, «продолжить как есть»); после фиксов ревью
  плана — 32 по скрипту, из них три хелпера `packages/server/test/{db,task-fixtures,actions}.ts`,
  фактически по-прежнему 29.
- Механика и проза одного адаптера расходятся: что tester правит как тестовую поддержку,
  то `plan.py` считает кодом. С 0.9.0 превышение порога — исключение разработчика, не
  решение лида, так что ложное срабатывание — лишняя эскалация разработчику.
- Обход есть и сейчас: расширение проекта `.claude/omixflow/lang/ts.md` с `extends:
  omixflow:ts` и своими глобами в `tests.files` — `plan.py` объединяет глобы цепочки. Но
  `tests.files` читает и MUTATIONS в `report.py check` («новые декларации тестов в
  изменённых тестовых файлах»); хелперы без `it(`/`test(` там безвредны, но смысл ключа —
  «файлы тестов», не «поддержка».

**Предложение.**
1. Ключ `tests.support` в front matter адаптеров lang — глобы тестовой поддержки,
   по прозе `test_conventions`: ts — `**/__mocks__/**`, `**/fixtures/**`, `**/test/**`,
   `**/test-utils/**`; ключ — в `adapters/lang/PORT.md`, чтобы проектные адаптеры (mewria,
   C#) задавали свой. Расширение проекта дополняет список, как `tests.files`.
2. `plan.py files` считает `tests.support` отдельно (`support N`) и в порог не включает;
   `report.py` MUTATIONS их не касается.
3. `review-cycle.md`, шаг 3, и `tiers.md:15` ссылаются на один источник: «тестовая
   поддержка — `tests.support` адаптера lang и проза `test_conventions`».
4. Линт: у адаптера с `test_conventions`, где проза называет каталоги поддержки, есть
   `tests.support`.

**Критерии приёмки.** План с хелперами в `packages/*/test/**` не превышает порог из-за них
(тест на `plan.py files` с такими путями); `review-cycle.md` шаг 3 и `plan.py` согласованы
в том, что считать тестовой поддержкой; doctor или README адаптеров называют, как проект
расширяет `tests.support`.
