---
id: omixflow-bytes-check-cyrillic
title: BYTES CHECK — coder пишет «n/a», когда проверил и ничего подозрительного не нашёл; в русскоязычных проектах n/a почти не бывает
status: draft
type: bug
created: 2026-10-16
updated: 2026-10-16
origin: Swarga AI Studio T-12 (G-71 лида swais-lead, 2026-10-16, сессия на 0.9.0; родственно возврату шага 1 T-10), сверено по scripts/report.py, agents/coder.md и транскрипту coder'а T-12
target: omixflow
external:
links: []
---

**Контекст.** Шаблон отчёта coder'а (`agents/coder.md:254-256`): `BYTES CHECK: - {file:line}
— {U+XXXX | escape \uXXXX}, verified by bytes — or "n/a: ASCII only"`. `report.py check`
(`scripts/report.py:661-668`): если в диффе агента есть файлы с не-ASCII строками, а секция
начинается с `n/a`, — возврат «BYTES CHECK: n/a, а в диффе не-ASCII строки: {первые 5
файлов}». Покрытие по файлам скрипт не сверяет.

**Проблема.**
- T-12, шаг 1: первый отчёт — `BYTES CHECK: n/a: escapes нет; не-ASCII — только кириллица
  и видимые типографские символы (—, «», ∪, ≠) в комментариях, тестах и записях решений;
  grep -P по U+00A0, U+200B–U+200D, U+2060, U+FEFF и комбинируемым знакам — ни одного
  совпадения` (транскрипт coder'а, `tail.md` в его scratchpad). Проверка сделана,
  `n/a` значило «подозрительного нет», а не «ASCII only».
- `report.py` вернул шаг: не-ASCII в `docs/decisions/T-12-run-model.md`,
  `…/T-12-run-trace-events.md`, `packages/schemas/src/keys.ts`, `keys.test.ts`,
  `pipeline/definition.test.ts`. Код не менялся, правка отчёта — круг coder'а и
  `report.py` впустую (log.md T-12, стр. 97). Гоча называет причиной `.md`; по тексту
  отчёта дело не в типе файла — n/a стоял на всю секцию, кириллица была и в `.ts`.
- В проекте с русскими комментариями, именами тестов и ADR дифф почти никогда не ASCII:
  `n/a` неприменим, а шаблон `{file:line} — {U+XXXX}` на каждую строку — десятки строк
  перечня кириллицы (исправленный отчёт T-12 — по диапазону строк на файл).

**Предложение.**
1. Шаблон coder'а: вторая форма — по файлу, `{file}: {классы символов: Cyrillic,
   typographic …}; invisible/escapes: none (verified by bytes)`; `n/a: ASCII only` —
   только при ASCII-диффе, со словами «n/a не значит „проверено, чисто“». Невидимые
   и escape — по строкам, как сейчас.
2. `report.py check`: каждый файл диффа с не-ASCII назван в BYTES CHECK; ошибка перечисляет
   все непокрытые файлы (не первые пять) и подсказывает форму по файлу.

**Критерии приёмки.** coder с кириллицей в диффе не пишет `n/a`, а пишет форму по файлу;
ошибка `report.py` перечисляет непокрытые файлы; тест на форму по файлу и на непокрытый
файл.
