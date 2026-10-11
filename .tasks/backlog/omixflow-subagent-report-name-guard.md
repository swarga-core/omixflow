---
id: omixflow-subagent-report-name-guard
title: Харнесс против файлов отчётов субагента — заметка в системном промпте и отказ Write в .md-файл «report*»
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-5 и T-6 (G-23 лида swais-lead, 2026-10-10/11, OMIXFlow 0.6.0 → 0.6.1), сверено по транскриптам всех прогонов SwAIS, mewria и AL
target: omixflow
external:
links: [omixflow-agent-report-file-first, omixflow-worktree-isolation-recipes]
---

**Контекст.** С 2026-10-10 агенты — обычные субагенты (режим команд агентов выключен).
Полный отчёт агент пишет в `REPORT_PATH` = `{TASK_DIR}/reports/{phase}-{метка}.md`
(`runtime.md`, «Отчёт агента»).

**Проблема — две стороны одного правила харнесса.**
1. **Отказ Write по имени (T-5).** coder-T-5 на шаге 2 и coder-T-5-2 на шаге 4 собирали
   отчёт из кусков: голова и хвост — Write в scratchpad (`t5-probes/report2-head.md`,
   `report2-tail.md`, `step4/report-head.md`, `report-tail.md`), MUTATIONS — скриптом,
   затем `cat` в `REPORT_PATH`. Все четыре Write отклонены: «Subagents should return
   findings as text, not write report files. Include this content in your final response
   instead.» Сразу после этого тот же coder записал `step4/report-head.txt` и
   `report-tail.txt` — прошли: отклоняется `.md`-файл с «report» в имени, как в формулировке
   заметки (п. 2). Записи в `reports/{phase}-{метка}.md` (около 60 по T-1…T-6, MEW-2, MEW-13,
   MEW-14) прошли: «report» там только в имени каталога. Лид связывал отказ с изоляцией
   worktree; это не так. Его обход «Write в scratchpad, затем cp» — ровно то, что
   отклонялось.
2. **Заметка в системном промпте (T-6).** Харнесс пишет каждому субагенту: «Do NOT Write
   report/summary/findings/analysis .md files. Return findings directly as your final
   assistant message — the parent agent reads your text output, not files you create.
   (Files written as input to another tool are fine; this note is about report files.)»
   В транскриптах — у всех субагентов начиная с Claude Code 2.1.267, раньше (2.1.252 и
   старше) её нет. tester-T-6 на проходе 1 ревью записи не пытался: «I didn't write the
   report file at REPORT_PATH, because my instructions say not to write report files; the
   full report is below». Отказа Write в T-6 нет ни у одного агента. Лид в log.md T-6
   записал вероятной причиной отказ по имени `report*`, но причина — заметка. Остальные
   агенты с `REPORT_PATH` (2.1.294–2.1.296) файл писали — Write или `cat >` в Bash.

**Решение (0.6.2).**
- `runtime.md`, «Отчёт агента», абзац «Харнесс и файл отчёта»: обе стороны правила; отчёт по
  `REPORT_PATH` — артефакт задачи (коммитится с ней, его читают оркестратор и сменщик).
- coder, tester, reviewer (`FINDINGS_PATH`), researcher (`research.md`): файл — артефакт
  задачи, заметка харнесса исходит из того, что родитель читает только ответ, и его не
  касается; прочие файлы отчётов — касается. Куски отчёта — его часть.
- Запись: одним Write, иначе разделы до MUTATIONS — Write, остальное по порядку через `>>`;
  временные файлы в scratchpad под нейтральным именем, с запасом не `report*`.
- Отказ записи `REPORT_PATH`: не обходить другим именем или shell; полный отчёт ответом
  с первой строкой `REPORT_PATH refused by the harness: {сообщение}`; оркестратор проверяет
  последний раздел формата (`NOTES` / `SUMMARY`) и пишет файл (implement 2.2, 2.3).
- Линт: метки и шаблоны путей `reports/`, `review/` без «report», запасной путь, оговорка
  про заметку у четырёх агентов.

**Критерии приёмки.** В прогоне на 0.6.2 нет отказов «return findings as text» и ответов
«instructions say not to write report files».
