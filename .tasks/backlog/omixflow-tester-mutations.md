---
id: omixflow-tester-mutations
title: Тесты tester'а без мутационной пробы; порядок coder → tester на Review не по зависимости
status: draft
type: bug
created: 2026-10-09
updated: 2026-10-09
origin: лид mewria-lead 2026-10-09 — гоча G-38 (MEW-2, Review); подтверждено по транскрипту сессией omixflow-lead
target: omixflow
external:
links: [omixflow-coder-mutation-report, omixflow-mutation-restore-mtime]
---

**Контекст.** Гоча G-38: «тесты фиксов пишет tester (после coder, skills/review:74), а tester
исходники не правит (agents/tester.md:11) — требование implement „каждый новый тест — строка
MUTATIONS с RED" (skills/implement:82) на Review без исполнителя».

**Проблема.**
- Мутационную пробу делает только coder; tester исходники не трогает даже временно. В MEW-2
  пробы к тестам tester'а гонял ревьюер кода (в копии дерева, `gate.py`) и coder отдельным
  заданием (`reports/review-mutations-il2cpp.md`). Тот же пробел — в Implement, когда тесты
  к шагу пишет tester (`tests-step{N}`).
- `skills/review`, шаг 4: tests → tester «после coder». В MEW-2 правки coder'а поведения не
  меняли, а его строки «Тест:» в `storage.md` называли новые тесты tester'а: оркестратор
  перевернул порядок сам (log.md MEW-2, «Ход ревью»).

**Решение (0.5.1).**
- tester делает мутационную пробу каждого нового теста сам: временная правка исходника
  по рецепту coder'а (копия рядом, откат `cp`, удаление копии), в отчёте `MUTATIONS`
  и `TREE STATE`. Постоянных правок исходников у tester'а по-прежнему нет.
- Сверка отчёта (`implement`, 2.2) требует `MUTATIONS` у автора теста — coder или tester.
- Порядок фиксов на Review — по зависимости: фикс кода раньше тестов к нему; строки
  спецификаций, называющие новые тесты, — после тестов (если нужно и то и другое,
  spec-sync уходит coder'у отдельным заданием после tester'а).

**Критерии приёмки.** Формат отчёта tester'а содержит `MUTATIONS` и `TREE STATE`; скилы
implement и review сверяют их; линт формата отчётов это проверяет.
