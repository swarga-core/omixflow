---
id: omixflow-agent-reply-paths
title: Агент называет в ответе путь основного дерева вместо TASK_DIR worktree
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-9 (G-43 лида swais-lead, 2026-10-11), сверено по транскрипту architect-T-9
target: omixflow
external:
links: [omixflow-worktree-isolation-recipes]
---

**Контекст.** В worktree агент получает абсолютные пути внутри него (`runtime.md`, «Спавн
агентов»: «В worktree все пути абсолютные внутри worktree»). Оркестратор читает артефакты
по своим путям (`TASK_DIR`, `REPORT_PATH`, `FINDINGS_PATH`), а не по пути из ответа.

**Проблема.** T-9, фикс ревью кода: architect-T-9 получил `TASK_DIR:
…/swarga-ai-studio/.claude/worktrees/T-9/.tasks/T-9`, все пять Edit ушли в
`…/worktrees/T-9/.tasks/T-9/spec.md`. В ответе он написал: «I've recorded all five items
(a–e) in `/Users/andreynitsenko/swarga/swarga-ai-studio/.tasks/T-9/spec.md`» — путь основного
дерева. Во втором ответе сам поправил: «the path in my last reply was wrong, though those
edits went to this same file». Вреда нет: оркестратор читает spec.md по `TASK_DIR`. Но
оркестратор или лид, поверивший пути из ответа, искал бы правку в основном дереве на чужой
ветке.

**Предложение.** Одной строкой в форматах вывода architect'а (и coder, tester, reviewer,
researcher — пути у них тоже в ответе): путь в ответе копируется из параметра спавна
(`TASK_DIR`, `REPORT_PATH`, `FINDINGS_PATH`), а не собирается заново. В `runtime.md`,
«Отчёт агента»: путь из ответа агента — не источник, оркестратор читает свой. Линт —
маркер в определениях агентов.

**Критерии приёмки.** Строка в определениях агентов и в runtime.md; ответы architect'а
называют пути внутри `TASK_DIR`.
