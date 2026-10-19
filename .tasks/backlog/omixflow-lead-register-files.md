---
id: omixflow-lead-register-files
title: lead.py register --file заменяет карту файлов сессии — дополнение после Spec и Implement стёрло прежнюю, overlaps дал []
status: draft
type: bug
created: 2026-10-19
updated: 2026-10-19
origin: Swarga AI Studio, волна 7, T-15 и T-16 (G-89 лида swais-lead, 2026-10-19, переслала omixflow-revision), сверено по журналу лида SwAIS и scripts/lead.py
target: omixflow
external:
links: [omixflow-lead-rule-retire]
---

**Контекст.** `lead.py register NAME [--phase P] [--file F ...]`: событие `session` с полями,
`fold` сливает их в запись сессии `cur.update({… if v is not None …})`
(`scripts/lead.py`, `fold`, ветка `session`) — поле с новым значением заменяет старое, и
`files` тоже. `overlaps` сравнивает карты сессий не в `done`/`retired` (`INACTIVE_PHASES`).
Скил лида: «карта файлов после Research — `lead.py register {сессия} --file …`, затем
`overlaps`» (`skills/lead/SKILL.md:176`).

**Проблема.**
- Журнал SwAIS: T-15 после Spec — карта 25 файлов (стр. 987), T-16 — 21 (стр. 1000). В Implement
  лид «дополнял» карты: T-16 — `--file` из 2 файлов (стр. 1017), затем 3 (стр. 1021), T-15 — 1
  (стр. 1018). Каждый вызов заменил карту целиком, `overlaps` дал `[]` при 15 общих файлах;
  карты восстановили полным перечнем (стр. 1024–1025: 28 и 26).
- `--phase` принимает свободный текст: «implement (шаг 1/7 88cbd94)», «implement (шаги 1–4/8,
  8504e2c; пауза на границе D-350 …)» (стр. 1016–1021). Сессию из `overlaps` это не выводит —
  отбрасываются только `done` и `retired`, — но поле `phase` перестаёт быть фазой: доска лида
  (`board`) и всё, что сверяет фазу с перечнем, видят текст.

**Предложение.**
1. `register --add-file F …`: файлы добавляются к карте; `--file` остаётся заменой, но сужение
   карты (новая без части прежних файлов) печатает в stderr «карта {NAME}: было N, стало M,
   выпали …; дополнить — `--add-file`».
2. `--phase` — только фазы профиля (`state.py`, перечень фаз) плюс `done`, `retired`; иное —
   ошибка. Прогресс — отдельное поле `--progress TEXT` (шаг, коммит, пауза), доска показывает
   его рядом с фазой.
3. Скил лида: после Spec/Plan и на шагах Implement — `--add-file` новыми файлами; `--file` —
   только полной картой.

**Критерии приёмки.** Дополнение карты не стирает прежние файлы; `overlaps` видит сессию в
любой фазе пайплайна; `--phase` со свободным текстом — ошибка с подсказкой `--progress`; тесты
в `tests/test_lead.py`.
