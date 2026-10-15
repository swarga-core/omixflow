---
name: implement
description: Implement phase of the OMIXFlow pipeline — drives the coder agent step by step through plan.md (or the Steps section of an S-tier spec), spawns the tester when a step needs tests, commits after every step, keeps state.yaml and log.md current, rotates long-lived agents. Use after /omixflow:plan or when the user says "реализуй", "implement".
---

# OMIXFlow implement

Реализация по шагам. На каждом шаге coder пишет код, поддерживает SDD-инвариант,
гоняет гейты; tester добавляет тесты, если coder их не покрыл; оркестратор
коммитит и ведёт состояние.

Протокол в `${CLAUDE_PLUGIN_ROOT}/protocol/`; секцию печатает `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" section {файл}.md «Секция»…` (подробности —
`runtime.md`, «Чтение протокола», по требованию).
Порты: lang, workspace.
Сначала: `runtime.md` «Пролог скила», «Спавн агентов», «Отчёт агента», «Гейты»;
`tiers.md` «Модели агентов по тиру»; `artifacts.md` «Коммит артефактов», «log.md»;
`worktree.md` «Ловушки».
По условию: повторное задание живому агенту → `review-cycle.md` «Continuation-принцип»
и `tiers.md` «Смена агента по ходу задачи» (она же — при новом спавне вместо живого
агента); обрыв агента (`failed`) → `runtime.md` «Отчёт агента» («Обрыв сбоем»); любой
вызов `resolve.py verify` (включая план `--paths` до первого шага) отдал непустой
`checks` или `on_demand` → `runtime.md` «Проверки оркестратора»; точка решения →
`dialog.md` целиком.

Агенту, которого скил продолжает SendMessage'ем, после перезапуска сессии — по id
(`runtime.md`, «Спавн агентов»).

**Оркестратор не редактирует файлы проекта, не выполняет замены, не пишет код,
даже «простой» и «механический».** Вся работа с файлами через coder: он несёт
SDD-флоу, гейты, формат коммитов, мутационную проверку и лимит попыток.

## Активация

- `/omixflow:implement {id}` или `{id}/{part}`.
- `--step={N}`: начать с шага N.

## Предусловия

`spec.md`; `plan.md` для M и L, секция `## Steps` в spec.md для S;
`state.py next` даёт `implement`. Источник шагов и их число записать:
`state.py set TASK_DIR steps_total={N}`.

## Алгоритм

### 1. Точка входа

`state.py get TASK_DIR`: `step` (текущий), `steps_done`, `agents.coder`,
`session`. `state.py agents TASK_DIR --session {session}` очищает агентов чужой
сессии. `--step=N` переопределяет текущий шаг с предупреждением, если шаги
после N уже были сделаны.

Лимиты: `cfg.py limits.coder_iterations`, `cfg.py limits.agent_rotation_steps`,
`cfg.py limits.agent_rotation_context`. Модель coder по таблице tiers.md (S: `models.light`).

Окна для проверок оркестратора: до первого шага `resolve.py verify --at step --paths
{все файлы шагов plan.md}` — какие проверки понадобятся на любом моменте задачи (с их `at`);
тем, кому адаптер называет ресурс разработчика, — вопрос в точке `lang.window` сейчас,
а не в момент проверки (`runtime.md`, «Проверки оркестратора»).

### 1a. Синхронизация с базой

Когда: перед первым шагом (`steps_done` пуст); между шагами, только после коммита
шага, по `advisory` лида «база сдвинулась» или по слову разработчика. Посреди шага
никогда.

