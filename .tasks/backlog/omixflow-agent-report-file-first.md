---
id: omixflow-agent-report-file-first
title: Обычный субагент считает итоговый ответ отчётом и не пишет файл по REPORT_PATH
status: draft
type: bug
created: 2026-10-10
updated: 2026-10-10
origin: Swarga AI Studio T-1 (G-9 лида swais-lead, 2026-10-10), сверено по транскрипту tester-T-1
target: omixflow
external:
links: [omixflow-agent-report-double, omixflow-coder-report-file]
---

**Контекст.** С 2026-10-10 режим команд агентов выключен: агенты — обычные субагенты, без
SendMessage. Для них строка `PARENT` шаблона спавна (`runtime.md:87-91`, 0.5.1) говорит:
«without SendMessage, or when the send fails, your final reply is the report».

**Проблема.** tester-T-1 (Review, проход 2, F7; первый обычный субагент в T-1 вместе
с reviewer-T-1-code) закончил ход итоговым ответом-отчётом и не записал
`reports/review-tests-pass2.md`. Оркестратор по «Ответ без итогов — не отчёт»
(`runtime.md:181-184`) вернул задание, файл появился вторым ходом. Все 9 отчётов coder'ов
(teammates, со SendMessage) и findings обоих reviewer'ов лежат файлами.

Формулировка «Output format» у tester'а не слабее, чем у coder'а: в обоих «Write the full
report to REPORT_PATH, then report to PARENT». Вероятные причины:
1. Строка `PARENT` называет итоговый ответ отчётом — у агента без SendMessage она спорит
   с «полный отчёт — в файл». Teammates шли по ветке SendMessage, и спор не проявлялся.
2. Чек-лист оркестратора в промпте («At the end: all four gates…, TREE STATE») не упоминал
   файл; ход занял ~35 секунд.

Один случай — сигнал, не закономерность; но теперь по ветке «без SendMessage» идут все агенты.

**Предложение.**
- `PARENT`: «your final reply is the short report» (сводка до 10 строк с путём), не «the
  report»; линт строки `PARENT` обновить.
- tester, coder, researcher: первая строка «Output format» — «A reply without the file at
  REPORT_PATH is not a report: write the file first».
- Оркестратор: проверка файла после ответа уже есть (`runtime.md:181-184`) — сработала; явно
  назвать её «один повтор, затем остановка с причиной».

**Критерии приёмки.** Строка `PARENT` и определения агентов не называют итоговый ответ полным
отчётом; в прогоне с обычными субагентами все отчёты coder'а и tester'а лежат по
`REPORT_PATH` без повторных просьб.
