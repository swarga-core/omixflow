---
id: omixflow-agent-bare-tmp
title: coder пишет вывод прогонов в голый /tmp при SCRATCH_DIR в брифе — правило есть, сверки нет
status: draft
type: bug
created: 2026-10-22
updated: 2026-10-22
origin: mewria MEW-30 (G-20 лида mewria-client-lead, 2026-10-22), сверено по /tmp и транскрипту субагента coder-MEW-30-4 (сессия 75ddc008)
target: omixflow
external:
links: [omixflow-agent-scratch-location, omixflow-vitest-json-outputfile]
---

**Контекст.** `agents/coder.md`, «Scratch outside the task», и `agents/tester.md`: временное — только в
SCRATCH_DIR, подкаталог на метку отчёта, «never bare `/tmp`» (0.7.2; MEW-17: 118 МБ проб в `/tmp`).
0.9.6 добавил явный путь в SCRATCH_DIR для отчётов инструментов. Сверки нет: `report.py check` видит
дерево проекта и git-каталог, не `/tmp`.

**Проблема.**
- MEW-30: `/tmp/coder-mew30-4-rel.txt` и `/tmp/coder-mew30-4-dbg.txt` (2026-10-21 23:21) — вывод `dotnet
  test` (Release и Debug) coder'а coder-MEW-30-4: `dotnet test … > /tmp/coder-mew30-4-rel.txt 2>&1`.
  В его брифе был `SCRATCH_DIR: …/jobs/75ddc008/tmp/coder-MEW-30-4`.
- Параллельные фоновые сессии делят `/tmp`: одноимённые файлы двух задач затирают друг друга, и
  файлы остаются после сессии.

**Предложение.**
1. Правило в coder и tester — уже есть; дописать пример с перенаправлением вывода (`> {SCRATCH_DIR}/
   {метка}/….txt`), а не только «временные файлы».
2. Сверка: `report.py check` — предупреждение на путь `/tmp/…` (или `/private/tmp/…`) вне SCRATCH_DIR в
   тексте отчёта; полнее — хук PreToolUse на Bash агентов плагина (`> /tmp/`, `tee /tmp/`, `-o /tmp/`) с
   предупреждением в `additionalContext`.
3. Оркестратор после ответа агента: `ls /tmp` по шаблону метки — по желанию, дёшево.

**Критерии приёмки.** Путь `/tmp/…` вне SCRATCH_DIR в отчёте даёт предупреждение `report.py check`;
правило coder и tester называет перенаправление вывода; тест в `tests/test_report.py`.
