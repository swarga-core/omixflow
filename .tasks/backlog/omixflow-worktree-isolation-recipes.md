---
id: omixflow-worktree-isolation-recipes
title: Фильтр изоляции worktree-сессии — конкретные рецепты для агентов, адаптеров и Finalize
status: draft
type: docs
created: 2026-10-06
updated: 2026-10-06
origin: прогоны AL-1151, AL-1154, AL-1161, AL-1162 (черновики issues-al-*, разобраны 2026-10-06)
target: omixflow
external:
links: [omixflow-worktree-mcp-root]
---

**Контекст.** Ограничение харнесса: изолированная сессия отклоняет команды, которые не может
проверить. В 0.3.0 записано общее (`protocol/worktree.md:87-93`: переменные shell, heredoc,
`python -c`, скрипт файлом), конкретики не хватает.

**Проблема.**
- Отклонялись: `python … && git add … && git commit`, `git -C` на чужой worktree,
  `comm <(git …) <(git …)`, `$W` в позиции опции (AL-1151, AL-1154); `node -e` со
  `spawn(…, {detached: true})` — «computed at runtime» (AL-1162); `perl` с переменными
  окружения, `lsof -p $P` (AL-1161).
- Расхождение: AL-1161 сообщает отказ `bash script.sh`, а `worktree.md:91-92` обещает, что
  скрипт-файл одной командой проходит — проверить.
- `adapters/workspace/git.md:75` сам содержит цепочку `git -C … add -A && … commit … || true`.
- Finalize, `delivery: integrate` из worktree-сессии: интеграция — шаг 4, `ExitWorktree` —
  шаг 7, а чужие деревья из изолированной сессии недоступны.
- В определениях агентов строки о простых командах нет.

**Предложение.** Список в «Ловушках»: git — по одной простой команде от cwd worktree
(`add` + `commit` отдельно), фоновые процессы и вычисляемые аргументы — только скрипт-файлом
с литеральными путями. Агентам — строка «в worktree команды простые, скрипты файлами».
Рецепт `git.md:75` разбить на простые вызовы. Finalize: `ExitWorktree keep` до интеграции
одиночной задачи.

**Критерии приёмки.** «Ловушки» и `git.md` с конкретикой; Finalize с выходом до интеграции;
пункт про `bash script.sh` проверен.
