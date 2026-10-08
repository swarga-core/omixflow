---
name: start
description: Starts development of a task — resolves the base branch, creates the task branch or worktree, writes task.md, state.yaml (with the pipeline profile) and log.md, moves the tracker status to in_work; starts a multitask (branch, multitask.md, snapshot of foreign repos for a research profile) or claims a part of it (worktree or shared part directory by profile). Use when the user says "начни задачу", "start AL-822", "возьми часть". Prefer /omixflow:develop for the full pipeline.
---

# OMIXFlow start

Setup разработки: ветка или worktree, артефакты, статус в трекере. Аналитика
постановки это `refine`, здесь только запуск.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Порты: tracker, workspace.
Артефакты и состояние: `${CLAUDE_PLUGIN_ROOT}/protocol/artifacts.md`. Worktree:
`${CLAUDE_PLUGIN_ROOT}/protocol/worktree.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Профили:
`${CLAUDE_PLUGIN_ROOT}/protocol/profiles.md`.

## Активация

- `/omixflow:start {id}`: задача из трекера.
- `/omixflow:start "{описание}"`: свободная формулировка (адаптер `none` или
  slug для `local`).
- `--worktree`: изолировать задачу в worktree (при `workspace.worktree: optional`).
- `--profile=NAME`: профиль одиночной задачи (`full` по умолчанию).
- `--tier=S|M|L`: тир; без флага и без `develop` пишется M. Профиль с
  `triage: false` тира не получает: `--tier` вместе с ним ошибка.
- `--mode=pipeline`: ставит `develop`, скил не печатает «следующий шаг».
- `{id} --part {part}`: старт части мультизадачи (обычно вызывает `develop`).
- `--lead=NAME`: сессия под лидом; состояние получает `--lead NAME --asked {K}`,
  где K последний номер вопроса к лиду до появления состояния.
- `--base=BRANCH`: база задачи вместо `resolve.py base`; под лидом это интеграционная
  ветка из `brief` (её передаёт `develop`).

## Алгоритм: одиночная задача

### 1. Источник и постановка

`identify` адаптера: id или свободная формулировка (адаптер может сразу завести по ней
задачу и вернуть её id). `get`, `comments`, связи. Эпик (родитель дочерних задач)
пайплайном не ведётся: СТОП, предложить взять дочернюю задачу.
Если в описании есть `## Уточнённая формулировка`, использовать её; иначе
спросить в точке `resume`: Сначала /omixflow:refine (Recommended) / Продолжить
с исходным описанием. Если в описании есть блок мультизадачи, это мультизадача: перейти
к разделу «Мультизадача»; адаптер, не поддерживающий её (раздел «Мультизадача»
адаптера), — СТОП с объяснением.

### 2. База и ветвление

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" base      # при --base не нужен
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

Всегда спросить в точке `workspace.branch`: Создать (Recommended) / Работать
в текущей / другое имя. Ветку создаёт адаптер (`branch`, идемпотентно).

**Предмет задачи в базе.** По правилу адаптера workspace проверить, что ключевой
символ или файл из постановки существует в базе; если нет, остановиться и спросить
в точке `deadlock`: задача могла ответвиться не от той линии.

### 3. Артефакты

`TASK_DIR = {artifacts.dir}/{id}`, уже в рабочей ветке. Трекер с возможностью
`artifacts`: сначала `checkout {id} --to TASK_DIR`, рабочая копия получает `task.md`
и формальный `state.yaml` задачи, `state.py init` дополняет его, а `finish` публикует
(`artifacts.md`, «Хранение в задаче трекера»). `task.md` по шаблону
из artifacts.md (исходная формулировка as-is, контекст, финальная формулировка,
scope, tier с обоснованием в одну строку). Затем:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" init "{TASK_DIR}" --id {id} --kind task \
  --profile {profile} [--tier {tier} [--forced]] --mode {manual|pipeline} --branch {branch} --base {base} --session {session} \
  [--lead {NAME} --asked {K}]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" finish "{TASK_DIR}" refine
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" finish "{TASK_DIR}" start
```

`--tier` не передаётся при `triage: false`. `log.md`: секция `## Start ✅` с веткой,
базой, профилем, статусом трекера. Коммит артефактов (`artifacts.md`).

### 4. Трекер

Спросить в точке `tracker.status`: «Перевести {id} в работу?» (Перевести
(Recommended) / Пропустить).
`set_status in_work`. Статус недоступен: предупредить, продолжить. Трекер
с возможностью `artifacts`: перевод без вопроса, статус показывает, что постановкой
владеет сессия. Перевод не удался: предупредить, что до перевода правка постановки
через трекер будет затёрта публикацией, и повторить перевод, когда трекер доступен.

### 5. Итог (mode manual)

```
Разработка {id} запущена: {TASK_DIR}, ветка {branch} от {base}, трекер: in_work.
Следующий шаг: /omixflow:research {id}
```

## Мультизадача

### Старт мультизадачи (`{id}` с блоком, без `--part`)

