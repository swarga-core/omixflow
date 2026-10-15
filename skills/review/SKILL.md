---
name: review
description: Review phase of the OMIXFlow pipeline — runs the full verify gates, has the reviewer agent check the whole implementation (spec sync, code quality, type safety, tests, conventions), resolves findings with coder/tester/architect and the developer, and commits the fixes. Use after /omixflow:implement or when the user says "проверь реализацию", "review the task". For reviewing a pull request use /omixflow:pr-review.
---

# OMIXFlow review

Целостная проверка реализации задачи перед финализацией. Это внутренний гейт
качества; ревью чужого PR с публикацией это `pr-review`.

Протокол в `${CLAUDE_PLUGIN_ROOT}/protocol/`; секцию печатает `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" section {файл}.md «Секция»…` (подробности —
`runtime.md`, «Чтение протокола», по требованию).
Порты: lang, workspace.
Сначала: `runtime.md` «Пролог скила», «Спавн агентов», «Отчёт агента», «Гейты»;
`tiers.md` «Модели агентов по тиру»; `review-cycle.md` «Цикл», «Контракт findings»;
`artifacts.md` «Коммит артефактов», «log.md»; `worktree.md` «Ловушки».
По условию: повторное задание живому агенту → `review-cycle.md` «Continuation-принцип»
и `tiers.md` «Смена агента по ходу задачи» (она же — при новом спавне вместо живого
агента); обрыв агента (`failed`) → `runtime.md` «Отчёт агента» («Обрыв сбоем»); проходы
ревью исчерпаны или красный гейт после approve → `review-cycle.md` «Лимит проходов»;
любой вызов `resolve.py verify` отдал непустой `checks` или `on_demand` → `runtime.md`
«Проверки оркестратора»; `sync.py check` даёт `moved: true` → порядок синхронизации из
`skills/implement/SKILL.md`, «1a. Синхронизация с базой»; точка решения → `dialog.md` целиком.

Агенту, которого скил продолжает SendMessage'ем, после перезапуска сессии — по id
(`runtime.md`, «Спавн агентов»).

## Активация

`/omixflow:review {id}` или `{id}/{part}`.

## Предусловия

`state.py next` даёт `review` (все шаги implement сделаны). Ревью обязателен,
даже если все шаги прошли чисто.

## Алгоритм

### 0. Синхронизация с базой

`sync.py check TASK_DIR`; `moved: true` → синхронизация по возможности `sync` порта
workspace до гейтов и до ревью: ревью видит итоговое дерево, и разрешения конфликтов
входят в его предмет. Порядок — `skills/implement/SKILL.md`, «1a. Синхронизация с базой».

### 1. Полный прогон гейтов и проверок оркестратора

`python3 {корень плагина}/scripts/resolve.py verify --at review --task TASK_DIR`: полный
набор гейтов (`gates`) и проверки оркестратора (`checks`) по ветке. Долгие гейты по
`runtime.md`, «Гейты», критерии чтения по адаптеру (zero-diagnostics, rerun-compare-set),
проверки — `runtime.md`, «Проверки оркестратора». Проверка по требованию задачи
(`on_demand`), назначенная на Review, — на итоговом дереве после фиксов. Красный гейт
или проверка до ревью: вернуть coder'у
как шаг «починить гейт» (`REPORT_PATH: {TASK_DIR}/reports/review-gate-fix{K}.md`; перед его
коммитом — `--at step`, затем полный прогон заново; сообщение — как у починки гейта после
approve, шаг 5), не идти в ревью с красным. Красный гейт после approve — по
`review-cycle.md`, «Лимит проходов»; исполнитель тот же, дефект только в тестах — tester'у
(`REPORT_PATH: {TASK_DIR}/reports/review-tests-gate-fix{K}.md`).

### 2. Reviewer

Спавн с `name: reviewer-{id}-code` (часть: `reviewer-{id}-{part}-code`): ревью кода
начинает свежий reviewer, ревьюер артефактов Spec и Plan сюда не переходит
(`review-cycle.md`, шаг 4). Имя — в `agents.reviewer_code` (`state.py set`); живой агент
оттуда в той же сессии (повторный запуск review) получает SendMessage, если порог
ротации не сработал. `MODE: review`,
`ADAPTERS.lang`, `ADAPTERS.workspace`, `RULES`, `SPECS` (из `specs.mode`), `PLUGIN_ROOT`, ASPECTS:

- spec sync: код соответствует spec.md; то, что просит `specs.mode`, на месте
  (`descriptions` — проектные спецификации обновлены, `adr` — запись решения на каждую
  смену контракта, `none` — ничего сверх spec.md); правки спеки по ходу
  (`SPEC AMENDMENTS` отчётов; дифф spec.md от коммита артефактов фазы Plan до HEAD:
  `git diff {коммит «## Plan ✅»}..HEAD -- {TASK_DIR}/spec.md`; при `artifacts.tracked:
  false` — снимок шага 1 из log.md («снимок spec.md шага 1: {blob}»): `git -C {PROJECT_ROOT}
  cat-file -p {blob} > {scratchpad}/spec-before.md`, затем `git diff --no-index
  {scratchpad}/spec-before.md {TASK_DIR}/spec.md`; снимок держит ref
  `refs/omixflow/snapshots/{id}/{blob}`, `git gc` его не трогает) согласованы с кодом и не
  трогают Contracts, Intent, Out of Scope и
  выбор решений без решения в log.md;
