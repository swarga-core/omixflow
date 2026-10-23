---
id: omixflow-spec-snapshot-after-architect-fix
title: report.py check считает правку spec.md architect'ом посреди пакета фиксов правкой coder'а — «вернуть spec.md» откатил бы решение лида
status: draft
type: bug
created: 2026-10-21
updated: 2026-10-21
origin: Swarga AI Studio T-19 (G-118 лида swais-lead, 2026-10-21), сверено по log.md T-19 и транскрипту сессии T-19
target: omixflow
external:
links: [omixflow-decision-wording-vs-choice, omixflow-review-spec-fix-tier-s]
---

**Контекст.** `report.py check` сверяет SPEC AMENDMENTS coder'а со снимком spec.md базовой линии
(`report.py baseline --task`, скил review, шаг 4: «перед каждым заданием прохода»). Правка выбора
решения или Contracts — стоп; `--amend-decision D{n}` (0.9.5) снимает стоп только для правки, которую
по заданию оркестратора сделал сам coder. Правку spec.md другим агентом между снимком и отчётом
скрипт не отличает.

**Проблема.**
- T-19 (тир M), Review, проход 1: лид решил F1 (D-419) с правкой контракта spec.md (Contracts, D7);
  оркестратор заказал её architect'у, пока coder работал над пакетом фиксов.
- `report.py check` отчёта coder'а: «SPEC AMENDMENTS: none, а spec.md изменён в секциях «Contracts»,
  «Decisions» … — это смена объёма, решения или контракта: не правка coder'а, а остановка … вернуть
  spec.md и остановиться» (транскрипт T-19). Текст уходит агенту «как есть» — отправленный, он
  откатил бы решение лида.
- Сессия обошла: пересобрала снимок базовой линии на spec.md после правки architect'а (blob 3cedd44)
  → `VERDICT: ok` (log.md T-19, стр. 233–235).

**Предложение.**
1. Правило протокола (скил review, шаг 4; `review-cycle.md`): правка spec.md architect'ом посреди
   пакета фиксов — до задания coder'у, если можно; иначе после неё оркестратор пересъёмывает снимок
   (`report.py baseline --task` заново или флаг ниже) и пишет строку в log.md «снимок spec.md
   пересобран после правки architect'а: {blob}».
2. Флаг `report.py check --spec-snapshot {blob}` — снимок spec.md явным blob'ом, без пересъёма всей
   базовой линии (дельта кода остаётся от прежнего снимка).
3. В вердикте с правкой spec.md, которой coder не называет, — подсказка оркестратору «если правил не
   coder — снимок после правки», не только сообщение агенту.

**Критерии приёмки.** Правка spec.md не coder'ом между базовой линией и отчётом не даёт вердикта
«вернуть spec.md»; протокол называет, кто и когда пересъёмывает снимок; тест в `tests/test_report.py`.
