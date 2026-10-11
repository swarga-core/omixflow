---
id: omixflow-tester-findings-input
title: У tester'а нет входа FINDINGS и построчного итога по findings в отчёте
status: draft
type: feature
created: 2026-10-11
updated: 2026-10-11
origin: ревью выпуска 0.6.1 (сессия omixflow-lead, 2026-10-11), после omixflow-review-fix-route-by-file
target: omixflow
external:
links: [omixflow-review-fix-route-by-file]
---

**Контекст.** С 0.6.1 исполнитель фикса ревью выбирается по файлам правки
(`review-cycle.md`, шаг 3): tester получает findings любой категории, если правка только
в тестах и тестовой поддержке, — не только `tests`, но и `code`, `spec-sync`.

**Проблема.** В `agents/tester.md` нет входа FINDINGS (принятые findings с решениями) и
строки отчёта по каждому finding. Findings приходят tester'у текстом задания (T-1:
«TASK: fix for code review finding F7 …»), а что закрыто, оркестратор и reviewer
восстанавливают из TESTS WRITTEN и диффа. Пробел старше 0.6.1, но теперь tester получает
больше findings и чужих категорий.

**Предложение.** Вход `FINDINGS` (необязательный: пакет фиксов ревью) с id, решением
и рекомендацией; в отчёте — блок `FINDINGS: #{id} — fixed | not fixed, почему`; скил review,
шаг 4, передаёт его в спавне. Сверить, есть ли такой блок у coder'а в пакете фиксов; если
нет — тем же выпуском.

**Критерии приёмки.** Вход и блок отчёта в `tester.md`; review передаёт FINDINGS tester'у;
re-review видит итог по каждому id без восстановления из диффа.
