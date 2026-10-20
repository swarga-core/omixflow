---
id: omixflow-mutations-per-declaration
title: coder не знает, что report.py считает новые тесты по объявлениям адаптера — [TestCase] считается каждый
status: draft
type: docs
created: 2026-10-20
updated: 2026-10-20
origin: mewria MEW-34, шаг 2 (G-72 лида mewria-sim-lead, 2026-10-20), сверено по .claude/omixflow/lang/csharp.md mewria, agents/coder.md и log.md MEW-34
target: omixflow
external:
links: [omixflow-mutations-per-test, omixflow-ts-declaration-each]
---

**Контекст.** `report.py check`, MUTATIONS: новых тестов столько, сколько новых строк, совпавших с
`tests.declaration` адаптера lang; строк с исходом должно быть не меньше. У mewria (проектный
адаптер `csharp.md`) — `^\s*\[(Test|TestCase|TestCaseSource|UnityTest)\b`: каждый `[TestCase(…)]` —
отдельное объявление. `agents/coder.md:139`: «MUTATIONS has a line for every NEW test» — о единице
счёта ни слова.

**Проблема.**
- MEW-34, шаг 2: coder дал 22 строки MUTATIONS на 31 объявление — параметризованные тесты строкой на
  метод; `report.py` вернул шаг, лишний круг coder'а; второй отчёт — 33 строки по случаям, ok
  (log.md MEW-34, стр. 249: «первый круг — return, проб 22 на 31 тест»).
- Ошибка `report.py` называет число по файлу («новых тестов N»), но не какие объявления — coder
  не видит, что считаются случаи.

**Предложение.**
1. `agents/coder.md` (и tester), MUTATIONS: строка на каждое новое объявление в смысле
   `tests.declaration` адаптера lang — у параметризованных тестов, где адаптер считает случаи
   (`[TestCase]`, `it.each` таблицей строк), строка на случай: проба с фильтром по аргументам случая.
2. `report.py check`: в ошибке «новых тестов N, строк с исходом M» — первые новые объявления по
   файлу (строки, до 5), чтобы единица счёта была видна.
3. Адаптерам — по желанию: в прозе `test_conventions` одна фраза о единице счёта (у mewria её
   предлагает лид проекта).

**Критерии приёмки.** coder.md и tester.md называют единицу счёта MUTATIONS — объявление по
`tests.declaration`; ошибка `report.py` показывает непокрытые объявления; тест на дифф с тремя
`[TestCase]` одного метода.
