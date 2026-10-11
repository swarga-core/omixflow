---
id: omixflow-agent-no-cd
title: Правила «команды без cd» нет в определениях агентов — coder делает cd
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-18 (G-39 лида swais-lead, 2026-10-11), сверено по reports/implement-step1.md и reports/review-fix-pass1.md задачи и по agents/*.md
target: omixflow
external:
links: [omixflow-report-labels-cd, omixflow-worktree-isolation-recipes, omixflow-kanban-board-cwd]
---

**Контекст.** `protocol/runtime.md`, пролог «Команды без `cd`»: харнесс сохраняет рабочий
каталог между вызовами Bash, `cd` уносит сессию (MEW-2: скрипт трекера после `cd` в
scratchpad упал). Пролог читает оркестратор. В `agents/coder.md`, `tester.md`, `reviewer.md`
правила нет: grep `cd` по `agents/` пуст.

**Проблема.** T-18: coder-T-18 дважды выполнил команду с `cd`:
- шаг 1 — `cd` в worktree для проверки линтера с `--write`
  (`reports/implement-step1.md:130`);
- фикс прохода 1 — `cd /tmp` для grep поверх вывода `git -C`
  (`reports/review-fix-pass1.md:31`).
Вреда нет, оба раза агент сам отметил это в NOTES. Лид говорит о «правиле промпта»: в
определении агента его нет, только в прологе оркестратора и, возможно, в брифе.

**Предложение.** В coder.md, tester.md и reviewer.md (раздел о командах или «Rules»): команды
без `cd` — каталог задаёт опция инструмента (её даёт адаптер lang: каталог пакета у пакетного
менеджера), `git -C`, абсолютные пути у линтера и grep; вывод другой команды — через `|`, не
через переход в каталог. Ядро инструменты не называет (линт `TOOL_NAMES`), примеры — в адаптере
lang. Хук на Bash (`cd ` в начале команды) — вторично, после замера, что правила мало.

**Критерии приёмки.** Правило в трёх определениях агентов, линт на маркер; в отчётах coder'а
нет `cd`.
