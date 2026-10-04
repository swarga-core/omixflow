---
name: develop
description: Full OMIXFlow development pipeline for a task — picks the pipeline profile (full by default, research for read-only investigations), triages the tier when the profile does, then runs the profile's phases (Refine, Start, Research, Spec, Plan, Implement, Review, Finalize for full) by invoking the phase skills, resuming from state.yaml; handles multitasks part by part with the dependency map, or delegates a research multitask to the research scheduler. Use when the user says "сделай задачу", "develop AL-822", "запусти пайплайн", or gives a task id / free-form task to implement end to end.
---

# OMIXFlow develop

Оркестратор пайплайна. Сам фазы не реализует: определяет тир, ведёт состояние,
вызывает фазовые скилы по очереди и решает, что дальше. Для мультизадачи ведёт
цикл по частям.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Фазы и инварианты:
`${CLAUDE_PLUGIN_ROOT}/protocol/phases.md`. Тиры:
`${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Профили:
`${CLAUDE_PLUGIN_ROOT}/protocol/profiles.md`. Диалог:
`${CLAUDE_PLUGIN_ROOT}/protocol/dialog.md`.

## Активация

- `/omixflow:develop {id}`: задача из трекера.
- `/omixflow:develop "{описание}"`: свободная формулировка.
- `--from={phase}`: перезапуск с фазы (артефакты фазы и последующих будут
  перезаписаны, предупредить).
- `--profile=NAME`: профиль одиночной задачи (`full` по умолчанию); для мультизадачи
  профиль задаёт маркер блока.
- `--tier=S|M|L`: форсированный тир; с профилем `triage: false` ошибка.
- `--worktree`: изолировать задачу в worktree.
- `--lead=NAME`: сессия задачи под лидом `NAME` (`protocol/lead.md`).
- `{id} --part {part}`: взять конкретную часть мультизадачи.

## Вызов фазового скила

Фаза выполняется её скилом: `Skill("omixflow:{phase}", "{id}[/{part}] --mode=pipeline …")`.
Если харнесс не позволяет вложенный вызов, прочитать
`${CLAUDE_PLUGIN_ROOT}/skills/{phase}/SKILL.md` и выполнить его как вызванный,
с теми же аргументами. В режиме pipeline фазовый скил не печатает «следующий шаг»
и не ждёт подтверждения перехода: переход делает develop.

После каждой фазы: `state.py next TASK_DIR` даёт следующую. Фазы строго
последовательно. Остановка на эскалации или по слову разработчика; состояние
уже сохранено, повторный запуск продолжит.

## Алгоритм: одиночная задача

### 1. Идентификация

`identify` адаптера tracker: id или slug из свободной формулировки.
`TASK_DIR = {artifacts.dir}/{id}`.

### 1a. Лид

`--lead=NAME`, либо `lead.name` в существующем состоянии: до любой фазы регистрация
по `lead.md` («Регистрация»): `register` с задачей, каталогом артефактов, фазой
и открытыми вопросами (`state.py get TASK_DIR lead.open`), будильник на `brief`.
По `brief`: путь журнала и номер вопроса в состояние, если оно есть
(`state.py set TASK_DIR lead.journal=… lead.asked=…`, номер берётся наибольший);
интеграционная ветка из `brief` становится базой задачи (`start --base=…`);
повторённые `decision` и `ack` по открытым вопросам применить. Дальше все точки
решения во всех фазах идут по `lead.md`, «Порядок действий сессии»; `refine` и `start`
получают `--lead=NAME`; `done` шлёт `finalize`.

### 2. Резюм

`TASK_DIR/state.yaml` существует:

- `state.py agents TASK_DIR --session {session}` (агенты чужой сессии
  очищаются).
- `phase == done`: задача завершалась. Через tracker `get` прочитать статус;
  если он снова `in_work` (вернулась на доработку), прочитать комментарии после
  финализации (`comments`), показать их, открыть в log.md секцию
  `## Итерация {N}` с замечаниями, `state.py set TASK_DIR iteration={N}
  completed='["refine","start"]' phase=research steps_done='[]' step=null`
  и продолжить с research. Артефакты дополняются секциями итерации, не
  пересоздаются. Если статус не `in_work`: сообщить, что доработка не требуется.
- Иначе показать состояние текстом (фаза, тир, шаг) и спросить в точке `resume`:
  Продолжить с {next} (Recommended) / Перезапустить с другой фазы / Начать заново.
- `--from={phase}`: `state.py set completed=[фазы до неё]`, предупреждение
  о перезаписи.

### 3. Новая задача

`get` задачи. Если описание содержит блок мультизадачи (`multitask.py has`),
перейти к разделу «Мультизадача». Иначе:

**Триаж.** Профиль с `triage: false` не триажится: шаг пропускается, тира нет.
Иначе оценить тир по критериям tiers.md (порог файлов из `tiers.*`).
Сомнение → больший. `--tier` форсирует и помечается `forced`; вскрывшийся масштаб
для форсированного тира не повышается молча: показать и спросить в точке
`scope-change`. Тир
подтверждается после Refine и может только расти.

**Фазы.**

1. `refine {id} [--lead=NAME]`: только для адаптеров с описанием в трекере; для `none`
   пропускается (уточнение фиксируется в task.md на Start).
2. `start {id} --profile={profile} [--tier={tier}] --mode=pipeline [--worktree]
   [--lead=NAME --base={интеграционная ветка из brief}]`.
3. Фазы профиля после start через `state.py next`, пока фаза не станет `done`.

Инвариант 7: одна задача мутирует один репозиторий, немутирующие фазы читают
репозитории из `workspace.repos`. Если Start или Research вскрыли, что задача требует
изменений в нескольких репозиториях, СТОП и предложить декомпозицию в точке
`scope-change`.

## Мультизадача

### M0. Детект и резюм

Свежее описание → файл; `multitask.py meta` (профиль) и `multitask.py validate`.
Ошибка маркера или валидации или нет блока при заявленной мультизадаче: СТОП,
предложить `refine --multitask`. `--profile`, противоречащий маркеру: СТОП.
`TASK_DIR/state.yaml` с `kind: multitask` нет → M1, есть → M2 (или MS).

Профиль с `part_runner: scheduler` ведётся делегированием, M2–M3 к нему не
применяются:

- **MS.** `start {id}` (если мультизадача не стартована), затем по
  `state.py next TASK_DIR` состояния мультизадачи:
  - `research` → `research {id} --parts` (планировщик, `multitask.md`
    «Планировщик»); после него снова `state.py next`: фаза `research` не закрыта
    (не все части терминальны) → показать сводку планировщика и остановиться;
  - `finalize` → `finalize {id} --multitask`;
  - `done` → как в резюме одиночной задачи (шаг 2, `phase == done`): мультизадача
    завершалась, сообщить об этом.

### M1. Старт мультизадачи

`start {id} --mode=pipeline` (ветка мультизадачи, multitask.md, состояние,
статус, комментарий). → M2.

### M2. Выбор части (`part_runner: sequential`)

`me` из `current_user`. `multitask.py ready --from {desc} --owner {me}`, строго
в этом порядке:

1. `blocked` не пуст: СТОП. Показать причину из комментариев и спросить в точке
   `part-blocked`: разблокировать (→ `pending` через `multitask.py set`) /
   `skipped` / обсудить. Другую часть не брать.
2. `blocked_by_skipped_dependency` не пуст: показать и спросить в точке
   `part-blocked`: снять зависимость / пропустить часть.
3. `mine_active` не пуст: продолжить эту часть → M3 в режиме resume.
4. `--part {part}` указан и часть в `ready`: → M3 fresh.
5. `ready` не пуст: показать волну, занятые части других владельцев как занятые,
   и спросить в точке `part-take`: взять первую готовую (Recommended) / другую
   из готовых / остановить. → M3 fresh. Лимит активных частей владельца
   `multitask.parallel_per_owner` (`ready --parallel`, `slots`).
6. `all_terminal`: → M4.
7. Иначе (всё занято другими или ждёт зависимостей): сообщить, чего ждём,
   остановиться.

### M3. Часть (`part_runner: sequential`)

- fresh: триаж части по её постановке из multitask.md → `start {id} --part {part}
  --tier={tier} --mode=pipeline [--lead=NAME]`.
- resume: войти в worktree части по `path` (пересоздать из ветки, если исчез),
  `PART_DIR = {artifacts.dir}/{id}/{part}`, `state.py next PART_DIR`.

Фазы research → review для `{id}/{part}` как у одиночной задачи. Затем
`finalize {id} --part {part}`. → M2.

**Эскалация внутри части** (лимиты coder или review, critical без решения):
блок → `blocked` (`multitask.py set … status=blocked`), `comment` с причиной
(точка `tracker.comment`), СТОП. Следующую часть не брать.

### M4. Финал

`finalize {id} --multitask`.

## Ошибки

| Ситуация | Действие |
|---|---|
| Трекер недоступен | работать как со свободной формулировкой |
| Конфига нет | предложить `/omixflow:doctor --init`, не продолжать |
| Мультизадача без блока | СТОП → `refine --multitask` |
| Часть `blocked` | СТОП на ней, точка `part-blocked` |
| Пустая часть (0 изменений) | не коммитить, `skipped` |
| Конфликт при интеграции части | СТОП, точка `deadlock`, блок остаётся `in-review` |
| Задача меняет несколько репозиториев | СТОП: одна задача мутирует один репозиторий, немутирующие фазы читают `workspace.repos`; декомпозиция в точке `scope-change` |
| coder или reviewer исчерпали лимит | СТОП, эскалация в точке `deadlock` (coder) или `finding` (review) |
| CLI хостинга не настроен | PR пропускается с инструкцией |

## Правила

- Агенты обязательны в M и L; в S оркестратор пишет только объединённый spec.md.
  Implement и Review во всех тирах только через агентов. Код оркестратор не пишет.
- Масштаб по тиру, инварианты нет: след каждой фазы, дельта до кода, обязательный
  Review, лимиты, подтверждения внешних действий.
- Фазы строго последовательно; параллельные агенты только внутри Research:
  web-fetcher рядом с researcher и researcher'ы частей в планировщике.
- Резюм по `state.yaml`; все решения разработчика попадают в log.md.
- Мультизадача аддитивна: одиночный поток от неё не меняется; часть = тот же
  пайплайн профиля мультизадачи под `{artifacts.dir}/{id}/{part}/`.
- Лимит параллельности по `part_runner`: `parallel_per_owner` для `sequential`,
  `multitask.parallel_parts` для `scheduler`; канон состояния мультизадачи в блоке
  описания, не в файлах и не в комментариях.
