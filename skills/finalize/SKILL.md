---
name: finalize
description: Finalize phase of the OMIXFlow pipeline — records the outcome in log.md, routes gotchas, comments in the tracker, proposes a pull request via the forge adapter (code, or research.md with artifacts for a research profile), moves the status, offers worktree exit; with --part integrates a multitask part (squash into the multitask branch, or a path-scoped commit of the part directory for a research profile), with --multitask closes a multitask (and tears down research-worktrees). Use after /omixflow:review or when the user says "финализируй", "закрой задачу", "интегрируй часть".
---

# OMIXFlow finalize

Фиксация результата. Код здесь не меняется.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Маршрутизация гочей:
`${CLAUDE_PLUGIN_ROOT}/protocol/phases.md`. Worktree:
`${CLAUDE_PLUGIN_ROOT}/protocol/worktree.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Профили:
`${CLAUDE_PLUGIN_ROOT}/protocol/profiles.md`. Порты: tracker, forge, workspace.

## Активация

- `/omixflow:finalize {id}`; без аргумента id берётся из имени текущей ветки
  по шаблону `workspace.branch`.
- `/omixflow:finalize {id} --part {part}`: интеграция части мультизадачи.
- `/omixflow:finalize {id} --multitask`: финал мультизадачи, когда все части
  терминальны.

## Одиночная задача

Предусловие: `state.py next` даёт `finalize`. Свойство `finalize_artifact` профиля
(`state.py get TASK_DIR profile`, таблица `profiles.md`): `code` → шаги ниже;
`research` → раздел «Задача с `finalize_artifact: research`».

### 1. Статистика

`base` из состояния:

```bash
git diff --stat {base}...HEAD
git log --oneline {base}...HEAD | wc -l
```

Из log.md: шаги, тесты, обновлённые project specs, findings ревью.

### 2. log.md

```markdown
## Finalize ✅
- Файлов создано/изменено: {N}
- Коммитов: {N}
- Тестов: {M} passed
- Project specs обновлены: {список или «нет»}
- Findings ревью: {N} total, {N} resolved
```

### 3. Гочи

Перебрать log.md (NOTES coder'а, замечания вне scope, особенности окружения)
и предложить адреса по phases.md: дефект плагина → issue в репозитории плагина
(текст готовится, создание за разработчиком); особенность проекта → CLAUDE.md
проекта или проектный адаптер (правка с подтверждением); личное → память сессии.
Ничего не записывать молча.

### 4. Трекер

Гибрид: текст комментария целиком (реализация завершена; ветка, коммиты, тесты,
файлы, PR), затем AskUserQuestion: Добавить (Recommended) / Поправить / Пропустить.
`comment` адаптера.

### 5. PR

Гибрид: превью (ветки, заголовок, body из шаблона), затем AskUserQuestion:
Создать (Recommended) / Поправить / Пропустить. `pr_create` адаптера forge:
push ветки и создание PR в base из состояния. Body:

```markdown
## Summary
{финальная формулировка из task.md}

## Changes
{ключевые изменения из log.md}

## Test plan
- [ ] гейты typecheck, test, lint зелёные ({M} tests)
- [ ] {e2e / build, если применимо}

Task: {id}
```

Адаптер `none`: push при наличии remote и сообщение, что PR открывается вручную.
CLI хостинга не настроен: инструкция, не ошибка.

### 6. Статус

Если PR создан или разработчик хочет: AskUserQuestion «Статус {id}?»
(in_review (Recommended) / другой / не менять). `set_status`.

### 7. Worktree

Сессия в worktree: AskUserQuestion «Выйти?» (keep (Recommended): ветка нужна
открытому PR / remove / остаться). `remove` блокируется незакоммиченными
изменениями. Worktree, в который вошли по `path`, `ExitWorktree` не удаляет:
сказать, что снос вручную.

### 8. Состояние и итог

`state.py complete TASK_DIR finalize` (фаза становится `done`). Коммит
артефактов до выхода из worktree.

```
Задача {id} финализирована: log.md обновлён, трекер {да/нет}, PR {url/нет},
ветка {branch}, worktree {оставлен/снесён/н/д}.
```

## Задача с `finalize_artifact: research`

Кода нет, статистики diff и тестов нет.

1. log.md: `## Finalize ✅` с числом файлов в карте, вопросов (отвечено, отложено).
2. Гочи как в шаге 3.
3. Коммит research.md и артефактов задачи.
4. Трекер: комментарий с итогами исследования (гибрид, как в шаге 4).
5. PR с артефактами из ветки задачи: предложить по шагу 5 (Summary из task.md,
   ключевые findings вместо Changes, без Test plan), решает разработчик.
6. Статус и worktree как в шагах 6–7; `state.py complete TASK_DIR finalize`.

## Часть мультизадачи (`--part`)

По `part_integration` профиля мультизадачи: `integrate` → шаги ниже; `commit` →
раздел «Часть с `part_integration: commit`».

