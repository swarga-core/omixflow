---
id: omixflow-vitest-json-outputfile
title: vitest --reporter=json без --outputFile пишет отчёт в рабочее дерево (.vitest/json/output.json)
status: draft
type: docs
created: 2026-10-19
updated: 2026-10-19
origin: Swarga AI Studio T-16, шаг 4 (G-101 лида swais-lead, 2026-10-19), сверено по транскрипту coder'а T-16
target: omixflow
external:
links: [omixflow-agent-scratch-location]
---

**Контекст.** Временные файлы агентов — только в `SCRATCH_DIR` (0.7.2, `runtime.md`, «Временные
файлы агента»). Адаптер ts (`adapters/lang/ts.md`, `test_conventions`) называет, как запустить один
файл и один тест, но о машиночитаемом выводе vitest не говорит.

**Проблема.**
- T-16, шаг 4 (2026-10-19 08:40): coder запускал vitest с `--reporter=json` без `--outputFile`;
  в дереве появился `packages/catalog/.vitest/json/output.json` (`?? packages/catalog/.vitest/` в
  `git status`). Coder убрал его сам (`rm -r`) и написал в NOTES, что такой прогон «пишет
  `packages/{пакет}/.vitest/json/output.json` в дерево».
- Не заметь он — файл ушёл бы в `git add` коммита шага или остался бы в дереве; `report.py check`
  поймал бы его только как расхождение TREE STATE.

**Предложение.**
1. `adapters/lang/ts.md`, `test_conventions`: машиночитаемый вывод vitest — только с
   `--outputFile={SCRATCH_DIR}/{метка}/vitest.json` (или `--reporter=json` в stdout без файла
   отчёта); никогда без него — vitest кладёт отчёт в пакет.
2. Определения coder и tester, «Временные файлы агента»: отчёты инструментов (json, junit,
   coverage) — с явным путём в SCRATCH_DIR.
3. Проекту — по желанию: `.vitest/` в `.gitignore` (это решение проекта, не плагина; doctor может
   подсказать).

**Критерии приёмки.** Прогоны агентов не оставляют файлов отчётов в рабочем дереве; адаптер ts
называет `--outputFile` в SCRATCH_DIR.
