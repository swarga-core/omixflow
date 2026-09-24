# OMIXFlow

Плагин Claude Code с пайплайном spec-driven разработки. Одна задача проходит фазы
Refine, Start, Research, Spec, Plan, Implement, Review, Finalize; каждую фазу ведут
специализированные агенты, а всё, что зависит от проекта (трекер задач, хостинг кода,
язык, устройство репозитория), вынесено в адаптеры и конфиг проекта.

Обкатан на семействе проектов omix (`eps-omix-lib`, `eps-eal-omix`), отсюда имя.
Проектируется как общий инструмент: разные языки, разные трекеры, несколько
разработчиков.

## Термины

Единый словарь в [protocol/glossary.md](protocol/glossary.md). Два термина,
без которых не читается остальное:

- **мультизадача** (multitask): задача, части которой выполняются как самостоятельные
  задачи, каждая со своим полным пайплайном, веткой и артефактами;
- **часть** (part): единица мультизадачи. Части образуют граф зависимостей,
  независимые части могут выполняться параллельно разными исполнителями.

Слова «эпик» и «подзадача» в плагине не используются: у них есть собственный смысл
в трекерах, и он другой.

## Устройство

```
omixflow/
├── skills/        develop, create, refine, start, research, spec, plan, implement,
│                  review, finalize, pr-review, doctor
├── agents/        researcher, architect, coder, tester, reviewer, web-fetcher
├── protocol/      канон: словарь, фазы, тиры, диалог, ревью-цикл, артефакты,
│                  worktree, мультизадача, адаптеры, рантайм скила
├── adapters/      порты и адаптеры
│   ├── tracker/   PORT.md + youtrack, local (+ backlog-index.py), none
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
| `/omixflow:develop {id}` | весь пайплайн: триаж тира, фазы по очереди, резюм по `state.yaml`, мультизадача по частям |
| `/omixflow:create` | задача в трекере из черновика или из файла локального бэклога |
| `/omixflow:refine {id} [--multitask]` | уточнение постановки; декомпозиция на части с картой зависимостей |
| `/omixflow:start`, `research`, `spec`, `plan`, `implement`, `review`, `finalize` | фазы по отдельности; каждая единственный источник своей логики |
| `/omixflow:pr-review {pr}` | ревью PR или ветки с публикацией через адаптер forge |
| `/omixflow:doctor [--init]` | проверка и настройка проекта |

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
python3 scripts/cfg.py workspace.setup            # значение из flow.yaml
python3 scripts/state.py get .tasks/AL-1          # состояние задачи (init/set/complete/next/step)
python3 scripts/multitask.py validate --from d.md # блок мультизадачи: validate/waves/ready/set/seed/file
```

## Статус

`0.2.0`: скилы, агенты и протокол перенесены из `eps-omix-lib/.claude/`
и `~/.claude/skills/omix-pr-review` с чисткой терминологии и закрытием известных
дефектов. Следующий шаг: миграция проектов на `flow.yaml` и первый прогон реальной
задачи через `/omixflow:develop`.

## Разработка

```bash
claude plugin validate .            # манифесты, скилы, агенты
python3 -m unittest discover tests  # скрипты
```

Правила для ядра: ссылаться на возможности портов, а не на инструменты
(в `skills/`, `agents/`, `protocol/` не должно быть `pnpm`, `vitest`, `gh`,
имён MCP-инструментов); одно правило живёт в одном месте, остальные ссылаются;
изменения протокола и портов отмечаются в CHANGELOG.