Предусловие: сессия в worktree части или ветка части доступна; implement и
review части завершены по её состоянию.

**Реконсиляция.** Ветки части уже нет, а блок говорит `in-work` или `in-review`:
интеграция прошла, блок не обновился. Найти squash-коммит в ветке мультизадачи
по сообщению `feat({id}): {part}`, довести блок до `done` с его хешем, комментарий.
Выход.

1. Финальная запись в log.md части: статистика ветки части относительно ветки
   мультизадачи.
2. Блок → `in-review` (`multitask.py set … status=in-review` на свежем описании,
   `update_description` с дисциплиной записи). Сводка текстом, AskUserQuestion:
   Интегрировать (Recommended) / Оставить in-review / Пропустить часть (skipped).
3. Интеграция по адаптеру workspace (`integrate`): закоммитить всё в worktree
   части, включая log.md и state.yaml; `ExitWorktree keep`; убедиться, что дерево
   на ветке мультизадачи, иначе временный worktree; rebase ветки части на ветку
   мультизадачи; squash; проверить, что застейджены только файлы части
   (`git diff --cached --stat`), иначе СТОП; один коммит `feat({id}): {part} —
   {title}`; push при `multitask.push`; снести worktree и ветку части. Пустая часть:
   не коммитить, статус `skipped`.
4. Блок → `done` с коротким хешем (или `skipped`). `comment`: «{part} → done.
   Squash `{sha}` → `{branch}`. Файлов: X, тестов: Y.»
5. Статус задачи и PR не трогать: это уровень мультизадачи. Вернуть управление
   `develop`.

Отказ разработчика: оставить `in-review`, worktree и ветку. Конфликт при squash:
СТОП, разрешение за разработчиком, блок остаётся `in-review`.

## Часть с `part_integration: commit`

Правила в `multitask.md`, «Часть профиля research» (явные пути, push на общей
ветке). Обычно вызывается планировщиком в шаге завершения части, пока другие
researcher'ы работают. Предусловие: research.md части существует, фаза `research`
части закрыта. Rebase и squash нет.

**Реконсиляция.** Блок говорит `in-work`, а в истории `task/{id}` есть коммит с темой,
начинающейся на `docs({id}): research {part} — `: довести блок до `done` с его хешем,
комментарий. Выход.

1. Открытые вопросы `### Open Questions for Dependents` из `## Handoff` research.md
   части: диалог (текст или AUQ по характеру вопроса), ответы записать в Handoff
   research.md части.
2. log.md части: `## Finalize ✅`; `state.py complete {PART_DIR} finalize`.
3. Коммит только каталога части: пути `.tasks/{id}/{part}/` явно, сообщение
   `docs({id}): research {part} — {title}`. Никогда не «все изменения».
4. Push при `multitask.push` по правилу общей ветки: fetch; если `origin/task/{id}`
   не предок HEAD, rebase с autostash на него; конфликт → СТОП, блок как есть.
5. После коммита, а при `multitask.push` — после успешного push: блок → `done`
   с коротким хешем коммита (после rebase, если он был), `comment`: «{part} → done. Коммит `{sha}` → `task/{id}`.» При трекере
   `none` коммит `multitask.md` по пути сразу после записи блока.

## Мультизадача (`--multitask`)

Предусловие: `multitask.py ready` на свежем описании даёт `all_terminal: true`.

1. log.md мультизадачи: частей N (done, skipped), суммарно коммитов, тестов,
   файлов по log.md частей. При `finalize_artifact: research` вместо коммитов
   и тестов число findings и отложенных вопросов сводного research.md (синтез уже
   выполнен планировщиком).
2. `comment`: «Мультизадача завершена: {done}/{N} частей done{, {skipped} skipped}.
   Ветка `{branch}` готова.»
3. Статус с подтверждением (in_review по умолчанию).
4. PR из ветки мультизадачи в base: предложить по шагу 5 одиночного потока,
   решает разработчик. При `finalize_artifact: research` PR несёт сводный
   research.md и артефакты частей.
5. При `finalize_artifact: research`: для каждого репозитория из `repos` состояния
   мультизадачи проверить research-worktree по детерминированному пути
   `{repo_path}/.claude/worktrees/research-{id}` и снести существующие
   с подтверждением в порядке адаптера workspace.
6. `state.py complete` для мультизадачи до `done`. При `part_isolation: shared`
   коммиты называют пути явно (`state.yaml`, `log.md`, `research.md` мультизадачи),
   push по правилу общей ветки.

## Правила

- Всё внешнее с подтверждением: комментарий, PR, статус, выход из worktree.
- Код не менять.
- PR body из артефактов, не выдумывать.
- Часть: при `part_integration: integrate` squash в один коммит, при `commit` коммит
  каталога части по пути; без PR и без смены статуса задачи.
- Артефакты коммитить до сноса worktree: иначе они пропадут вместе с ним.
