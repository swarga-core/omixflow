---
id: omixflow-probe-no-tests-ran
title: Фильтр теста без совпадений даёт ложно GREEN пробу — vitest без единого прогнанного теста выходит с кодом 0
status: draft
type: bug
created: 2026-10-18
updated: 2026-10-18
origin: Swarga AI Studio T-14, шаг 1 (G-85 лида swais-lead, 2026-10-18), сверено по reports/implement-step1.md T-14 и scripts/probe.py
target: omixflow
external:
links: [omixflow-probe-backup-outside, omixflow-mutations-per-test]
---

**Контекст.** `probe.py`: базовый прогон `--cmd` без мутанта должен быть зелёным (иначе
`PROBE NOT RUN`), мутант — RED по ненулевому коду или таймауту, иначе GREEN («усилить тест»).
Зелёный — это код выхода 0.

**Проблема.**
- T-14, шаг 1: двенадцать проб `keys.test.ts` с фильтром `-t 'DecisionKey отклоняют …'` (имя
  describe) вышли GREEN ложно: фильтр не совпал ни с одним тестом, все тесты skipped, exit 0 —
  и база «зелёная», и мутант «зелёный» (reports/implement-step1.md, стр. 83). Проба лида:
  `vitest run src/keys.test.ts -t 'нет такого'` → «92 skipped», EXIT=0. С фильтром по имени
  теста пробы дали RED.
- Ни probe.py, ни report.py не отличают «тест прошёл» от «тест не запускался».

**Предложение.**
1. Адаптер lang: `tests.ran` — шаблон строки вывода, доказывающей, что тесты выполнялись (ts,
   vitest: `Tests\s+\d+ passed` или `\d+ failed`; не только `skipped`). `probe.py` проверяет его
   на базовом прогоне: нет совпадения — `PROBE NOT RUN: … no tests ran (filter matches nothing?)`,
   а не проба. Без ключа в адаптере — как сейчас.
2. `agents/coder.md` и `tester.md`, рецепт пробы: фильтр — по имени теста, не describe;
   базовый прогон показывает число прошедших тестов.

**Критерии приёмки.** Проба с фильтром без совпадений не засчитывается как GREEN (`PROBE NOT RUN`);
тест `probe.py` с командой, печатающей «0 passed, 92 skipped» и выходящей с 0.
