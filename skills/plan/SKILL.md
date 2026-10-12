---
name: plan
description: Plan phase of the OMIXFlow pipeline — produces plan.md (ordered atomic steps with files and test checkpoints) via the architect agent and reviews it with the reviewer agent. Runs standalone only for L-tier tasks; in S and M the plan was produced with the spec. Use after /omixflow:spec or when the user says "составь план", "plan".
---

# OMIXFlow plan

Декомпозиция реализации на атомарные шаги с тест-чекпоинтами.

Протокол в `${CLAUDE_PLUGIN_ROOT}/protocol/`; секцию печатает `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" section {файл}.md «Секция»…` (подробности —
`runtime.md`, «Чтение протокола», по требованию).
Порт: lang.
Сначала: `runtime.md` «Пролог скила», «Спавн агентов»; `tiers.md` «Модели агентов по
тиру»; `review-cycle.md` «Цикл», «Контракт findings»; `artifacts.md` «Коммит артефактов».
По условию: повторное сообщение живому агенту → `review-cycle.md` «Continuation-принцип»
и `tiers.md` «Смена агента по ходу задачи» (она же — при новом спавне вместо живого
агента); обрыв агента (`failed`) → `runtime.md` «Отчёт агента» («Обрыв сбоем»); проходы
ревью исчерпаны → `review-cycle.md` «Лимит проходов»; точка решения → `dialog.md` целиком.

Агенту, которого скил продолжает SendMessage'ем, после перезапуска сессии — по id
(`runtime.md`, «Спавн агентов»).

## Активация

`/omixflow:plan {id}` или `{id}/{part}`.

## Предусловия

`task.md`, `research.md`, `spec.md`; `state.py next` даёт `plan`. Если состояние
говорит, что plan уже завершён (S и M: план создан вместе со spec), сообщить об
этом и ничего не делать. Если `plan.md` существует при `next == plan`: обзор
(число шагов) и вопрос в точке `resume`: Пропустить (Recommended) / Создать заново.

## Алгоритм

1. **Architect.** Если агент из `agents.architect` (`state.yaml`, имя может быть с суффиксом
   ротации) жив в этой сессии (`session` совпадает), SendMessage ему `MODE: plan`; иначе
   спавн с `name: architect-{id}`, `MODE: plan`, `TASK_DIR`, `ADAPTERS.lang`,
   `RULES`. Формат: Overview, Steps (файлы CREATE/MODIFY, тест-чекпоинт), Project
   Specs to Update, Verification. Порядок: types → domain → application → infra →
   UI → integration → tests.
2. **Reviewer.** Аналогично: SendMessage живому агенту из `agents.reviewer` или спавн
   с `name: reviewer-{id}`. `MODE: review`, ASPECTS: coverage (план реализует всё
   из spec), ordering
   (порядок зависимостей), granularity (шаг атомарен и верифицируем), test
   checkpoints (у каждого шага), files (пути точны, новые помечены CREATE).
   `ARTIFACT_PATHS: spec.md, plan.md`. Категории plan, architecture.
   `FINDINGS_PATH: {TASK_DIR}/review/plan-pass{N}.json`.
3. **Findings.** `suggestion` auto-accept; `warning [plan]` с понятным фиксом
   auto-accept; `warning [architecture]` и `critical` эскалация в точке `finding`.
4. **FIX и re-review** по review-cycle.md: фиксы architect'у по имени, re-review
   тому же reviewer по тем же id, не больше `limits.review_passes` (`review-cycle.md`, «Лимит проходов»).
   Живой architect и reviewer со Spec продолжают, если не сработал порог ротации (`tiers.md`).
5. **Состояние.** Строка стоимости из `cost.py phase TASK_DIR plan` (`runtime.md`,
   «Стоимость»); `state.py finish TASK_DIR plan`; `state.py set TASK_DIR
   steps_total={N}`. log.md: `## Plan ✅`, шагов, findings, проходов, стоимость. Коммит артефактов (`artifacts.md`).

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
