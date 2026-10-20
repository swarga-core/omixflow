---
id: omixflow-plan-check-done-steps
title: plan.py check посреди Implement — «CREATE … already exists» по файлам уже сделанных шагов
status: draft
type: bug
created: 2026-10-19
updated: 2026-10-19
origin: Swarga AI Studio T-16, Implement (G-97 лида swais-lead, 2026-10-19, сессия на 0.9.4–0.9.5), сверено по транскрипту T-16 и scripts/plan.py
target: omixflow
external:
links: [omixflow-architect-plan-quality]
---

**Контекст.** `plan.py check` (0.9.0) сверяет пути шагов с деревом: CREATE файла, который уже
есть, — «the file already exists (MODIFY?)», MODIFY или DELETE отсутствующего — «is not in the tree»
(`scripts/plan.py`, проверка `file_ops`). Рассчитан на план до Implement; скилы spec и plan
зовут его до ревью и после фиксов.

**Проблема.**
- T-16: оркестратор запускал `plan.py check` и посреди Implement — после шагов 1–3
  (2026-10-19 08:31) и после шага 7 (11:23), сверяя план с деревом. Вывод: «PLAN CHECK: 9 problems»,
  затем «17 problems», почти все — «step 1: CREATE `packages/server/src/db/trace-views.ts` — the
  file already exists (MODIFY?)» и т. п. по файлам, которые создали сами сделанные шаги.
- Шум маскирует настоящие расхождения: среди 17 строк не видно той, что о шаге, который ещё
  впереди.

**Предложение.**
1. `plan.py check` читает `state.yaml` (`steps_done`, `step`) задачи: у сделанного шага CREATE не
   сверяется с деревом (файл создал он сам), MODIFY/DELETE — тоже; проверяются поля и чекпоинт,
   как прежде. Файлы, которые создали сделанные шаги, для последующих шагов — существующие (как уже
   учитывается `created` по порядку шагов).
2. Вывод называет, что сделанные шаги по дереву не сверялись («шаги 1–3 сделаны: пути не
   сверяются»).
3. По желанию: `--step N` — сверить только шаги от N.

**Критерии приёмки.** `plan.py check` посреди Implement без ложных «already exists» по сделанным
шагам; тест на план с `steps_done: [1, 2]` и созданными этими шагами файлами.
