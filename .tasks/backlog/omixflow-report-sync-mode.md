---
id: omixflow-report-sync-mode
title: report.py check не знает отчёта синхронизации — требует FILES и считает тесты базы работой coder'а
status: draft
type: bug
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-14, Finalize, синхронизация с main после вливания T-13 (G-88 лида swais-lead, 2026-10-18; E-53/D-323), сверено по транскрипту T-14, scripts/report.py и agents/coder.md
target: omixflow
external:
links: [omixflow-bytes-check-cyrillic, omixflow-ts-declaration-each]
---

**Контекст.** Синхронизация с базой (implement 2.x, finalize шаг 0): оркестратор начинает
слияние, на конфликтах шлёт coder'у `MODE: sync` с `CONFLICTS` и `REPORT_PATH:
{TASK_DIR}/reports/{phase}-sync{K}.md`; coder разрешает, `git add`, гоняет полный набор и пишет
отчёт, где «the per-file resolutions replace FILES» (`agents/coder.md:233`, «Sync mode»). Коммит
слияния делает оркестратор. `report.py check --role coder` проверяет этот отчёт как отчёт шага:
дельта агента — против HEAD или baseline, разделы — набор шага.

**Проблема.**
- T-14, `finalize-sync1.md` (2026-10-18 12:28, 8 конфликтов, слияние main @ 05dd08d после T-13):
  `VERDICT: return` — «нет разделов: FILES» (формат синхронизации его не содержит) и «MUTATIONS:
  none, но новых тестов 93»: `task.test.ts` 5, `run-control-actions.test.ts` 20,
  `task-status.test.ts` 18 и т. д. — это тесты T-13, принесённые базой, а не работа coder'а.
- Baseline перед заданием синхронизации не снимался: слияние уже шло. Дельта против HEAD задачи
  — всё, что принесла база. Оркестратор сверил отчёт руками и пошёл дальше; отчёт починки
  (`finalize-sync-fix1.md`, после коммита слияния, со своим baseline) прошёл `ok`.

**Предложение.**
1. `report.py check` распознаёт синхронизацию: идёт слияние (`MERGE_HEAD` есть) или отчёт с
   `MODE: sync` — режим sync.
2. В режиме sync: FILES не требуется, вместо него — построчные разрешения (`{file} — {how}`),
   и каждый файл из CONFLICTS (`--conflicts` или `git diff --name-only --diff-filter=U` до `add`,
   оркестратор передаёт список) назван; TREE STATE сверяется как обычно.
3. Дельта агента в sync — только конфликтные файлы, и «новое» в них — то, чего нет ни в одном
   родителе: объявления тестов (MUTATIONS) и не-ASCII строки (BYTES CHECK) в итоговом файле минус
   те, что есть в `HEAD:{file}` или `MERGE_HEAD:{file}`. Тест базы и тест задачи, оба
   сохранённые разрешением, — не новые.
4. Скилы implement и finalize: в задании sync — `CONFLICTS` тем же списком, что получает
   `report.py check --conflicts`.

**Критерии приёмки.** Отчёт синхронизации с чужими тестами из базы проходит `report.py check`
без ручной сверки; MUTATIONS требуются только для тестов, добавленных или изменённых при
разрешении; тест на репозиторий с идущим слиянием (два родителя с тестами, конфликт в одном файле,
разрешение добавляет один тест).
