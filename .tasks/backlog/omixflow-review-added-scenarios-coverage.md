---
id: omixflow-review-added-scenarios-coverage
title: Сценарии, добавленные в спеку на Review и закрытые пакетом фиксов, — plan.py check даёт код 1, протокол не говорит, править ли план
status: draft
type: docs
created: 2026-10-23
updated: 2026-10-23
origin: Swarga AI Studio T-25 (G-126 лида swais-lead, 2026-10-23), сверено по log.md T-25 и skills/review, skills/spec, scripts/plan.py
target: omixflow
external:
links: [omixflow-plan-check-done-steps, omixflow-spec-snapshot-after-architect-fix]
---

**Контекст.** `plan.py check` требует, чтобы каждый сценарий spec.md был в Covers какого-то шага.
Скил spec после фикса спеки снова зовёт `plan.py check` («фикс мог добавить сценарий»); скил review
`plan.py check` не зовёт и о покрытии сценариев, добавленных на Review, не говорит. Шаги Implement к
Review сделаны (`steps_done`).

**Проблема.**
- T-25 (тир M, 0.9.6), Review, проход 1: finding F1 ревью кода решён лидом (lead D-441) с правкой
  спеки — architect добавил S11, S12, coder закрыл их в пакете фиксов прохода 1 (коммит ee365fc).
- Сессия по аналогии со скилом spec прогнала `plan.py check`: код 1, S11 и S12 не в Covers ни одного
  шага. Записала: «plan.py check после правки спеки: S11, S12 не в Covers шагов — их покрывает пакет
  фиксов прохода 1 (шаги 1–2 сделаны), план не правится» (log.md T-25, стр. 106).
- Правило не названо: править план задним числом (Covers сделанного шага — неправда) или нет; и
  `plan.py check` на Review — шум или проверка.

**Предложение.**
1. Скил review, шаг фиксов: сценарий, добавленный в спеку на Review, покрывает пакет фиксов; план не
   правится; строка в log.md «S{n}: покрыт пакетом фиксов прохода {N}».
2. `plan.py check`: сценарий, названный покрытым пакетом фиксов (строка log.md выше или Covers/MUTATIONS
   отчёта `reports/review-fix-pass{N}.md`), из проверки покрытия выходит, с пометкой в выводе.
3. Либо проще: на Review `plan.py check` не зовётся, и скил это говорит.

**Критерии приёмки.** Сценарий, добавленный в спеку на Review и закрытый пакетом фиксов, не даёт кода 1
в `plan.py check` (или проверка на Review не требуется и скил это называет); без такого покрытия —
по-прежнему код 1; тест в `tests/test_plan.py` для п. 2.
