---
id: omixflow-tier-ceiling
title: Потолок тира проекта — tiers.max, триаж не поднимает выше
status: draft
type: feature
created: 2026-10-10
updated: 2026-10-10
origin: лид swais-lead 2026-10-10 — подключение OMIXFlow 0.5.1 к swarga-ai-studio, находка 3
target: omixflow
external:
links: []
---

**Проблема.** `tiers` в конфиге хранит только пороги файлов (`s_max_files`, `m_max_files`);
`--tier` форсирует тир, а не ограничивает сверху. Политику проекта «тир не выше M»
выразить нельзя.

**Предложение.** `tiers.max: S|M|L` (по умолчанию L): триаж, давший тир выше, ставит потолок
и пишет в log.md «тир {триаж} → {max} по tiers.max»; `--tier` выше потолка — отказ с
объяснением; doctor показывает потолок.

**Критерии приёмки.** При `tiers.max: M` триаж, давший L, ставит M со строкой в log.md;
`protocol/tiers.md` описывает ключ; схема и шаблон его знают.
