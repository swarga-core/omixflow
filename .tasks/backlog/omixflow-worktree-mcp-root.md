---
id: omixflow-worktree-mcp-root
title: MCP-инструменты навигации и рефакторинга в worktree работают на основном дереве
status: draft
type: bug
created: 2026-10-06
updated: 2026-10-06
origin: прогоны AL-1151, AL-1153 (черновики issues-al-*, разобраны 2026-10-06)
target: omixflow
external:
links: [omixflow-agent-tools-lsp]
---

**Контекст.** Риск порчи данных: project-scope MCP-серверы стартуют из каталога запуска
сессии и держат его проект, а после `EnterWorktree` агенты правят и читают уже другое дерево.

**Проблема.**
- AL-1151: `mcp-tsmorph-refactor` держит `tsconfig.json` основного дерева; rename, move,
  change_signature из worktree молча правят основной checkout на чужой ветке. Оркестратор
  запрещал инструмент вручную в каждом промпте.
- AL-1153: serena стартует с cwd основного дерева, `activate_project` в наборе сессии нет;
  агенты в worktree читают `release/2.3.0` вместо `task/AL-1153`, ложные findings.
- Правило «навигация активируется на `PROJECT_ROOT`» (`adapters/lang/PORT.md:60-61`) есть
  только у researcher (`agents/researcher.md:109-110`); `agents/coder.md:90-93` велит
  многофайловые рефакторинги через инструменты без оговорки; `adapters/lang/ts.md:54` —
  serena для всех операций без запасного пути; в «Ловушках» `protocol/worktree.md` пункта нет.
  Параметр вида `TOOLS_DISABLED` спорит с `protocol/runtime.md:83-84` («инструменты в промпте
  не перечисляются») — решить в постановке.

**Предложение.**
- `worktree.md`, «Ловушки»: project-scope MCP привязан к дереву запуска.
- Правило для агентов: инструмент навигации или рефакторинга, который нельзя активировать на
  `PROJECT_ROOT`, в worktree не используется; запасной путь — ast-grep, Grep/Read, Edit +
  typecheck (в адаптере lang). Строка об активации во всех агентах.
- `doctor`: предупреждение для проектов с `worktree` и project-scope MCP навигации.

**Критерии приёмки.** Сессия в worktree не меняет основное дерево ни одним инструментом;
агенты знают запасной путь.
