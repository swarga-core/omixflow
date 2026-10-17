---
id: omixflow-orchestrator-model
title: Модель оркестратора задачи не задаётся — фоновые сессии лида идут на модели по умолчанию, cost.py phase считает Fable как Opus
status: draft
type: bug
created: 2026-10-17
updated: 2026-10-17
origin: сессия omixflow-revision, 2026-10-17 (решение разработчика: в ближайший выпуск); сверено по scripts/sessions.py, scripts/cost.py, ~/.claude/settings.json и транскриптам SwAIS
target: omixflow
external:
links: [omixflow-agents-without-name]
---

**Контекст.** Лид запускает сессии задач `sessions.py launch` (0.7.0): `claude --bg --name N
…flags prompt` или окно Terminal с `claude -n N …` (`scripts/sessions.py:249`, `:263`); флага
`--model` нет. Модели агентов задаёт таблица тиров (`protocol/tiers.md`, «Модели»;
`models.strong`, `models.light` в flow.yaml), модель самой сессии-оркестратора — ничто.
`cost.py phase` пишет строку «Стоимость» в log.md; коэффициенты моделей он не выводит из
`cost-state` (запись появляется при выходе процесса, `scripts/cost.py:530`), а Fable в
`MODEL_FACTORS` нет — множитель 1,0, как у Opus (`scripts/cost.py:78`, `model_factor`).

**Проблема.**
- В `~/.claude/settings.json` разработчика `"model": "opus"`, а оркестраторы SwAIS идут на
  Fable: по транскриптам swais-lead — 793 ответа `claude-fable-5-1`, T-13 — 158 Fable и 45
  Opus, T-14 — 199 и 27, T-10 — весь прогон на Fable (и после `respawn` 2026-10-16). Фоновая
  сессия берёт модель родителя или умолчание харнесса, а не настройки.
- Fable по `cost-state` харнесса дороже Opus в 2,045 раза (T-10: `cost.py session` выводит
  `claude-fable-5-1: 2.045`). Оркестратор T-10 — $45,51 из $134,47; у задач базы на Opus
  (T-5…T-11, T-18, лид запускал их с Opus) оркестратор ~$28 при 205–333 запросах против 190
  у T-10. Пары 0.9 против базы по долларам несопоставимы.
- `cost.py phase` по T-10 дал 33,3M cost_eq при 42,7M по `session` — Fable посчитан как Opus.
- `claude respawn` флага `--model` не принимает; T-10 после respawn остался на Fable, но это
  была и модель запуска — сохраняет ли respawn модель, заданную при запуске, не проверено.

**Предложение.**
1. `models.orchestrator` в flow.yaml (по умолчанию — значение `models.strong`): модель сессии
   задачи задаётся при запуске, до триажа, поэтому одна на проект, а не строка таблицы тиров.
   Лид берёт её `cfg.py get models.orchestrator` и передаёт в `sessions.py launch --model X`
   (`claude --bg … --model X`, в окне — `claude -n … --model X`); разработчик может назвать
   другую для задачи — тогда она в `launch` и в строке log.md лида.
2. Start пишет модель оркестратора в `state.yaml` (`model`) по факту — из транскрипта сессии,
   модель её последнего ответа, тем же разбором, что `cost.py`, а не из флага запуска; модель
   не та, что просили (`models.orchestrator` или слово разработчика), — строка в log.md
   («просили opus, идёт fable»). Строка «Стоимость» называет модель.
3. `cost.py phase` берёт коэффициенты как `session`: из `cost-state` завершённых сессий
   проекта, когда текущей ещё нет, и с умолчанием `fable` (~2,0) в `MODEL_FACTORS` по
   данным `cost-state` 2026-10.
4. `sessions.py respawn` — проверить на пробной сессии, сохраняет ли `claude respawn` модель,
   заданную при запуске. Если не сохраняет, снаружи её не вернуть (модель меняется только
   изнутри, `/model`), и подъём с нужной моделью — `stop` и новый `launch` с `--model`
   и `--resume {id}`; записать, что верно. Не сохраняет — `sessions.py respawn` после подъёма
   сверяет модель сессии (транскрипт) с `model` в её `state.yaml` и пишет лиду предупреждение.

5. Дока `docs/releases/0.9.2-vs-0.9.1.md`: до 0.9.2 модель оркестратора не фиксировалась —
   T-13 и T-14 смешанные (158/45 и 199/27 ответов Fable/Opus), сравнения по долларам на задачах
   до 0.9.2 условны.

Состав согласован с omixflow-revision 2026-10-17: отдельный выпуск 0.9.2 (omixflow-lead), её
набор (G-66, G-70, stats.py, ADR в счёте plan.py files, researcher для M) — следующим номером;
пересечение одно — абзац про оркестратор под таблицей в `tiers.md`, строка researcher'а не
трогается.

**Сделано в 0.9.2** (2026-10-17): `models.orchestrator`, `sessions.py launch --model` и `{model}` в
промпте → `develop --model` → `state.yaml` `model_requested`; `cost.py phase` пишет `model` по
транскрипту и помечает «(запущена на …)». Fable — 1,8: вывод из `cost-state` раньше считал часовые
записи кэша 5-минутными (T-10: 2,045, с разбивкой 1,856; медиана 16 сессий 1,825). `claude respawn`
модель запуска сохраняет (проба на 2.1.302); после `/model` не проверено. T-11 шла на Opus, на Fable —
T-10, T-12, T-13, T-14.

**Критерии приёмки.** `sessions.py launch --model X` передаёт модель в оба режима запуска;
лид передаёт `models.orchestrator`; state.yaml и строка «Стоимость» называют модель
оркестратора; `cost.py phase` по T-10 даёт ~42,7M, а не 33,3M; поведение respawn проверено
и записано; тесты.
