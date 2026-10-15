---
name: plan
description: Plan phase of the OMIXFlow pipeline — produces plan.md (ordered atomic steps with design, covered scenarios and contracts, files and test checkpoints) via the architect agent, checks it against the tier's file and step thresholds and reviews it with the reviewer agent. Runs standalone only for L-tier tasks; in S and M the plan was produced with the spec. Use after /omixflow:spec or when the user says "составь план", "plan".
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
   `RULES`, `SPECS` (из `specs.mode`). Формат: Overview, Steps (Covers — сценарии, контракты и D-n шага; Design;
   файлы CREATE/MODIFY; тест-чекпоинт), Project Specs to Update, Verification. Порядок:
   types → domain → application → infra → UI → integration → tests. Сразу после —
   порог: `python3 {корень плагина}/scripts/plan.py files --task TASK_DIR`; код 1 — шаг 5
   до ревью (план, который будут резать, целиком не ревьюится). Затем механическая проверка:
   `python3 {корень плагина}/scripts/plan.py check --task TASK_DIR` (поля шагов, гейты
   чекпоинтов названы и объявлены, нет ручных проверок и read-only путей, пути в дереве,
   покрытие сценариев и контрактов, Project Specs to Update); код 1 — строки вывода
   architect'у в `MODE: fix` как есть и повтор (до двух кругов; ответ architect'а «not a
   defect: …» и остаток — reviewer'у строкой в ASPECTS; в log.md «plan.py check: кругов
   {N}, остаток {M}»), только потом ревью.
2. **Reviewer.** Аналогично: SendMessage живому агенту из `agents.reviewer` или спавн
   с `name: reviewer-{id}`. `MODE: review`, `SPECS`, ASPECTS плана из `agents/reviewer.md`,
   «Aspects by phase» — только суждение: шаг с `Covers: none` без поведения, выбор уровня
   решения без D-n — finding категории `spec` с пробой утверждения, порядок, гранулярность,
   Design против спеки, внешний ресурс отдельным шагом, швы с живыми ветками, переходные
   пометки, остаток `plan.py check`; механику скрипта (покрытие, чекпоинты, пути) не повторять.
   `ARTIFACT_PATHS: spec.md, plan.md`. Категории plan, architecture, spec.
   `FINDINGS_PATH: {TASK_DIR}/review/plan-pass{N}.json`.
3. **Findings.** `suggestion` auto-accept; `warning [plan]` и `warning [spec]` с понятным
   фиксом auto-accept (фикс `spec` — architect правит spec.md: недостающее решение или
   сценарий); `warning [architecture]` и `critical` эскалация в точке `finding`.
4. **FIX и re-review** по review-cycle.md: фиксы architect'у по имени, re-review
   тому же reviewer по тем же id (только сверка фиксов по id; новые findings лишь
   `critical` и `warning [architecture]`, прочие оркестратор отклоняет строкой в log.md),
   не больше `limits.review_passes` (`review-cycle.md`, «Лимит проходов»).
   Живой architect и reviewer со Spec продолжают, если не сработал порог ротации (`tiers.md`).
5. **Порог файлов и шагов, проверка после фиксов.** `python3 {корень плагина}/scripts/plan.py
   files --task TASK_DIR` после фиксов (и до ревью, шаг 1); код 1 — у L это больше восьми
   шагов («Калибровка»), у S и M ещё и нетестовые файлы сверх порога — точка `scope-change`
   с вариантами из `tiers.md`, «Порог файлов после плана»; решение строкой в log.md; код 2 —
   план без распознанных строк файлов: поправить план. Затем снова `plan.py check`: фикс
   мог добавить сценарий или файл; код 1 — architect'у, как в шаге 1.
6. **Состояние.** Строка стоимости из `cost.py phase TASK_DIR plan` (`runtime.md`,
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

Больше восьми шагов: задачу стоит декомпозировать, возможно в мультизадачу — точка
`scope-change`, варианты как у порога файлов (`tiers.md`, «Порог файлов после плана»).

## Правила

- Один шаг = один коммит; шаг, который нельзя закоммитить атомарно, разбивается.
- Каждый шаг верифицируем: минимум гейт typecheck в чекпоинте.
- Пути точные, из Source Files Map; CREATE для новых файлов.
- План реализует spec и ничего сверх spec: нужно больше, сначала обновить spec.
