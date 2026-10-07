---
port: tracker
name: kanban
capabilities: [identify, get, update_description, comment, set_status, current_user, comments, create, link, search, artifacts]
requires:
  tools: []
  bin: [git]
scripts:
  board: kanban/board.py
  artifacts: kanban/board.py
  doctor: kanban/board.py
  detect: kanban/board.py
---

# Адаптер tracker: kanban

Доска задач на отдельной ветке `tracker.branch` (по умолчанию `board`), открытой worktree
в `tracker.dir` (по умолчанию `.tasks/board`) основного дерева. Колонки — папки
`backlog/`, `working/`, `review/`, `done/`; статус задачи это колонка её карточки.
Карточка `{колонка}/{ID}-{slug}/` — досье задачи: `task.md`, `state.yaml`, `comments.md`
и артефакты пайплайна. Вид доски — сгенерированный `board.md`, точка входа — `README.md`.

Все операции выполняет скрипт `board` (`resolve.py adapter-script tracker board`):

```bash
BOARD=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" adapter-script tracker board)
python3 "$BOARD" get T-12
```

Файлы доски руками не правятся: каждая запись скрипта берёт блокировку, при
`tracker.push: true` (по умолчанию) обновляет доску с `origin`, коммитит и пушит,
а при отказе push повторяет запись. Код выхода 2 с сообщением `omixflow: …` — ошибка,
показать её разработчику как есть; код 3 — устаревшая ревизия (`update_description`).
Чтение идёт из локальной доски без сети (раздел «Свежесть»).

## Песочница

При `tracker.push: true` команды доски ходят в `origin` по ssh, а в песочнице Bash Claude Code
ssh-агент недоступен (`Permission denied (publickey)`). Записи (`create`, `describe`, `move`,
`set`, `link`, `comment`, `publish`), `checkout`, `pull` и `state.py finish` / `step done`
(они публикуют) запускать вне песочницы. В песочнице записи падают с кодом 2 и подсказкой,
публикация из `state.py` остаётся предупреждением, `checkout` читает локальную доску.

## identify

Id `^{tracker.project}-\d+$` (переопределяется `tracker.id_pattern`), например `T-12`.
Свободная формулировка сразу становится карточкой: `create` в начале скила, который её
получил (refine или start), и дальше работа идёт с выданным id. Название карточки —
короткое резюме формулировки, текст формулировки — исходная постановка.

## get

`get {ID}` → JSON: `id`, `kind` (`task` | `epic`), `title`, `type`, `column`, `owner`,
`parent`, `blocked`, `resolution`, `path`, `rev`, `state` (весь `state.yaml`),
`task_md`, `comments`. Summary — `title`, описание — `task_md`, связи — `state.links`.
`rev` запомнить для `update_description`. Эпик (`kind: epic`) пайплайном не ведётся:
он группирует дочерние задачи (`parent`).

## update_description

Записать `task.md` целиком во временный файл, затем
`describe {ID} --from {файл} --rev {rev из get}`. Код 3: карточку изменили после чтения,
перечитать `get` и повторить правку на свежем тексте. Управляемые блоки — по общей
дисциплине `PORT.md`.

Задача пишется только пока её карточка в `backlog`. После Start постановкой владеет
рабочая копия сессии: правится `task.md` в `.tasks/{id}/` и уходит в карточку
публикацией (`artifacts`). Эпик сессии не имеет и пишется в любой колонке (сводный
блок лида у родителя).

## comment

`comment {ID} --text "{текст}"`: строка `- {дата} {автор}: {текст}` в конец
`comments.md`; автор — `current_user`. Журнал пайплайна (`log.md`) — отдельный файл.

## comments

Поле `comments` из `get` (содержимое `comments.md`).

## set_status

| Статус порта | Команда |
|---|---|
| `in_work` | `move {ID} --to working` |
| `in_review` | `move {ID} --to review` |
| `done` | `move {ID} --to done` (резолюция `done`) |

Start переводит задачу в `working` без вопроса: колонка показывает, что постановкой
владеет сессия (`protocol/artifacts.md`). Отмена: `move {ID} --to done --resolution canceled`
(или `skipped`); резолюция меняется только вместе с колонкой, `set` её не принимает.
Блокировка не статус, а поле: `set {ID} blocked="{причина}"`, снять — `set {ID} blocked=null`.
`tracker.status_map` не используется: колонки фиксированы.

Другие поля — `set {ID} KEY=VALUE` (`title`, `type`, `owner`, `parent`, `external`).
Новое название в `backlog` (и у эпика) правит и заголовок `task.md`; после Start заголовок
принадлежит рабочей копии сессии, скрипт предупреждает и его не трогает.

## current_user

`git config user.name`, при отсутствии `USER` из окружения.

## create

Текст постановки во временный файл, затем
`create --title "{название}" --from {файл} [--type feature|bug|chore|docs] [--kind epic] [--parent {эпик}]`
→ id новой карточки в `backlog`. Без `--type` скрипт берёт `tracker.create_defaults.type`,
иначе `feature`. Родителем может быть только эпик.

## link

`link {ID} {другой ID}`: связь в `links` обеих карточек.

## search

`list [--column C] [--kind K] [--parent ID] [--owner U]` → JSON-список карточек с полями
`get` без текста. Поиск по тексту — Grep по `task.md` карточек в `tracker.dir`.

