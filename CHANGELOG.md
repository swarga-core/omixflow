# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии по SemVer.
Изменения протокола (`protocol/`) и контрактов портов (`adapters/*/PORT.md`) помечаются
как **protocol** и **port**: проект, пинящий версию плагина, читает именно их.

## [Unreleased]

Профили пайплайна (`full`, `research`), планировщик research-частей мультизадачи
и кросс-репо ресёрч по `workspace.repos`.

**Совместимость.** Блок мультизадачи с атрибутом маркера (`profile=research`) не
виден версиям плагина до этой: старый поиск маркера ищет его точную строку без
атрибутов. Проекты, использующие немутирующие профили, должны поднять
`plugin.min_version` в `flow.yaml` до релиза, в который войдут эти изменения.
Блоки без атрибута и `state.yaml` без `profile` работают как раньше (`full`).

### Added
- **protocol** `profiles.md`: профиль пайплайна, подмножество фаз со свойствами `mutates`, `part_isolation`, `part_integration`, `finalize_artifact`, `triage`, `part_runner`; профили `full` и `research`; отсутствие профиля означает `full`; добавление профиля без правки скилов только при уже существующих значениях свойств.
- **port** workspace: `workspace.repos` (чужие репозитории: `path`, `remote`, `ref`, `setup`) в списке `config` порта и в примере конфига; возможность `worktree` покрывает research-worktree; в адаптере `git` раздел research-worktree (создание на sha, setup с submodule и `setup: true`, снос) и примечание, что `part_integration: commit` не использует `integrate`.
- Схема и шаблон конфига: `workspace.repos`, `multitask.parallel_parts` (по умолчанию 4, для `part_runner: scheduler`); `parallel_per_owner` относится к `part_runner: sequential`.
- `state.py`: канон `PROFILES`, `init --profile`, `get DIR profile` печатает действующий профиль (`full` для старых состояний), `set profile=` с проверкой `completed`. Линт сверяет таблицу `protocol/profiles.md` с `PROFILES`.
- `multitask.py`: команда `meta` (профиль, атрибуты, репозитории блока); колонка `repo` с проверкой `--repos` в `validate`/`set`/`seed`, `set repo=` только у `pending`; `ready --parallel N` отдаёт `slots`, `ready_by_repo`, `active_repos`; `seed --profile/--repo`, `render --profile`; раздел «Интеграция» и строка `- Репозиторий:` в скелете `file` по профилю.
- `resolve.py`: `repo NAME [--json]` (ref записи `workspace.repos` → sha, HEAD, dirty, наличие flow.yaml; ветка берётся с `origin/`, без fetch), `repo --list`; `--fallback-project HOME` для чужого репозитория без flow.yaml (адаптеры по конфигу HOME с приоритетом проектного слоя чужого, `base` как `auto` в чужом репозитории, `agent` из HOME с правилами чужого). `omixflow_lib`: `resolve_repo_ref`, `repo_checkout_state`, `normalize_remote`.
- `doctor`: секция `repo:{name}` для каждой записи `workspace.repos`: `slug`, `path` (FAIL, если каталога нет или он внутри домашнего проекта), `git`, `remote` (ssh и https одного репозитория равны), `ref`, `flow.yaml`, `research worktrees` (WARN для завершённой задачи по состоянию в дереве или на ветке задачи и при числе больше 3).
- Скил `research`: режим планировщика `research {id} --parts` (группировка по репозиторию, сверка HEAD со снимком, синтез, резюм); именованные продолжаемые спавны researcher (`researcher-{id}`, `researcher-{id}-{part}`) с ответом на блокирующий вопрос через SendMessage, лимит два блокирующих вопроса, формат `### Blocking Q{n}` в log.md.
- Агент `researcher`: режим синтеза; входы `MODE`, `REPO`, `INPUTS`, `HANDOFF`, `ANSWERS`, `CONTINUABLE`; инструмент `Write`.
- **port** lang: гейт `visual` (визуальная регрессия в браузере) в фиксированном словаре гейтов.
- **port** lang: критерий чтения `no-new-diagnostics` для репозиториев с накопленным долгом линтера (baseline на базовой ветке в начале задачи).
- `doctor`: предупреждение о накоплении review-worktree (`.claude/worktrees/pr-*`).
- `pr-review`: проверка свежести `_repo-context.md` по base-ветке и дате; остановка на MERGED/CLOSED PR с предложением снести worktree; имена групп из скила, не из архива прошлого раунда.
- `workspace/git`, `protocol/worktree.md`: снос worktree с инициализированным submodule (удалить содержимое submodule и `{gitdir}/modules`, затем `worktree remove --force`); `submodule deinit` из worktree запрещён, он деинициализирует submodule основного дерева через общий конфиг.

