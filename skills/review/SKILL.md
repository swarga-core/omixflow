---
name: review
description: Review phase of the OMIXFlow pipeline — runs the full verify gates, has the reviewer agent check the whole implementation (spec sync, code quality, type safety, tests, conventions), resolves findings with coder/tester/architect and the developer, and commits the fixes. Use after /omixflow:implement or when the user says "проверь реализацию", "review the task". For reviewing a pull request use /omixflow:pr-review.
---

# OMIXFlow review

Целостная проверка реализации задачи перед финализацией. Это внутренний гейт
качества; ревью чужого PR с публикацией это `pr-review`.

Пролог и спавн: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Ревью-цикл
и контракт findings: `${CLAUDE_PLUGIN_ROOT}/protocol/review-cycle.md`. Порты:
lang, workspace.

## Активация

`/omixflow:review {id}` или `{id}/{part}`.

## Предусловия

`state.py next` даёт `review` (все шаги implement сделаны). Ревью обязателен,
даже если все шаги прошли чисто.

## Алгоритм

### 0. Синхронизация с базой

`sync.py check TASK_DIR`; `moved: true` → синхронизация по возможности `sync` порта
workspace до гейтов и до ревью: ревью видит итоговое дерево, и разрешения конфликтов
входят в его предмет. Порядок как в `implement`, «Синхронизация с базой».

### 1. Полный прогон гейтов

Все гейты адаптера lang: typecheck, test, lint, плюс build и e2e, если заданы
и их `when` затронут изменениями (`git diff --name-only {base}...HEAD`). Гейты
с `background: true` в фоне с чтением вывода. Критерии чтения по адаптеру
(zero-diagnostics, rerun-compare-set). Красный гейт до ревью: вернуть coder'у
как шаг «починить гейт», не идти в ревью с красным.

### 2. Reviewer

SendMessage живому `reviewer-{id}` или спавн с `name: reviewer-{id}` (часть:
`reviewer-{id}-{part}`), `MODE: review`, `ADAPTERS.lang`, `ADAPTERS.workspace`,
`RULES`, ASPECTS:

- spec sync: код соответствует spec.md, project specs обновлены;
- code quality: именование, паттерны, обработка ошибок, мёртвый код;
- type safety и запрещённые подавления из адаптера;
- tests: покрытие сценариев spec, edge cases, отсутствие test fraud, мутационная
  проверка отражена в NOTES coder'а;
- conventions: CLAUDE.md проекта; read-only пути адаптера workspace не тронуты.

`ARTIFACT_PATHS`: spec.md, plan.md (если есть), все изменённые файлы ветки.
Категории: code, tests, spec-sync, architecture.
`FINDINGS_PATH: {TASK_DIR}/review/review-pass{N}.json`: findings читаются из файла.

### 3. Findings

По review-cycle.md: `suggestion` auto-accept; `warning` категорий code, tests,
spec-sync с понятным фиксом auto-accept; `warning [architecture]` и `critical`
эскалация в точке `finding`. Low-confidence findings тоже идут в точку `finding`,
а не принимаются молча.

### 4. FIX

По исполнителю категории: code и spec-sync → coder (SendMessage `coder-{id}`
или спавн с `name: coder-{id}`), tests → tester (спавн с `name: tester-{id}`,
после coder), spec и plan → architect (SendMessage `architect-{id}` или спавн
с `name: architect-{id}`), architecture → решение в точке `finding`. Re-review:
SendMessage тому же reviewer по тем же id. Не больше `limits.review_passes` проходов (`review-cycle.md`, «Лимит проходов»),
затем эскалация нерешённых findings в точке `finding`.

### 5. Коммит и состояние

Фиксы кода одним коммитом; артефакты (`state.yaml`, `log.md`, `review/`) — в нём же
по правилу «Коммит артефактов» (`artifacts.md`):

```
fix: address review findings for {id}
```

`state.py finish TASK_DIR review`; log.md:

```markdown
## Review ✅
- Findings: {N} total ({C} critical, {W} warning, {S} suggestion)
- Принято: {N}, отклонено: {N}, отложено: {N}
- Проходов: {M}
```

Отклонённые и отложенные findings записываются с причиной строкой решения
(`artifacts.md`, «log.md»): они трассируются.

## Итог (mode manual)

```
Review завершён: findings {N}, проходов {M}, ревью approved.
Следующий шаг: /omixflow:finalize {id}
```

## Правила

- Ревью обязателен.
- Critical без решения в точке `finding` останавливает фазу.
- Reviewer в MODE fix только когда у finding'а нет своего исполнителя.
- Фиксы не расширяют scope: bonus-улучшения не принимаются.
