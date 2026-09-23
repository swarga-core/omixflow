---
port: tracker
name: youtrack
capabilities: [identify, get, update_description, comment, set_status, current_user, comments, create, link, search, tag]
requires:
  tools: [mcp__youtrack__*]
  bin: []
scripts: {}
---

# Адаптер tracker: YouTrack

Работает через MCP-сервер `youtrack`. Ключ проекта берётся из `tracker.project`.

## identify

Шаблон id по умолчанию `^[A-Z][A-Z0-9]*-\d+$`; переопределяется `tracker.id_pattern`.
Строка, не подходящая под шаблон, считается свободной формулировкой и обрабатывается
адаптером `none` внутри той же задачи: id становится kebab-slug из формулировки.

## get

`get_issue({id})`: summary, description, Type, Priority, custom fields, ссылки.
Тип `Epic` для пайплайна ничего не значит: мультизадача определяется блоком
в description, не типом.

## update_description

`update_issue({id}, description)` заменяет описание целиком, патча нет. Поэтому:
`get_issue` непосредственно перед записью, замена только нужного фрагмента
(блок между маркерами или секция уточнённой формулировки), запись всего текста,
контрольный `get_issue` после. Не восстанавливать описание по памяти.

## comment

`add_issue_comment({id}, text)`. Правки комментариев инструментом недоступны,
комментарии считаются append-only.

## comments

`get_issue_comments({id})` отдаёт не больше десяти за вызов: для истории листать
по `offset`. Для определения состояния мультизадачи комментарии не нужны, канон
в блоке.

## set_status

`update_issue({id}, customFields: {"Status": "{значение из tracker.status_map}"})`.
Если статус недоступен в workflow проекта, предупредить и пропустить.

## current_user

`get_current_user()`, поле login.

## create

`create_issue(project, summary, description, customFields)` с полями из
`tracker.create_defaults`. Обязательные поля проекта и их enum-значения смотреть через
`get_issue_fields_schema`, не угадывать. Поля, которые нельзя задавать для некоторых
типов, документируются в проектном расширении адаптера.

## link

`link_issues({id}, {other}, type)`.

## search

`search_issues(query)` с синтаксисом YouTrack. Связанные задачи: `links: {id}`.
Мультизадачи проекта: `project: {key} description: "omixflow:multitask"`.

## tag

`manage_issue_tags({id}, add|remove, "multitask")`. Требует прав на тег; при отказе
предупредить и продолжить, детект мультизадачи от тега не зависит.
