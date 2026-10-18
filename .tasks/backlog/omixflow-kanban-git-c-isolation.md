---
id: omixflow-kanban-git-c-isolation
title: Адаптер kanban советует git -C .tasks/board — изолированная сессия такую команду отклоняет
status: draft
type: docs
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-13 (G-80 лида swais-lead, 2026-10-18), сверено по adapters/tracker/kanban.md
target: omixflow
external:
links: [omixflow-worktree-isolation-recipes]
---

**Контекст.** `adapters/tracker/kanban.md:30-32`: «В `.tasks/board` не заходить (`cd`)…
Доску читать `get`, `list`, `path` или `git -C .tasks/board` только для чтения». Доска —
отдельное дерево (ветка доски) в основном checkout.

**Проблема.** В worktree-сессии харнесс отклоняет `git -C` на другое дерево («redirects git to
the shared checkout via -C», разбивка отказов изоляции 2026-10-12: 14 таких). T-13 пошла по
совету адаптера и получила отказ.

**Предложение.** Строку заменить: доску читать `board.py get`, `list`, `path` и файлы карточки
по пути, который печатает `path` (Read); `git -C .tasks/board` — только из основного дерева, не
из изолированной сессии. Линт: адаптеры не советуют `git -C` на чужое дерево без оговорки.

**Критерии приёмки.** kanban.md не предлагает изолированной сессии запрещённую форму; линт.
