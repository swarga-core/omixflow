---
port: tracker
name: none
capabilities: [identify, get, update_description, comment, set_status, current_user]
requires:
  tools: []
  bin: [git]
scripts: {}
---

# Адаптер tracker: none

Пайплайн без трекера. Постановка приходит аргументом скила, состояние живёт
в `state.yaml`, журнал в `log.md`. Ничего внешнего не читается и не пишется.

## identify

Любая строка это свободная формулировка; id это kebab-slug из неё, не длиннее
пяти слов. Если каталог `.tasks/{slug}/` уже существует, это резюм той же задачи.

## get

Вернуть формулировку как description, summary как первую строку, тип и приоритет
пустыми.

## update_description

Уточнённая формулировка записывается в `task.md` секцией «Финальная формулировка».
Блок мультизадачи хранится в `multitask.md` и является единственным носителем
статусов частей.

## comment

Запись в `log.md`.

## set_status

Поле `phase` в `state.yaml` уже отражает статус; отдельного действия нет.

## current_user

`git config user.name`.
