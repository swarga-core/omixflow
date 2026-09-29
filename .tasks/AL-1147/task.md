# AL-1147: [OMIXFlow] Профили пайплайна: research, параллельные части, кросс-репо ресёрч

## Исходная формулировка

## Описание

Ввести в OMIXFlow понятие **профиля пайплайна**: именованного подмножества фаз с производными свойствами (мутирует ли код, изоляция части, способ интеграции части, артефакт Finalize). Профиль ортогонален `kind: task | multitask | part` и тиру. Первые два профиля: `full` (текущее поведение, дефолт) и `research` (Refine, Start, Research, Finalize; код не меняется).

На базе профиля `research` реализовать три возможности, которых сейчас нет:

1. **Параллельные части мультизадачи в одной сессии** по карте зависимостей: событийный планировщик запускает готовые части фоновыми именованными researcher'ами, зависимые части стартуют, как только готовы их входы.
2. **Два типа design questions**: `blocking` (меняет направление или scope части, задаётся по ходу, researcher продолжается тем же агентом) и `deferred` (влияет на будущее решение, уходит на синтез).
3. **Кросс-репо ресёрч**: части читают другие репозитории из `workspace.repos` на зафиксированной ревизии, артефакты живут в домашнем репозитории.

## Контекст

- Мультизадача сегодня склеивает две оси: декомпозицию (части, карта зависимостей, борд, владельцы) и форму пайплайна части (все восемь фаз, ветка + worktree, squash). Для большого ресёрча по двум проектам нужна первая ось без второй.
- `state.py` держит фазы жёстким списком `PHASES`; `multitask.py` ищет маркер блока точной строкой и при каждом `set` перерисовывает блок из фиксированных колонок, теряя всё лишнее.
- Реконсиляция «ветки части нет, а блок говорит in-work → интегрирована» и проверка пересечения Source Files Map между частями рассчитаны на мутирующие части и для read-only частей дают ложные срабатывания.
- Лимит `parallel_per_owner: 1` зашит в start, develop (M2 и правила) и `protocol/multitask.md`; тир S пишет ресёрч инлайн в spec.md без агента.
- Researcher одноразовый и безымянный, у отчёта нет статуса и секции передачи; линт требует именованный спавн и SendMessage в одном SKILL.md.
- Инвариант 7 «одна задача, один репозиторий» повторён в develop, start, refine и glossary.

## Требования

### Профили

- Канон профилей: словарь `PROFILES` в `state.py` (имя → фазы и свойства); человеко-читаемая таблица в `protocol/` (phases.md или новый `profiles.md`); линт-тест сверяет их.
- `state.yaml` получает `profile` (отсутствие = `full`); часть наследует профиль мультизадачи. `state.py next`, `init`, `set phase=`, `complete` валидируют по профилю.
- Профиль мультизадачи объявляется атрибутом маркера `<!-- omixflow:multitask:start profile=research -->`; блок без атрибута = `full`. `multitask.py` находит маркер регуляркой, парсит атрибуты и **сохраняет их при render/set**. Контракт управляемых блоков в `adapters/tracker/PORT.md` обновляется (изменение порта).
- Одиночная задача: `--profile=research` у `develop` и `start`, персистится в `state.yaml`.
- Профиль `research` тир не триажит: всегда researcher-агент на `models.strong`, всегда `research.md`. Инлайн-ресёрч S-тира к этому профилю не применяется.
- Одиночная задача профиля `research`: Start как в `full` (ветка `task/{id}` от base, артефакты, статус in_work); Finalize коммитит research.md, комментирует в трекер, ставит статус, предлагает PR с артефактами.

### Части профиля `research`

- Start части: без ветки и без worktree, только `.tasks/{id}/{part}/` на общей ветке `task/{id}` в основном дереве; блок получает `owner` и `in-work`.
- Finalize части: без rebase и squash. Диалог по вопросам Handoff (см. ниже), коммит **только** `.tasks/{id}/{part}/` по пути (никогда `-A`: рядом пишутся другие части), фиксированный формат сообщения коммита, push при `multitask.push`, `done` в блоке с хешем.
- Реконсиляция для профиля `research`: признак интеграции это коммит части в истории `task/{id}`, а не отсутствие ветки.
- Проверка пересечения Source Files Map (`PARTS_IN_FLIGHT`) для немутирующих профилей отключена.
- `parallel_per_owner` действует только для `full`; для немутирующих профилей вводится `multitask.parallel_parts` (дефолт 4): максимум одновременных researcher'ов.