## artifacts

Тот же скрипт (`scripts.artifacts`); когда ядро вызывает операции, описывает
`protocol/artifacts.md`, «Хранение в задаче трекера».

| Операция | Команда |
|---|---|
| `path` | `path {ID}` → абсолютный путь карточки; меняется при переезде, не хранится |
| `publish` | `publish {ID} --from {TASK_DIR}`: файлы только добавляются и обновляются, `comments.md` не трогается, `state.yaml` склеивается (поля формальной записи с доски, остальное из рабочей копии) |
| `checkout` | `checkout {ID} --to {TASK_DIR} [--force]`: рабочая копия из карточки без `comments.md`, после него равна карточке (лишние файлы удаляются); отличающаяся копия без `--force` не перезаписывается |

Кодовые ветки артефакты не несут: нужен `artifacts.tracked: false` и в `.gitignore`
строки `/.tasks/*` и `!/.tasks/_lead/` (журнал лида остаётся на ветке лида).

## Свежесть

В начале `develop` и лида: `pull` (rebase доски на `origin`). Без связи — предупредить
и работать с локальной доской. Записи и `checkout` обновляют доску сами; `checkout` без связи
предупреждает и восстанавливает рабочую копию из локальной доски, запись без связи
отменяется (код 2). Отказ сервера при push (`! [remote rejected]`: ошибка, хук, правило ветки)
— тоже отмена записи с текстом git, без повторов: повторяется только отказ из-за чужой
записи (`! [rejected]`).

## Ссылка на задачу

`ref {ID}` → `T-12 «Название» · [доска](…/blob/board/board.md)`: путь карточки
меняется с колонкой, поэтому ссылка ведёт на `board.md` ветки доски; без GitHub-remote
вместо ссылки текст с веткой.

## Эпики

Эпик — карточка `kind: epic` (`get`), дочерние задачи несут `parent`. Пайплайном эпик
не ведётся.

- Создать эпик: `create --kind epic …`; дочернюю задачу: `create --parent {эпик} …`.
- Эпик по колонкам двигается вручную (`move`), с одним исключением: первая дочерняя
  задача, взятая в работу, переносит эпик из `backlog` в `working` тем же `move`.
- Прогресс: `epic {эпик}` → JSON `children` (id, title, column, resolution), `total`,
  `closed` (в `done`, отменённые тоже), `canceled`, `complete` (все дочерние закрыты).
  `board.md` показывает `{closed}/{total} закрыто (отменено N)`.
- Закрыть: после перевода дочерней задачи в `done` — `epic {parent}`; `complete: true`,
  а эпик не в `done` → спросить в точке `tracker.status` «Все дочерние задачи {parent}
  закрыты — закрыть эпик?». `complete` считает только заведённые задачи: если
  в постановке эпика есть `### Ещё не заведены`, рекомендовать Оставить и назвать
  незаведённое, иначе Закрыть (Recommended). Закрыть → `move {parent} --to done`.

## Перенос с local

`import --from-local [--dir .tasks/backlog]` без `--apply` — превью (`{slug} → {ID}
({колонка}, …)`), с `--apply` — одна запись доски:

- номера по `created`, папка `{ID}-{старый slug}`, в `state.yaml` метка
  `imported: local:{slug}`: повторный запуск переносит только новое;
- статусы: `draft`, `ready` → `backlog`; `done` → `done`; `canceled` → `done`
  с резолюцией `canceled`; тип, название, `external` как есть, `links` на новые номера
  (несуществующие отбрасываются и называются в превью), `## Журнал` → `comments.md`,
  `origin` и `target` строкой в `task.md`;
- артефакты закрытой задачи (`{artifacts.dir}/{slug}/`) переезжают в карточку,
  их `task.md` заменяет описание, поля пайплайна из `state.yaml` сохраняются;
- задачи `in_work`, `in_review` и незавершённые мультизадачи отменяют перенос целиком:
  их доводят на `local`; завершённая мультизадача переносится обычной карточкой,
  блок остаётся в `task.md` историей.

Хук `doctor` предупреждает, пока в `.tasks/backlog` есть неперенесённые задачи. Уборку
кодовой ветки (снять `.tasks/` с индекса, переключить конфиг) ведёт скил `doctor`.

## Мультизадача

Не поддерживается: блок мультизадачи в карточке → СТОП с объяснением, задача
делится на отдельные карточки, при необходимости под общим эпиком.

## Настройка и doctor

Конфиг: `tracker.project` (префикс номеров, латиница в верхнем регистре),
`tracker.branch`, `tracker.dir`, `tracker.push`; плюс `artifacts.tracked: false`.

- `init` открывает доску: создаёт ветку без общей истории с кодом и публикует её
  в `origin`, а в клоне, где доска уже есть на `origin`, подхватывает её. Второму
  разработчику достаточно `init`.
- Хук `doctor` (`scripts.doctor`) проверяет префикс, открытую доску, `.gitignore`,
  `status_map` и remote; каждая проблема несёт команду исправления.
- Хук `detect` (`scripts.detect`) для `doctor --init`: если в репозитории уже есть ветка
  доски, черновик конфига получает `tracker: kanban` с префиксом из карточек.
