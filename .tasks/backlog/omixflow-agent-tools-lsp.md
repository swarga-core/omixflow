---
id: omixflow-agent-tools-lsp
title: Инструменты агентов зашиты на serena и ts-morph — LSP Claude Code агентам недоступен
status: draft
type: feature
created: 2026-10-05
updated: 2026-10-05
origin: настройка OMIXFlow в mewria 2026-10-05
target: omixflow
external:
links: []
---

**Контекст.** В mewria serena и ts-morph выключены намеренно; навигация по C# — LSP-плагин
Claude Code `csharp-lsp` (csharp-ls на Roslyn: определения, ссылки, символы, иерархия
вызовов; проверено в проекте). Проектный адаптер lang пришлось оговорить: «LSP доступен
только оркестратору», агентам остались ast-grep и Grep / Read.

**Проблема.**
- `agents/{architect,coder,researcher,reviewer,tester}.md:4` — `tools` перечисляет
  `mcp__serena__*` и `mcp__mcp-tsmorph-refactor__*`, инструмента LSP Claude Code там нет.
- `adapters/lang/PORT.md:55` — «Базовый набор для всех языков это LSP-навигация (serena)»:
  LSP приравнен к serena.
- Адаптер lang выдать агенту инструмент не может: список статичен в фронтматтере агента.
  Замена агента проектным (`agents:` в конфиге или `.claude/agents/{role}.md`) ради одного
  инструмента снимает с плагина ответственность за контракт вывода (`protocol/adapters.md`,
  «Агенты»).

**Предложение.**
- Добавить инструмент LSP Claude Code (`LSP`; имя сверить по документации при правке)
  в `tools` researcher, architect, coder, reviewer и tester.
- `PORT.md` порта lang, «Навигация»: базовый набор — LSP-навигация через serena или через
  LSP-инструмент Claude Code (языковой плагин); какой из них и с какими условиями (корневой
  solution, бинарь в `PATH`) — говорит адаптер, он же может запретить.
- Агенты по-прежнему не называют инструменты в теле: только «навигация по адаптеру lang».

**Критерии приёмки.**
- Агенты получают LSP-инструмент; адаптер `ts` работает как раньше (serena).
- Формулировка `PORT.md` не привязывает LSP к serena.
- В mewria оговорка «LSP только у оркестратора» снимается.