1. Сохранить описание в файл. Профиль `multitask.py meta --from {desc}` (ошибка
   маркера → СТОП); `multitask.py validate --from {desc} --repos {resolve.py repo
   --list}`; ошибки → СТОП, предложить `refine --multitask`.
2. Ветка мультизадачи `{workspace.branch}` с `{id}` от base, идемпотентно,
   с подтверждением в точке `workspace.branch`. При `multitask.push: true`
   запушить сразу.
3. `TASK_DIR = {artifacts.dir}/{id}`: `multitask.md` из блока
   (`multitask.py file --from {desc} --id {id} --title "{summary}"`), постановки
   частей дополнить из описания и уточнённой формулировки; `state.py init --kind
   multitask --profile {profile}`; `log.md`.
4. Снимок (раздел «Кросс-репо» multitask.md): для каждого имени из `meta.repos`
   `resolve.py repo {name} --json`; `sha: null` → СТОП с причиной. Запись одним
   JSON-объектом, чтобы sha остался строкой:
   `state.py set {TASK_DIR} 'repos.{name}={"ref":"{ref}","sha":"{sha}"}'`.
   Репозиторий, впервые появившийся в части после старта, снимается при старте его
   первой части.
5. `state.py finish` refine и start. Коммит; при `part_isolation: shared` пути
   явно (`state.yaml`, `multitask.md`, `log.md` мультизадачи), никогда не «все
   изменения».
6. Статус трекера in_work в точке `tracker.status`; `comment` в точке
   `tracker.comment`: «Мультизадача стартована: N частей, ветка `{branch}`, волн: K».
7. Ветки частей здесь не создаются.

### Старт части (`{id} --part {part}`)

Предусловие: ветка мультизадачи существует; текущий пользователь известен
(`current_user`).

Профиль и его свойства — `state.py get {artifacts.dir}/{id} profile --json`.

1. Свежее описание из трекера → файл; `multitask.py ready --from {desc} --owner {me}
   --parallel {лимит}`, лимит по `part_runner`: `multitask.parallel_per_owner` для
   `sequential`, `multitask.parallel_parts` для `scheduler`. Часть не в `ready` → СТОП
   с причиной (зависимости не `done`, часть занята, `blocked`); `slots: 0` → СТОП:
   лимит активных частей исчерпан.
2. **Взять часть** одной записью: `multitask.py set --from {desc} --part {part}
   status=in-work owner={me} branch={branch}-{part}` (при `part_isolation: shared`
   без `branch`, ячейка остаётся `—`) → `update_description` с дисциплиной записи.
   `comment`: «{part} → in-work ({me}, …)». Часть с `repo`, которого нет в снимке
   мультизадачи: снять его, как в шаге 4 старта мультизадачи.
3. `part_isolation: worktree`: worktree части от ветки мультизадачи по адаптеру
   workspace: явный
   `git worktree add {root}/.claude/worktrees/{id}-{part} -b {branch}-{part} {branch}`,
   идемпотентно (существующий worktree или ветка переиспользуются), вход по `path`.
   При `multitask.push: true` ветка части пушится при первом коммите.
   `part_isolation: shared`: ни ветки, ни worktree; каталог части в основном дереве
   на `task/{id}`.
4. `TASK_DIR = {artifacts.dir}/{id}/{part}`: `task.md` из секции части
   в `multitask.md`; `state.py init --kind part --multitask-id {id} --part {part}
   [--lead {NAME} --asked {K}]`
   (профиль наследуется из состояния мультизадачи, `--tier` только при
   `triage: true`); затем `state.py finish` refine и start; `log.md`. Коммит; при
   `part_isolation: shared` только пути каталога части.
5. Статус самой задачи не трогать: он уровня мультизадачи.

Резюм части (`in-work` с моим owner): артефакты уже есть, ничего не создавать
заново; при `part_isolation: worktree` войти по `path`, если worktree исчез, а ветка
есть, пересоздать из ветки.

## Ошибки

| Ситуация | Действие |
|---|---|
| Трекер недоступен | работать как со свободной формулировкой, сказать об этом |
| Задача не найдена | проверить ключ проекта, предложить поиск |
| Base не разрешается | СТОП: поправить `workspace.base`, `doctor` |
| `--part`, но ветки мультизадачи нет | СТОП: сначала старт мультизадачи |
| Задача меняет несколько репозиториев | СТОП: одна задача мутирует один репозиторий, немутирующие фазы читают `workspace.repos`; декомпозиция |
| `--tier` с профилем `triage: false` | СТОП: профиль не триажится |
| Ref репозитория из `workspace.repos` не разрешается | СТОП: поправить `ref` или fetch в том репозитории, `doctor` |
| Статус недоступен | пропустить, предупредить |

## Правила

- task.md и state.yaml обязательны: без них пайплайн не двигается.
- Исходная формулировка сохраняется as-is.
- Ветвление и статус только с подтверждением в точках `workspace.branch`
  и `tracker.status`.
- Постановку здесь не анализировать: для этого `refine`.
- Одиночный путь не меняется от существования мультизадач.
