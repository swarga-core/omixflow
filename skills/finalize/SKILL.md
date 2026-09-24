---
name: finalize
description: Finalize phase of the OMIXFlow pipeline — records the outcome in log.md, routes gotchas, comments in the tracker, proposes a pull request via the forge adapter, moves the status, offers worktree exit; with --part integrates a multitask part (squash into the multitask branch), with --multitask closes a multitask. Use after /omixflow:review or when the user says "финализируй", "закрой задачу", "интегрируй часть".
---

# OMIXFlow finalize

Фиксация результата. Код здесь не меняется.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Маршрутизация гочей:
`${CLAUDE_PLUGIN_ROOT}/protocol/phases.md`. Worktree:
`${CLAUDE_PLUGIN_ROOT}/protocol/worktree.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Порты: tracker, forge, workspace.

## Активация

- `/omixflow:finalize {id}`; без аргумента id берётся из имени текущей ветки
  по шаблону `workspace.branch`.
- `/omixflow:finalize {id} --part {part}`: интеграция части мультизадачи.
- `/omixflow:finalize {id} --multitask`: финал мультизадачи, когда все части
  терминальны.

## Одиночная задача

Предусловие: `state.py next` даёт `finalize`.

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

## Часть мультизадачи (`--part`)

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

## Мультизадача (`--multitask`)

Предусловие: `multitask.py ready` на свежем описании даёт `all_terminal: true`.

1. log.md мультизадачи: частей N (done, skipped), суммарно коммитов, тестов,
   файлов по log.md частей.
2. `comment`: «Мультизадача завершена: {done}/{N} частей done{, {skipped} skipped}.
   Ветка `{branch}` готова.»
3. Статус с подтверждением (in_review по умолчанию).
4. PR из ветки мультизадачи в base: предложить по шагу 5 одиночного потока,
   решает разработчик.
5. `state.py complete` для мультизадачи до `done`.

## Правила

- Всё внешнее с подтверждением: комментарий, PR, статус, выход из worktree.
- Код не менять.
- PR body из артефактов, не выдумывать.
- Часть: squash в один коммит, без PR и без смены статуса задачи.
- Артефакты коммитить до сноса worktree: иначе они пропадут вместе с ним.
