# OMIXFlow

Плагин Claude Code с пайплайном spec-driven разработки. Задача проходит фазы своего
профиля в одном глобальном порядке: профиль `full` (по умолчанию) это Refine, Start,
Research, Spec, Plan, Implement, Review, Finalize; немутирующий `research` это Refine,
Start, Research, Finalize, код он не меняет. Профили и их свойства:
[protocol/profiles.md](protocol/profiles.md). Каждую фазу ведут специализированные
агенты, а всё, что зависит от проекта (трекер задач, хостинг кода, язык, устройство
репозитория), вынесено в адаптеры и конфиг проекта.

Обкатан на семействе проектов omix (`eps-omix-lib`, `eps-eal-omix`), отсюда имя.
Проектируется как общий инструмент: разные языки, разные трекеры, несколько
разработчиков.

## Термины

Единый словарь в [protocol/glossary.md](protocol/glossary.md). Два термина,
без которых не читается остальное:

- **мультизадача** (multitask): задача, части которой выполняются как самостоятельные
  задачи, каждая с пайплайном профиля мультизадачи и своими артефактами;
- **часть** (part): единица мультизадачи. Части образуют граф зависимостей,
  независимые части могут выполняться параллельно разными исполнителями.

Слово «подзадача» в плагине не используется. «Эпик» значит то же, что в трекерах:
родительская задача с дочерними задачами; это не мультизадача.

## Устройство

```
omixflow/
├── skills/        develop, create, refine, start, research, spec, plan, implement,
│                  review, finalize, pr-review, doctor, lead
├── agents/        researcher, architect, coder, tester, reviewer, web-fetcher
├── protocol/      канон: словарь, фазы, тиры, диалог, ревью-цикл, артефакты,
│                  worktree, мультизадача, профили, адаптеры, рантайм скила, лид
├── adapters/      порты и адаптеры
│   ├── tracker/   PORT.md + youtrack, local (+ backlog-index.py), kanban (+ board.py), none
│   ├── forge/     PORT.md + github (+ pr.py), none
│   ├── lang/      PORT.md + ts
│   └── workspace/ PORT.md + git
├── schema/        JSON-схема конфига проекта
├── templates/     шаблон flow.yaml
├── scripts/       doctor, resolve, cfg, state, multitask, wt-setup, общая библиотека
├── hooks/         hooks.json
└── tests/         тесты скриптов, линт терминологии и слоёв, фикстуры
```

## Скилы

| Скил | Что делает |
|---|---|
| `/omixflow:develop {id} [--profile=NAME]` | весь пайплайн: профиль, триаж тира, фазы профиля по очереди, резюм по `state.yaml`, мультизадача по частям или через планировщик research |
| `/omixflow:create` | задача в трекере из черновика или из файла локального бэклога |
| `/omixflow:refine {id} [--multitask]` | уточнение постановки; декомпозиция на части с картой зависимостей, профилем и (для `research`) репозиторием части |
| `/omixflow:research {id} --parts` | планировщик мультизадачи профиля `research`: параллельные researcher'ы частей в одной сессии, блокирующие вопросы, синтез сводного research.md; части могут исследовать чужие репозитории из `workspace.repos` на зафиксированном sha (кросс-репо ресёрч) |
| `/omixflow:start`, `research`, `spec`, `plan`, `implement`, `review`, `finalize` | фазы по отдельности; каждая единственный источник своей логики |
| `/omixflow:pr-review {pr}` | ревью PR или ветки с публикацией через адаптер forge |
| `/omixflow:doctor [--init]` | проверка и настройка проекта |
| `/omixflow:lead [--integration=BRANCH]` | лид: координирует сессии задач, отвечает на их вопросы по политике или передаёт разработчику, ведёт журнал (`protocol/lead.md`) |

Три слоя:

1. **Ядро**: скилы, агенты, `protocol/`. Не знает про конкретный трекер, язык или хостинг.
   Параметризуется конфигом, но не заменяется проектом.
2. **Порты и адаптеры**: `adapters/{port}/PORT.md` описывает контракт, файлы рядом
   реализуют его. Проект может настроить адаптер, расширить его правилами или подменить
   своим. Механизм: [protocol/adapters.md](protocol/adapters.md).
3. **Конфиг проекта**: `.claude/omixflow/flow.yaml`. Только значения. Схема:
   [schema/flow.schema.json](schema/flow.schema.json), шаблон с комментариями:
   [templates/flow.yaml](templates/flow.yaml).

## Установка