- code quality: именование, паттерны, обработка ошибок, мёртвый код;
- type safety и запрещённые подавления из адаптера во всём диффе ветки, тесты тоже;
- tests: покрытие сценариев spec, edge cases, отсутствие test fraud, мутационная
  проверка отражена в `MUTATIONS` отчётов coder'а и tester'а (`reports/*.md`);
- сырые невидимые и неоднозначные символы в диффе (проверка байтами);
- conventions: CLAUDE.md проекта; read-only пути адаптера workspace не тронуты.

`ARTIFACT_PATHS`: spec.md, plan.md (если есть), все изменённые файлы ветки, отчёты
`reports/`.
Категории: code, tests, spec-sync, architecture.
`FINDINGS_PATH: {TASK_DIR}/review/review-pass{N}.json`: findings читаются из файла.

### 3. Findings

По review-cycle.md: `suggestion` auto-accept; `warning` категорий code, tests,
spec-sync с понятным фиксом auto-accept; `warning [architecture]` и `critical`
эскалация в точке `finding`. Low-confidence findings тоже идут в точку `finding`,
а не принимаются молча.

### 4. FIX

Исполнитель — по файлам правки каждого finding (`review-cycle.md`, шаг 3), не по
категории: правка задевает исходники → coder целиком (SendMessage живому агенту из
`agents.coder`, имя может быть с суффиксом ротации, или спавн с `name: coder-{id}` и
`SPECS` из `specs.mode`),
правка только в тестах и тестовой поддержке любой категории → tester (спавн с
`name: tester-{id}`; файл, который в этом проходе правит coder, — coder'у), spec и plan → architect
(SendMessage живому агенту из `agents.architect` или спавн с `name: architect-{id}`),
architecture → решение в точке `finding`. Один файл в проходе — один агент. Порядок
coder и tester — `review-cycle.md`, шаг 3. Coder получает `REPORT_PATH: {TASK_DIR}/reports/review-fix-pass{N}.md`, второе
задание прохода (только `specs.mode: descriptions` с правилом проекта о строках тестов) —
`{TASK_DIR}/reports/review-spec-sync-pass{N}.md`; tester —
`{TASK_DIR}/reports/review-tests-pass{N}.md`. Перед каждым заданием прохода — базовая
линия `report.py baseline --out {scratchpad}/baseline-{метка отчёта}.json --task {TASK_DIR}`:
coder, tester и coder снова делят один незакоммиченный пакет, и каждому считается только
его дельта, а правки spec.md — только с этого снимка.
Вид ответа (`failed`, `refused`, без файла) — как в implement 2.2; затем отчёт сверяет
скрипт: `python3 {корень плагина}/scripts/report.py check --role coder|tester --report
{REPORT_PATH} --root {PROJECT_ROOT} --baseline {файл}` без `--also` (у пакета фиксов
гейтов checkpoint нет); код 0 — вердикт с исходами гейтов и NOTES, код 1 — текст
вывода исполнителю как есть, код 2 — «дождись гейтов и отчитайся» (`runtime.md`, «Отчёт
агента»), код 3 — ошибка вызова, поправить. Перед
каждым пакетом — порог ротации (`tiers.md`). Re-review: SendMessage ревьюеру кода из
`agents.reviewer_code` по тем же id. Не больше `limits.review_passes` проходов
(`review-cycle.md`, «Лимит проходов»), затем эскалация нерешённых findings в точке
`finding`.

### 5. Коммит и состояние

Один коммит фиксов на проход ревью: пакет фиксов прохода N коммитится до повторного
ревью, новые findings прохода N+1 дают свой коммит; прежний коммит не переписывается.
Перед коммитом пакета — гейты и проверки оркестратора момента `step` (`resolve.py verify
--at step`), как перед коммитом шага.
Артефакты (`state.yaml`, `log.md`, `review/`, `reports/`) — в коммите своего прохода
по правилу «Коммит артефактов» (`artifacts.md`):

```
fix[({область})]: address review findings for {id} (pass {N})
```

Починка красного гейта после approve, закрытая без нового прохода, — свой коммит
`fix[({область})]: repair red gate for {id} (gate fix {K})`. Область — по правилу адаптера
workspace о сообщении коммита, как в implement 2.5. В MEW-25 шаблон без места под область
дал коммит фиксов без зоны, которую требует адаптер mewria.

Строка стоимости из `cost.py phase TASK_DIR review` (`runtime.md`, «Стоимость»), затем
`state.py finish TASK_DIR review`; log.md:

```markdown
## Review ✅
- Findings: {N} total ({C} critical, {W} warning, {S} suggestion)
- Принято: {N}, отклонено: {N}, отложено: {N}
- Проходов: {M}
{строка `- Стоимость: …` из cost.py}
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