### Changed
- **protocol** `phases.md`: набор фаз задаёт профиль, порядок глобальный; инвариант 7 «Одна задача мутирует один репозиторий; немутирующие фазы читают репозитории из `workspace.repos`»; инварианты 2 и 9 для профилей с Implement и Review; внешние действия Research в режиме планировщика.
- **protocol** `tiers.md`: профиль с `triage: false` не триажится (`tier: null`, researcher на `models.strong`, всегда `research.md`); триаж частей только в профилях с триажем.
- **protocol** `runtime.md`: порты research — lang, workspace, tracker; researcher именуется, когда его продолжают (`researcher-{id}`, `researcher-{id}-{part}`); параметры researcher; шаблон кросс-репо спавна.
- **protocol** `review-cycle.md`: continuation-принцип распространяется на продолжаемого researcher.
- **protocol** `multitask.md`: атрибуты маркера (`profile=`, отсутствие означает `full`), маркеры только целой строкой, второй блок и ошибки атрибутов; колонка `repo` (после `title`, `—` = домашний репозиторий, только в немутирующем профиле, неизменна после старта части), `branch` `—` у частей с `part_isolation: shared`; части идут по профилю мультизадачи; проверка пересечений только в мутирующих профилях; «Выбор части» для `part_runner: sequential`; новые разделы «Часть профиля research» (явные пути коммитов, трекер `none`, push на общей ветке), «Планировщик», «Синтез», «Кросс-репо»; `blocked` в немутирующем профиле останавливает только зависимых; реконсиляция для `part_integration: commit` по теме коммита.
- **protocol** `artifacts.md`: `profile` и снимок `repos` в `state.yaml`, сводный research.md мультизадачи, контракт research.md (Handoff, кросс-репо заголовок, типизированные вопросы).
- **protocol** `dialog.md`: блокирующий вопрос researcher'а, открытые вопросы Handoff, отложенные вопросы синтеза, создание research-worktree, сводка планировщика.
- **protocol** `glossary.md`: термины профиль, блокирующий и отложенный вопрос, передача, планировщик, синтез, репозиторий workspace, снимок, research-worktree; `STATUS: blocked` против статуса части `blocked`; фаза, мультизадача, ветка части, интеграция части по профилю; адрес агента синтеза.
- **protocol** `worktree.md`: вид research-worktree (корень в чужом репозитории, detached на sha снимка, без входа, путь не хранится в состоянии).
- **port** tracker: маркер начала управляемого блока может нести атрибуты `key=value`; маркеры занимают строку целиком; адаптер находит блок по началу строки маркера и сохраняет её с атрибутами как есть.
- **port** lang: инструменты навигации активируются на `PROJECT_ROOT` из промпта, не на cwd.
- `state.py`: `next`/`set phase=`/`complete` по фазам профиля; часть наследует профиль из состояния мультизадачи (`kind: multitask` с тем же id, иначе ошибка); для профиля с `triage: false` `--tier` отклоняется и хранится `tier: null`.
- `multitask.py`: маркер ищется целой строкой, атрибуты маркера; ошибки маркера отклоняют `validate`/`meta`/`ready`/`file` и терпят `extract`/`has`/`set`/`waves`; `set` переписывает только строку части, пустой `set` возвращает текст байт в байт.
- Агент `researcher`: отчёт начинается с `STATUS: done | blocked` (`blocked` только при `CONTINUABLE: yes`, без research.md); типизированные вопросы `[blocking]`/`[deferred]`, секция `## Handoff`, кросс-репо заголовок и префикс `{repo}:`; навигация на `PROJECT_ROOT`.
- Скил `research`: `triage: false` без S-инлайна; `PARTS_IN_FLIGHT` только в мутирующих профилях; ответы обязательны только в профиле со Spec.
- Скил `start`: `--profile`, запрет `--tier` при `triage: false`; мультизадача берёт профиль из `meta`, снимок `repos` одним JSON на запись, `--repos` из `resolve.py repo --list`; старт части по `part_isolation`, лимит по `part_runner`, часть закрывает refine и start.
- Скил `develop`: `--profile`; профиль мультизадачи из `meta`; `part_runner: scheduler` делегирует `start` → `research --parts` → `finalize --multitask`; M2–M3 для `sequential`; новая формулировка инварианта 7; лимит параллельности по `part_runner`.
- Скил `finalize`: задача с `finalize_artifact: research` (research.md и артефакты, PR без статистики кода); часть с `part_integration: commit` (реконсиляция по теме коммита, диалог по Handoff, коммит по пути, push на общей ветке, хеш после push); `--multitask` сносит research-worktree.
- Скил `refine`: вопрос о профиле в `--multitask`, репозиторий части для немутирующего профиля, `seed --profile/--repo/--repos` и `validate --repos`.
- README: фазы и профили, планировщик и кросс-репо ресёрч, `resolve.py repo` и `--fallback-project`.