### Планировщик

- Живёт в скиле `research` как режим для мультизадачи профиля `research`; `develop` делегирует: `start {id}` → `research {id} --parts` → `finalize {id} --multitask`. Внутри планировщик вызывает `start --part` и `finalize --part` как вложенные скилы, не дублируя их логику.
- Цикл: `multitask.py ready` → запустить готовые части фоновыми агентами `researcher-{id}-{part}` в пределах `parallel_parts` → по завершении части: диалог, коммит, `done`, пересчёт `ready` → до терминальности всех частей.
- **Группировка по репозиторию**: одновременно активен один репозиторий (LSP-инструменты держат один активный проект на сессию); части одного репозитория параллельны, репозитории последовательно.
- Зависимая часть получает `INPUTS`: пути к research.md частей из `depends`, с инструкцией читать сначала `## Handoff`.
- Часть, исчерпавшая лимит blocking-вопросов или упавшая: `blocked` в блоке с причиной; её зависимые ждут, независимые продолжают; сводка в конце. Правило develop M2.1 «blocked = стоп для владельца» на профиль `research` не распространяется.
- Резюм в новой сессии: части `in-work` текущего владельца без research.md перезапускаются свежим именованным researcher'ом, ранее данные ответы на blocking-вопросы передаются входом (хранятся в log.md части).

### Researcher и вопросы

- Researcher части и синтеза: именованный continuation-агент (`researcher-{id}-{part}`, `researcher-{id}`). Правило runtime.md и review-cycle.md меняется на «именуется, когда продолжается»; researcher скила `create` остаётся одноразовым.
- Отчёт получает `STATUS: done | blocked`; при `blocked` блок вопроса: формулировка, варианты, что зависит, что уже установлено. Оркестратор ведёт диалог по dialog.md и продолжает агента через SendMessage. Лимит два blocking-вопроса на часть.
- Критерий типа: blocking меняет направление или scope самой части; deferred влияет на будущее решение и записывается в `## Design Questions` без ответа. Скил `research` перестаёт требовать ответы на все вопросы для профиля `research`.
- research.md получает `## Handoff` (обязательна для частей, от которых кто-то зависит): установленные факты, принятые решения, затрагиваемые файлы и контракты, открытые вопросы для зависимых. Вопросы Handoff задаются разработчику при завершении части до старта зависимых.
- Шапка research.md кросс-репо части: репозиторий, ref, sha. Пути Source Files Map с префиксом `{repo}:`.
- Синтез: researcher в режиме `synthesis` (`INPUTS` = research.md всех частей) пишет `.tasks/{id}/research.md`: сводный Source Files Map по репозиториям, объединённые findings, все deferred-вопросы. Оркестратор проводит диалог по deferred-вопросам, ответы фиксируются в сводке.
- Строка в агенте researcher и в секции navigation `adapters/lang/PORT.md`: инструменты навигации активируются на `PROJECT_ROOT`, не на cwd. В ядре без имён инструментов.

### Кросс-репо

