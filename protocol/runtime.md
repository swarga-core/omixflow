# Рантайм скила

Как любой скил OMIXFlow начинает работу, где берёт конфиг, адаптеры и состояние,
как спавнит агентов. Скилы ссылаются сюда и не пересказывают.

## Пролог скила

1. **Корень плагина**: `${CLAUDE_PLUGIN_ROOT}`. Все скрипты и протокол адресуются
   от него: `"${CLAUDE_PLUGIN_ROOT}/scripts/state.py"`, `"${CLAUDE_PLUGIN_ROOT}/protocol/…"`.
   Переменная пуста (плагин подключён каталогом скилов, например симлинком
   `~/.claude/skills/omixflow`): корень это каталог на два уровня выше `SKILL.md`
   загруженного скила. В командах корень подставляется буквально, абсолютным путём:
   изолированная worktree-сессия отклоняет команды с переменными shell
   (`worktree.md`, «Ловушки»).
2. **Корень проекта**: каталог с `.claude/omixflow/flow.yaml`; в worktree это сам
   worktree. Все пути агентам передаются абсолютными от него.
3. **Конфиг**: если `flow.yaml` нет, остановиться и предложить `/omixflow:doctor --init`.
   Значения читать через `cfg.py`, не парсить YAML в голове: ключ, которого нет
   в `flow.yaml`, `cfg.py` отдаёт умолчанием схемы (`--raw` — только конфиг).
4. **Адаптеры**: для каждого порта, который нужен фазе, получить цепочку и прочитать
   файлы в порядке вывода:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve.py" adapter tracker
   ```
   Какие порты нужны какой фазе:

   | Фаза | tracker | forge | lang | workspace |
   |---|---|---|---|---|
   | create, refine | да | | | |
   | start | да | | | да |
   | research | да | | да | да |
   | spec, plan | | | да | |
   | implement, review | | | да | да |
   | finalize | да | да | | да |
   | doctor | все | все | все | все |

   В research tracker нужен в режиме планировщика (блок и комментарии), workspace
   для кросс-репо ресёрча (research-worktree, `multitask.md`).

5. **Состояние**: `.tasks/{id}/state.yaml` через `state.py`. Резюм читает `phase`
   и `completed`, не угадывает по файлам. Адаптер tracker с возможностью `artifacts`:
   рабочая копия, публикация и восстановление по `protocol/artifacts.md`, «Хранение
   в задаче трекера».
6. **Диалог**: точки решения, их режимы и маршрут вопроса по `protocol/dialog.md`.
7. **Лид**: в состоянии задачи есть `lead` или `develop` запущен с `--lead` →
   регистрация и вопросы в точках решения по `protocol/lead.md` («Регистрация»,
   «Порядок действий сессии»). После каждого `state.py finish` сессия шлёт лиду
   `notice` о пройденной фазе: после Start с веткой, базой, worktree, профилем
   и тиром, после Research с файлами Source Files Map.

## Спавн агентов

Роли: researcher, architect, coder, tester, reviewer, web-fetcher. Агент берётся
по маппингу `agents` из конфига (`resolve.py agent {role}`): плагинный по умолчанию,
проектный при замене. Правила проекта к агенту (`.claude/omixflow/agents/{role}.md`)
передаются путём в промпте.

Каждый спавн architect, coder, tester и reviewer **обязан иметь `name`**:
`{role}-{id}` для задачи, `{role}-{id}-{part}` для части. Дальше общение
с агентом идёт через SendMessage по имени (continuation, см. `review-cycle.md`).
**Researcher именуется, когда его продолжают**: каждый researcher, которого спавнит
скил `research` для задачи или части, получает имя (`researcher-{id}`,
`researcher-{id}-{part}`; синтез идёт под `researcher-{id}`) и параметр
`CONTINUABLE: yes`. Researcher скила `create`, standalone `research "{тема}"`
и web-fetcher одноразовые, имя не обязательно.

Шаблон промпта:

```
Agent tool:
  subagent_type: "{агент по маппингу}"
  name: "{role}-{id}"
  model: "{по protocol/tiers.md, если таблица задаёт}"
  prompt: |
    PROJECT_ROOT: {абсолютный путь}
    TASK_DIR: {абсолютный путь к .tasks/{id} или .tasks/{id}/{part}}
    ADAPTERS:
      lang: {пути цепочки lang, через запятую}
      workspace: {пути цепочки workspace}          # coder, reviewer
    RULES: {пути проектных правил агента или "none"}
    {параметры режима агента: MODE, STEP, ASPECTS, ARTIFACT_PATHS, FINDINGS_PATH, ...}
