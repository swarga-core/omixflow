# AL-1147: журнал

## Refine ✅

- Постановка в трекере признана полной; в описание добавлена секция «Уточнённая формулировка» (2026-09-28).
- Решение разработчика: базовая ветка `task/AL-1140` (стек), так как на `main` нет `flow.yaml`, адаптера `py` и части правимого кода.
- Решение разработчика: живой прогон на `eps-omix-lib` и `eps-eal-omix` и `doctor` в трёх проектах — ручная приёмка после Finalize, не гейт пайплайна; правки чужих `flow.yaml` вне scope.
- Тир L подтверждён.

## Start ✅

- Ветка `task/AL-1147` от `task/AL-1140` в основном дереве (решение разработчика: без worktree, как AL-1140).
- Предмет задачи в базе проверен: `PHASES` в `scripts/state.py`, точный маркер `MARK_START` в `scripts/multitask.py`, `parallel_per_owner` в `skills/start/SKILL.md`. Тесты базы зелёные (43).
- Артефакты: task.md, state.yaml (kind task, tier L, mode pipeline), log.md.
- Трекер: статус Draft → In Work (подтверждено разработчиком).
- Коммит артефактов: 254a9f4.

## Research ✅

- Researcher (opus, тир L) → research.md: Source Files Map 46 файлов, 23 findings, веб-ресёрч нет.
- Ключевые находки: маркер с атрибутом сегодня ломает `find_block` целиком (has/extract/set/seed); `render` теряет неизвестные колонки и стиль разделителя; `parallel_per_owner` нигде не enforced в коде; `resolve.py --project` уже есть, без flow.yaml exit 2 у `adapter` и `agent`; валидатор схемы не умеет `patternProperties`; doctor только OK/WARN/FAIL; лint таблиц в protocol/ нет; инвариант 7 в glossary отсутствует (постановка ошибалась); `start --part` не отмечает refine/start завершёнными в state части (существующая дыра).
- Design questions: 6, все отвечены разработчиком:
  - A1 хирургический `set` (verbatim всё, кроме ячеек изменённой строки);
  - A2 причина `blocked` в комментарии трекера и log.md части, колонки нет;
  - A3 `seed --profile/--repo` плюс диалог в `refine --multitask`;
  - A4 doctor: info как OK с деталью, без нового статуса;
  - A5 `resolve.py --fallback-project {home}`;
  - A6 submodule в research-worktree всегда, `workspace.setup` чужого проекта по `setup: true`.
- Коммит: 665b3ca.

## Spec ✅

- architect-AL-1147 (MODE spec) → spec.md: 9 слайсов, 21 решение (D1–D6 = A1–A6, D7–D21 собственные). D5 уточнено architect'ом: агент всегда из домашнего проекта, чужой даёт только RULES; принято оркестратором без эскалации (сессия спавнит только свои агенты).
- reviewer-AL-1147: проход 1 — 15 findings (0 critical, 8 warning [spec], 7 suggestion), все auto-accept по review-cycle; finding 7 закрыт альтернативой «явное свойство `part_runner` + суженное утверждение о расширяемости». Проход 2 — 1–15 resolved, новые 16–18 (18 warning: rebase в общем дереве), приняты. Проход 3 — approve, 16–18 resolved, неблокирующие 19–20 приняты и исправлены architect'ом без четвёртого прохода (лимит `review_passes: 3`).
- Итог: 20 findings, все resolved, проходов 3.
- Коммит: 51d8266.

## Plan ✅

- architect-AL-1147 (MODE plan, continuation) → plan.md: 8 шагов (state.py профили → multitask.py маркер/set → multitask.py repo → схема/lib/resolve → doctor → протокол и порты → researcher и скилы → README/CHANGELOG). Шаг 7 умышленно один коммит: скилы ссылаются друг на друга, линт SendMessage/named spawn работает по файлу.
- reviewer-AL-1147: проход 1 — 4 findings (1 warning [plan], 3 suggestion), все auto-accept; проход 2 — approve, все resolved.
- Итог: 4 findings, все resolved, проходов 2.

## Implement

- coder-AL-1147 (opus), ITERATION_LIMIT 7. Coder пишет тесты шага сам с мутационной проверкой; tester спавнится только если coder тесты не покрыл.

### Шаг 1: Profile canon in state.py ✅
- Файлы: scripts/state.py, protocol/profiles.md (новый), tests/test_state_multitask.py (ProfileTests, parent для test_part_requires_multitask_fields), tests/test_lint.py (ProfilesLint), CHANGELOG.md
- Гейты: test PASS, lint PASS
- Тесты: 51 passed; мутаций 16, все красные
- Итерации: 0/7
- NOTES вне scope: `--forced` при `triage: false` не отклоняется (spec не требует); `tier = None` и порядок `completed` по профилю без мутационно-чувствительного теста (ненаблюдаемо).
- Коммит: 79432a4

