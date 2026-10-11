---
id: omixflow-gate-name-from-report
title: Имя фонового гейта агента — выводимо из пути отчёта и названо в отчёте
status: draft
type: bug
created: 2026-10-10
updated: 2026-10-10
origin: Swarga AI Studio T-3 (G-17 лида swais-lead, 2026-10-10, OMIXFlow 0.6.0), сверено по транскриптам coder-T-3 и оркестратора
target: omixflow
external:
links: [omixflow-subagent-background-stall, omixflow-report-labels-cd]
---

**Контекст.** Долгий гейт идёт через `scripts/gate.py start {имя}` / `poll {имя}`; лог —
`{git-каталог дерева}/omixflow-gates/{имя}.log`. Имя фиксирует только coder и только для шага
плана: `step{N}-{gate}` (`agents/coder.md:67-71`). `runtime.md`, «Гейты» и `agents/tester.md`
говорят `{имя}` без шаблона.

**Проблема.** T-3, синхронизация с базой (sync mode): coder-T-3 запустил
`gate.py start step-sync-build` — имя придумано, шаблона для синхронизации нет. В отчёте —
«build exit 0 (фоновый, через `gate.py`)», без имени. Оркестратор сверял отчёт
`gate.py poll build` и получил «гейт build не запускался: нет …/omixflow-gates/build.log»;
лог нашёлся листингом каталога. То же ждёт пакеты фиксов (`fix-pass{N}`), починки гейта
(`gate-fix{K}`) и tester'а — у всех имя свободное.

**Предложение.**
- Одно правило в `runtime.md`, «Гейты»: имя фонового гейта агента — `{метка отчёта}-{gate}`,
  где метка — имя файла `REPORT_PATH` без `.md` (`implement-step3-build`,
  `review-fix-pass1-e2e`; в T-3 отчёт синхронизации — `review-sync1.md`, гейт был бы
  `review-sync1-build`); у оркестратора — `{phase}-{gate}`
  (`delivery-build`, как он уже делает в T-3). Метки уже уникальны на задание (таблица
  «Отчёт агента»), значит и имена гейтов.
- coder и tester: шаблон вместо `step{N}-{gate}` и свободного `{name}`; строка GATES отчёта для
  фонового гейта — `build: PASS (gate.py {имя}, EXIT 0)`.
- Линт: шаблон имени в `coder.md` и `tester.md` совпадает с `runtime.md`.

**Критерии приёмки.** Оркестратор находит фоновый гейт агента по отчёту или выводит имя из
`REPORT_PATH`, без листинга каталога; в sync mode и пакете фиксов имя не придумывается.
