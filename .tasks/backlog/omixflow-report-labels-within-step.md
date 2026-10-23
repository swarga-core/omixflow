---
id: omixflow-report-labels-within-step
title: В таблице меток отчётов нет повтора задания внутри шага (после красной проверки оркестратора) и задания-части шага
status: draft
type: docs
created: 2026-10-22
updated: 2026-10-22
origin: mewria MEW-36 (G-76 лида mewria-sim-lead, 2026-10-22), сверено по protocol/runtime.md и .tasks/board/done/MEW-36-tools-core-no-dev/reports mewria
target: omixflow
external:
links: []
---

**Контекст.** `protocol/runtime.md`, «Отчёт агента»: путь отчёта `{TASK_DIR}/reports/{phase}-{метка}.md`,
метки — `step{N}`, `tests-step{N}`, `fix-pass{N}`, `tests-pass{N}`, `sync{K}`, `sync-fix{K}`,
`spec-sync-pass{N}`, `gate-fix{K}` («вне шага плана и вне пакета фиксов прохода»), `tests-gate-fix{K}`.
«Проверки оркестратора», «Красная»: дефект кода уходит coder'у продолжением задания в счёт
`limits.coder_iterations`. Метка нужна и для имени фонового гейта (`gate.py {метка}-{гейт}`, его
сверяет `report.py check`); сами метки скрипты не проверяют.

**Проблема.**
- MEW-36, шаг 6: прогон проверки оркестратора S18 (`sim-player-tests` android) дал код 3 на уборке
  (`PermissionError` из `os.killpg`), фикс делал coder в счёт `coder_iterations`. Метки для повтора
  задания внутри шага нет: `gate-fix{K}` — вне шага плана.
- Шаг 6 состоял из двух заданий — фикс и доки; метки части шага тоже нет.
- Оркестратор взял метки сам: `implement-step6-fix1.md`, `implement-step6-docs.md` рядом с
  `implement-step6.md` (`reports/` карточки `done/MEW-36-tools-core-no-dev` на доске mewria). Другая
  сессия возьмёт другие, и сменщик, лид и `stats.py` такие отчёты не узнают по таблице.

**Предложение.**
1. Таблица `runtime.md`: `step{N}-fix{K}` — K-й повтор задания шага N после красной проверки
   оркестратора на приёмке шага (в счёт `coder_iterations`); `tests-step{N}-fix{K}` — то же для
   tester'а.
2. `step{N}-{part}` — задание-часть шага N, когда шаг идёт несколькими заданиями (код, доки); `{part}` —
   слово из плана или задания. Либо правило: шаг — одно задание, часть — продолжением с тем же путём.
3. Скил implement, 2.4 «Проверки оркестратора»: назвать метку повтора.

**Критерии приёмки.** Таблица меток называет повтор внутри шага и часть шага; implement 2.4 ссылается
на метку повтора; строка в `tests/test_lint.py`.
