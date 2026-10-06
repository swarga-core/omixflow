---
id: omixflow-skill-text-contradictions
title: Противоречия в тексте скилов — doctor о .gitignore, spec о complete
status: draft
type: docs
created: 2026-10-06
updated: 2026-10-06
origin: ревью ветки task/kanban-tracker 2026-10-05, перепроверено на main после 0.4.0; переезд mewria на kanban
target: omixflow
external:
links: []
---

**Контекст.** Ревью ветки kanban; на `main` после 0.4.0 оба места на месте. При переезде
mewria на kanban скил doctor исполнялся по разделам 3 и 4a, вопреки собственным «Правилам».

**Проблемы.**

1. **doctor и `.gitignore`.** `skills/doctor/SKILL.md:72` — строку в `.gitignore` дописать
   Edit после согласия и попросить закоммитить; `:96` (раздел 4a) — уборка кодовой ветки
   коммитит `.gitignore`. А «Правила», `:105` — «Скил не редактирует ничего вне
   `.claude/omixflow/`. Изменение `.gitignore` … только предлагается». Шапка скила (`:8-9`)
   говорит третье: «Ничего в проекте не меняет без подтверждения, кроме файлов внутри
   `.claude/omixflow/`».
2. **spec называет синоним `complete`.** `skills/spec/SKILL.md:33, 46, 62` — «Состояние:
   `complete spec`», «`complete plan`». Изолированная worktree-сессия отклоняет `complete`
   как встроенную команду shell (поэтому скилы перешли на `state.py finish`, см. CHANGELOG
   0.3.0); линт `test_core_calls_finish_not_complete` ловит только форму `state.py complete`
   и это место пропускает.

**Предложение.**
1. «Правила» doctor привести к шапке и разделам 3 и 4a: вне `.claude/omixflow/` — только
   с согласия разработчика (строка `.gitignore`, команды из `detail` хука адаптера, уборка
   при переезде трекера), с превью.
2. В spec — `state.py finish {TASK_DIR} spec` (и `plan`); регулярное выражение линта
   расширить на `` `complete {фаза}` `` в обратных кавычках.

**Критерии приёмки.** Скил doctor не противоречит себе; в скилах нет `complete` в роли
команды; линт ловит обе формы.
