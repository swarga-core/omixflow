---
id: omixflow-sleep-not-second-failure
title: Сон машины обрывает агента как сбой API — второй такой «failed» по правилу даёт deadlock
status: draft
type: bug
created: 2026-10-19
updated: 2026-10-19
origin: Swarga AI Studio T-15, Implement, шаг 1 (G-95 лида swais-lead, 2026-10-19, переслала omixflow-revision), сверено по транскрипту T-15 и protocol/runtime.md
target: omixflow
external:
links: [omixflow-agent-failed-resume, omixflow-usage-limit-wake]
---

**Контекст.** `protocol/runtime.md`, «Обрыв сбоем»: `failed` без файла отчёта — повтор того же
задания тому же агенту; «второй `failed` на то же задание — СТОП, вопрос в точке `deadlock`:
сбой сети не лечится новым агентом». Причину обрыва правило не различает.

**Проблема.**
- T-15 (сессия `b2f19cb1`), coder шага 1 оборвался дважды: 2026-10-18 19:53 и 21:41 UTC,
  «Agent terminated early due to an API error: API Error: Your computer went to sleep
  mid-response. The response above may be incomplete. (error type server_error)». Это сон хоста,
  не сеть и не дефект задания.
- После второго обрыва оркестратор сам упёрся в «Can't reach the API server … (ENOTFOUND)»
  (22:51), харнесс остановил сессию; утром лид поднял её (A-37), и продолжение тем же agentId
  прошло. Deadlock не случился только потому, что оркестратор не успел действовать; по правилу
  второй `failed` — СТОП.
- По слову лида, DB-тесты висели 100–976 с из-за Maintenance Sleep хоста (`pmset -g log`):
  зависший гейт выглядит как дефект, хотя это сон.

**Предложение.**
1. «Обрыв сбоем»: обрыв с причиной сна или сети хоста («went to sleep», ENOTFOUND, «Can't reach
   the API server») — повтор без счёта; deadlock — второй обрыв по другой причине или третий
   подряд по любой. Причина — из текста уведомления `failed`.
2. «Гейты»: гейт, превысивший обычное время в разы при сне хоста, — повтор, не дефект; на время
   долгих прогонов — `caffeinate -i` (macOS) вокруг `gate.py start`, в адаптере проекта или
   рецептом в `worktree.md`, «Ловушки».
3. Лид: остановка сессии сразу после обрыва сном — тот же случай, что сетевой сбой
   («Остановленная сессия»): поднять по постоянной санкции, `advisory` «продолжить тем же id».

**Критерии приёмки.** Сон машины не останавливает задачу точкой deadlock; повтор после
пробуждения идёт без вопроса; правило «Обрыв сбоем» называет причины, которые не в счёт.
