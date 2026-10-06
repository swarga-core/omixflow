---
id: omixflow-wt-setup-old-base
title: Хук worktree пропускает setup, если в базе ещё нет flow.yaml
status: draft
type: bug
created: 2026-10-06
updated: 2026-10-06
origin: прогоны AL-1152, AL-1153, AL-1154 (черновики issues-al-*, разобраны 2026-10-06)
target: omixflow
external:
links: []
---

**Контекст.** Задачи волны от `release/2.2.3`, где `.claude/omixflow/flow.yaml` ещё нет.

**Проблема.** `scripts/wt-setup.sh:25-29` строго ищет `$wt/.claude/omixflow/flow.yaml`, иначе
пишет «has no flow.yaml; skip»: submodule `omix/` пуст, `node_modules` нет, первый гейт красный
на `@omix/*` и выглядит дефектом ветки. Обход в прогоне: копия `.claude/omixflow/` и `.mcp.json`,
`.git/info/exclude`, `submodule update --init --reference`, `pnpm install --offline`. Флага
`--reference` в хуке нет (`:34`), хотя `adapters/workspace/git.md:38-39` его упоминает.
`protocol/runtime.md:15-16` требует корень проекта = worktree, поэтому родительский обход
конфига надо оговорить.

**Предложение.** Хук берёт конфиг родительским обходом или через `--git-common-dir`
основного дерева и всё равно делает submodule init и `workspace.setup`, записывая в лог, откуда
взят конфиг. `start --worktree` от базы старее конфига копирует `.claude/omixflow/` с
`exclude` и предупреждением; Finalize напоминает снять `exclude`. `worktree.md`: раздел
«База старее конфига».

**Критерии приёмки.** Worktree от базы без `flow.yaml` получает submodule и зависимости;
тест на скрипт хука.
