---
id: omixflow-mutations-orchestrator-round
title: report.py check не знает исхода MUTATIONS «ждёт раунда оркестратора» — отчёт до Unity-раунда получает return
status: draft
type: feature
created: 2026-10-21
updated: 2026-10-21
origin: mewria MEW-29 (G-17 лида mewria-client-lead, 2026-10-21), сверено по транскрипту сессии f373b592 и .claude/omixflow/lang/csharp.md mewria
target: omixflow
external:
links: [omixflow-orchestrator-gates, omixflow-mutations-per-declaration]
---

**Контекст.** У mewria клиентские тесты идут только в Unity: при открытом редакторе основного
дерева их гоняет оркестратор через MCP for Unity (`orchestrator_checks`, проверка `unity` адаптера
`csharp.md`); агенты Unity не запускают. Протокол (`runtime.md`, «Проверки оркестратора») описывает
проверки оркестратора, но не мутационные пробы тестов, которые агент запустить не может.
`report.py check` считает строки MUTATIONS с исходом (RED, GREEN → … → RED, `no probe possible`) и
возвращает отчёт, если их меньше новых тестов; остановка агента (`RUN RESULT: NOT RUN …`) снимает
только сверку гейтов.

**Проблема.**
- MEW-29 (клиент Unity) вёл пробы раундами: агент готовит файлы-мутанты и `round.sh` (apply/restore
  с sha256), оркестратор делает `refresh_unity` и `run_tests` и шлёт исход, агент откатывает и пишет
  RED в MUTATIONS. По словам лида — 9 + 5 + 7 + 2 раунда (implement-step4, 6, 7, review-tests-pass1).
- До раунда `report.py check --role tester --report …/review-tests-pass1.md` вернул «VERDICT: return …
  MUTATIONS: новых тестов 1 (…/SceneAssemblerTests.cs: новых тестов 1), строк с исходом 0 … —
  остановка агента: NOT RUN in Unity (editor of the main tree is open, the orchestrator runs rounds via
  MCP)» (транскрипт f373b592). Coder шага 4 ждал того же: «until then report.py check returns the
  report». Отчёт, который честно ждёт раунда, читается как неполный; сверку гоняют до раунда и после,
  первый return — шум. Второй return после раундов в MEW-29 был дефектом формата отчёта tester'а и
  сюда не относится.

**Предложение.**
1. Строка MUTATIONS `{test} ← {probe} → pending: orchestrator round {id}` — допустимая форма, когда
   у адаптера lang есть `orchestrator_checks`. `report.py check` даёт на такой отчёт отдельный вердикт
   («ждёт раунда»; список раундов и тестов), не `return`; оркестратор отличает его от готового.
2. Итоговая сверка после раунда: ни одной `pending` — каждая строка с исходом, иначе `return`
   (флаг вызова или состояние раунда — решить при реализации).
3. Без `orchestrator_checks` строка `pending` — ошибка формата, как сейчас.
4. Протокол: раунд проб оркестратора — в `runtime.md`, «Проверки оркестратора» (агент готовит
   мутантов и скрипт apply/restore, оркестратор гоняет проверку, агент откатывает и пишет исход);
   сейчас это практика mewria без правила.

**Критерии приёмки.** При `orchestrator_checks` отчёт со строками `pending` получает отдельный
вердикт, не `return`; отчёт с `pending` не проходит как итоговый, после раунда `check` требует исход
по каждой строке; без `orchestrator_checks` `pending` — ошибка формата; тесты `report.py` на все три
случая.