### Шаг 2: Multitask marker, meta, surgical set ✅
- Файлы: scripts/multitask.py (START_RE/END_RE по строке, marker_attrs/marker_errors, declared_profile/strict_profile, block_meta + `meta`, set_row), tests/test_state_multitask.py (MarkerTests, 13), protocol/multitask.md («Идентификация» → «Маркеры»), adapters/tracker/PORT.md, CHANGELOG.md
- Гейты: test PASS, lint PASS
- Тесты: 63 passed; мутаций 21+4, после добавления тестов на якоря все красные
- Итерации: 0/7
- NOTES: `set title=—` по-прежнему отклоняется («пустой title»); перерисованная строка теряет ведущий отступ; `local.md`/`youtrack.md` показывают маркер без атрибута (корректно, атрибут опционален); тест «объявленный профиль меняет валидацию в set/waves» переносится в шаг 3.
- Коммит: 0bf13e4

### Шаг 3: Multitask repo column, profile-aware validate/ready/seed/file ✅
- Файлы: scripts/multitask.py (Row.repo, block_header, parse_repos, validate(profile, repos), set repo= только pending, ready --parallel, seed --profile/--repo, render --profile, multitask_file по профилю), tests/test_state_multitask.py (RepoProfileTests, 9, включая отложенный тест шага 2), protocol/multitask.md, CHANGELOG.md
- Гейты: test PASS, lint PASS
- Тесты: 72 passed; мутаций 26+2, после добавления кейса с чужим owner все красные
- Итерации: 0/7
- NOTES: `set repo=` на блоке без колонки → exit 2 (колонку добавляет только seed/render; известное ограничение, связано с «добавление частей при повторном refine» вне scope); `waves`/`file` не принимают `--repos`; `multitask_file` получил дополнительный kwarg `repo_column` (без него нельзя отличить колонку из одних `—`).
- Коммит: 79f5ff0

### Шаг 4: Config schema, library helpers, resolve.py ✅
- Файлы: schema/flow.schema.json (definitions.repo, workspace.repos, multitask.parallel_parts), templates/flow.yaml, scripts/omixflow_lib.py (resolve_repo_ref, repo_checkout_state, normalize_remote), scripts/resolve.py (--fallback-project, repo NAME [--json], repo --list), adapters/workspace/PORT.md, tests/test_scripts.py (WorkspaceReposSchemaTests 4, ForeignRepoTests 9, фикстура foreign_clone с локальным bare origin), CHANGELOG.md
- Гейты: test PASS, lint PASS
- Тесты: 85 passed; мутаций 30, 28 красных, 1 закрыт добавлением фикстуры, 1 неуловим (`:(exclude).claude/worktrees` при `--untracked-files=no`)
- Итерации: 1/7
- NOTES: `fallback_cfg` в resolve_repo_ref = конфиг при отсутствии чужого flow.yaml, resolve.py домашний конфиг не передаёт (D5); `repo NAME` без `--json` печатает только sha; отсутствующий path → sha/head null, exit 1 (doctor в шаге 5); `script`/`repo` с `--fallback-project` используют чужой корень.
- Коммит: 4e296a2

### Шаг 5: Doctor checks for workspace repos ✅
- Файлы: scripts/doctor.py (check_repo, task_phase, RESEARCH_WORKTREE_WARN), tests/test_scripts.py (DoctorRepoTests, 5), CHANGELOG.md
- Гейты: test PASS, lint PASS
- Тесты: 90 passed; мутаций 20, все красные
- Итерации: 0/7
- NOTES: `git`-проверка строже spec: FAIL, если путь внутри git-репозитория, но не его toplevel (иначе `resolve.py repo` укажет не на тот корень); `research worktrees` считает каталоги `.claude/worktrees/research-*`, а не `git worktree list`, поэтому видит и снятые с учёта каталоги; подсказка о порядке сноса в WARN ссылается на секцию git.md, которая появится в шаге 6.
- Коммит: 519721d

### Шаг 6: Protocol documents and port rules ✅
- Файлы: protocol/{phases,tiers,runtime,review-cycle,multitask,artifacts,dialog,glossary,worktree}.md, adapters/workspace/PORT.md, adapters/workspace/git.md, adapters/lang/PORT.md, CHANGELOG.md
- Гейты: test PASS (90/90, включая линты терминологии, инструментов, SendMessage, профилей), lint PASS
- Тесты: новых нет (механических правил не появилось)
- Итерации: 0/7
- Решение оркестратора: spec просил определить «фаза» через «этап», но «этап» запрещён таблицей самого glossary; оставлена формулировка coder'а «единица пайплайна в глобальном порядке; набор фаз задачи задаёт профиль». Spec не правится (расхождение в одном слове).
- NOTES: строка Research в phases.md теперь описывает только действия режима планировщика, явного «нет» для одиночной задачи не осталось; протокол называет флаги скриптов (`--parallel`, `--fallback-project`), это допустимо (скрипты плагина не «инструменты адаптеров»); полные правила планировщика и research-части живут в multitask.md, скилы шага 7 должны ссылаться, а не повторять.
- Коммит: 2f6b882

