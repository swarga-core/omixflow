---
id: omixflow-lead-worktree-sparse
title: worktree лида держит полный снимок проекта на момент создания — устаревший flow.yaml ловит скрипты, запущенные из него
status: draft
type: improvement
created: 2026-10-08
updated: 2026-10-08
origin: настройка mewria под 0.4.3, 2026-10-08 — ветка lead/mewria-lead ответвлена на MEW-4 (8bae2e1), её flow.yaml без секции lead и с min_version 0.4.1
target: omixflow
external:
links: [omixflow-lead-coordinator, omixflow-kanban-board-cwd]
---

**Контекст.** Лид работает на ветке `lead/{имя}` в worktree `.claude/worktrees/{имя}`, в который
не входит (`protocol/worktree.md`, «Worktree лида»); коммитит туда только `_lead/`, ветка
в интеграционную не вливается (`protocol/lead.md`, «Ветка лида»). Создаётся полным checkout
от базы (`skills/lead/SKILL.md`, шаг 1.2).

**Проблема.**
- Всё, кроме `_lead/`, в этом worktree — замороженный снимок проекта на момент создания.
  В mewria `flow.yaml` там без секции `lead:`, с `worktree: "off"` и `min_version: 0.4.1`,
  в `main` — уже 0.4.3 с `lead.plugin_session`.
- Сейчас это безвредно: лид читает конфиг из основного дерева. Но любой запуск скриптов
  плагина из worktree лида (после `cd` — см. `omixflow-kanban-board-cwd.md`, ручной `doctor`,
  будущий скрипт с `--project` на путь worktree) молча возьмёт устаревший конфиг:
  `find_project_root` найдёт ближайший `flow.yaml`.
- Обновлять снимок правкой на ветке лида нельзя: «коммиты только `_lead/`», и это worktree
  живой сессии.
- Попутно: полный checkout проекта ради одного каталога — время и место (в Unity-проекте —
  `client/Assets`, LFS).

**Предложение.** Создавать worktree лида разреженным: `git worktree add --no-checkout`,
затем `git -C {wt} sparse-checkout set --no-cone /{artifacts.dir}/_lead/` и `checkout`.
В дереве остаётся только `_lead/` (и файлы корня при cone-режиме — выбрать no-cone, чтобы
`flow.yaml` и `.claude/` не попадали). Существующий полный worktree при старте лида
доводить до разреженного тем же `sparse-checkout set` (с подтверждением, как создание).

**Критерии приёмки.**
- В новом worktree лида нет `.claude/omixflow/flow.yaml`; запуск `doctor` / `resolve.py`
  с каталогом внутри worktree находит конфиг основного дерева или явно падает, а не читает
  снимок.
- Основное дерево и worktree сессий не становятся разреженными (настройка per-worktree,
  `extensions.worktreeConfig` git включает сам — проверить на git 2.31+).
- `doctor`, секция `lead`: WARN, если worktree лида не разреженный.

**Ограничения.** Протокольная правка `worktree.md` и шаг 1.2 скила `lead`; коммиты журнала
(`git -C {wt} add {artifacts.dir}/_lead/...`) в разреженном дереве работают без изменений.
