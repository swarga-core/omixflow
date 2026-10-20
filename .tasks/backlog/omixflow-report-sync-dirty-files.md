---
id: omixflow-report-sync-dirty-files
title: report.py check в режиме синхронизации берёт в дельту грязные файлы вне слияния — BYTES CHECK по чужой правке
status: draft
type: bug
created: 2026-10-19
updated: 2026-10-19
origin: mewria MEW-28 (G-5 лида mewria-client-lead, 2026-10-19, сессия на 0.9.5), сверено по log.md и reports/implement-sync1.md MEW-28 и scripts/report.py
target: omixflow
external:
links: [omixflow-report-sync-mode]
---

**Контекст.** Режим синхронизации `report.py check` (0.9.4, G-88): пока идёт слияние, новым в
MUTATIONS и BYTES CHECK считается то, чего не дало бы трёхстороннее слияние (`sync_new_lines`).
Дельта агента при этом — все незакоммиченные изменения против HEAD (`agent_delta` без
`--baseline`), то есть и файлы, которых слияние не касается.

**Проблема.**
- mewria MEW-28, синхронизация с main @ 3ddcfdc по правилу проекта R-2 (адаптер workspace mewria:
  правки фаундера в `knowledge/` слиянию не мешают, если база их не трогает): в дереве — грязный
  файл фаундера `knowledge/lore/purr-world.md` с кириллицей. Ни HEAD, ни MERGE_HEAD его не
  меняют.
- `report.py check --role coder --conflicts none` без `--baseline` вернул отчёт: «BYTES CHECK: n/a,
  а в диффе не-ASCII строки: ['knowledge/lore/purr-world.md']» — правки фаундера посчитаны работой
  coder'а (log.md MEW-28, стр. 145–147). С `--baseline`, снятым после старта слияния, — `VERDICT: ok`.
- Попутно: `--conflicts none` читается как список из одного файла `none` — сейчас безвредно
  (слово есть в RESOLUTIONS), но форма «нет конфликтов» не определена.

**Предложение.**
1. В режиме синхронизации дельта — только файлы, которые трогает слияние: `git diff --name-only
   HEAD MERGE_HEAD` (у rebase — `REBASE_HEAD^ REBASE_HEAD`) и конфликтные; грязный файл, которого
   не меняет ни одна сторона, в дельту не входит (о нём — факт «вне слияния: …»).
2. `--conflicts none` (или пустой список) — «конфликтов нет»: RESOLUTIONS может быть `none`.
3. Скил implement, «1a»: при грязном дереве по правилу проекта (R-2 mewria) — `report.py baseline`
   перед заданием синхронизации тоже допустим; с ним дельта — только изменённое с тех пор.

**Критерии приёмки.** При грязном файле вне слияния (не-ASCII) `report.py check` в режиме sync
без `--baseline` даёт ok; не-ASCII строка, внесённая разрешением конфликта, по-прежнему ловится;
`--conflicts none` — без конфликтов; тесты в `tests/test_report.py`.
