---
name: research
description: Research phase of the OMIXFlow pipeline — investigates the codebase (and web sources when needed) for a started task or part, possibly in a foreign repository from workspace.repos, produces research.md with a Source Files Map, then walks the developer through design questions. Tier- and profile-aware (S inline, M/L and non-triaged profiles via a named researcher agent that may stop on a blocking question). With --parts it is the scheduler of a research-profile multitask (parallel researchers, synthesis). Use after /omixflow:start or when the user says "исследуй задачу", "research".
---

# OMIXFlow research

Исследование кодовой базы и, при необходимости, внешних источников. Результат:
Source Files Map, текущее состояние, паттерны, findings, ответы на design questions.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Порты: lang; workspace для
кросс-репо research-worktree; tracker для блока и комментариев в режиме планировщика.
Тиры: `${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`. Профили:
`${CLAUDE_PLUGIN_ROOT}/protocol/profiles.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`.

## Активация

- `/omixflow:research {id}` или `{id}/{part}`.
- `/omixflow:research {id} --parts`: режим планировщика для мультизадачи профиля
  с `part_runner: scheduler` (обычно вызывает `develop`).
- `/omixflow:research "{тема}"`: standalone исследование без задачи; результат
  возвращается текстом, артефакты не создаются. Researcher одноразовый: без имени,
  без `CONTINUABLE`.

## Предусловия

`TASK_DIR/task.md` и `state.yaml` существуют; `state.py next` даёт `research`
(иначе показать состояние и спросить в точке `resume`, пересоздавать ли research).

## Алгоритм

### 1. Контекст

`task.md`: финальная формулировка, scope. Профиль из `state.py get TASK_DIR profile`,
его свойства по таблице `profiles.md`. Тир из `state.py get TASK_DIR tier` (нет → M;
при `triage: false` тира нет). Цепочка адаптеров lang. Для части мультизадачи
мутирующего профиля (`mutates: true`) собрать `PARTS_IN_FLIGHT`: для каждой другой
части со статусом не терминальным, у которой есть
`{artifacts.dir}/{id}/{other}/research.md`, взять файлы из её Source Files Map.

### 2. Нужен ли веб-ресёрч

Баг или рефакторинг: обычно нет. Новая фича с нестандартными паттернами: возможно.
Стандарты, спецификации, RFC: да. Веб-ресёрч не по умолчанию.

### 3. Исследование

**S-тир (инлайн).** Только в профиле с триажем. Оркестратор исследует сам,
read-only, инструментами навигации из адаптера lang. Результат: секция `## Research`
(mini Source Files Map + findings) в `TASK_DIR/spec.md`; отдельный research.md не
создаётся. Если вскрылся масштаб больше S: повысить тир (`state.py set tier=M`),
записать причину в log.md и выполнить фазу заново через агента.

**M, L и профиль с `triage: false`.** Именованный спавн `researcher` по шаблону
runtime.md, `model: {models.strong}` на L и всегда при `triage: false`:

```
Agent tool:
  subagent_type: "{агент researcher по маппингу}"
  name: "researcher-{id}"            # часть: "researcher-{id}-{part}"
  model: "{по tiers.md}"
  prompt: |
    PROJECT_ROOT: …   TASK_DIR: …   ADAPTERS: lang …   RULES: …   PARENT: …
    SCOPE: …   OUTPUT: file   CONTINUABLE: yes
    PARTS_IN_FLIGHT: …               # только при mutates: true
    ANSWERS: …                       # при перезапуске, из log.md
```

При веб-ресёрче параллельно второй агент `web-fetcher` с конкретным QUERY,
MAX_SOURCES 3, MAX_CHARS_PER_SOURCE 8000; его результат добавить секцией
`## External Research`. Research единственная фаза с параллельными агентами:
web-fetcher здесь и researcher'ы частей в режиме планировщика.

**Блокирующий вопрос.** Ответ агента начинается с `STATUS:`. На `STATUS: blocked`
спросить в точке `research-blocking`, записать вопрос и ответ в `log.md` задачи
или части и продолжить того же агента:
SendMessage to `researcher-{id}` (часть: `researcher-{id}-{part}`) с ответом.
Research.md появляется только после `STATUS: done`.

Формат записи в `log.md`, по нему же собирается `ANSWERS` при перезапуске: в секции
`## Research`, одна запись на вопрос

```markdown
### Blocking Q{n}
{вопрос}
A{n}: {ответ}
```

На `STATUS: done` секция становится `## Research ✅` с обычными фактами.

**Лимит**: два блокирующих вопроса на часть (на задачу для одиночной задачи),
считая записи `### Blocking Q{n}` в её `log.md`, включая отвеченные до перезапуска.
Третий: часть под планировщиком становится `blocked`, иначе остановиться и спросить
в точке `deadlock`.

Если агент оборвался без research.md: новый спавн с тем же именем и `ANSWERS`
из `log.md`.

### 4. Необъявленные зависимости (часть мутирующей мультизадачи)

Только при `mutates: true`. Пересечение Source Files Map части с `PARTS_IN_FLIGHT`:
остановиться, показать файлы и части, спросить в точке `scope-change`: объявить зависимость
(обновить блок через `multitask.py set … depends=…` и `multitask.md`) / продолжить
осознанно / изменить scope. Молча не продолжать.

### 5. Design questions

