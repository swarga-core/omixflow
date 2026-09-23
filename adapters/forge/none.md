---
port: forge
name: none
capabilities: [current_user, pr_create]
requires:
  tools: []
  bin: [git]
scripts: {}
---

# Адаптер forge: none

Хостинга нет или PR не используются.

## current_user

`git config user.name`.

## pr_create

Ничего не создаёт: Finalize пушит ветку, если есть remote, и сообщает, что PR
нужно открыть вручную. Скил ревью PR при этом адаптере недоступен; ревью ветки
работает.
