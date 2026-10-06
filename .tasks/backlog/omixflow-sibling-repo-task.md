---
id: omixflow-sibling-repo-task
title: Задача целиком в соседнем репозитории — EnterWorktree отказывает, хук не срабатывает
status: draft
type: feature
created: 2026-10-06
updated: 2026-10-06
origin: прогон AL-1176 (черновик issues-al-1176, разобран 2026-10-06)
target: omixflow
external:
links: [omixflow-part-reads-repos]
---

**Контекст.** AL-1176 запущен из `eps-eal-omix`, а мутирует только сиблинг `eps-omix-lib`.

**Проблема.** `git worktree add` прошёл, но `EnterWorktree({path})` вернул «not a registered
worktree» — харнесс принимает только репозиторий запуска или вложенный. Дальше шли
по абсолютным путям (`--project` у скриптов, абсолютный `TASK_DIR`), `wt-setup.sh` не сработал,
`pnpm install --offline` вручную. Инвариант 7 (`protocol/phases.md:36-39`, повторы в
`skills/develop`, `skills/start`) ловит только задачу на несколько репозиториев; случай
«задача целиком в чужом репозитории из `workspace.repos`» не различается; `protocol/worktree.md`
создаёт worktree только в своём репозитории.

**Предложение.** `develop` и `start` распознают задачу, целиком лежащую в другом репозитории,
и предлагают запустить сессию там (Recommended) либо вести её без входа по абсолютным путям
с ручным setup; режим описать в `worktree.md`.

**Критерии приёмки.** Скилы распознают случай и дают выбор; ручной режим описан.
