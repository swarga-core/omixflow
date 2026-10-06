---
name: finalize
description: Finalize phase of the OMIXFlow pipeline — records the outcome in log.md, routes gotchas, comments in the tracker, proposes a pull request via the forge adapter (code, or research.md with artifacts for a research profile), moves the status, offers worktree exit; with --part integrates a multitask part (squash into the multitask branch, or a path-scoped commit of the part directory for a research profile), with --multitask closes a multitask (and tears down research-worktrees). Use after /omixflow:review or when the user says "финализируй", "закрой задачу", "интегрируй часть".
---

# OMIXFlow finalize

Фиксация результата. Код здесь не меняется.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Маршрутизация гочей:
`${CLAUDE_PLUGIN_ROOT}/protocol/phases.md`. Worktree:
`${CLAUDE_PLUGIN_ROOT}/protocol/worktree.md`. Мультизадача:
`${CLAUDE_PLUGIN_ROOT}/protocol/multitask.md`. Профили:
`${CLAUDE_PLUGIN_ROOT}/protocol/profiles.md`. Порты: tracker, forge, workspace.

## Активация

- `/omixflow:finalize {id}`; без аргумента id берётся из имени текущей ветки
  по шаблону `workspace.branch`.
- `/omixflow:finalize {id} --part {part}`: интеграция части мультизадачи.
- `/omixflow:finalize {id} --multitask`: финал мультизадачи, когда все части
  терминальны.

## Одиночная задача

Предусловие: `state.py next` даёт `finalize`. Свойство `finalize_artifact` профиля
(`state.py get TASK_DIR profile`, таблица `profiles.md`): `code` → шаги ниже;
`research` → раздел «Задача с `finalize_artifact: research`».

### 0. Синхронизация с базой

`sync.py check TASK_DIR`; база ушла вперёд после Review → синхронизация по
возможности `sync` порта workspace (порядок как в `implement`). Слияние с конфликтами
в коде возвращает задачу на повторный проход ревью по разрешениям (`reviewer-{id}`
проверяет дифф слияния); чистое слияние с зелёным полным набором гейтов идёт дальше.

### 1. Статистика

`base` из состояния:

```bash
git diff --stat {base}...HEAD
git log --oneline {base}...HEAD | wc -l
```

Из log.md: шаги, тесты, обновлённые project specs, findings ревью.

### 2. log.md

```markdown
## Finalize ✅
- Файлов создано/изменено: {N}
- Коммитов: {N}
- Тестов: {M} passed
- Project specs обновлены: {список или «нет»}
- Findings ревью: {N} total, {N} resolved
- Сдача: {PR url | squash {sha} в {base} | лиду}
```

### 3. Гочи