`sync.py check TASK_DIR`; `moved: true` → синхронизация по возможности `sync` порта
workspace (`PORT.md`, «sync»; команды в адаптере). Конфликты разрешает coder
в `MODE: sync` с `CONFLICTS` и `REPORT_PATH: {TASK_DIR}/reports/{phase}-sync{K}.md`
(фаза скила, K — номер синхронизации; `runtime.md`, «Отчёт агента»); живой агент из
`agents.coder` получает сообщение, иначе спавн по шаблону шага. Поломки вне конфликтных файлов после
коммита слияния чинит coder отдельным коммитом (`STEP: sync-fix`, `REPORT_PATH:
{TASK_DIR}/reports/{phase}-sync-fix{K}.md`, вне `steps_total`; сообщение
`fix[({область})]: repair sync breakage for {id} (sync {K})`, область — как в 2.5).
Конфликт, требующий решения по дизайну: точка `deadlock`. Перед коммитом слияния: гейты
полного набора по ветке гоняет coder (`MODE: sync`), проверки оркестратора —
`resolve.py verify --at review --task TASK_DIR --since HEAD`, только задетые тем, что
принесла база; перед коммитом починки — `--at step` (2.4). log.md:
`### Синхронизация с {base} @ {sha} ✅` с перечнем конфликтов и гейтов.

### 2. Цикл по шагам

Для каждого шага N от текущего до последнего:

**2.1 Coder.** Отчёт шага: `REPORT_PATH: {TASK_DIR}/reports/implement-step{N}.md`.
Перед заданием — базовая линия дельты: `python3 {корень плагина}/scripts/report.py baseline
--out {scratchpad оркестратора}/baseline-implement-step{N}.json --root {PROJECT_ROOT} --task
{TASK_DIR}` (что в дереве не закоммичено до задания и снимок spec.md для сверки `SPEC
AMENDMENTS` — единственная база при `artifacts.tracked: false`; blob снимка из вывода —
строкой в log.md «снимок spec.md шага {N}: {blob}», по нему ревью кода в другой сессии
восстанавливает спеку до шага; сверка в 2.2 считает агенту только изменённое
после неё). Если `agents.coder` жив в этой сессии и порог ротации не сработал: SendMessage ему
`STEP: N` и `REPORT_PATH` (контекст сохраняется, артефакты перечитывать не нужно).
Иначе спавн по шаблону runtime.md: `name: coder-{id}` (часть: `coder-{id}-{part}`),
`STEP: N`, `TASK_DIR`, `ADAPTERS.lang`, `ADAPTERS.workspace`, `RULES`, `SPECS` (из
`specs.mode` и `specs.adr_dir` конфига), `PLUGIN_ROOT`,
`REPORT_PATH`, `ITERATION_LIMIT`. Записать `state.py set TASK_DIR agents.coder=… session=…`.

**Ротация** по `tiers.md`, «Смена агента по ходу задачи»: порог проверяется перед
каждым шагом и пакетом фиксов, новый `coder-{id}-{k}` получает `PREVIOUS_REPORTS`
(отчёты `reports/implement-*` предшественника и log.md). При stall агента: один
SendMessage-резюм с требованием сверить `git status` и `git diff` (остатки мутационных
проб), при повторном stall новый агент. `failed` — не stall (`runtime.md`, «Обрыв сбоем»).

**2.2 Отчёт coder.** Сначала вид ответа, потом сверка. Уведомление `failed` без файла —
повтор того же задания (`runtime.md`, «Обрыв сбоем»). Ответ с первой строкой `REPORT_PATH
refused by the harness` — отчёт: оркестратор проверяет, что он целый (есть `NOTES`), пишет
его в `REPORT_PATH` сам целиком, с первой строкой, со строкой в log.md (там же, «Отказ
записи»), дальше как обычный.
Ответ `done` без файла — не отчёт (`runtime.md`, «Отчёт агента»): сообщение coder'у
«дождись гейтов и отчитайся». Файл `REPORT_PATH` сверяет скрипт, оркестратор читает
вердикт, а не отчёт: `python3 {корень плагина}/scripts/report.py check --role coder
--report {REPORT_PATH} --root {PROJECT_ROOT} --baseline {файл из 2.1} [--also {гейты
checkpoint шага, если есть}]`. Код 0 — `VERDICT: ok` (дальше 2.3) или `VERDICT: stopped`:
`STATUS: stopped` с `GATES: not run` — остановка с причиной, разбор по таблице «Ошибки»;
код 1 — вернуть coder'у текст из вывода сообщением как есть, без пересказа; код 2 — отчёт
обрезан или его нет: «дождись гейтов и отчитайся»; код 3 — ошибка самого вызова (конфиг,
`--also`, базовая линия), не агента — поправить и повторить. Строки вердикта после
`VERDICT` — то, на что оркестратор реагирует вместо чтения отчёта: исходы гейтов (все
PASS → 2.3, FAIL → ниже), `not declared` — строка в log.md, NOTES — в log.md, строка
`SPEC AMENDMENTS` — в log.md «спека поправлена coder'ом на шаге {N}: …» (ревью кода читает
дифф spec.md; под лидом — `notice`), строка
`НЕ СВЕРЕНО` — сверить этот раздел руками. Что сверяет скрипт (руками — только по
`НЕ СВЕРЕНО` или если скрипт недоступен):
- `SPEC AMENDMENTS` против диффа spec.md от снимка базовой линии (2.1): правка названа;
  правка в Contracts, Intent, Out of Scope или смена выбора решения D-n (его пункт без
  части `rests on`) — не правка, а остановка: coder возвращает spec.md и останавливается,
  дальше таблица «Ошибки» (`agents/coder.md`, «The spec learns»).