Требования: Claude Code, `python3` 3.9+ с PyYAML (`python3 -m pip install pyyaml`),
`git`. Адаптеры могут требовать своё (`gh`, MCP-сервер трекера), это проверяет `doctor`.

Из marketplace (репозиторий плагина одновременно является marketplace):

```bash
claude plugin marketplace add swarga-core/omixflow
claude plugin install omixflow@swarga-core
```

Для разработки плагина, из локального клона:

```bash
claude plugin marketplace add /path/to/omixflow
claude plugin install omixflow@swarga-core
```

Либо без marketplace: каталог с `.claude-plugin/plugin.json` внутри `~/.claude/skills/`
автозагружается как `omixflow@skills-dir`, достаточно symlink'а
`ln -s /path/to/omixflow ~/.claude/skills/omixflow`.

## Настройка проекта

```
/omixflow:doctor --init
```

Скил собирает `.claude/omixflow/flow.yaml` из шаблона и автодетекта, уточняет
неопределимое диалогом и прогоняет проверки: адаптеры разрешаются, обязательные
возможности покрыты, base branch существует, команды гейтов доступны. Без `--init`
`doctor` только проверяет.

Кастомизация адаптера в проекте: каталог `.claude/omixflow/{port}/` зеркалит
`adapters/{port}/`. Файл с фронтматтером `extends: omixflow:{name}` расширяет плагинный
адаптер, файл без `extends` заменяет его. Подробности и приоритеты:
[protocol/adapters.md](protocol/adapters.md).

## Скрипты

```bash
python3 scripts/doctor.py [--project DIR] [--json] [--init [--force]]
python3 scripts/resolve.py adapter tracker        # цепочка файлов адаптера, base → leaf
python3 scripts/resolve.py adapter-script forge pr  # скрипт, объявленный адаптером
python3 scripts/resolve.py agent coder            # subagent_type, файл агента, проектные правила
python3 scripts/resolve.py script gate.sh         # проектный скрипт затеняет плагинный
python3 scripts/resolve.py base                   # разрешённая base-ветка
python3 scripts/resolve.py repo omix-lib --json   # запись workspace.repos: ref → sha, HEAD, dirty
python3 scripts/resolve.py repo --list            # имена workspace.repos через запятую
python3 scripts/resolve.py adapter lang --project ../other --fallback-project .  # чужой репозиторий без flow.yaml
python3 scripts/cfg.py workspace.setup            # значение из flow.yaml
python3 scripts/state.py get .tasks/AL-1          # состояние задачи (init/set/finish/next/step; ask/ack/close для лида)
python3 scripts/multitask.py validate --from d.md # блок мультизадачи: validate/meta/waves/ready/set/seed/file
python3 scripts/lead.py show                      # журнал лида: decide/escalate/resolve/replace/rule/oblige/approve/accept/register/list
python3 scripts/sync.py check .tasks/AL-1         # сдвиг базы и стратегия синхронизации (record)
python3 scripts/accept.py plan task/AL-1 --into main  # приёмка мержа лидом: plan/prepare/merge/commit/abort/cleanup
```

## Статус

`0.4.0`: трекер `kanban` — доска задач на отдельной ветке `board` с worktree
в `.tasks/board/`, карточка как досье задачи (постановка, состояние, комментарии,
артефакты пайплайна), работа нескольких разработчиков через push с повторами,
эпики с дочерними задачами, переезд с `local`. Артефакты задачи живут в карточке
и на кодовые ветки не попадают. Проверен скриптовым прогоном на двух клонах
и живой сессией.

`0.3.0`: профили пайплайна и research-мультизадачи с кросс-репо ресёрчем; точки
решения с маршрутом вопроса; лид (`/omixflow:lead`), который координирует сессии
задач одного разработчика: отвечает на их вопросы по политике или передаёт
разработчику, ведёт журнал, принимает мержи в интеграционную ветку, сводит гочи;
синхронизация с ушедшей базой и сдача без PR. Лид проверен тремя прогонами
в песочнице; следующий шаг: первый прогон на реальной задаче.

## Разработка

```bash
claude plugin validate .            # манифесты, скилы, агенты
python3 -m unittest discover tests  # скрипты
```

Правила для ядра: ссылаться на возможности портов, а не на инструменты
(в `skills/`, `agents/`, `protocol/` не должно быть `pnpm`, `vitest`, `gh`,
имён MCP-инструментов); одно правило живёт в одном месте, остальные ссылаются;
изменения протокола и портов отмечаются в CHANGELOG.
