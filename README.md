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
├── skills/        скилы фаз и утилит (пока только doctor)
├── agents/        агенты (переносятся следующим шагом)
├── protocol/      канон процесса: фазы, тиры, диалог, ревью-цикл, артефакты, мультизадача
├── adapters/      порты и адаптеры
│   ├── tracker/   PORT.md + youtrack, local, none
│   ├── forge/     PORT.md + github, none
│   ├── lang/      PORT.md + ts
│   └── workspace/ PORT.md + git
├── schema/        JSON-схема конфига проекта
├── templates/     шаблон flow.yaml
├── scripts/       doctor, resolve, cfg, wt-setup, общая библиотека
├── hooks/         hooks.json
└── tests/         тесты скриптов и фикстуры
```

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
python3 scripts/resolve.py adapter tracker      # цепочка файлов адаптера, base → leaf
python3 scripts/resolve.py agent coder          # агент и проектные правила к нему
python3 scripts/resolve.py script gate.sh       # проектный скрипт затеняет плагинный
python3 scripts/resolve.py base                 # разрешённая base-ветка
python3 scripts/cfg.py workspace.setup          # значение из flow.yaml
```

## Статус

`0.1.0`: скелет. Перенос скилов фаз, агентов и review-машинерии из
`eps-omix-lib/.claude/` и `~/.claude/skills/omix-pr-review` идёт следующим шагом,
с одновременной чисткой терминологии и закрытием известных дефектов.

## Разработка

```bash
claude plugin validate .            # манифесты, скилы, агенты
python3 -m unittest discover tests  # скрипты
```

Правила для ядра: ссылаться на возможности портов, а не на инструменты
(в `skills/`, `agents/`, `protocol/` не должно быть `pnpm`, `vitest`, `gh`,
имён MCP-инструментов); одно правило живёт в одном месте, остальные ссылаются;
изменения протокола и портов отмечаются в CHANGELOG.
