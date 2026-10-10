---
id: omixflow-doctor-init-defaults
title: doctor --init — трекер по MCP user-scope, гейт-заглушка выглядит зелёной, комментарии шаблона теряются, .claude/worktrees/ не проверяется, действующий способ сдачи не виден
status: draft
type: bug
created: 2026-10-10
updated: 2026-10-10
origin: лид swais-lead 2026-10-10 — подключение OMIXFlow 0.5.1 к ~/swarga/swarga-ai-studio (пустой репозиторий, только docs), находки 1, 2, 7; G-10 (задача T-1)
target: omixflow
external:
links: [omixflow-cfg-schema-defaults]
---

**Контекст.** Подключение к новому репозиторию без кода через `/omixflow:doctor --init`.

**Проблема** (сверено по коду `main` 2026-10-10):
1. **Трекер по подключённому MCP.** `scripts/doctor.py`, `detect_defaults`: youtrack в
   `lib.known_mcp_servers` (сюда входят и серверы user-scope из `~/.claude.json`) → черновик
   получает `tracker: {adapter: youtrack, project: CHANGE-ME}`, хотя проект его не использует.
2. **Заглушка гейта зелёная.** Схема требует `verify.test`; `--init` пишет
   `echo 'configure verify.test'`, а `check_verify` даёт OK любой команде, найденной в PATH.
   Сказать «гейтов пока нет» нечем.
3. **Комментарии шаблона теряются.** `write_init` пишет конфиг `yaml.safe_dump` — подсказки
   `templates/flow.yaml` пропадают.
4. **`.claude/worktrees/` в `.gitignore`** doctor не проверяет (проверяет каталог артефактов
   и `_lead/`).
5. **Два способа сдачи без пояснения** (G-10 swais-lead, T-1). В `flow.yaml` Swarga AI Studio
   `workspace.delivery: pr` (строка 24) и `lead.delivery: lead` (строка 43). Под лидом
   действует второе; шаблон это объясняет (`templates/flow.yaml:46`: «как сдаётся задача без
   лида (под лидом — lead.delivery)»), но комментарий теряется по п. 3. doctor пишет только
   «сдача под лидом lead» внутри строки `lead.policy` (`doctor.py:366-369`), что действует без
   лида, не говорит; spec T-1 вынесла расхождение в Out of Scope.

**Предложение.**
- MCP user-scope не признак трекера проекта; без признаков в репозитории — вопрос
  none / local / kanban.
- Явная заглушка (`verify.test: none` или `placeholder: true`): doctor WARN «гейт-заглушка»,
  сдача по такому гейту запрещена (implement / finalize не считают его зелёным).
- `--init` собирает `flow.yaml` из шаблона с подстановками, комментарии остаются.
- doctor: WARN, если `.claude/worktrees/` не игнорируется.
- doctor: отдельная строка `delivery` (INFO): «без лида — {workspace.delivery}, под лидом —
  {lead.delivery}»; `--init` при `lead` в конфиге оставляет у `workspace.delivery`
  комментарий шаблона «действует только без лида».

**Критерии приёмки.** `--init` без признаков трекера не ставит youtrack; doctor на заглушке —
WARN, не OK; после `--init` в `flow.yaml` есть комментарии шаблона; WARN без игнора worktrees;
doctor показывает действующий способ сдачи для сессии с лидом и без.
