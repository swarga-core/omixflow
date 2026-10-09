---
name: implement
description: Implement phase of the OMIXFlow pipeline — drives the coder agent step by step through plan.md (or the Steps section of an S-tier spec), spawns the tester when a step needs tests, commits after every step, keeps state.yaml and log.md current, rotates long-lived agents. Use after /omixflow:plan or when the user says "реализуй", "implement".
---

# OMIXFlow implement

Реализация по шагам. На каждом шаге coder пишет код, поддерживает SDD-инвариант,
гоняет гейты; tester добавляет тесты, если coder их не покрыл; оркестратор
коммитит и ведёт состояние.

Пролог и спавн: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Тиры и ротация
агентов: `${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`. Порты: lang, workspace.

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
{TASK_DIR}/reports/{phase}-sync-fix{K}.md`, вне `steps_total`). Конфликт, требующий
решения по дизайну: точка `deadlock`. log.md: `### Синхронизация с {base} @ {sha} ✅`
с перечнем конфликтов и гейтов.

### 2. Цикл по шагам

Для каждого шага N от текущего до последнего:

**2.1 Coder.** Отчёт шага: `REPORT_PATH: {TASK_DIR}/reports/implement-step{N}.md`.
Если `agents.coder` жив в этой сессии и порог ротации не сработал: SendMessage ему
`STEP: N` и `REPORT_PATH` (контекст сохраняется, артефакты перечитывать не нужно).
Иначе спавн по шаблону runtime.md: `name: coder-{id}` (часть: `coder-{id}-{part}`),
`STEP: N`, `TASK_DIR`, `ADAPTERS.lang`, `ADAPTERS.workspace`, `RULES`, `PLUGIN_ROOT`,
`REPORT_PATH`, `ITERATION_LIMIT`. Записать `state.py set TASK_DIR agents.coder=… session=…`.

**Ротация** по `tiers.md`, «Смена агента по ходу задачи»: порог проверяется перед
каждым шагом и пакетом фиксов, новый `coder-{id}-{k}` получает `PREVIOUS_REPORTS`
(отчёты `reports/implement-*` предшественника и log.md). При stall агента: один
SendMessage-резюм с требованием сверить `git status` и `git diff` (остатки мутационных
проб), при повторном stall новый агент.

**2.2 Отчёт coder.** Читать файл `REPORT_PATH`, не ответ. Ответ `done` без кода выхода
какого-либо гейта или без файла — не отчёт (`runtime.md`, «Отчёт агента»): сразу
сообщение coder'у «дождись гейтов и отчитайся». `STATUS: stopped` с `GATES: not run` —
остановка с причиной, разбор по таблице «Ошибки». Сверка отчёта:
- `TREE STATE` совпадает со свежим `git status --short` без путей каталога артефактов
  (отчёт, state.yaml и log.md пишутся после снимка); расхождение — вопрос coder'у до
  коммита.
- Каждый новый тест шага (по `FILES` и диффу тестовых файлов) есть в `MUTATIONS`
  строкой с исходом RED (или GREEN с усилением и повторной пробой). Пропуск или
  обобщение вместо списка — шаг возвращается coder'у.
- Дифф шага с не-ASCII строками требует `BYTES CHECK` с проверкой байтами.

Все гейты PASS → 2.3. FAIL после лимита → СТОП, спросить в точке `deadlock`: разбор
проблемы («шаг N не завершён, последняя ошибка, что пробовали»), затем Продолжить
вручную / Пропустить шаг / Остановить. NOTES с замечаниями вне scope шага копировать
в log.md, не чинить.

**2.3 Tester.** Спавн `tester` с `name: tester-{id}`, `SPEC_PATH`, `CODE_PATHS`
файлов шага, `TEST_TYPES` по конвенциям адаптера lang, `ADAPTERS.lang`, `PLUGIN_ROOT`,
`REPORT_PATH: {TASK_DIR}/reports/implement-tests-step{N}.md`, когда:
coder тесты не написал, а шаг меняет поведение; шаг это UI-компонент и адаптер
требует тестов доступности. Не нужен, когда шаг чисто типы или контракты и гейта
typecheck достаточно, или coder уже покрыл шаг тестами с мутационной проверкой.
`CODE_BUG` в отчёте tester возвращается coder'у как часть шага. Отчёт tester'а сверяется
как в 2.2: `TREE STATE`, `MUTATIONS` по каждому его новому тесту (пробы tester делает сам,
временной правкой исходника), `BYTES CHECK`; пропуск — задание возвращается tester'у.

**2.4 Коммит.** Файлы шага одним коммитом; `state.yaml`, `log.md` и отчёты шага (`reports/`) — в нём же по правилу
«Коммит артефактов» (`artifacts.md`):

```
{feat|fix|refactor|test|docs}: {описание шага}

Step {N}/{total} of {id}
```

Часть мультизадачи при `multitask.push: true`: `git push` ветки части после
первого коммита.

**2.5 Состояние.** log.md:

```markdown
### Шаг {N}: {название} ✅
- Файлы: {список}
- Гейты: {typecheck/test/lint…}
- Тесты: {M} passed
- Коммит: {short hash}
```

затем `state.py step TASK_DIR done N` (с трекером `artifacts` он публикует рабочую
копию вместе с записью шага).

### 3. Завершение

Все шаги в `steps_done`: log.md `## Implement ✅`, затем `state.py finish TASK_DIR
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
| coder сообщает конфликт spec и plan | СТОП, решение в точке `scope-change`, при необходимости вернуться в spec |
| гейт падает из-за окружения (зависимости, submodule) | выполнить `workspace.setup` по адаптеру, повторить; не считать дефектом кода |

## Правила

- Шаги строго последовательно, без параллели.
- Коммит после каждого шага; артефакты задачи — по правилу «Коммит артефактов» (`artifacts.md`).
- SDD-инвариант: project specs обновляются coder'ом вместе с кодом.
- Никаких подавлений из запрещённого списка адаптера.
- Лимиты вместо бесконечных циклов.
- В worktree агентам только абсолютные пути внутри него.
