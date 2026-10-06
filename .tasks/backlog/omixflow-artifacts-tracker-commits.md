---
id: omixflow-artifacts-tracker-commits
title: Скилы коммитят артефакты задачи и при трекере с возможностью artifacts, где .tasks/ игнорируется
status: draft
type: bug
created: 2026-10-05
updated: 2026-10-05
origin: настройка OMIXFlow в mewria 2026-10-05 (переезд на kanban)
target: omixflow
external:
links: [omixflow-kanban-tracker]
---

**Контекст.** Переезд mewria на kanban: при трекере с возможностью `artifacts` артефакты
живут в карточке, `artifacts.tracked: false`, а `.gitignore` кодовых веток содержит
`/.tasks/*` (`protocol/artifacts.md`, «Хранение в задаче трекера»; `doctor` это проверяет).
Проектное расширение `workspace/git.md` mewria пришлось явно оговорить: «`state.yaml`
и `log.md` в коммит шага не входят».

**Проблема.** Указания скилов коммитить артефакты не учитывают этот режим; условие есть
только у Start (`skills/start/SKILL.md:87`, «Коммит артефактов (`artifacts.tracked: true`)»):

- `skills/implement/SKILL.md:84` — «Файлы шага плюс `state.yaml` и `log.md` одним
  коммитом»; `:111` — «Коммит состояния»; `:132` — «log.md и state.yaml в том же коммите»;
- `skills/spec/SKILL.md:64` — «Во всех тирах коммит артефактов после фазы»;
- `skills/plan/SKILL.md:44`, `skills/research/SKILL.md:131`, `skills/review/SKILL.md`
  (§5 «Коммит и состояние»), `skills/finalize/SKILL.md` (§8 «Коммит артефактов до выхода
  из worktree»).

`git add` игнорируемого пути падает («The following paths are ignored by one of your
.gitignore files», код 1), коммит одних артефактов — «nothing to commit». Оркестратор либо
спотыкается на каждом шаге, либо добавляет `-f`, и тогда рабочая копия попадает в кодовую
ветку вопреки модели хранения. В песочнице kanban (TK-6) не всплыло; найдено чтением
скилов при настройке mewria.

**Предложение.** Одно правило в `protocol/artifacts.md` (и пункт пролога в `runtime.md`):
коммит артефактов фазы — только при `artifacts.tracked: true`; иначе след фазы уносит
публикация (`state.py finish`, `step … done`), а `git add -f` каталога артефактов запрещён.
Скилы ссылаются на правило одной фразой вместо безусловного «коммит артефактов»;
implement 2.4: «файлы шага; при `artifacts.tracked: true` ещё `state.yaml` и `log.md`».

**Критерии приёмки.**
- Ни один скил не велит коммитить `{artifacts.dir}/{id}` при `artifacts.tracked: false`.
- Запрет `git add -f` каталога артефактов записан в `artifacts.md`.
- Линт: фраза о коммите артефактов в скилах пайплайна сопровождается ссылкой на правило
  (или проверка, что безусловных формулировок нет).
