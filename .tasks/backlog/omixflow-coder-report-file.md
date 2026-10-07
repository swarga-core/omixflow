---
id: omixflow-coder-report-file
title: Отчёты агентов — в файл, с состоянием дерева по свежему git status
status: draft
type: feature
created: 2026-10-06
updated: 2026-10-07
origin: прогоны AL-1162, AL-1164 (черновики issues-al-*, разобраны 2026-10-06); mewria MEW-1, MEW-7 (лид mewria-lead, 2026-10-07)
target: omixflow
external:
links: [omixflow-coder-mutation-report, omixflow-agent-escape-bytes]
---

**Проблемы.**
1. **Обрезка длинного ответа.** AL-1164: ответ reviewer'а с findings обрезался в канале
   сообщений дважды; в 0.3.0 исправлено только для findings (`FINDINGS_PATH`,
   `protocol/review-cycle.md:8-12`, `protocol/runtime.md:86-87`). Отчёт coder'а
   (`agents/coder.md:95-114`) по-прежнему идёт сообщением, а NOTES с мутационными пробами
   станут длиннее после `omixflow-coder-mutation-report`. mewria (лид mewria-lead): отчёт
   coder'а MEW-7 обрезался на каждом шаге (4 раза: «[result truncated — ask the agent for
   the rest via SendMessage]»), ответ researcher'а MEW-1 — тоже; хвост NOTES оркестратор
   добирал SendMessage.
2. **Отчёт по памяти** (AL-1162): continuation-coder написал «файлы шага 6 не закоммичены»
   после коммита оркестратора, без `git status`; сверка дерева предписана только при
   возобновлении после обрыва (`agents/coder.md:37-38`).

**Предложение.**
1. `REPORT_PATH: {TASK_DIR}/reports/{phase}-{N}.md` в шаблоне спавна coder'а, tester'а
   и researcher'а (как `FINDINGS_PATH` у reviewer'а); в ответе — сводка (STEP, GATES, SUMMARY
   или `STATUS`) и путь. Правило «длинный отчёт агента — в файл» в `runtime.md` общее для
   всех агентов.
2. Блок `TREE STATE` в отчёте coder'а — только по свежему `git status --short`.

**Критерии приёмки.** Форматы вывода coder'а, tester'а и researcher'а с путём отчёта;
`TREE STATE` у coder'а; implement и research читают отчёт из файла.
