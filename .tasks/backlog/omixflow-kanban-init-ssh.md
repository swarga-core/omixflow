---
id: omixflow-kanban-init-ssh
title: kanban — board.py init даёт два коммита «board: init»; оговорка про ssh в песочнице слишком категорична
status: draft
type: bug
created: 2026-10-10
updated: 2026-10-10
origin: лид swais-lead 2026-10-10 — подключение OMIXFlow 0.5.1 к swarga-ai-studio, находки 6, 8
target: omixflow
external:
links: [omixflow-kanban-sandbox-offline]
---

**Проблема.**
- `adapters/tracker/kanban/board.py` `init`: пустой корневой коммит (`commit-tree … -m
  "board: init"`) и коммит README с тем же сообщением — в истории доски два одинаковых.
- `adapters/tracker/kanban.md`: «в песочнице Bash Claude Code ssh-агент недоступен
  (`Permission denied (publickey)`)» — в swarga-ai-studio push в `board` из песочницы прошёл.

**Предложение.** Один коммит или разные сообщения (`board: init (root)`, `board: init README`);
в адаптере — «может быть недоступен» и проверка в doctor (пробный `git ls-remote` под
песочницей).

**Критерии приёмки.** История доски после `init` без дублей; текст адаптера не утверждает
недоступность ssh безусловно.
