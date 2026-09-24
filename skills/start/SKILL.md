---
name: start
description: Starts development of a task — resolves the base branch, creates the task branch or worktree, writes task.md, state.yaml and log.md, moves the tracker status to in_work; starts a multitask (branch + multitask.md) or claims a part of it. Use when the user says "начни задачу", "start AL-822", "возьми часть". Prefer /omixflow:develop for the full pipeline.
---

# OMIXFlow start

Setup разработки: ветка или worktree, артефакты, статус в трекере. Аналитика
постановки это `refine`, здесь только запуск.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Порты: tracker, workspace.
Артефакты и состояние: `${CLAUDE_PLUGIN_ROOT}/protocol/artifacts.md`. Worktree:
`${CLAUDE_PLUGIN_ROOT}/protocol/worktree.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`.

## Активация

- `/omixflow:start {id}`: задача из трекера.
- `/omixflow:start "{описание}"`: свободная формулировка (адаптер `none` или
  slug для `local`).
- `--worktree`: изолировать задачу в worktree (при `workspace.worktree: optional`).
- `--tier=S|M|L`: тир; без флага и без `develop` пишется M.
- `--mode=pipeline`: ставит `develop`, скил не печатает «следующий шаг».
- `{id} --part {part}`: старт части мультизадачи (обычно вызывает `develop`).

## Алгоритм: одиночная задача

### 1. Источник и постановка

`identify` адаптера: id или свободная формулировка. `get`, `comments`, связи.
Если в описании есть `## Уточнённая формулировка`, использовать её; иначе
AskUserQuestion: «Сначала /omixflow:refine (Recommended) / Продолжить с исходным
описанием». Если в описании есть блок мультизадачи, это мультизадача: перейти
к разделу «Мультизадача».

### 2. База и ветвление

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" base
git branch --show-current
[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ] && echo in-worktree
```

- Уже в worktree (enter-first): не ветвиться, подтвердить «работаем в `{path}`
  на `{branch}`».
- `--worktree` или `workspace.worktree: always`: worktree от base по адаптеру
  workspace (`worktree`), вход по `path`; хук поставит зависимости.
- Иначе: текущая ветка это base → предложить `{workspace.branch}` с `{id}`;
  ветка задачи уже есть → «переключиться?»; другая ветка → спросить. Защищённые
  ветки из `workspace.protected` для коммитов запрещены.

Всегда AskUserQuestion: Создать (Recommended) / Работать в текущей / другое имя
через Other. Ветку создаёт адаптер (`branch`, идемпотентно).

**Предмет задачи в базе.** По правилу адаптера workspace проверить, что ключевой
символ или файл из постановки существует в базе; если нет, остановиться и показать:
задача могла ответвиться не от той линии.

### 3. Артефакты

`TASK_DIR = {artifacts.dir}/{id}`, уже в рабочей ветке. `task.md` по шаблону
из artifacts.md (исходная формулировка as-is, контекст, финальная формулировка,
scope, tier с обоснованием в одну строку). Затем:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" init "{TASK_DIR}" --id {id} --kind task \
  --tier {tier} [--forced] --mode {manual|pipeline} --branch {branch} --base {base} --session {session}
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" complete "{TASK_DIR}" refine
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" complete "{TASK_DIR}" start
```

`log.md`: секция `## Start ✅` с веткой, базой, статусом трекера. Коммит артефактов
(`artifacts.tracked: true`).

### 4. Трекер

AskUserQuestion «Перевести {id} в работу?» (Перевести (Recommended) / Пропустить).
`set_status in_work`. Статус недоступен: предупредить, продолжить.

### 5. Итог (mode manual)

```
Разработка {id} запущена: {TASK_DIR}, ветка {branch} от {base}, трекер: in_work.
Следующий шаг: /omixflow:research {id}
```

## Мультизадача

### Старт мультизадачи (`{id}` с блоком, без `--part`)

1. Сохранить описание в файл, `multitask.py validate`; ошибки → СТОП, предложить
   `refine --multitask`.
2. Ветка мультизадачи `{workspace.branch}` с `{id}` от base, идемпотентно,
   с подтверждением. При `multitask.push: true` запушить сразу.
3. `TASK_DIR = {artifacts.dir}/{id}`: `multitask.md` из блока
   (`multitask.py file --from {desc} --id {id} --title "{summary}"`), постановки
   частей дополнить из описания и уточнённой формулировки; `state.py init --kind
   multitask`; `log.md`. Коммит.
4. Статус трекера in_work с подтверждением; `comment`: «Мультизадача стартована:
   N частей, ветка `{branch}`, волн: K».
5. Ветки частей здесь не создаются.

### Старт части (`{id} --part {part}`)

Предусловие: ветка мультизадачи существует; текущий пользователь известен
(`current_user`).

1. Свежее описание из трекера → файл; `multitask.py ready --from {desc} --owner {me}`.
   Часть не в `ready` → СТОП с причиной (зависимости не `done`, часть занята,
   `blocked`). Активных частей у владельца не больше `multitask.parallel_per_owner`.
2. **Взять часть** одной записью: `multitask.py set --from {desc} --part {part}
   status=in-work owner={me} branch={branch}-{part}` → `update_description` с
   дисциплиной записи. `comment`: «{part} → in-work ({me}, ветка …)».
3. Worktree части от ветки мультизадачи по адаптеру workspace: явный
   `git worktree add {root}/.claude/worktrees/{id}-{part} -b {branch}-{part} {branch}`,
   идемпотентно (существующий worktree или ветка переиспользуются), вход по `path`.
   При `multitask.push: true` ветка части пушится при первом коммите.
4. `TASK_DIR = {artifacts.dir}/{id}/{part}`: `task.md` из секции части
   в `multitask.md`; `state.py init --kind part --multitask-id {id} --part {part}`
   с тиром части; `log.md`. Коммит.
5. Статус самой задачи не трогать: он уровня мультизадачи.

Резюм части (`in-work` с моим owner): worktree и артефакты уже есть, ничего не
создавать заново, войти по `path`; если worktree исчез, а ветка есть, пересоздать
из ветки.

## Ошибки

| Ситуация | Действие |
|---|---|
| Трекер недоступен | работать как со свободной формулировкой, сказать об этом |
| Задача не найдена | проверить ключ проекта, предложить поиск |
| Base не разрешается | СТОП: поправить `workspace.base`, `doctor` |
| `--part`, но ветки мультизадачи нет | СТОП: сначала старт мультизадачи |
| Задача затрагивает несколько репозиториев | СТОП: декомпозиция по одному репозиторию |
| Статус недоступен | пропустить, предупредить |

## Правила

- task.md и state.yaml обязательны: без них пайплайн не двигается.
- Исходная формулировка сохраняется as-is.
- Ветвление и статус только с подтверждением.
- Постановку здесь не анализировать: для этого `refine`.
- Одиночный путь не меняется от существования мультизадач.