- `workspace.repos: { name: { path, remote, ref?, setup? } }` в схеме, шаблоне и списке `config` порта workspace. `path` относительно корня домашнего проекта; `remote` идентичность для doctor; `ref` ветка, тег, sha или `auto` (base чужого проекта); `setup` (дефолт false) устанавливает зависимости в research-worktree.
- Опциональная колонка `repo` в блоке: имя из `workspace.repos`, `—` или отсутствие = домашний. `multitask.py validate` проверяет имена (список репозиториев передаётся аргументом) и запрещает не домашний `repo` в блоке профиля `full`. `repo` неизменяем после старта. `Row`, `render`, `set` поддерживают колонку.
- Спавн researcher'а кросс-репо части: `PROJECT_ROOT` = чужой репозиторий (только чтение), `TASK_DIR` в домашнем, `ADAPTERS.lang` через `resolve.py adapter lang --project {чужой}`; при отсутствии там flow.yaml фолбэк на цепочку домашнего проекта (флаг `resolve.py` или обработка кода 2 в скиле, doctor предупреждает). `RULES` из чужого проекта, если есть.
- Снимок: `ref` разрешается в полный sha один раз на старте мультизадачи и хранится в `state.yaml` мультизадачи (`repos: {name: {ref, sha}}`); все части и исполнители читают его. Перед запуском каждой части HEAD чужого checkout сверяется с sha повторно.
- Если HEAD чужого checkout ≠ sha или дерево грязное (проверка с `--untracked-files=no`, каталог `.claude/worktrees/` игнорируется): с подтверждением `git worktree add --detach {repo}/.claude/worktrees/research-{id} {sha}`, один на репозиторий на мультизадачу, общий для параллельных частей. Инициализация submodule и `setup` по адаптеру workspace выполняются оркестратором (хук не срабатывает). Снос на Finalize мультизадачи по порядку из `adapters/workspace/git.md`.
- Инвариант 7 переформулирован: «одна задача мутирует один репозиторий; немутирующие фазы читают репозитории из `workspace.repos`». Правка во всех местах повтора: phases.md, develop, start, refine, glossary.
- `doctor`: для каждого `workspace.repos` проверяет slug имени, существование пути и git-репозитория, совпадение `origin` с `remote`, разрешимость `ref`, наличие flow.yaml (info); предупреждает о накоплении `research-*` worktree в чужих репозиториях, особенно с `phase: done` у домашней задачи.

### Документация и словарь

- glossary: профиль, передача (handoff), блокирующий и отложенный вопрос, синтез, планировщик, репозиторий workspace. Развести `STATUS: blocked` researcher'а и статус части `blocked`.
- dialog.md: строки для blocking-вопросов и диалога завершения части. artifacts.md: `profile`, `repos` в state.yaml, Handoff и шапка research.md. tiers.md, multitask.md, worktree.md, runtime.md (таблица портов: research получает workspace для кросс-репо), review-cycle.md.
- CHANGELOG с пометками **protocol** и **port** (tracker: маркер; workspace: `repos`, `config`; lang: navigation). README: фазы и профили.

## Критерии приёмки

- `python3 -m unittest discover tests` и `claude plugin validate .` зелёные; новые тесты: последовательность фаз по профилю в `state.py` (отклонение `spec` в `research`); маркер с атрибутом находится, `set` сохраняет атрибут и колонку `repo`, блок без атрибута round-trip байт-в-байт; валидация `repo` и запрет не домашнего в `full`; `workspace.repos` в схеме (плохие записи отклоняются); doctor предупреждает о `research-*` worktree; линт «таблица профилей = `PROFILES`».
- Существующие блоки и `state.yaml` без `profile` работают как `full` без изменений; `test_lifecycle` проходит.
- Живой прогон: мультизадача профиля `research` из не менее четырёх частей с зависимостями, части в двух репозиториях (`eps-omix-lib`, `eps-eal-omix`) из домашнего `omixflow` или одного из проектов: части одного репозитория выполняются параллельно, зависимая стартует после Handoff-диалога, хотя бы один blocking-вопрос отработан продолжением того же агента, синтез создан, deferred-вопросы отвечены на синтезе, research-worktree снесён на Finalize.
- `/omixflow:doctor` в трёх проектах без FAIL после добавления `workspace.repos`.
- В ядре нет имён инструментов (линт), словарь пополнен, CHANGELOG размечен.

## Ограничения

- Другие профили (`design`, `audit`) не реализуются; таблица должна позволять их добавить без правки скилов.
- Профили, объявляемые проектом в конфиге, вне scope.
- Добавление и удаление частей при повторном `refine --multitask` (`multitask.py set` строки не добавляет, `seed` отказывает при существующем блоке): известная дыра, отдельная задача.
- Локальный override путей `workspace.repos` для разных машин: отдельная задача.
- Параллель частей профиля `full` (с worktree) не меняется.
- Несколько исполнителей на одной research-мультизадаче: протокол допускает, живой прогон не требуется.

