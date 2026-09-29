---
port: workspace
name: git
capabilities: [resolve_base, branch, setup, integrate, worktree, submodules, protected]
requires:
  tools: []
  bin: [git]
scripts: {}
---

# Адаптер workspace: git

## resolve_base

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" base` печатает имя. Ветка
должна существовать локально или как `origin/{name}`; при отсутствии остановиться,
не ветвиться от текущего HEAD молча.

## branch

Идемпотентно:

```bash
if git show-ref --verify --quiet "refs/heads/{branch}"; then git checkout "{branch}"
else git checkout -b "{branch}" "{base}"; fi
```

Ветвление всегда с подтверждением разработчика. Если текущая ветка не base
и не ветка задачи, спросить, а не предполагать.

Перед стартом проверить, что предмет задачи есть в базе: `git grep` по ключевому
символу из постановки. Задача, предмет которой лежит в сиблинг-ветке, а не в базе,
стартует от неверной точки, и это вскрывается только на Research.

## setup

`workspace.setup` в каталоге дерева. При непустом `workspace.submodules` сначала
`git submodule update --init --recursive`; для worktree ускоряет `--reference`
на локальный клон, если он известен проекту.

## integrate

`workspace.integration: squash` (дефолт):

```bash
git -C "{part_worktree}" add -A && git -C "{part_worktree}" commit -m "chore({part}): finalize artifacts" || true
# ExitWorktree keep, затем в дереве на ветке мультизадачи:
git checkout "task/{id}"
git rebase "task/{id}" "task/{id}-{part}" && git checkout "task/{id}"
git merge --squash "task/{id}-{part}"
git diff --cached --stat        # только файлы части, иначе СТОП
git diff --cached --quiet && echo EMPTY_PART || git commit -m "feat({id}): {part} — {title}"
git worktree remove ".claude/worktrees/{id}-{part}" && git branch -D "task/{id}-{part}"
```

Если основное дерево оказалось на другой ветке, интегрировать во временном worktree
на `task/{id}`. `merge` вместо `squash` сохраняет историю части; выбор проекта.

Части с `part_integration: commit` (`protocol/profiles.md`) `integrate` не используют:
каталог части коммитится по пути (`git add -- .tasks/{id}/{part}/` и коммит этих
путей), никогда не `add -A`.

## worktree

По `protocol/worktree.md`. Создание от произвольной базы явным
`git worktree add {path} -b {branch} {base}` и вход по `path`.

### research-worktree

Worktree чужого репозитория из `workspace.repos` на sha снимка (`protocol/worktree.md`).
Все команды через `git -C "{repo_path}"`, в worktree не входить.

```bash
wt="{repo_path}/.claude/worktrees/research-{id}"
git -C "{repo_path}" worktree add --detach "$wt" "{sha}"      # с подтверждением
```

Setup:

- submodule'ы инициализируются всегда: `git -C "$wt" submodule update --init --recursive`
  (с `--reference` на локальный клон, если он известен, как в `setup`);
- `workspace.setup` чужого проекта (из его flow.yaml) выполняется в `$wt` только при
  `workspace.repos.{name}.setup: true`; без flow.yaml или без `workspace.setup`
  предупредить и пропустить.

Снос с подтверждением, порядок как у worktree с инициализированным submodule
(раздел `submodules` ниже): проверить `git -C "$wt" status --porcelain`, удалить
содержимое submodule и `{gitdir}/modules` этого worktree, затем
`git -C "{repo_path}" worktree remove --force "$wt"`. Без submodule достаточно
`git -C "{repo_path}" worktree remove "$wt"`.

## submodules

- Файлы внутри submodule с `readonly: true` не редактируются; изменения делаются
  в его репозитории и подтягиваются bump'ом указателя отдельным коммитом.
- Указатель submodule обязан быть достижим из ветки origin его репозитория; проект
  может гейтить это pre-push хуком, ревью проверяет группой F.
- В review-worktree submodule не инициализирован по умолчанию: без `setup` гейты
  падают на неразрешённых пакетах, и это выглядит как дефект PR.
- **Снос worktree с инициализированным submodule.** `git worktree remove` отказывает
  («working trees containing submodules cannot be moved or removed»), пока в gitdir
  worktree есть каталог `modules` (там живёт клон submodule этого worktree, счёт идёт
  на гигабайты) или в каталоге submodule есть `.git`. **`git submodule deinit` из
  worktree не использовать:** он снимает `submodule.{name}.url` в общем `.git/config`
  и деинициализирует submodule основного дерева (лечится `git submodule init {path}`
  в основном дереве). Порядок:

  ```bash
  wt=.claude/worktrees/{name}
  git -C "$wt" status --porcelain          # чисто, кроме самого submodule
  rm -r "$wt/{sub}"                        # содержимое submodule, ничего уникального
  rm -r "$(git -C "$wt" rev-parse --git-dir)/modules"
  git worktree remove --force "$wt"        # --force только из-за удалённого submodule
  ```

  Это касается любого worktree, где отработал `setup` хука.

## protected

В `workspace.protected` коммитить напрямую запрещено; Start отказывается создавать
артефакты на защищённой ветке и предлагает ветку задачи.
