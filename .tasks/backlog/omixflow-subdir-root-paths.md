---
id: omixflow-subdir-root-paths
title: Корень проекта в подкаталоге git-репозитория — пути git diff от корня репозитория, report.py не видит изменённые файлы
status: draft
type: bug
created: 2026-10-20
updated: 2026-10-20
origin: ревью выпуска 0.9.6 (F4), воспроизведено фикстурой ревьюера; ошибка старше 0.9.6
target: omixflow
external:
links: [omixflow-report-sync-dirty-files]
---

**Контекст.** `omixflow_lib.changed_files` собирает дельту из `git diff --name-only HEAD` и `git
ls-files --others` (оба через `git -C {root}`). `report.py` затем читает `root / path`. Корень
проекта — ближайший каталог с `.claude/omixflow/flow.yaml`, он может лежать в подкаталоге репозитория
(монорепо с проектом в `app/`).

**Проблема.**
- `git diff --name-only` печатает пути от корня репозитория (`app/src/b.test.ts`), `ls-files
  --others` — от текущего каталога (`src/c.test.ts`): дельта смешивает формы.
- `root / "app/src/b.test.ts"` не существует: MUTATIONS и BYTES CHECK не видят изменённых
  отслеживаемых файлов — ни в шаге, ни в синхронизации (`sync_files`, 0.9.6, и `MERGE_MSG` дают те же
  пути от корня репозитория). Ревью 0.9.6: новый тест с кириллицей в отслеживаемом `b.test.ts` не
  посчитан, посчитан только неотслеживаемый `c.test.ts`; seam-тест в конфликтном файле — «новых
  тестов 0» и на 0.9.5, и на 0.9.6.

**Предложение.**
1. `--relative` во всех `git diff --name-only` (`changed_files`, `report.sync_files`, остальные
   вызовы в скриптах): пути от корня проекта, файлы вне его отброшены.
2. Пути из `MERGE_MSG` — снять префикс `git rev-parse --show-prefix`.
3. Менять одновременно: если поправить только `changed_files`, фильтр синхронизации отбросит всё.

**Критерии приёмки.** Фикстура с корнем проекта в подкаталоге репозитория: `report.py check` видит
изменённый отслеживаемый тестовый файл в шаге и в синхронизации; тест в `tests/test_report.py`.