## Затронутые компоненты

- `scripts/state.py`, `scripts/multitask.py`, `scripts/resolve.py`, `scripts/doctor.py`, `scripts/omixflow_lib.py`
- `schema/flow.schema.json`, `templates/flow.yaml`
- `protocol/`: phases, tiers, runtime, multitask, artifacts, dialog, glossary, worktree, review-cycle (+ возможный `profiles.md`)
- `skills/`: develop, start, research, finalize, refine
- `agents/researcher.md`
- `adapters/tracker/PORT.md`, `adapters/workspace/PORT.md`, `adapters/workspace/git.md`, `adapters/lang/PORT.md`
- `tests/`: test_state_multitask, test_scripts, test_lint, фикстуры
- `README.md`, `CHANGELOG.md`

## Тир

L. Вести как обычную задачу, не мультизадачу: задача меняет саму механику мультизадачи.

## Контекст

- Трекер: youtrack, https://tm.ertdev.com/issue/AL-1147
- Тип, приоритет: Task / Feature, Normal; Subsystems: Frontend; Parrot Points: 5
- Связанные задачи: AL-1140 (relates to) — плагин OMIXFlow 0.2.0, незамерженная ветка `task/AL-1140`, база этой задачи

## Финальная формулировка

Постановка из секций «Описание», «Требования», «Ограничения» и «Затронутые компоненты» выше является канонической. Решения уточнения 2026-09-28:

- **Базовая ветка.** `task/AL-1147` ведётся от `task/AL-1140` (стек): на `main` нет `.claude/omixflow/flow.yaml`, проектного адаптера `py` и части правимого кода (`doctor.py`, `adapters/workspace/git.md`, `protocol/worktree.md`). PR открывается в `main` после мержа AL-1140 либо в `task/AL-1140`.
- **Граница задачи.** Задача мутирует только репозиторий `omixflow`. `workspace.repos` в `flow.yaml` проектов `eps-omix-lib` и `eps-eal-omix` добавляет разработчик вручную после Finalize; это не часть коммитов задачи.
- **Тир.** L, без пересмотра.

### Критерии приёмки

Автоматические (проверяются пайплайном в Review):
- `python3 -m unittest discover tests` и `claude plugin validate .` зелёные.
- Новые тесты из секции «Критерии приёмки» исходной формулировки присутствуют и проходят: фазы по профилю, атрибут маркера и колонка `repo`, round-trip блока без атрибута, валидация `repo`, `workspace.repos` в схеме, предупреждение doctor о `research-*` worktree, линт «таблица профилей = `PROFILES`».
- `test_lifecycle` проходит; блоки и `state.yaml` без `profile` работают как `full`.
- В ядре нет имён инструментов (линт), словарь пополнен, CHANGELOG размечен **protocol** и **port**.

Ручная приёмка разработчиком после Finalize (не блокирует закрытие задачи пайплайном, фиксируется комментарием в трекере):
- Живой прогон research-мультизадачи из не менее четырёх частей с зависимостями в двух репозиториях (`eps-omix-lib`, `eps-eal-omix`).
- `/omixflow:doctor` в трёх проектах без FAIL после добавления `workspace.repos`.

### Ограничения

- Без изменений относительно секции «Ограничения» исходной формулировки.
- Правки `flow.yaml` в чужих проектах вне scope.

## Scope

- Пакеты, модули: `scripts/` (state, multitask, resolve, doctor, omixflow_lib), `schema/`, `templates/`, `protocol/` (phases, tiers, runtime, multitask, artifacts, dialog, glossary, worktree, review-cycle, новый profiles), `skills/` (develop, start, research, finalize, refine), `agents/researcher.md`, `adapters/` (tracker/PORT, workspace/PORT, workspace/git, lang/PORT), `tests/`, `README.md`, `CHANGELOG.md`

## Tier

- L — несколько подсистем плагина (скрипты, схема, протокол, скилы, агент, четыре порта), новые контракты портов и протокола, заведомо больше `tiers.m_max_files` файлов.
