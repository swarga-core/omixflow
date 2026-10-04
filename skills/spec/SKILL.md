---
name: spec
description: Spec phase of the OMIXFlow pipeline — produces spec.md describing the delta (what changes and why) via the architect agent, reviews it with the reviewer agent and resolves findings with the developer. Tier-aware: S writes a combined spec inline, M creates spec+plan in one architect call, L spec only. Use after /omixflow:research or when the user says "напиши спеку", "spec".
---

# OMIXFlow spec

Task spec: дельта, а не полное состояние. Что меняется, какие контракты затронуты,
какие решения приняты и что вне scope.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Ревью-цикл:
`${CLAUDE_PLUGIN_ROOT}/protocol/review-cycle.md`. Тиры:
`${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`. Порт: lang.

## Активация

`/omixflow:spec {id}` или `{id}/{part}`.

## Предусловия

`task.md`; `research.md` для M и L (для S секция `## Research` в spec.md);
`state.py next` даёт `spec`. Если `spec.md` уже полный: показать резюме и спросить
в точке `resume`: Пропустить (Recommended) / Создать заново.

## Алгоритм по тирам

### S: объединённый артефакт инлайн

Оркестратор дописывает в `TASK_DIR/spec.md` секции `## Delta` (формат Changes
как у architect: modified / new / removed contracts, decisions, out of scope)
и `## Steps` (2–4 атомарных шага с файлами CREATE/MODIFY и тест-чекпоинтами,
заменяет plan.md). Отдельное ревью артефакта не проводится: его покрывает
единый Review в фазе review. Состояние: `complete spec` и `complete plan`.
log.md: `## Spec ✅ (inline, combined)`, `## Plan ✅ (combined)`.

### M: architect в режиме spec+plan, один общий review

1. Спавн `architect` с `name: architect-{id}`, `MODE: spec+plan`, `TASK_DIR`,
   `ADAPTERS.lang`, `RULES`. Создаёт spec.md и plan.md.
2. Один спавн `reviewer` с `name: reviewer-{id}`, `MODE: review`, ASPECTS обоих
   артефактов (completeness, clarity, consistency, dependencies; coverage, ordering,
   granularity, test checkpoints, files), `ARTIFACT_PATHS: task.md, research.md,
   spec.md, plan.md`, категории spec, plan, architecture,
   `FINDINGS_PATH: {TASK_DIR}/review/spec-pass{N}.json`.
3. Findings и FIX-цикл по review-cycle.md; фиксы идут architect'у по имени.
4. Состояние: `complete spec`, `complete plan`. log.md: обе секции с числом findings
   и проходов. Фаза plan затем пропускается.

### L: spec отдельно

1. Спавн `architect` с `name: architect-{id}`, `MODE: spec`. Формат: Summary,
   Changes по слайсам, Dependencies, Decisions, Out of Scope.
2. Спавн `reviewer` с `name: reviewer-{id}`, `MODE: review`, ASPECTS:
   completeness (покрывает ли spec требования task.md), clarity (каждое изменение
   однозначно), consistency (изменения между слайсами согласованы), dependencies
   (все затронутые пакеты найдены). `ARTIFACT_PATHS: task.md, research.md, spec.md`.
   Категории spec, architecture. `FINDINGS_PATH: {TASK_DIR}/review/spec-pass{N}.json`.
3. Findings: `suggestion` auto-accept; `warning [spec]` с понятным фиксом
   auto-accept; `warning [architecture]` и `critical` эскалация в точке `finding`.
4. FIX: SendMessage `architect-{id}` с `MODE: fix` и принятыми findings. Re-review:
   SendMessage `reviewer-{id}` по тем же id. Не больше `limits.review_passes`.
5. Состояние: `complete spec`. log.md: `## Spec ✅`, findings, проходов.

Во всех тирах коммит артефактов после фазы. Имена агентов записать в состояние:
`state.py set TASK_DIR agents.architect=architect-{id} agents.reviewer=reviewer-{id}`.

## Итог (mode manual)

```
Spec завершён: {TASK_DIR}/spec.md, findings: {N} ({resolved}), проходов: {M}.
Следующий шаг: /omixflow:plan {id}   (для S и M: /omixflow:implement {id})
```

## Правила

- spec = дельта.
- Ревью обязателен в M и L; critical без решения в точке `finding` останавливает фазу.
- architect читает код сам: Source Files Map говорит что читать.
- Спавн architect и reviewer без `name` это дефект: FIX-цикл идёт по имени.
