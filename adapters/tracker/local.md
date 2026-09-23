---
port: tracker
name: local
capabilities: [identify, get, update_description, comment, set_status, current_user, comments, create, link, search]
requires:
  tools: []
  bin: [git]
scripts: {}
---

# Адаптер tracker: local

Задачи хранятся файлами в каталоге `tracker.dir` (по умолчанию `.tasks/backlog`),
версионируются вместе с кодом. Подходит проектам без трекера и как накопитель
хвостов, которые позже переносятся во внешний трекер.

## Формат файла

`{tracker.dir}/{id}.md`:

```markdown
---
id: combobox-live-region
title: Live region у Combobox читается дважды
status: draft            # draft | ready | in_work | in_review | done | canceled
type: bug                # bug | feature | chore | docs
created: 2026-09-23
updated: 2026-09-23
origin: AL-980, review warning 3
target: eps-omix-lib     # репозиторий, если задача не про этот
external:                # ссылка после переноса в другой трекер
links: []
---

{описание: контекст и происхождение, проблема с доказательствами, предлагаемое
решение, критерии приёмки}

<!-- omixflow:multitask:start -->   (только у мультизадачи)
...
<!-- omixflow:multitask:end -->

## Журнал
- 2026-09-23 создана из ревью AL-980
```

## identify

Id это kebab-slug: `^[a-z0-9]+(-[a-z0-9]+)*$`, совпадает с именем файла. Свободная
формулировка превращается в slug и создаёт файл при Start.

## get

Прочитать файл: фронтматтер как поля, тело как описание.

## update_description

Переписать тело файла, сохранив фронтматтер; для управляемых блоков та же дисциплина,
что у любого адаптера: заменить только фрагмент между маркерами.

## comment

Дописать строку `- {дата} {текст}` в секцию `## Журнал`, создать секцию, если её нет.

## comments

Прочитать секцию `## Журнал`.

## set_status

Поле `status` во фронтматтере, отображение из `tracker.status_map`; дефолтная карта
адаптера совпадает с перечислением выше. Обновить `updated`.

## current_user

`git config user.name`, при отсутствии `USER` из окружения.

## create

Создать файл с фронтматтером и телом из постановки. Индекс каталога
(`{tracker.dir}/README.md` с таблицей) генерируется скриптом, руками не ведётся;
скрипт появится вместе со скилом create.

## link

Добавить id в `links` обеих задач.

## search

Перебор фронтматтеров каталога по полям `status`, `type`, `target`.

## Перенос во внешний трекер

Создание задачи во внешнем адаптере из локального файла: `create` там, затем
в локальном файле `external: {id}` и `status: done` с записью в журнал. Файл
не удаляется, история происхождения сохраняется.
