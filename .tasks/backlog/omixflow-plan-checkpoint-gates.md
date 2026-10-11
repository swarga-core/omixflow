---
id: omixflow-plan-checkpoint-gates
title: Гейт из checkpoint плана, которого нет в наборе шага resolve.py, coder не запускает
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-9 (G-42 лида swais-lead, 2026-10-11, OMIXFlow 0.6.1 → 0.7.0), сверено по plan.md, reports/implement-step6.md и log.md задачи, flow.yaml SwAIS
target: omixflow
external:
links: [omixflow-architect-plan-quality]
---

**Контекст.** Порт lang, «Гейты» (0.6.0): набор шага — typecheck, test, lint и гейты с `when`,
чью область задели изменения; полный набор (с гейтами без `when`) — на Review, при
синхронизации, перед сдачей и на приёмке. `resolve.py verify --at step` отдаёт набор шага
в `gates`, остальное — в `skipped`. `agents/coder.md`, шаг 4: «Run only `gates` … Never pick
the set yourself». Шаг плана при этом несёт «Test checkpoint» с гейтами, которые architect
считает нужными (`agents/architect.md`: имена гейтов из адаптера).

**Проблема.** T-9, шаг 6: checkpoint плана — «Гейты test (пакет UI), typecheck, lint, build
зелёные» (styles.css должен попасть в сборку). У SwAIS `build: { cmd: "pnpm build",
background: true }` без `when` — в набор шага он не входит, `resolve.py` положил его
в `skipped`. coder-T-9 запустил только `gates`, оркестратор вернул задание; во втором отчёте
build прогнан «по указанию оркестратора (checkpoint плана шага 6 выше набора resolve.py)».
Правила, что сильнее, нет ни у coder'а, ни в implement 2.2.

**Предложение.** Гейты, которые называет checkpoint шага, обязательны сверх набора шага:
- `agents/coder.md`, шаг 4: гейт из checkpoint, которого нет в `gates`, coder запускает
  по его записи в `skipped` (команда, критерий, фон) и называет в GATES с пометкой
  «по checkpoint плана»;
- либо `resolve.py verify --at step --also {gate}` переносит названные гейты из `skipped`
  в `gates`, и coder передаёт гейты checkpoint — тогда правило «только `gates`» остаётся
  без исключений;
- implement 2.2: сверка GATES с гейтами checkpoint шага.

**Критерии приёмки.** Шаг с build в checkpoint возвращается с прогнанным build без возврата
задания; линт на маркер в coder.md и implement 2.2.
