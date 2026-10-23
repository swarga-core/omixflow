---
id: omixflow-review-spec-fix-tier-s
title: Правку решения спеки по finding ревью протокол отдаёт architect'у — в тире S его нет, исполнитель не назван
status: draft
type: docs
created: 2026-10-21
updated: 2026-10-21
origin: Swarga AI Studio T-22 (G-109 лида swais-lead, 2026-10-21), сверено по log.md T-22, skills/review/SKILL.md, protocol/review-cycle.md, skills/spec/SKILL.md и protocol/tiers.md
target: omixflow
external:
links: [omixflow-decision-wording-vs-choice]
---

**Контекст.** Исполнитель фикса ревью — по файлам правки: `skills/review/SKILL.md`, шаг 4 («spec и
plan → architect»), `protocol/review-cycle.md`, шаг 3 («`spec` и `plan` — architect'у задачи»; текст
spec.md без смены контракта правит и coder). В тире S architect не спавнится (`tiers.md`, таблица
ролей), спеку тира S пишет оркестратор инлайн (`skills/spec/SKILL.md`, «S: объединённый артефакт
инлайн»). Правки spec.md в пакете фиксов `report.py check` сверяет от снимка базовой линии
(`baseline --task`): правка выбора решения D-n после снимка — стоп SPEC AMENDMENTS.

**Проблема.**
- T-22 (тир S, профиль full), Review, проход 1: F2 `warning [architecture]` — подсказка нарушения при
  `dyn` вела к тихо несовпадающему статусу; лид решил D-402: изменить выбор решения D2 спеки (log.md
  T-22, стр. 78–79).
- Исполнителя правки D2 в тире S протокол не называет. Оркестратор поправил D2 и S1 сам, строкой в
  log.md: «Спека: D2 и S1 поправлены оркестратором по D-402 (тир S, спека — инлайн-артефакт
  оркестратора)» (стр. 82); по словам лида — до снимка baseline пакета фиксов. По смыслу верно, но вне
  буквы протокола; правка после снимка дала бы coder'у стоп SPEC AMENDMENTS.

**Предложение.**
1. `skills/review/SKILL.md`, шаг 4, и `protocol/review-cycle.md`, шаг 3: ветка тира S — «S: spec.md
   правит оркестратор (спека тира S — его инлайн-артефакт), до базовой линии пакета фиксов, строкой в
   log.md»; M и L — architect, как сейчас.
2. Там же — почему до базовой линии: снимок spec.md берётся с правкой, и coder пакета не получает
   стопа за чужое изменение выбора.

**Критерии приёмки.** В `review/SKILL.md` и `review-cycle.md` для тира S назван исполнитель правки
решения спеки по finding и момент (до базовой линии пакета фиксов); для M и L — architect, как
сейчас; строка в `tests/test_lint.py`.
