---
name: spec
description: Spec phase of the OMIXFlow pipeline — produces spec.md (intent, acceptance scenarios, contracts, decisions with rationale) via the architect agent, reviews it with the reviewer agent and resolves findings with the developer. Tier-aware: S writes a combined spec inline, M creates spec+plan in one architect call, L spec only. Use after /omixflow:research or when the user says "напиши спеку", "spec".
---

# OMIXFlow spec

Task spec: дельта, а не полное состояние. Что меняется, какие контракты затронуты,
какие решения приняты и что вне scope.

Протокол в `${CLAUDE_PLUGIN_ROOT}/protocol/`; секцию печатает `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" section {файл}.md «Секция»…` (подробности —
`runtime.md`, «Чтение протокола», по требованию).
Порт: lang.
Сначала: `runtime.md` «Пролог скила»; `artifacts.md` «Коммит артефактов».
По условию: тир M или L → `runtime.md` «Спавн агентов», `review-cycle.md` «Цикл»,
«Контракт findings», `tiers.md` «Модели агентов по тиру»; повторное сообщение живому
агенту → `review-cycle.md` «Continuation-принцип» и `tiers.md` «Смена агента по ходу
задачи» (она же — при новом спавне вместо живого агента); обрыв агента (`failed`) →
`runtime.md` «Отчёт агента» («Обрыв сбоем»); проходы ревью исчерпаны → `review-cycle.md`
«Лимит проходов»; точка решения → `dialog.md` целиком.

Агенту, которого скил продолжает SendMessage'ем, после перезапуска сессии — по id
(`runtime.md`, «Спавн агентов»).

## Активация

`/omixflow:spec {id}` или `{id}/{part}`.

## Предусловия

`task.md`; `research.md` для M и L (для S секция `## Research` в spec.md);
`state.py next` даёт `spec`. Если `spec.md` уже полный: показать резюме и спросить
в точке `resume`: Пропустить (Recommended) / Создать заново.

## Алгоритм по тирам

### S: объединённый артефакт инлайн

Оркестратор дописывает в `TASK_DIR/spec.md` секции `## Scenarios` (1–3 сценария S1…
в форме given/when/then — план тестов tester'а и ревью), `## Decisions` (только если
решение было), `## Out of Scope` (одной строкой, когда рядом есть соблазн расширить
правку) и `## Steps` (2–4 атомарных шага, заменяет plan.md) в форме, которую читает
`plan.py` — ярлыки буквально:

```markdown
### Step 1: {имя}

**Covers:** S1
**Files:**

- MODIFY: `{путь}` — {что}
  **Test checkpoint:**
- [ ] `test` зелёный
```

Секции Delta нет: контракты S не меняет (критерий тира); `## Research` (мини-карта файлов и факты `R{n}` из фазы
Research) остаётся — по ней coder находит файлы. Отдельное ревью артефакта не
проводится: его покрывает единый Review в фазе review. Порог файлов: `python3 {корень
плагина}/scripts/plan.py files --task TASK_DIR`, код 1 — точка `scope-change`
(`tiers.md`, «Порог файлов после плана»), код 2 — строки файлов не распознаны; затем
`python3 {корень плагина}/scripts/plan.py check --task TASK_DIR` — код 1 — оркестратор
правит шаги по строкам вывода сам (один круг; в S это единственная проверка плана до
кода), остаток — строкой в log.md и в ASPECTS единого Review.
Состояние: `state.py finish TASK_DIR spec`, затем `… plan`.
log.md: `## Spec ✅ (inline, combined)`, `## Plan ✅ (combined)`.

### M: architect в режиме spec+plan, один общий review

1. Спавн `architect` с `name: architect-{id}`, `MODE: spec+plan`, `TASK_DIR`,
   `ADAPTERS.lang`, `RULES`, `SPECS` (из `specs.mode` конфига; `runtime.md`, шаблон
   спавна). Создаёт spec.md и plan.md.
   Сразу после — порог: `python3 {корень плагина}/scripts/plan.py files --task TASK_DIR`;
   код 1 — шаг 4 до ревью (план, который будут резать, целиком не ревьюится). Затем
   механическая проверка плана: `python3 {корень плагина}/scripts/plan.py check --task
   TASK_DIR`; код 1 — строки вывода architect'у в `MODE: fix` как есть и повтор проверки
   (до двух кругов; ответ architect'а «not a defect: …» и остаток идут reviewer'у строкой
   в ASPECTS; в log.md «plan.py check: кругов {N}, остаток {M}»), только потом ревью.
