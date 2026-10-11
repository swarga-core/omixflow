---
id: omixflow-tester-probe-existing-behaviour
title: Tester пропускает мутационную пробу теста «существующего поведения» и непрошенную пробу
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-18 (G-38 лида swais-lead, 2026-10-11, сессия на определениях агентов до 0.6.2), сверено по транскрипту tester-T-18, log.md и reports/review-tests-pass1.md
target: omixflow
external:
links: [omixflow-mutations-per-test, omixflow-tester-mutations, omixflow-tester-findings-input]
---

**Контекст.** `agents/tester.md`, «Mutation-check your tests»: «Every NEW test you write is
verified by mutation…», рецепт — у coder'а; с 0.6.1 `MUTATIONS` — строка на каждый новый
тест. Implement 2.3 и review сверяют `MUTATIONS` по каждому новому тесту и возвращают задание
при пропуске.

**Проблема.** T-18, пакет фиксов прохода 1 ревью кода: tester-T-18 добавил три проверки, пробу
сделал только для теста SAVEPOINT + RELEASE. Для двух других — обоснования в первом ответе:
- `ActionResponse.safeParse({ event })` (новое утверждение в существующем тесте): «I did not
  run a mutation probe for it, since the schema is unchanged and it checks existing behaviour»;
- SAVEPOINT + ROLLBACK TO: «it has no mutation probe of its own, since none was requested».
Пробы предлагал coder в NOTES своего отчёта (`review-fix-pass1.md`) — для теста к #3, и tester
прочёл список как исчерпывающий. Оркестратор вернул задание, обе пробы дали RED
(`review-tests-pass1.md`: «проверка существования → false» — RED трёх тестов; `result`
optional — RED). Сверка 2.3 сработала, но стоила лишнего круга.

**Предложение.** `agents/tester.md` (и тот же абзац у coder'а): пробу получает каждый новый
тест и каждое новое утверждение в существующем тесте — независимо от того, назвал ли пробу
кто-то в задании, и когда тест закрепляет поведение, которое уже было (проба ломает это
поведение). «Схема не менялась», «поведение уже было», «пробу не просили» — не причины.
Пробу сделать нельзя — строка `MUTATIONS` с причиной; оркестратор её принимает.

**Критерии приёмки.** Формулировка в tester.md и coder.md, линт на маркер; в прогоне нет
возврата задания за пропущенную пробу.