Под лидом гочи здесь не раскладываются: раздел «Сессия под лидом». Иначе перебрать
log.md (NOTES coder'а, замечания вне scope, особенности окружения) и предложить адреса
по phases.md в точке `gotchas`: дефект плагина → issue в репозитории плагина
(текст готовится, создание за разработчиком); особенность проекта → CLAUDE.md
проекта или проектный адаптер (правка с подтверждением); личное → память сессии.
Ничего не записывать молча.

### 4. Сдача

Способ: `workspace.delivery` конфига; не задан → `lead` у задачи под лидом (поле
`lead` состояния), иначе `pr`. Подтвердить в точке `delivery`: найденный способ
(Recommended) / два других.

**pr.** Превью (ветки, заголовок, body из шаблона), затем подтверждение в точке `forge.pr`:
Создать (Recommended) / Поправить / Пропустить. `pr_create` адаптера forge:
push ветки и создание PR в base из состояния. Body:

```markdown
## Summary
{финальная формулировка из task.md}

## Changes
{ключевые изменения из log.md}

## Test plan
- [ ] гейты typecheck, test, lint зелёные ({M} tests)
- [ ] {e2e / build, если применимо}

Task: {id}
```

`Task:` — ссылка на задачу по разделу «Ссылка на задачу» адаптера трекера, если он
есть, иначе id. С трекером `artifacts` артефакты в PR не входят: они в задаче трекера.

Адаптер `none`: push при наличии remote и сообщение, что PR открывается вручную.
CLI хостинга не настроен: инструкция, не ошибка.

**integrate.** Влить ветку задачи в базу без PR возможностью `integrate` порта
workspace (`workspace.integration`: squash или merge). Превью: ветка, база, файлы
(`git diff --stat {base}...HEAD`), сообщение коммита `feat({id}): {title}`; затем
подтверждение в точке `workspace.integrate`. База в `workspace.protected`:
подтверждает только разработчик, режим маршрута `lead` к этой точке не применяется.
Итог: хеш коммита в базе.

**lead.** Сессия под лидом ничего не вливает и PR не создаёт. Ветка синхронизирована
с текущей головой базы (шаг 0, `sync.py check` даёт `moved: false`), полный набор
гейтов зелёный на итоговом дереве; лиду уходит `done` с отчётом о готовности
(`protocol/lead.md`, «Сдача лиду»). Мерж делает лид.

### 5. Трекер

Текст комментария целиком (реализация завершена; ветка, коммиты, тесты, файлы; итог
сдачи: URL PR, хеш коммита в базе или «сдано лиду»), затем подтверждение в точке
`tracker.comment`: Добавить (Recommended) / Поправить / Пропустить. `comment` адаптера.

### 6. Статус

Спросить в точке `tracker.status`: «Статус {id}?» с рекомендацией по итогу сдачи:
PR или сдача лиду → in_review (Recommended); интеграция в базу → done (Recommended);
другой / не менять. `set_status`. Трекер с возможностью `artifacts`: перед сменой
статуса `publish {id} --from TASK_DIR`, задача переезжает с итоговыми артефактами.
Задача ушла в `done`, а у неё есть родитель-эпик: проверка и закрытие эпика по разделу
«Эпики» адаптера (вопрос в точке `tracker.status`).

### 7. Worktree

Сессия в worktree: спросить в точке `workspace.exit`: «Выйти?». Ветка ещё нужна
(открытый PR, сдача лиду) → keep (Recommended) / remove / остаться; ветка влита
в базу → remove (Recommended) / keep / остаться. `remove` блокируется
незакоммиченными изменениями. Worktree, в который вошли по `path`, `ExitWorktree`
не удаляет: сказать, что снос вручную.

### 8. Состояние и итог

`state.py finish TASK_DIR finalize` (фаза становится `done`). Коммит артефактов
(`artifacts.md`) до выхода из worktree. Трекер с возможностью `artifacts`: `finish` публикует
итог, тоже до выхода из worktree; статус задачи `done` → ещё раз `publish {id} --from
TASK_DIR` и при коде 0 удалить `TASK_DIR` (`finish` при сбое публикации только
предупреждает); при `in_review` рабочая копия остаётся для доработки.

```
Задача {id} финализирована: log.md обновлён, трекер {да/нет}, сдача {PR url |
squash {sha} в {base} | лиду}, ветка {branch}, worktree {оставлен/снесён/н/д}.
```

## Задача с `finalize_artifact: research`

Кода нет, статистики diff и тестов нет.

1. log.md: `## Finalize ✅` с числом файлов в карте, вопросов (отвечено, отложено).
2. Гочи как в шаге 3.
3. Коммит артефактов задачи с research.md (`artifacts.md`).
4. PR с артефактами из ветки задачи: предложить как способ `pr` шага 4 в точке
   `forge.pr` (Summary из task.md, ключевые findings вместо Changes, без Test plan).
   Трекер с возможностью `artifacts`: шаги 3–4 не выполняются, итог исследования
   живёт в задаче трекера.
5. Трекер: комментарий с итогами исследования в точке `tracker.comment`, как в шаге 5.
6. Статус и worktree как в шагах 6–7; `state.py finish TASK_DIR finalize`.

## Часть мультизадачи (`--part`)

По `part_integration` профиля мультизадачи: `integrate` → шаги ниже; `commit` →
раздел «Часть с `part_integration: commit`».

Предусловие: сессия в worktree части или ветка части доступна; implement и
review части завершены по её состоянию.

**Реконсиляция.** Ветки части уже нет, а блок говорит `in-work` или `in-review`:
интеграция прошла, блок не обновился. Найти squash-коммит в ветке мультизадачи
по сообщению `feat({id}): {part}`, довести блок до `done` с его хешем, комментарий.
Выход.

1. Финальная запись в log.md части: статистика ветки части относительно ветки
   мультизадачи.
2. Блок → `in-review` (`multitask.py set … status=in-review` на свежем описании,
   `update_description` с дисциплиной записи). Сводка и вопрос в точке
   `part-integrate`: Интегрировать (Recommended) / Оставить in-review / Пропустить
   часть (skipped).
3. Интеграция по адаптеру workspace (`integrate`): закоммитить всё в worktree
   части, включая log.md и state.yaml; `ExitWorktree keep`; убедиться, что дерево
   на ветке мультизадачи, иначе временный worktree; rebase ветки части на ветку
   мультизадачи; squash; проверить, что застейджены только файлы части
   (`git diff --cached --stat`), иначе СТОП в точке `deadlock`; один коммит `feat({id}): {part} —
   {title}`; push при `multitask.push`; снести worktree и ветку части. Пустая часть:
   не коммитить, статус `skipped`.
4. Блок → `done` с коротким хешем (или `skipped`). `comment`: «{part} → done.
   Squash `{sha}` → `{branch}`. Файлов: X, тестов: Y.»
5. Статус задачи и PR не трогать: это уровень мультизадачи. Вернуть управление
   `develop`.

Отказ в точке `part-integrate`: оставить `in-review`, worktree и ветку. Конфликт при
squash: СТОП, решение в точке `deadlock`, блок остаётся `in-review`.

## Часть с `part_integration: commit`

Правила в `multitask.md`, «Часть профиля research» (явные пути, push на общей
ветке). Обычно вызывается планировщиком в шаге завершения части, пока другие
researcher'ы работают. Предусловие: research.md части существует, фаза `research`
части закрыта. Rebase и squash нет.

**Реконсиляция.** Блок говорит `in-work`, а в истории `task/{id}` есть коммит с темой,
начинающейся на `docs({id}): research {part} — `: довести блок до `done` с его хешем,
комментарий. Выход.

1. Открытые вопросы `### Open Questions for Dependents` из `## Handoff` research.md
   части: спросить в точке `handoff`, ответы записать в Handoff research.md части.
2. log.md части: `## Finalize ✅`; `state.py finish {PART_DIR} finalize`.
3. Коммит только каталога части: пути `.tasks/{id}/{part}/` явно, сообщение
   `docs({id}): research {part} — {title}`. Никогда не «все изменения».
4. Push при `multitask.push` по правилу общей ветки: fetch; если `origin/task/{id}`
   не предок HEAD, rebase с autostash на него; конфликт → СТОП в точке `deadlock`,
   блок как есть.
5. После коммита, а при `multitask.push` — после успешного push: блок → `done`
   с коротким хешем коммита (после rebase, если он был), `comment`: «{part} → done. Коммит `{sha}` → `task/{id}`.» При трекере
   `none` коммит `multitask.md` по пути сразу после записи блока.

## Мультизадача (`--multitask`)

Предусловие: `multitask.py ready` на свежем описании даёт `all_terminal: true`.

1. log.md мультизадачи: частей N (done, skipped), суммарно коммитов, тестов,
   файлов по log.md частей. При `finalize_artifact: research` вместо коммитов
   и тестов число findings и отложенных вопросов сводного research.md (синтез уже
   выполнен планировщиком).
2. `comment` в точке `tracker.comment`: «Мультизадача завершена: {done}/{N} частей
   done{, {skipped} skipped}. Ветка `{branch}` готова.»
3. Статус в точке `tracker.status` (in_review по умолчанию).
4. PR из ветки мультизадачи в base: предложить по шагу 5 одиночного потока в точке
   `forge.pr`. При `finalize_artifact: research` PR несёт сводный research.md
   и артефакты частей.
5. При `finalize_artifact: research`: для каждого репозитория из `repos` состояния
   мультизадачи проверить research-worktree по детерминированному пути
   `{repo_path}/.claude/worktrees/research-{id}` и снести существующие
   с подтверждением в точке `workspace.exit`, в порядке адаптера workspace.
6. `state.py finish` для мультизадачи до `done`. При `part_isolation: shared`
   коммиты называют пути явно (`state.yaml`, `log.md`, `research.md` мультизадачи),
   push по правилу общей ветки.

## Сессия под лидом

Состояние задачи или части содержит `lead`: гочи из log.md уходят лиду пунктами
`G{n}` в `notice` (суть, факты с `path:line`, предлагаемый адрес) вместо раскладки
в шаге 3, кандидаты в память тоже; раскладывает лид (`protocol/lead.md`, «Гочи, бэклог
и память»); после `state.py finish … finalize` сессия шлёт `done` по `protocol/lead.md`:
способ сдачи и его итог, при сдаче лиду отчёт о готовности («Сдача лиду»).

## Правила

- Всё внешнее с подтверждением: комментарий (точка `tracker.comment`), PR (`forge.pr`),
  статус (`tracker.status`), выход из worktree (`workspace.exit`).
- Код не менять.
- PR body из артефактов, не выдумывать.
- Часть: при `part_integration: integrate` squash в один коммит, при `commit` коммит
  каталога части по пути; без PR и без смены статуса задачи.
- Артефакты коммитить до сноса worktree: иначе они пропадут вместе с ним.
