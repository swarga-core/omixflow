---
id: omixflow-ts-declaration-each
title: tests.declaration адаптера ts не видит it.each, it.only, test.concurrent — report.py недосчитывает новые тесты
status: draft
type: bug
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-13, шаги 1, 2, 4 (G-78 лида swais-lead, 2026-10-18), сверено по adapters/lang/ts.md
target: omixflow
external:
links: [omixflow-mutations-per-test]
---

**Контекст.** `report.py check`, MUTATIONS: новые объявления тестов в изменённых тестовых файлах
ищутся по `tests.declaration` адаптера lang; столько строк MUTATIONS и должно быть. У ts —
`'^\s*(it|test)\s*\('` (`adapters/lang/ts.md:11`).

**Проблема.**
- Шаблон не совпадает с модификаторами vitest: проверено — `it.each([1,2])("x %s", …)`,
  ``test.each`…`("y", …)``, `it.only(…)`, `it.skip(…)`, `test.concurrent(…)` не считаются.
- T-13, шаги 1, 2, 4: «новых тестов 5» при 7 (два `it.each`), coder оговаривал расхождение
  в отчёте вручную.

**Предложение.** Шаблон с цепочкой модификаторов: `'^\s*(it|test)(\.\w+)*\s*[(`]'` — `it.each(`
и ``test.each` `` — одно объявление (одна строка MUTATIONS на таблицу случаев), `it.skip`/`it.todo`
тоже объявления (их добавление видно в отчёте). Тест в `tests/test_report.py` на дифф с
`it.each`, `it.only`, `test.concurrent`.

**Критерии приёмки.** `it.each` и модификаторы в диффе учитываются в счёте `report.py`;
тест на каждую форму.
