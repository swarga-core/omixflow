---
id: omixflow-mutations-per-test
title: MUTATIONS в отчёте coder'а — строка на каждый новый тест, а не на пробу
status: draft
type: bug
created: 2026-10-11
updated: 2026-10-11
origin: Swarga AI Studio T-4 (G-21 лида swais-lead, 2026-10-10, OMIXFlow 0.6.0), сверено по reports/implement-step3.md и log.md T-4
target: omixflow
external:
links: [omixflow-coder-mutation-report, omixflow-tester-mutations]
---

**Контекст.** 0.5.0 (`omixflow-coder-mutation-report`) запретил обобщение мутационной проверки
в отчёте. Получились два разных правила:
- `agents/coder.md:103`, «Mutation-check your tests»: «Report every probe in MUTATIONS, one
  line per probe»;
- `skills/implement/SKILL.md:90-92`, сверка 2.2: «Каждый новый тест шага … есть в MUTATIONS
  строкой с исходом RED», иначе шаг возвращается coder'у.
Шаблон отчёта (`coder.md`, `- {test} ← {mutation} → RED | GREEN`) ближе ко второму, но проза
велит первое.

**Проблема.** T-4, шаг 3: coder дал каталог из 47 проб, сгруппированный по функциям («lock: без
блокировки», «create: без разбора NewTask» …), все RED. Тесты отката, ключей и позитивные
проверки БД в нём не назывались. Оркестратор по 2.2 вернул шаг: «MUTATIONS не перечисляли тесты
отката, ключей и позитивные проверки БД → дополнено потестовой таблицей» (log.md:114). Возврат
стоил лишнего хода coder'а; на шагах 4–5 coder сразу писал потестовую таблицу.

**Предложение.** Одно правило в `coder.md` (tester читает тот же раздел как рецепт пробы,
`tester.md:81-83`, и шаблон у него тот же): MUTATIONS — строка на каждый новый тест: `{test} ← {проба} → RED | GREEN, …`;
тест, который ловят несколько проб, — несколько строк; проба, ловящая несколько тестов, —
строка у каждого. Список проб без привязки к тестам — не отчёт. Сверка 2.2 остаётся как есть.

**Критерии приёмки.** Проза и шаблон MUTATIONS в `coder.md` (и шаблон в `tester.md`) говорят
«строка на новый тест» и совпадают с 2.2 implement; в прогоне нет возвратов шага из-за таблицы.
