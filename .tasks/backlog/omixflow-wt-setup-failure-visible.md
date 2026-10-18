---
id: omixflow-wt-setup-failure-visible
title: Упавший хук установки worktree (pnpm install) пайплайну не виден — Start идёт дальше без зависимостей
status: draft
type: bug
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-13 (G-76 лида swais-lead, 2026-10-18), сверено по ~/.claude/omixflow-wt-setup.log, hooks/hooks.json и scripts/wt-setup.sh
target: omixflow
external:
links: [omixflow-worktree-isolation-recipes]
---

**Контекст.** Хук плагина `PostToolUse[EnterWorktree]` (`hooks/hooks.json`) запускает
`scripts/wt-setup.sh`: submodule'ы и `workspace.setup` в новом worktree. Скрипт «Always exits 0:
a PostToolUse hook must not block» и пишет только в `~/.claude/omixflow-wt-setup.log`
(`protocol/worktree.md:19-22`). Start и develop итог хука не проверяют.

**Проблема.**
- T-13, 2026-10-17 00:11:05: `[wt-setup] run in …/worktrees/T-13: pnpm install` →
  `ERR_PNPM_UNSUPPORTED_ENGINE`, `wanted: {"node":">=24"} (current: …)` (корневой
  package.json SwAIS — `"engines": {"node": ">=24"}`), `[wt-setup] FAILED: …/worktrees/T-13`.
  T-14 в ту же минуту — `done`; почему у неё прошло, по логу не видно. По слову лида, фоновая
  сессия унаследовала Node 22 в PATH.
- Сессия T-13 узнала о сбое, только когда не нашла `node_modules`: вывод хука в контекст модели
  не попадает, лог общий для всех проектов машины.

**Предложение.**
1. `wt-setup.sh` при сбое печатает JSON хука с `hookSpecificOutput.additionalContext`
   («wt-setup FAILED in {wt}: {последние строки ошибки}; лог …») — харнесс кладёт его в контекст
   сессии сразу после `EnterWorktree`; код выхода по-прежнему 0.
2. Итог пишется и в git-каталог worktree (`{git-dir}/omixflow-wt-setup.status`: `done` | `FAILED`
   + хвост ошибки), а Start после входа читает его: `FAILED` — точка `deadlock` с причиной
   (зависимости не поставлены, гейты будут красными), повтор `workspace.setup` после исправления
   окружения разработчиком.
3. `worktree.md`, «Ловушки»: фоновая сессия берёт PATH процесса-супервизора `claude`, а не
   интерактивной оболочки (nvm и т. п.) — версия Node может не совпасть; `doctor` в проекте с
   `engines.node` сверяет `node --version`.

**Критерии приёмки.** Упавший хук останавливает Start с текстом ошибки из лога; тест на
`wt-setup.sh` с падающим `workspace.setup` (JSON с `additionalContext` и файл статуса).
