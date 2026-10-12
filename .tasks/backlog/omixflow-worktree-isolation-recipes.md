---
id: omixflow-worktree-isolation-recipes
title: Фильтр изоляции worktree-сессии — конкретные рецепты для агентов, адаптеров и Finalize
status: draft
type: docs
created: 2026-10-06
updated: 2026-10-12
origin: прогоны AL-1151, AL-1154, AL-1161, AL-1162 (черновики issues-al-*, разобраны 2026-10-06); Swarga AI Studio T-1 и T-6 (G-8 лида swais-lead, 2026-10-10/11); mewria MEW-15 (G-53 лида mewria-lead, 2026-10-12)
target: omixflow
external:
links: [omixflow-worktree-mcp-root]
---

**Контекст.** Ограничение харнесса: изолированная сессия отклоняет команды, которые не может
проверить. В 0.3.0 записано общее (`protocol/worktree.md:89-95`: переменные shell, heredoc,
`python -c`, скрипт файлом), конкретики не хватает.

**Проблема.**
- Отклонялись: `python … && git add … && git commit`, `git -C` на чужой worktree,
  `comm <(git …) <(git …)`, `$W` в позиции опции (AL-1151, AL-1154); `node -e` со
  `spawn(…, {detached: true})` — «computed at runtime» (AL-1162); `perl` с переменными
  окружения, `lsof -p $P` (AL-1161).
- Swarga AI Studio T-1 (2026-10-10, 0.5.1, сверено по транскриптам): 23 отказа изоляции у
  оркестратора и четырёх агентов (coder-T-1 — 6, coder-T-1-2 — 8, reviewer-T-1 и
  reviewer-T-1-code — по 3, оркестратор — 3). Новые формы:
  - `PATH=…:$PATH pnpm …` и `export PATH=…:$PATH; …` — переменная в команде;
  - цикл с переменной (`for v in …; do gh api …$v…`), `R=…; sed … $R`;
  - `docker ps --format '{{.Names}}'`, `docker run --entrypoint sh …` — второе отклонено
    даже простой командой («cannot be shown not to be git»);
  - `ast-grep run -p '$A!'` в составной команде — метапеременная выглядит как переменная
    shell; одна простая команда проходит;
  - `env -u X node …`, `sed -E 's/…/'` после конвейера, `$(date +%s)` в арифметике;
  - цикл `for f in … .gitignore …` — «names git»: фильтр срабатывает на подстроку `git`
    в имени файла.
  Обходили скриптом в scratchpad: оркестратор сам вписал рецепт в промпт спавна
  («ENVIRONMENT AND CONSTRAINTS: … write a script to the scratchpad … run it with
  `zsh <path>`»). В определениях агентов и в шаблоне спавна (`runtime.md`) рецепта нет.
- Swarga AI Studio T-6 (2026-10-11, 0.6.1, G-8 swais-lead, сверено по транскриптам): 22 отказа
  у оркестратора (3) и девяти агентов, 12 из них — «computed at runtime»: переменная shell
  в позиции программы, опции или аргумента — `R=…; pnpm … $R`, `S=…; python3 $S/…`,
  `P=…; sed -n … $P/…`, `time pnpm --dir $P`, `find "$R/…"`, `python3 -c` с путём из
  переменной («runs python with a program computed at runtime»). Помогали литеральные
  абсолютные пути.
- mewria MEW-15 (2026-10-12, G-53 mewria-lead со слов сессии; сверено по транскрипту сессии):
  три отказа в изолированной сессии задачи — `W=…; cat >> $W/.tasks/MEW-15/log.md <<'EOF'`
  («names git in a form too complex to verify»: переменная в пути и heredoc) и
  `R=…/reports/implement-step3.md; sed -n '1,40p' $R; awk …` («computed at runtime»).
  Сессия обошла так: журнал и артефакты — Edit/Write, пути литерально, по одной команде.
  Рядом, уже в правилах mewria (G-50 MEW-17): `git -C {основное дерево}` из изолированной
  сессии отклоняется («redirects git to the shared checkout»).
- Swarga AI Studio T-11 (2026-10-12, дополнение swais-lead): изолированная сессия отклоняет
  `git add … && git commit -q -F - <<'EOF'` («too complex to verify»). Сообщение коммита
  сессия клала файлом в `TASK_DIR` (`.tasks/T-11/commit-msg.txt`), а `TASK_DIR`
  публикуется в карточку трекера — файл приходилось удалять перед публикацией. Нужное место —
  scratchpad оркестратора: `git -C {дерево} commit -F {scratchpad}/commit-msg.txt` одной
  командой, `git add` отдельно.
- Харнесс в отказе сам говорит, как надо: «Split it into plain, separate commands and run
  them from {worktree}» / «Run the plain command from {worktree}».
- Расхождение AL-1161 (отказ `bash script.sh`) снято: в T-1 `bash {scratchpad}/f6_check.sh`
  и `zsh {scratchpad}/m.zsh` прошли — скрипт-файл одной командой не отклоняется.
- `adapters/workspace/git.md:75` сам содержит цепочку `git -C … add -A && … commit … || true`.
- Finalize, `delivery: integrate` из worktree-сессии: интеграция — шаг 4, `ExitWorktree` —
  шаг 7, а чужие деревья из изолированной сессии недоступны.
- Рядом, не изоляция: `rm -rf` отклоняется deny-правилом пользователя (T-1: coder-T-1,
  coder-T-1-2, reviewer-T-1); coder нашёл замену — `mv` каталога в scratchpad.

**Предложение.**
- Файл сообщения коммита (многострочного) оркестратор кладёт в свой scratchpad, не
  в `TASK_DIR` (T-11): `implement` 2.5, review и `artifacts.md` — одной строкой.
- Оркестратор в изолированной сессии дописывает log.md и артефакты инструментами Edit
  и Write, а не heredoc'ом в shell (MEW-15); скрипты OMIXFlow (`state.py`, `lead.py`)
  пишут свои файлы сами.
- Список в «Ловушках» `worktree.md` с формами выше: git — по одной простой команде
  с абсолютными путями (`git -C {worktree}`, `add` и `commit` отдельно), без `$VAR`, без
  `PATH=…:$PATH` в команде; фоновые процессы, вычисляемые аргументы и длинные цепочки — скрипт
  файлом в scratchpad (инструментом Write) и одна команда `zsh {путь}`.
- Строка рецепта в шаблон спавна `runtime.md` для сессий в worktree (условная, как строка
  «В worktree все пути абсолютные») — вместо импровизации оркестратора; линт проверяет её
  наличие в шаблоне.
- Рецепт `git.md:75` разбить на простые вызовы.
- Finalize: `ExitWorktree keep` до интеграции одиночной задачи.

**Критерии приёмки.** «Ловушки» и `git.md` с конкретикой; рецепт в шаблоне спавна для
worktree; Finalize с выходом до интеграции; в прогоне под worktree нет отказов изоляции на
типовых командах (гейты, git-статус, пробы).