```

Агент читает адаптеры сам: из них он узнаёт гейты, конвенции тестов, запрещённые
подавления и инструменты навигации. В промпте инструменты не перечисляются.

Длинный отчёт агента (findings reviewer'а) пишется в файл внутри `TASK_DIR`,
а ответ агента содержит сводку и путь: длинный ответ обрезается в канале сообщений.

В worktree все пути абсолютные внутри worktree, с явным запретом читать основное
дерево (`protocol/worktree.md`).

Параметры researcher (все необязательные):

| Параметр | Значение |
|---|---|
| `MODE` | `task` (дефолт) или `synthesis`: сводный research.md мультизадачи по отчётам частей |
| `REPO` | `{name} ref={ref} sha={sha}` для части в чужом репозитории |
| `INPUTS` | абсолютные пути research.md частей-зависимостей (в синтезе всех частей) |
| `HANDOFF` | `required`, если от части зависят другие, иначе `optional` |
| `ANSWERS` | уже отвеченные блокирующие вопросы при перезапуске |
| `CONTINUABLE` | `yes` только у именованного спавна скила `research`; иначе `no` |
| `PARTS_IN_FLIGHT` | файлы незавершённых частей; только в мутирующих профилях |

Кросс-репо спавн (часть с `repo` из `workspace.repos`):

```
Agent tool:
  subagent_type: "{агент researcher домашнего проекта}"
  name: "researcher-{id}-{part}"
  model: "{models.strong}"
  prompt: |
    PROJECT_ROOT: {абсолютный корень чужого репозитория или его research-worktree; только чтение}
    TASK_DIR: {абсолютный путь к .tasks/{id}/{part} в домашнем проекте}
    ADAPTERS:
      lang: {resolve.py adapter lang --project {чужой} --fallback-project {домашний}}
    RULES: {resolve.py agent researcher --project {чужой} --fallback-project {домашний}}
    REPO: {name} ref={ref} sha={sha}
    CONTINUABLE: yes
    {INPUTS, HANDOFF, ANSWERS}
```

Агент берётся из домашнего проекта (сессия регистрирует только его агентов),
правила из чужого репозитория. Пишет агент только в `TASK_DIR`.

## Модели

`model` при спавне берётся из таблицы `protocol/tiers.md`; имена сильной
и облегчённой модели в конфиге `models.strong` и `models.light`. Пустая ячейка
таблицы означает значение из фронтматтера агента.

## Гейты

Скилы и агенты называют гейты по именам порта lang: typecheck, test, lint, build,
e2e. Команду и критерий даёт адаптер и конфиг `verify.*`; гейты с `background: true`
запускаются в фоне с чтением файла вывода. Полный набор гейтов обязателен перед
коммитом шага; гейты с `when` обязательны, когда изменения затронули перечисленные
области.

## Внешние действия

Запись в трекер, ветвление, PR, смена статуса: только через возможности адаптера
и только с подтверждением по `dialog.md`. Оркестратор не вызывает инструменты
трекера или хостинга «в обход» адаптера.

## Режим запуска

`state.yaml` хранит `mode`: `pipeline`, когда фазу ведёт `develop`, или `manual`
при standalone-запуске фазового скила. В `pipeline` фазовый скил не печатает
«следующий шаг» и не ждёт подтверждения перехода: это делает `develop`.
