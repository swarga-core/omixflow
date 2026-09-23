---
port: tracker
name: youtrack
extends: omixflow:youtrack
capabilities: []
requires:
  tools: []
  bin: []
---

# Расширение адаптера youtrack для фикстуры

## create

Поля `Task Type` и `Developer` при создании мультизадачи не задавать: workflow
проекта их отклоняет.

## Overrides

- Правило «search: мультизадачи проекта» дополняется фильтром `Subsystems: Frontend`.
