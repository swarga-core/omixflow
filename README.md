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
| `/omixflow:lead [--integration=BRANCH]` | лид: запускает сессии задач по слову разработчика (в фоне — все в `claude agents` — или в окнах Terminal), отвечает на их вопросы по политике или передаёт разработчику, ведёт журнал (`protocol/lead.md`) |

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
python3 scripts/cfg.py workspace.setup            # значение из flow.yaml, иначе умолчание схемы (--raw: без него)
python3 scripts/state.py get .tasks/AL-1          # состояние задачи (init/set/finish/next/step; ask/ack/close для лида)
python3 scripts/multitask.py validate --from d.md # блок мультизадачи: validate/meta/waves/ready/set/seed/file
python3 scripts/lead.py show                      # журнал лида: decide/escalate/resolve/replace/rule/oblige/approve/accept/register/list
python3 scripts/sync.py check .tasks/AL-1         # сдвиг базы и стратегия синхронизации (record)
python3 scripts/sessions.py probe --root .         # запуск сессий задач лидом: probe/launch/status/watch/respawn
python3 scripts/accept.py plan task/AL-1 --into main  # приёмка мержа лидом: plan/prepare/merge/commit/abort/cleanup
python3 scripts/cost.py session --session {id}     # стоимость сессии по транскриптам: роли, контекст, перестройки кэша; phase — строка в log.md
python3 scripts/probe.py run --root . --test t --file f --cmd 'cmd' --replace OLD --with NEW  # мутационная проба одним вызовом; batch — пробы шага
python3 scripts/report.py check --role coder --report .tasks/AL-1/reports/implement-step1.md  # сверка отчёта агента с деревом и логами гейтов
python3 scripts/plan.py files --task .tasks/AL-1                 # файлы и шаги плана против порогов тира; код 1 — точка scope-change
python3 scripts/plan.py check --task .tasks/AL-1                 # механическая часть ревью плана: строки для architect'а в MODE: fix
python3 scripts/stats.py task .tasks/AL-1 .tasks/AL-2            # переделки, решения, проходы ревью и стоимость задач по log.md — для сравнения пар
python3 scripts/lead.py decide … --exception                     # исключение из limits.* или порога файлов: записано, прецедентом не станет
```

## Статус

`0.4.0`: трекер `kanban` — доска задач на отдельной ветке `board` с worktree
в `.tasks/board/`, карточка как досье задачи (постановка, состояние, комментарии,
артефакты пайплайна), работа нескольких разработчиков через push с повторами,
эпики с дочерними задачами, переезд с `local`. Артефакты задачи живут в карточке
и на кодовые ветки не попадают. Проверен скриптовым прогоном на двух клонах
и живой сессией. `0.4.1`: исправления по первому реальному проекту на kanban (коммит
артефактов по `artifacts.tracked`, умолчания схемы в `cfg.py`, инварианты доски). `0.4.2`: мелкие исправления по прогонам под лидом (рецепт отката
мутационной пробы, сбои связи доски, родитель агента в шаблоне спавна). `0.4.3`: сдача под лидом
без вопроса, адрес гоч плагина, лимит проходов ревью, повторный refine мультизадачи.

`0.5.0`: агенты — полный отчёт в файл, ответ сводкой; отчёт coder'а с состоянием дерева по `git status`,
мутационными пробами поштучно и проверкой байтами; git у coder'а и tester'а только на чтение;
долгие гейты через `scripts/gate.py` без ухода агента в простой; ротация continuation-агентов
по объёму контекста; свежий reviewer на ревью кода; пакетная запись доски kanban (`batch`).
`0.5.1`: исправления по первому прогону 0.5.0 (MEW-2) — объём контекста агента из его транскрипта
(`scripts/agent_ctx.py`), один отчёт агента за ход, одно задание агенту за раз, мутационные
пробы tester'а, порядок фиксов coder и tester по зависимости.
`0.6.0`: области изменений и наборы гейтов считает `resolve.py verify`; проверки оркестратора
(среда разработки через MCP, ресурс разработчика) — возможность порта lang с моментами шага, ревью,
сдачи и приёмки; точка `lang.window`.
`0.6.1`: исправления по прогонам Swarga AI Studio T-1…T-4 — полный отчёт в файл и у агента без
SendMessage, исполнитель фикса ревью по файлам правки, имя фонового гейта от метки отчёта,
`MUTATIONS` строкой на каждый новый тест.
`0.6.2`: исправления по прогонам T-5 и T-6 — агенты пишут файл отчёта, хотя общая заметка харнесса
против файлов отчётов говорит иное; временные файлы не `report*`; запасной путь, когда харнесс
отклоняет запись; порог ротации — проверка между заданиями, не потолок.
`0.7.0`: лид запускает сессии задач сам — в фоне (`claude --bg`, все сессии в одном терминале
`claude agents`) или в окнах Terminal; режим спрашивается на первой задаче; сессия в режиме
разрешений лида; наблюдение за фоновыми сессиями, которые ждут разработчика, и подъём остановленных.
`0.7.1`: исправления по прогонам T-9 и T-18 — гейты checkpoint плана вне набора шага (`--also`),
пробы для тестов существующего поведения, команды агентов без `cd`, пути в ответе агента.
`0.7.2`: временные файлы агентов только в scratchpad, остаток — в отчёте и итоге задачи;
подпункт, выделенный лидом, живёт в открытых вопросах сессии (`state.py ack --add`).
`0.7.3`: после перезапуска сессии агенты продолжаются по id (`agent_ctx.py`); оборванный сбоем
агент получает то же задание; область коммита из адаптера workspace (`commit_message`).
`0.8.0`: расход токенов — `cost.py` (стоимость сессии и фазы, строка в log.md), диета протокола
(скилы читают секции, `resolve.py section`), architect одним Write, `probe.py` (мутационная проба
одним вызовом), `report.py check` (сверка отчёта агента скриптом вместо чтения), один долгий
опрос гейтов, рецепты изоляции worktree-сессии (`ISOLATION` в спавне).
`0.9.0`: форма спеки и размер задачи — спека как намерение, сценарии приёмки, контракты и
решения с основанием (дизайн и `Covers` в плане); порог файлов и шагов после плана
(`plan.py files`, `tiers.max`, тир из постановки или брифа); механическая часть ревью плана
(`plan.py check`); один содержательный проход ревью артефактов; research.md как вход спеки;
coder правит спеку по ходу (`SPEC AMENDMENTS`, снимок spec.md в baseline); `specs.mode`
(descriptions | adr | none) и гейт `structure`; `stats.py` для сравнения задач.

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