2. Один спавн `reviewer` с `name: reviewer-{id}`, `MODE: review`, `SPECS`, ASPECTS обоих
   артефактов из `agents/reviewer.md`, «Aspects by phase», `ARTIFACT_PATHS: task.md, research.md,
   spec.md, plan.md`, категории spec, plan, architecture,
   `FINDINGS_PATH: {TASK_DIR}/review/spec-pass{N}.json`.
3. Findings и FIX-цикл по review-cycle.md; фиксы идут architect'у по адресу. Re-review —
   только сверка фиксов по id; новые findings лишь `critical` и `warning [architecture]`,
   прочие оркестратор отклоняет строкой в log.md (`review-cycle.md`, «Лимит проходов»).
4. Порог файлов плана после фиксов: `python3 {корень плагина}/scripts/plan.py files --task
   TASK_DIR`; код 1 — точка `scope-change` с вариантами из `tiers.md`, «Порог файлов после
   плана» (срез по сценариям и задачи-продолжения, тир выше, продолжить без прецедента),
   решение строкой в log.md; код 2 — строки файлов не распознаны, поправить план. Затем
   снова `plan.py check`: фикс мог добавить сценарий или файл; код 1 — architect'у, как в
   шаге 1.
5. Состояние: `state.py finish TASK_DIR spec`, затем `… plan`. log.md: обе секции с числом findings
   и проходов. Фаза plan затем пропускается.

### L: spec отдельно

1. Спавн `architect` с `name: architect-{id}`, `MODE: spec`, `SPECS` из `specs.mode`. Формат: Summary,
   Intent, Scenarios (S1…), Contracts, Dependencies, Decisions (с основанием и фактами,
   на которые решение опирается), Out of Scope (`agents/architect.md`, «Mode: spec»).
2. Спавн `reviewer` с `name: reviewer-{id}`, `MODE: review`, `SPECS`, ASPECTS спеки из
   `agents/reviewer.md`, «Aspects by phase». `ARTIFACT_PATHS: task.md, research.md, spec.md`.
   Категории spec, architecture. `FINDINGS_PATH: {TASK_DIR}/review/spec-pass{N}.json`.
3. Findings: `suggestion` auto-accept; `warning [spec]` с понятным фиксом
   auto-accept; `warning [architecture]` и `critical` эскалация в точке `finding`.
4. FIX: SendMessage architect'у по адресу из `agents.architect` с `MODE: fix` и принятыми
   findings. Re-review: SendMessage reviewer'у по адресу из `agents.reviewer` по тем же id — только сверка фиксов по id; новые findings
   лишь `critical` и `warning [architecture]`, прочие оркестратор отклоняет строкой в
   log.md. Не больше `limits.review_passes` (`review-cycle.md`, «Лимит проходов»).
   Перед каждым сообщением architect'у и reviewer'у — порог ротации (`tiers.md`, «Смена агента
   по ходу задачи»).
5. Состояние: `state.py finish TASK_DIR spec`. log.md: `## Spec ✅`, findings, проходов.

Во всех тирах перед `finish` — строка стоимости из `cost.py phase TASK_DIR spec` в секцию
`## Spec ✅` (`runtime.md`, «Стоимость»; в S и M фаза plan идёт в ту же строку), затем коммит
артефактов после фазы (`artifacts.md`). Адрес каждого агента (`runtime.md`, «Спавн агентов»:
имя, с суффиксом после ротации, или agentId) оркестратор записывает сразу после его спавна, во
всех тирах: `state.py set TASK_DIR agents.architect={адрес}` и `agents.reviewer={адрес}` — FIX
и re-review идут по ним, и после перезапуска сессии посреди ревью тоже.

## Итог (mode manual)

```
Spec завершён: {TASK_DIR}/spec.md, findings: {N} ({resolved}), проходов: {M}.
Следующий шаг: /omixflow:plan {id}   (для S и M: /omixflow:implement {id})
```

## Правила

- spec = дельта.
- Ревью обязателен в M и L; critical без решения в точке `finding` останавливает фазу.
- architect читает код сам: Source Files Map говорит что читать.
- Спавн architect и reviewer без имени роли (в `name`, когда харнесс его принимает, иначе
  в `description`) и без адреса в `agents.*` это дефект: FIX-цикл идёт по адресу.
