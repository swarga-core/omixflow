---
name: develop
description: Full OMIXFlow development pipeline for a task — triages the tier, then runs Refine, Start, Research, Spec, Plan, Implement, Review, Finalize by invoking the phase skills, resuming from state.yaml; handles multitasks part by part with the dependency map. Use when the user says "сделай задачу", "develop AL-822", "запусти пайплайн", or gives a task id / free-form task to implement end to end.
---

# OMIXFlow develop

Оркестратор пайплайна. Сам фазы не реализует: определяет тир, ведёт состояние,
вызывает фазовые скилы по очереди и решает, что дальше. Для мультизадачи ведёт
цикл по частям.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Фазы и инварианты:
`${CLAUDE_PLUGIN_ROOT}/protocol/phases.md`. Тиры:
`${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Диалог:
`${CLAUDE_PLUGIN_ROOT}/protocol/dialog.md`.

## Активация

- `/omixflow:develop {id}`: задача из трекера.
- `/omixflow:develop "{описание}"`: свободная формулировка.
- `--from={phase}`: перезапуск с фазы (артефакты фазы и последующих будут
  перезаписаны, предупредить).
- `--tier=S|M|L`: форсированный тир.
- `--worktree`: изолировать задачу в worktree.
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
- Иначе показать состояние текстом (фаза, тир, шаг) и AskUserQuestion:
  Продолжить с {next} (Recommended) / Перезапустить с другой фазы / Начать заново.
- `--from={phase}`: `state.py set completed=[фазы до неё]`, предупреждение
  о перезаписи.

### 3. Новая задача

`get` задачи. Если описание содержит блок мультизадачи (`multitask.py has`),
перейти к разделу «Мультизадача». Иначе:

**Триаж.** Оценить тир по критериям tiers.md (порог файлов из `tiers.*`).
Сомнение → больший. `--tier` форсирует и помечается `forced`; вскрывшийся масштаб
для форсированного тира не повышается молча: показать и спросить. Тир
подтверждается после Refine и может только расти.

**Фазы.**

1. `refine {id}`: только для адаптеров с описанием в трекере; для `none`
   пропускается (уточнение фиксируется в task.md на Start).
2. `start {id} --tier={tier} --mode=pipeline [--worktree]`.
3. `research`, `spec`, `plan`, `implement`, `review`, `finalize` через
   `state.py next`, пока фаза не станет `done`.

Правило одного репозитория: если Start или Research вскрыли, что задача требует
изменений в нескольких репозиториях, СТОП и предложить декомпозицию.

## Мультизадача

### M0. Детект и резюм

Свежее описание → файл; `multitask.py validate`. Ошибка валидации или нет
блока при заявленной мультизадаче: СТОП, предложить `refine --multitask`.
`TASK_DIR/state.yaml` с `kind: multitask` нет → M1, есть → M2.

### M1. Старт мультизадачи

`start {id} --mode=pipeline` (ветка мультизадачи, multitask.md, состояние,
статус, комментарий). → M2.

### M2. Выбор части

`me` из `current_user`. `multitask.py ready --from {desc} --owner {me}`, строго
в этом порядке:

1. `blocked` не пуст: СТОП. Показать причину из комментариев текстом,
   AskUserQuestion: разблокировать (→ `pending` через `multitask.py set`) /
   `skipped` / обсудить. Другую часть не брать.
2. `blocked_by_skipped_dependency` не пуст: показать, спросить: снять
   зависимость / пропустить часть.
3. `mine_active` не пуст: продолжить эту часть → M3 в режиме resume.
4. `--part {part}` указан и часть в `ready`: → M3 fresh.
5. `ready` не пуст: показать волну, занятые части других владельцев как занятые,
   AskUserQuestion: взять первую готовую (Recommended) / другую из готовых /
   остановить. → M3 fresh. Активных частей у владельца не больше
   `multitask.parallel_per_owner`.
6. `all_terminal`: → M4.
7. Иначе (всё занято другими или ждёт зависимостей): сообщить, чего ждём,
   остановиться.

### M3. Часть

- fresh: триаж части по её постановке из multitask.md → `start {id} --part {part}
  --tier={tier} --mode=pipeline`.
- resume: войти в worktree части по `path` (пересоздать из ветки, если исчез),
  `PART_DIR = {artifacts.dir}/{id}/{part}`, `state.py next PART_DIR`.

Фазы research → review для `{id}/{part}` как у одиночной задачи. Затем
`finalize {id} --part {part}`. → M2.

**Эскалация внутри части** (лимиты coder или review, critical без решения):
блок → `blocked` (`multitask.py set … status=blocked`), `comment` с причиной,
СТОП. Следующую часть не брать.

### M4. Финал

`finalize {id} --multitask`.

## Ошибки

| Ситуация | Действие |
|---|---|
| Трекер недоступен | работать как со свободной формулировкой |
| Конфига нет | предложить `/omixflow:doctor --init`, не продолжать |
| Мультизадача без блока | СТОП → `refine --multitask` |
| Часть `blocked` | СТОП на ней, разработчик решает |
| Пустая часть (0 изменений) | не коммитить, `skipped` |
| Конфликт при интеграции части | СТОП, блок остаётся `in-review` |
| Задача затрагивает несколько репозиториев | СТОП, декомпозиция |
| coder или reviewer исчерпали лимит | СТОП, эскалация |
| CLI хостинга не настроен | PR пропускается с инструкцией |

## Правила

- Агенты обязательны в M и L; в S оркестратор пишет только объединённый spec.md.
  Implement и Review во всех тирах только через агентов. Код оркестратор не пишет.
- Масштаб по тиру, инварианты нет: след каждой фазы, дельта до кода, обязательный
  Review, лимиты, подтверждения внешних действий.
- Фазы строго последовательно; параллельны только researcher и web-fetcher внутри
  Research.
- Резюм по `state.yaml`; все решения разработчика попадают в log.md.
- Мультизадача аддитивна: одиночный поток от неё не меняется; часть = тот же
  одиночный пайплайн под `{artifacts.dir}/{id}/{part}/`.
- Одна активная часть на владельца; канон состояния мультизадачи в блоке
  описания, не в файлах и не в комментариях.