- `TREE STATE` совпадает со свежим `git status --short` без путей каталога артефактов
  (отчёт, state.yaml и log.md пишутся после снимка); расхождение — вопрос coder'у до
  коммита.
- Каждый новый тест шага и каждое новое утверждение в существующем тесте (по `FILES`
  и диффу тестовых файлов) есть в `MUTATIONS` строкой с исходом RED (или GREEN
  с усилением и повторной пробой) либо с причиной, почему пробу не построить (мутант
  не компилируется, поведение вне дерева). «Схема не менялась», «поведение уже было»,
  «пробу не просили» — не причины. Пропуск, такая причина или обобщение вместо списка —
  шаг возвращается coder'у.
- Гейты, которые называет «Test checkpoint» шага (plan.md; у тира S — `## Steps`
  в spec.md), есть в `GATES` (coder берёт их `resolve.py verify --at step --also`); нет —
  шаг возвращается coder'у. Гейт `not declared` — дефект плана: строка в log.md, шаг
  дальше без него.
- Дифф шага с не-ASCII строками требует `BYTES CHECK` с проверкой байтами.
- `SCRATCH` не `clean` — в log.md строкой `- SCRATCH {метка}: {путь} {размер}`
  (`runtime.md`, «Временные файлы агента»).
- Фоновый гейт в `GATES` — с именем `gate.py` (`{метка}-{gate}`, `runtime.md`, «Гейты»);
  исход под сомнением — `gate.py poll {имя}` и чтение лога, без листинга каталога гейтов.

Все гейты PASS → 2.3. FAIL после лимита → СТОП, спросить в точке `deadlock`: разбор
проблемы («шаг N не завершён, последняя ошибка, что пробовали»), затем Продолжить
вручную / Пропустить шаг / Остановить. NOTES с замечаниями вне scope шага копировать
в log.md, не чинить.

**2.3 Tester.** Спавн `tester` с `name: tester-{id}` (часть: `tester-{id}-{part}`),
`SPEC_PATH`, `CODE_PATHS` файлов шага, `TEST_TYPES` по конвенциям адаптера lang,
`ADAPTERS.lang`, `PLUGIN_ROOT`, `CHECKPOINT_GATES` (гейты «Test checkpoint» шага
кроме `test`, которые гоняют его тесты: e2e, visual; иначе `none`),
`REPORT_PATH: {TASK_DIR}/reports/implement-tests-step{N}.md`, когда:
coder тесты не написал, а шаг меняет поведение; шаг это UI-компонент и адаптер
требует тестов доступности. Не нужен, когда шаг чисто типы или контракты и гейта
typecheck достаточно, или coder уже покрыл шаг тестами с мутационной проверкой.
Перед спавном — базовая линия `report.py baseline --out {scratchpad}/baseline-implement-tests-step{N}.json
--task {TASK_DIR}`: в дереве уже лежит незакоммиченный шаг coder'а, tester'у считается только его дельта.
`CODE_BUG` в отчёте tester (строка `CODE BUGS FOUND` вердикта) возвращается coder'у как
часть шага. Вид ответа (`failed`, `REPORT_PATH refused by the harness`, без файла) — как в 2.2. Гейты
`CHECKPOINT_GATES` tester прогоняет сам и называет в `CHECKPOINT GATES`. Отчёт tester'а
сверяет тот же скрипт с `--role tester --baseline {файл}` и `--also {CHECKPOINT_GATES}`
только если они есть (`none` не передавать): `TREE STATE`, `MUTATIONS` по каждому его
новому тесту (пробы tester делает сам, `probe.py`), `BYTES CHECK`, `BACKGROUND GATES`
с именами `gate.py`, `CHECKPOINT GATES`, `SCRATCH`; код 1 — текст вывода tester'у как есть,
коды 0/2/3 — как в 2.2.