### Fixed
- `forge/github/pr.py`: логин пользователя через `--jq .login` приходит строкой, не JSON (падали `reviews-mine` и `threads --mine`). Найдено живым прогоном на PR #34.

## [0.2.0] — 2026-09-24

Перенос пайплайна из `eps-omix-lib/.claude/` и `omix-pr-review`.

### Added
- Скилы `develop`, `create`, `refine`, `start`, `research`, `spec`, `plan`,
  `implement`, `review`, `finalize`, `pr-review`.
- Агенты `researcher`, `architect`, `coder`, `tester`, `reviewer`, `web-fetcher`:
  языконезависимые, инструменты и гейты берут из адаптеров, переданных при спавне.
- **protocol**: `runtime.md` (пролог скила, спавн агентов, режим pipeline/manual).
- Скрипты `state.py` (state.yaml), `multitask.py` (блок мультизадачи, карта
  зависимостей, волны, готовность частей).
- Скрипты адаптеров: `forge/github/pr.py` (view, files, reviews-mine, threads,
  build-payload, validate, submit, reply, permalink), `tracker/local/backlog-index.py`.
- `resolve.py adapter-script`, `resolve.py agent` печатает `subagent_type`;
  проектный агент с тем же именем перекрывает плагинного.
- Линт: агенты объявляют фронтматтер; тело агентов и скилов не называет инструментов;
  у каждого адресата SendMessage есть именованный спавн.

### Changed
- **protocol**: `artifacts.md` — `state.yaml` получил `mode`, `completed`,
  `steps_done`, `session`; управляется скриптом.
- `develop` тонкий: вызывает фазовые скилы, дублирования логики фаз нет.
- Тир и лимиты читаются из конфига, а не зашиты в скилы.

### Fixed (относительно предыдущего поколения)
- architect спавнится с `name`, FIX-цикл spec/plan идёт ему, а не reviewer'у.
- Статистика finalize считается от base из состояния, а не от литерала `main`.
- Раунды re-review считаются по настоящим ревью (ответы в треды не раунды).
- Отсутствие артефактов пайплайна у автора PR не считается spec drift.
- Review-worktree получает setup (submodule, зависимости) до гейтов.
- Probe-правки файлов PR запрещены явно; APPROVE-раунд без находок описан.

## [0.1.0] — 2026-09-23

Скелет плагина. Скилы фаз и агенты ещё не перенесены из `eps-omix-lib/.claude/`.

### Added
- Манифесты плагина и marketplace.
- **protocol**: glossary, phases, tiers, dialog, review-cycle, artifacts, worktree, multitask, adapters.
- **port**: контракты `tracker`, `forge`, `lang`, `workspace` (`adapters/*/PORT.md`).
- Стартовые адаптеры: `tracker/{youtrack,local,none}`, `forge/{github,none}`, `lang/ts`, `workspace/git`.
- Схема конфига `schema/flow.schema.json`, шаблон `templates/flow.yaml`.
- Скрипты `scripts/doctor.py`, `scripts/resolve.py`, `scripts/cfg.py`, библиотека `scripts/omixflow_lib.py`.
- Хук `PostToolUse[EnterWorktree]` → `scripts/wt-setup.sh` (setup worktree по `workspace.setup`).
- Скил `doctor`.
- Тесты `tests/`.

### Changed
- Терминология: «эпик» заменён на «мультизадача», «подзадача» на «часть» (см. `protocol/glossary.md`).