### Шаг 7: Researcher agent and skills ✅
- Файлы: agents/researcher.md, skills/research/SKILL.md (переписан: именованные continuation-спавны, blocking-вопросы, планировщик), skills/start/SKILL.md, skills/develop/SKILL.md (путь MS для `part_runner: scheduler`), skills/finalize/SKILL.md (секции `finalize_artifact: research` и `part_integration: commit`), skills/refine/SKILL.md (шаги 0 и 1a), CHANGELOG.md
- Гейты: test PASS (90/90), lint PASS
- Тесты: новых нет; мутации линтов 3/3 красные (снятие named spawn, SendMessage researcher'у в finalize, MCP-id в теле агента)
- Итерации: 0/7
- NOTES вне scope: свойства профиля скилы читают из таблицы profiles.md (скрипт их не печатает; кандидат `state.py profile-props`, вне плана); существующий integrate-поток части никогда не закрывал `finalize` в state части (существующая дыра, не трогалась).
- Коммит: 1816a57

### Шаг 8: README, CHANGELOG consolidation, full verification ✅
- Файлы: README.md, CHANGELOG.md (`[Unreleased]`: сводка, «Совместимость» с `plugin.min_version`, Added/Changed, дубли шагов 1–7 слиты)
- Гейты: test PASS (90/90), lint PASS
- Проверки плана: у всех 10 файлов protocol/, трёх PORT.md и git.md есть строка CHANGELOG; старые формулировки из protocol/ ушли; test_lifecycle нетронут; таблица профилей = PROFILES.
- Итерации: 0/7

## Implement ✅

- Шагов 8/8, коммитов 8, один coder без ротации (лимит 10 шагов не достигнут), tester не понадобился: coder покрывал каждый шаг тестами с мутационной проверкой.
- Тесты: 43 → 90 passed.
- Коммит шага 8: 596a916.

## Review ✅

- Полные гейты до ревью: test 90/90, lint PASS.
- Findings: 6 total (0 critical, 1 warning, 5 suggestion)
- Принято: 5, отклонено: 0, отложено: 1
- Проходов: 2 (проход 2 approve)
- Резолюции:
  - 1 warning [code]: CRLF-блок не находился (`$` под re.M не съедает `\r`), подтверждено пробой reviewer'а; фикс `[ \t\r]*$` + test_crlf_block.
  - 2 [code]: `set` отклоняет `|` и переводы строк в значении (иначе ячейка ползла в соседнюю колонку).
  - 3 [spec-sync]: «done с хешем после коммита, а при multitask.push после push» в finalize, multitask.md и research (иначе при push: false часть не доходила до done).
  - 4 [code, low confidence, принято разработчиком]: путь MS в develop роутит по `state.py next` (research / finalize / done).
  - 6 [code]: `SLUG_RE` в omixflow_lib, `multitask.check_profile` заменён на `state.check_profile`; doctor не импортирует multitask/state.
  - 5 [architecture, low confidence, отложено разработчиком]: скилы читают свойства профиля из таблицы profiles.md; команда `state.py`, печатающая профиль со свойствами JSON, вынесена в отдельную задачу (гоча для Finalize).
- Тесты после фиксов: 92 passed.
- Коммит: 0baa8fa

## Finalize ✅

- Файлов создано/изменено: 38 (без .tasks), +3781/−234
- Коммитов: 13 (4 артефактов, 8 шагов, 1 фиксы ревью)
- Тестов: 92 passed (было 43)
- Project specs обновлены: protocol/{profiles (новый), phases, tiers, runtime, review-cycle, multitask, artifacts, dialog, glossary, worktree}.md; adapters/tracker/PORT.md, adapters/workspace/PORT.md, adapters/workspace/git.md, adapters/lang/PORT.md; CHANGELOG с пометками protocol/port
- Findings ревью: spec 20 resolved / plan 4 resolved / code 6 (5 resolved, 1 отложен)
- Ручная приёмка за разработчиком (решение Refine): живой прогон research-мультизадачи на eps-omix-lib и eps-eal-omix, `/omixflow:doctor` в трёх проектах после добавления `workspace.repos`.
- Гочи: 4 issue плагина подготовлены в `issues-al-1147.md` (не коммитится): команда свойств профиля, `set repo=` без колонки + добавление частей, `finalize` части в integrate-потоке, мелочи (`--forced`, строка Research, подсчёт research-worktree). Память сессии: стек веток AL-1147 → AL-1140 и ручная приёмка.
- Трекер: комментарий добавлен; статус In Work оставлен (решение разработчика: до живого прогона).
- PR: пропущен до мержа AL-1140 (решение разработчика); ветка `task/AL-1147` запушена в origin.
- Worktree: н/д (основное дерево).
