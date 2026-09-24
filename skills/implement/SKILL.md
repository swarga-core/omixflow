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

Лимиты: `cfg.py limits.coder_iterations`, `cfg.py limits.agent_rotation_steps`.
Модель coder по таблице tiers.md (S: `models.light`).

### 2. Цикл по шагам

Для каждого шага N от текущего до последнего:

**2.1 Coder.** Если `agents.coder` жив в этой сессии: SendMessage ему
`STEP: N` (контекст сохраняется, артефакты перечитывать не нужно). Иначе спавн
по шаблону runtime.md: `name: coder-{id}` (часть: `coder-{id}-{part}`),
`STEP: N`, `TASK_DIR`, `ADAPTERS.lang`, `ADAPTERS.workspace`, `RULES`,
`ITERATION_LIMIT`. Записать `state.py set TASK_DIR agents.coder=… session=…`.

**Ротация.** Когда один coder сделал `agent_rotation_steps` шагов, следующий шаг
начинает новый агент `coder-{id}-{k}` с самодостаточным промптом и сводкой
сделанного; смена фиксируется в log.md. При stall агента: один SendMessage-резюм
с требованием сверить `git status` и `git diff` (остатки мутационных проб), при
повторном stall новый агент.

**2.2 Отчёт coder.** Все гейты PASS → 2.3. FAIL после лимита → СТОП, гибрид:
разбор проблемы текстом («шаг N не завершён, последняя ошибка, что пробовали»),
затем AskUserQuestion: Продолжить вручную / Пропустить шаг / Остановить.
NOTES с замечаниями вне scope шага копировать в log.md, не чинить.

**2.3 Tester.** Спавн `tester` с `name: tester-{id}`, `SPEC_PATH`, `CODE_PATHS`
файлов шага, `TEST_TYPES` по конвенциям адаптера lang, `ADAPTERS.lang`, когда:
coder тесты не написал, а шаг меняет поведение; шаг это UI-компонент и адаптер
требует тестов доступности. Не нужен, когда шаг чисто типы или контракты и гейта
typecheck достаточно, или coder уже покрыл шаг тестами с мутационной проверкой.
`CODE_BUG` в отчёте tester возвращается coder'у как часть шага.

**2.4 Коммит.** Файлы шага плюс `state.yaml` и `log.md` одним коммитом:

```
{feat|fix|refactor|test|docs}: {описание шага}

Step {N}/{total} of {id}
```

Часть мультизадачи при `multitask.push: true`: `git push` ветки части после
первого коммита.

**2.5 Состояние.** `state.py step TASK_DIR done N`; log.md:

```markdown
### Шаг {N}: {название} ✅
- Файлы: {список}
- Гейты: {typecheck/test/lint…}
- Тесты: {M} passed
- Коммит: {short hash}
```

### 3. Завершение

Все шаги в `steps_done`: `state.py complete TASK_DIR implement`; log.md
`## Implement ✅`. Коммит состояния.

## Итог (mode manual)

```
Implement завершён: шагов {N}/{total}, коммитов {N}, тестов {M} passed.
Следующий шаг: /omixflow:review {id}
```

## Ошибки

| Ситуация | Действие |
|---|---|
| coder не уложился в лимит | СТОП, эскалация с описанием |
| tester не уложился в лимит | СТОП, вероятно дефект кода, эскалация |
| coder сообщает конфликт spec и plan | СТОП, решение разработчика, при необходимости вернуться в spec |
| гейт падает из-за окружения (зависимости, submodule) | выполнить `workspace.setup` по адаптеру, повторить; не считать дефектом кода |

## Правила

- Шаги строго последовательно, без параллели.
- Коммит после каждого шага; log.md и state.yaml в том же коммите.
- SDD-инвариант: project specs обновляются coder'ом вместе с кодом.
- Никаких подавлений из запрещённого списка адаптера.
- Лимиты вместо бесконечных циклов.
- В worktree агентам только абсолютные пути внутри него.
