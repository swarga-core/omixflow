---
id: omixflow-report-run-result-multiline
title: report.py check не читает исход многострочного RUN RESULT tester'а — «нет исхода гейтов test» при PASS в первой строке
status: draft
type: bug
created: 2026-10-22
updated: 2026-10-22
origin: mewria MEW-30 (G-18 лида mewria-client-lead, 2026-10-22), сверено по scripts/report.py и воспроизведено
target: omixflow
external:
links: []
---

**Контекст.** `report.py check --role tester`: исход гейта test — из секции RUN RESULT,
`re.match(r"^\s*(PASS|FAIL)\b(.*)$", rr, re.I)` (`scripts/report.py:926` на 0.9.5), где `rr` —
`section_text`: строки секции, склеенные через `\n`.

**Проблема.**
- Без `re.S` точка не берёт перевод строки, без `re.M` `$` — только конец всей строки: у секции из
  двух и более строк совпадения нет, и check пишет «RUN RESULT / CHECKPOINT GATES: нет исхода гейтов
  test», хотя первая строка — PASS.
- Воспроизведено: `RUN RESULT: PASS (EditMode 12/12)` и строка продолжения `PlayMode 5/5 via
  orchestrator` → `rr = 'PASS (EditMode 12/12)\n  PlayMode 5/5 via orchestrator'`, `match: None`.
- MEW-30: tester из-за этого дважды переписывал отчёт (со слов лида).

**Предложение.** Исход — по первой строке секции (`rr.splitlines()[0]`), остальное — подробности; или
`re.M`. Формат tester'а (`agents/tester.md`, «Output format») не меняется.

**Критерии приёмки.** Многострочный RUN RESULT с PASS в первой строке — PASS, с FAIL — FAIL; тест в
`tests/test_report.py` на оба случая.