**2.4 Проверки оркестратора.** `python3 {корень плагина}/scripts/resolve.py verify --at step`
до коммита: каждая проверка из `checks` выполняется по своему подразделу адаптера lang,
результат и след — `runtime.md`, «Проверки оркестратора». Пустой `checks` — шаг дальше.

**2.5 Коммит.** Файлы шага одним коммитом; `state.yaml`, `log.md` и отчёты шага (`reports/`) — в нём же по правилу
«Коммит артефактов» (`artifacts.md`):

```
{feat|fix|refactor|test|docs}[({область})]: {описание шага}

Step {N}/{total} of {id}
```

Область — по правилу адаптера workspace о сообщении коммита (`commit_message`,
`adapters/workspace/PORT.md`; в адаптере без раздела — его правило в прозе); правила нет —
без области. Сообщение — файлом `{scratchpad}/commit-msg-step{N}.txt` (Write) и одним
вызовом `git -C {дерево} add {файлы} && git -C {дерево} commit -F {файл}`: heredoc изолированная сессия
отклоняет, а файл в `TASK_DIR` уходит в карточку (T-11; `runtime.md`, «Формы команд в
изоляции»).

Часть мультизадачи при `multitask.push: true`: `git push` ветки части после
первого коммита.

**2.6 Состояние.** log.md:

```markdown
### Шаг {N}: {название} ✅
- Файлы: {список}
- Гейты: {typecheck/test/lint…}
- Тесты: {M} passed
- {строка следа проверки оркестратора по адаптеру — если была}
- Коммит: {short hash}
```

затем `state.py step TASK_DIR done N` (с трекером `artifacts` он публикует рабочую
копию вместе с записью шага).

### 3. Завершение

Все шаги в `steps_done`: log.md `## Implement ✅` со строкой стоимости из
`cost.py phase TASK_DIR implement` (`runtime.md`, «Стоимость»), затем `state.py finish TASK_DIR
implement`. Коммит артефактов (`artifacts.md`).

## Итог (mode manual)

```
Implement завершён: шагов {N}/{total}, коммитов {N}, тестов {M} passed.
Следующий шаг: /omixflow:review {id}
```

## Ошибки

| Ситуация | Действие |
|---|---|
| coder не уложился в лимит | СТОП, эскалация с описанием в точке `deadlock` |
| tester не уложился в лимит | СТОП, вероятно дефект кода, эскалация в точке `deadlock` |
| coder остановился на спеке: смена объёма (Intent, Out of Scope), выбора решения D-n или контракта (`## Contracts`) | СТОП, решение в точке `scope-change` (под лидом — вопрос лиду: решение D-n утверждал он или разработчик, контракт — швы соседей), при необходимости вернуться в spec; остальные правки спеки coder делает сам и называет в `SPEC AMENDMENTS` |
| coder сообщает конфликт spec и plan (план противоречит спеке, шаг не выполним по обоим) | СТОП; план против спеки — architect `MODE: fix` по плану; спека неверна — точка `scope-change` и возврат в spec |
| гейт падает из-за окружения (зависимости, submodule) | выполнить `workspace.setup` по адаптеру, повторить; не считать дефектом кода |

## Правила

- Шаги строго последовательно, без параллели.
- Коммит после каждого шага; артефакты задачи — по правилу «Коммит артефактов» (`artifacts.md`).
- SDD-инвариант: то, что просит `specs.mode` (project specs, записи решений или ничего), coder обновляет вместе с кодом.
- Никаких подавлений из запрещённого списка адаптера.
- Лимиты вместо бесконечных циклов.
- В worktree агентам только абсолютные пути внутри него.
