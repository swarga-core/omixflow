# Ревью-цикл

Общий протокол для фаз Spec, Plan и Review и для любого места, где артефакт или код
проверяет reviewer.

## Цикл

1. Спавн **reviewer** через Agent tool с параметром `name` (`reviewer-{id}` или
   `reviewer-{id}-{part}`), MODE: review, с ASPECTS и ARTIFACT_PATHS фазы.
2. Ответ reviewer заканчивается JSON-блоком контракта. Решения принимаются программно
   по `severity` и `category`:
   - `suggestion` любой категории: auto-accept;
   - `warning` категорий `spec`, `plan`, `code`, `tests`, `spec-sync` с понятным
     фиксом: auto-accept;
   - `warning [architecture]` и любой `critical`: эскалация разработчику по `dialog.md`
     (гибрид, пакетами до четырёх).
3. FIX выполняет **исполнитель по категории**: `spec` и `plan` идут architect'у задачи,
   `code` и `spec-sync` идут coder'у, `tests` идут tester'у (после coder). Reviewer
   в MODE fix только когда правка тривиальна и своего исполнителя у задачи нет.
   Исполнитель получает принятые findings с решениями через SendMessage, потому что
   он уже существует как continuation-агент.
4. Re-review: SendMessage тому же reviewer по имени, не новый спавн. Проверяются только
   исправленные findings по тем же id; новые дефекты, внесённые фиксами, получают
   новые id.
5. Не больше `limits.review_passes` проходов, затем эскалация с нерешёнными findings.

## Контракт findings

```json
{
  "findings": [
    {
      "id": 1,
      "severity": "critical | warning | suggestion",
      "category": "code | tests | spec-sync | spec | plan | architecture",
      "file": "path:line или artifact: name",
      "problem": "что не так",
      "recommendation": "что сделать"
    }
  ],
  "recommendation": "approve | request_changes",
  "blocking": [1]
}
```

`critical` всегда блокирует. Пустой список findings означает approve.

## Continuation-принцип

Действует для всех агентов задачи: один спавн с `name`, далее SendMessage. Coder
получает шаги 2+ и fix-пакеты сообщениями; architect получает fix-пакеты по spec
и plan; reviewer получает re-review. При обрыве агента SendMessage возобновляет его
из транскрипта; перед продолжением попросить сверить фактическое состояние файлов
(`git status`, `git diff`), потому что мутационные пробы могли остаться в дереве.

Для этого каждый спавн architect, coder, tester и reviewer обязан иметь `name`.
Спавн без имени это дефект скила.
