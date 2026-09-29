# Артефакты задачи

Каталог артефактов задаёт `artifacts.dir` в конфиге, по умолчанию `.tasks`.
Артефакты версионируются в git вместе с кодом (`artifacts.tracked: true`, дефолт):
без этого они не переживают снос worktree и не доезжают до другой машины,
а для мультизадачи это обязательно.

## Раскладка

```
.tasks/
├── {id}/
│   ├── task.md          постановка as-is и финальная, контекст, scope, тир
│   ├── state.yaml       машинное состояние
│   ├── log.md           журнал для человека
│   ├── research.md      Source Files Map, findings, design questions, Handoff (см. ниже)
│   ├── spec.md          дельта: Summary, Changes, Dependencies, Decisions, Out of Scope; в S ещё Research и Steps
│   └── plan.md          шаги с файлами и тест-чекпоинтами (M, L)
├── {id}/                мультизадача
│   ├── multitask.md     определение частей и их постановки, карта зависимостей, волны
│   ├── state.yaml       состояние мультизадачи
│   ├── log.md
│   ├── research.md      синтез частей мультизадачи профиля research
│   └── {part}/          артефакты части: та же структура, что у одиночной задачи
└── backlog/             хранилище адаптера tracker/local, если он используется
```

Артефакты ревью PR (`.review/`) в git не входят: их добавляет в `.gitignore` скил ревью.

## state.yaml

Единственный источник для резюма. Пишется оркестратором при каждом переходе.

```yaml
schema: 1
id: AL-822
kind: task                 # task | multitask | part
profile: full              # full | research (protocol/profiles.md); нет ключа = full
mode: pipeline             # pipeline (ведёт develop) | manual (standalone-скилы)
tier: M                    # null у профиля с triage: false
tier_forced: false
phase: implement           # текущая фаза из фаз профиля или done
completed: [refine, start, research, spec, plan]
step: 3                    # текущий шаг плана, только в implement
steps_total: 6
steps_done: [1, 2]
iteration: 1               # номер доработки после возврата; 1 = первая реализация
agents:                    # живые continuation-агенты этой сессии
  coder: coder-AL-822
  reviewer: reviewer-AL-822
session: 3f2a…             # id сессии, в которой созданы agents
branch: task/AL-822
base: release/2.3.0
multitask:                 # только для kind: part
  id: AL-9
  part: auth-flow
repos:                     # только для kind: multitask с частями в workspace.repos: снимок
  omix-lib: {ref: auto, sha: 9f8e7d6c5b4a39281706f5e4d3c2b1a098765432}
updated: 2026-09-23T16:00:00Z
```

Управляется скриптом `state.py` (`init`, `get`, `set`, `complete`, `next`);
скилы не редактируют файл руками.

Правила:

- Резюм читает `phase`, `completed`, `step`, не угадывает по наличию файлов. Если
  файла фазы нет, а `completed` её содержит, это рассинхрон: остановиться и показать.
- `agents` действительны только в сессии `session`: в новой сессии агентов
  предыдущей не существует, `state.py` их очищает при несовпадении, спавн заново.
- Форсированный тир хранится здесь и переживает резюм.
- Часть наследует `profile` из состояния мультизадачи; противоречащий флаг это ошибка.
- Запись снимка `repos` идёт одним JSON-объектом на запись
  (`repos.{name}={"ref":"…","sha":"…"}`), чтобы sha из одних цифр остался строкой.

## research.md

- Секции: Task Summary, Source Files Map, Current State, Existing Patterns, Findings,
  Design Questions; при `HANDOFF` ещё `## Handoff` (`### Facts`, `### Decisions`,
  `### Affected Files and Contracts`, `### Open Questions for Dependents`).
- Кросс-репо: сразу после заголовка `Repository`, `Ref`, `Sha`; пути Source Files Map
  чужого репозитория с префиксом `{repo}:`.
- Design questions типизированы: `Q{n} [blocking]:` с ответом `A{n}:` и
  `Q{n} [deferred]:`. Отложенные вопросы в профиле без Spec могут остаться без ответа.
- Файл пишется только при `STATUS: done` агента.

## log.md

Журнал для человека. Секция на фазу с заголовком `## {Phase} ✅`, внутри факты:
что создано, сколько findings, сколько проходов, какие решения принял разработчик.
Шаги Implement как `### Шаг {N}: {название} ✅` с файлами, тестами и хешем коммита.
Доработка после возврата открывает секцию `## Итерация {N}` с замечаниями и повторяет
фазы под ней.

log.md коммитится вместе с артефактом фазы, не позже.

## task.md

```markdown
# {id}: {название}

## Исходная формулировка
{as-is из трекера или от разработчика}

## Контекст
- Трекер: {адаптер}, {ссылки}
- Тип, приоритет: {из трекера}
- Связанные задачи: {links}

## Финальная формулировка
{уточнённая постановка}

## Scope
- Пакеты, модули: {список}

## Tier
- {S|M|L} — {обоснование в одну строку}
```
