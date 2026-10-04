---
name: plan
description: Plan phase of the OMIXFlow pipeline — produces plan.md (ordered atomic steps with files and test checkpoints) via the architect agent and reviews it with the reviewer agent. Runs standalone only for L-tier tasks; in S and M the plan was produced with the spec. Use after /omixflow:spec or when the user says "составь план", "plan".
---

# OMIXFlow plan

Декомпозиция реализации на атомарные шаги с тест-чекпоинтами.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Ревью-цикл:
`${CLAUDE_PLUGIN_ROOT}/protocol/review-cycle.md`. Порт: lang.

## Активация

`/omixflow:plan {id}` или `{id}/{part}`.

## Предусловия

`task.md`, `research.md`, `spec.md`; `state.py next` даёт `plan`. Если состояние
говорит, что plan уже завершён (S и M: план создан вместе со spec), сообщить об
этом и ничего не делать. Если `plan.md` существует при `next == plan`: обзор
(число шагов) и вопрос в точке `resume`: Пропустить (Recommended) / Создать заново.

## Алгоритм

1. **Architect.** Если агент `architect-{id}` жив в этой сессии (`state.yaml`
   `agents.architect`, `session` совпадает), SendMessage ему `MODE: plan`; иначе
   спавн с `name: architect-{id}`, `MODE: plan`, `TASK_DIR`, `ADAPTERS.lang`,
   `RULES`. Формат: Overview, Steps (файлы CREATE/MODIFY, тест-чекпоинт), Project
   Specs to Update, Verification. Порядок: types → domain → application → infra →
   UI → integration → tests.
2. **Reviewer.** Аналогично: SendMessage живому `reviewer-{id}` или спавн
   с `name: reviewer-{id}`. `MODE: review`, ASPECTS: coverage (план реализует всё
   из spec), ordering
   (порядок зависимостей), granularity (шаг атомарен и верифицируем), test
   checkpoints (у каждого шага), files (пути точны, новые помечены CREATE).
   `ARTIFACT_PATHS: spec.md, plan.md`. Категории plan, architecture.
   `FINDINGS_PATH: {TASK_DIR}/review/plan-pass{N}.json`.
3. **Findings.** `suggestion` auto-accept; `warning [plan]` с понятным фиксом
   auto-accept; `warning [architecture]` и `critical` эскалация в точке `finding`.
4. **FIX и re-review** по review-cycle.md: фиксы architect'у по имени, re-review
   тому же reviewer по тем же id, не больше `limits.review_passes`.
5. **Состояние.** `state.py finish TASK_DIR plan`; `state.py set TASK_DIR
   steps_total={N}`. log.md: `## Plan ✅`, шагов, findings, проходов. Коммит.

## Итог (mode manual)

```
Plan завершён: {TASK_DIR}/plan.md, шагов: {N}, findings: {N}, проходов: {M}.
Следующий шаг: /omixflow:implement {id}
```

## Калибровка

| Задача | Шагов |
|---|---|
| точечный баг | 1 |
| изменение API | 2–3 |
| малая фича | 3–4 |
| средняя фича | 4–6 |
| большая фича | 6–8 |

Больше восьми шагов: задачу стоит декомпозировать, возможно в мультизадачу.

## Правила

- Один шаг = один коммит; шаг, который нельзя закоммитить атомарно, разбивается.
- Каждый шаг верифицируем: минимум гейт typecheck в чекпоинте.
- Пути точные, из Source Files Map; CREATE для новых файлов.
- План реализует spec и ничего сверх spec: нужно больше, сначала обновить spec.
