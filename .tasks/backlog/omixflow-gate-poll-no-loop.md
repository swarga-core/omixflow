---
id: omixflow-gate-poll-no-loop
title: Ожидание фонового гейта циклом shell ставит фоновую сессию в ожидание разработчика
status: draft
type: bug
created: 2026-10-12
updated: 2026-10-12
origin: Swarga AI Studio T-11 (G-56 лида swais-lead, 2026-10-12, фоновая сессия на 0.7.x), сверено по транскриптам сессии и её субагентов
target: omixflow
external:
links: [omixflow-agent-no-cd, omixflow-worktree-isolation-recipes]
---

**Контекст.** `runtime.md`, «Гейты», и агенты coder, tester, reviewer: долгий гейт
запускается `gate.py start`, ждётся `gate.py poll {имя} --root …` до `EXIT` (`RUNNING` —
опросить снова). `poll` сам ждёт до `--timeout` секунд (по умолчанию 100) и возвращается
с `EXIT`, `RUNNING` или `LOST` (`scripts/gate.py`). Запрет циклов shell записан только
в «Ловушках» `worktree.md` для изолированных сессий.

**Проблема.** T-11 (фоновая сессия): субагенты ждали гейты циклом shell — coder
(`a3d39a7e…`) дважды `until python3 …/gate.py poll implement-step3-test --root … | grep -qE
"EXIT|LOST"; do sleep 15; done`, coder-T-11-3 дважды `until [ -f /tmp/coder-T-11-3/…/uncaught.txt
]; do sleep 5; done` (ещё и в голом `/tmp`: сессия запущена до 0.7.2). Харнесс такую команду не
разбирает и спрашивает «Parse error. Do you want to proceed?» — только Yes/No, без «don't ask
again»; allow-правила (`Bash(*)`, `Bash(python3 …/gate.py poll:*)`) не помогают. Запрос
разрешения субагента ставит в `waiting` всю фоновую сессию до подключения разработчика: по
словам лида, трижды подряд (review-test, review-build, delivery-test).

**Предложение.**
- coder, tester, reviewer (и `runtime.md`, «Гейты»): фоновый гейт ждётся повтором одной
  команды `gate.py poll {имя} --root … --timeout {N}` — она сама ждёт до N секунд; никогда
  не в цикле shell (`until`, `while`, `sleep`) и не в конвейере условия: харнесс не
  разбирает такую команду и спрашивает разрешение, а фоновая сессия ждёт разработчика.
- Правило агентов «Commands without `cd`» дополнить: «and without shell loops» — то же для
  ожидания файла (`until [ -f … ]`): ждать результат своей команды, а не опрашивать файл.
- `gate.py wait` не нужен: `poll --timeout` блокирует.

**Критерии приёмки.** Правило у трёх агентов и в runtime.md, линт на маркер; фоновая сессия
проходит гейты без запросов разрешения.
