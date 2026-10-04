---
id: omixflow-findings-prefix
title: Findings Research и findings ревью делят префикс F
status: draft
type: feature
created: 2026-10-04
updated: 2026-10-04
origin: третий прогон лида, гоча G4 add-camel-case (G-10 журнала лида)
target: omixflow
external:
links: []
---

**Контекст.** Третий прогон лида, `add-camel-case`: секция Research в `spec.md`
(F1–F6) и findings ревью по контракту `F{id}` (F1–F6).

**Проблема.** Оба набора нумеруются `F{n}`. В Out of Scope `spec.md` сессии
пришлось различать их словами: «Research F4» (`:193`) и «ревью F4» (`:197`, решение
лида D-88). В вопросах лиду метка `F4` неоднозначна без контекста фазы.

**Предложение.** `artifacts.md`: findings research.md и секции Research получают
отдельный префикс (например `R{n}`), `F{id}` остаётся за контрактом ревью.

**Критерии приёмки.**
- Шаблон research.md и секции Research использует свой префикс.
- Метки в вопросах лиду однозначны без указания фазы.