Секция `## Design Questions` из research.md (или из инлайн-исследования).
Спросить в точке `design-question` (`dialog.md`, «Design questions»: весь список одним
сообщением, ответ свободным текстом). Ответы записать в артефакт дословно, с условиями,
которые разработчик добавил к варианту:

```markdown
Q1 [deferred]: {вопрос}
Context: {контекст}
A1: {ответ разработчика дословно}
```

В профиле с фазой Spec ответы обязательны для architect: без них spec не пишется.
В профиле без Spec отложенные вопросы предлагаются (ответить сейчас / оставить
отложенным) и могут остаться без ответа в research.md.

### 6. Состояние и журнал

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" finish "{TASK_DIR}" research
```

`log.md`: `## Research ✅` с числом файлов в карте, вопросов и ответов, веб-ресёрч
да/нет, пометка `(inline)` для S. Коммит артефактов (`artifacts.md`; в мультизадаче с
`part_isolation: shared` только пути каталога части, правило «Явные пути»
multitask.md).

### 7. Итог (mode manual)

```
Research завершён: {артефакт}, файлов в карте: {N}, вопросов: {N} (отвечено: {M}).
Следующий шаг: /omixflow:spec {id}      # или finalize, если в профиле нет spec
```

## Режим планировщика (`{id} --parts`)

Правила процесса в `multitask.md`, разделы «Часть профиля research», «Планировщик»,
«Синтез», «Кросс-репо»; здесь только порядок действий. `me` из `current_user`,
`TASK_DIR = {artifacts.dir}/{id}`.

1. Свежее описание из трекера (при трекере `none` блок из `multitask.md`) → файл;
   `multitask.py ready --from {desc} --owner {me} --parallel {multitask.parallel_parts}`.
2. Активный репозиторий: первый из `active_repos`, если он не пуст, иначе первый
   ключ `ready_by_repo`. Запустить до `slots` готовых частей этого репозитория: для
   каждой вложенный `start {id} --part {part}`, затем фоновый именованный
   `researcher-{id}-{part}` с `CONTINUABLE: yes`, `PROJECT_ROOT` репозитория (домашний
   корень, checkout чужого или его research-worktree; один корень на все части
   репозитория), `INPUTS` из `depends`, `HANDOFF: required`, если от части кто-то
   зависит, для чужой части `REPO` и кросс-репо спавн по runtime.md.
3. Перед запуском каждой чужой части: `resolve.py repo {name} --json` против sha
   снимка из `state.py get TASK_DIR repos`. HEAD ≠ sha или dirty → research-worktree
   по адаптеру workspace (создать с подтверждением в точке `workspace.branch`, если
   его нет). Если части
   репозитория уже идут на checkout, новые части этого репозитория ждут их
   завершения, затем группа переходит на research-worktree.
4. `STATUS: blocked` от `researcher-{id}-{part}`: вопрос в точке `research-blocking`,
   запись `### Blocking Q{n}`
   в `log.md` части, SendMessage to `researcher-{id}-{part}` с ответом.
   `STATUS: done`: `## Research ✅` в `log.md` части,
   `state.py finish {TASK_DIR}/{part} research`, вложенный
   `finalize {id} --part {part}` (коммит по пути, push по правилу общей ветки,
   `done` с хешем после коммита, а при `multitask.push` — после успешного push),
   пересчитать `ready`. Остальные researcher'ы в это время
   работают.
5. Сбой агента или третий блокирующий вопрос: `multitask.py set … status=blocked`,
   причина в комментарии трекера и в `log.md` части; зависимые ждут, независимые
   продолжают.
6. Цикл до тех пор, пока ничего не работает и ничего нельзя запустить; сводка текстом
   (готовые, заблокированные с причинами, ждущие). Если `all_terminal`: синтез,
   спавн `researcher-{id}` с `MODE: synthesis` и `INPUTS` всех частей; отложенные
   вопросы в точке `design-question`, ответы в `.tasks/{id}/research.md`; коммит
   `docs({id}): research synthesis` с явными путями;
   `state.py finish {TASK_DIR} research`.
7. Резюм в новой сессии: для моих частей `in-work` коммит части в `task/{id}` есть →
   довести блок до `done`; research.md есть, но не закоммичен → `finalize --part`;
   research.md нет → новый `researcher-{id}-{part}` с `ANSWERS` из `log.md` части.
   Перезапуски группируются по репозиторию тем же правилом, что в шаге 2.
   Заблокированные части: спросить в точке `part-blocked` (разблокировать в `pending`
   / `skipped` / оставить), независимые не останавливать.
8. Каждый коммит планировщика называет пути явно, никогда не «все изменения»; при
   трекере `none` `multitask.md` коммитится по пути сразу после каждой записи блока.

## Масштаб

| Задача | Глубина | Файлов в карте |
|---|---|---|
| точечный баг | несколько файлов вокруг симптома | до 8 |
| изменение API | пакет и потребители | 10–15 |
| новая фича | несколько пакетов и паттерны | 15–25 |
| архитектурное изменение | всё затронутое плюс документация | 25+ |

## Правила

- Source Files Map обязателен: без него spec и plan не имеют контекста.
- Исследование read-only; чужой репозиторий только читается.
- Вопросы лучше предположений.
- Веб-ресёрч только когда действительно нужен.
- В worktree и в чужом репозитории агентам только абсолютные пути.
