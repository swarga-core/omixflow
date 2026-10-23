---
port: lang
name: ts
capabilities: [verify, test_conventions, suppressions, navigation, deps_setup, workspace_layout, long_running]
requires:
  tools: [mcp__serena__*]
  bin: [node]
scripts: {}
tests:                                   # test_conventions machine-readable (report.py check)
  files: ["**/*.test.ts", "**/*.test.tsx", "**/*.a11y.test.tsx", "**/*.variants.test.tsx", "**/*.visual.test.tsx"]
  # it(…), it.each(…)(…), test.each`…`, it.only, test.concurrent — declarations; Playwright's test.describe,
  # test.beforeEach/afterAll, test.step, test.use, test.extend are not tests
  declaration: '^\s*(it|test)(\.(?!(?:describe|beforeEach|afterEach|beforeAll|afterAll|step|use|extend|info|slow|setTimeout|configure|expect)\b)\w+)*\s*[(`]'
  support: ["**/__mocks__/**", "**/fixtures/**", "**/test/**", "**/test-utils/**"]   # test_conventions, «Тестовая поддержка»: plan.py files
  ran: '\b[1-9]\d* passed\b'   # vitest «Tests  7 passed (7)», jest «7 passed, 7 total», playwright «7 passed (3s)»; not «92 skipped» (probe.py)
---

# Адаптер lang: TypeScript / JavaScript

Стек по умолчанию: pnpm, vitest, biome, tsc. Проект переопределяет команды
в `verify.*`; адаптер задаёт критерии и идиомы.

## verify

| Гейт | Дефолт команды | Критерий | Примечания |
|---|---|---|---|
| typecheck | `pnpm check-types` | exit-code | в монорепо запускается через turbo; отдельный пакет: `pnpm --dir {пакет} check-types` |
| test | `pnpm test` | exit-code | e2e и visual в него не входят |
| lint | `pnpm exec biome check {path}` | zero-diagnostics или no-new-diagnostics | вывод biome обрезан на двадцати диагностиках: маленькое число из него это артефакт обрезки, не факт; для `no-new-diagnostics` baseline замеряется на базовой ветке в начале задачи с `--max-diagnostics` достаточного размера |
| build | `pnpm build` | exit-code | долгий |
| e2e | по проекту | rerun-compare-set | не входит в `test`; обязателен, когда правка тронула словарь, разметку, стили или моки API |
| visual | по проекту | exit-code | снимки в браузере; не входит в `test`; обновление baseline только осознанно и только на хосте, где baseline воспроизводим |
| structure | `pnpm exec depcruise --config .dependency-cruiser.cjs packages` | exit-code | направление зависимостей слоёв и запрещённые импорты (dependency-cruiser); в наборе шага; правило живёт в конфиге инструмента, не в прозе спецификаций. Ловушки: без путей `depcruise` печатает справку и выходит с 0 — пути в команде обязательны; правило с `severity: warn` тоже даёт 0 — инварианты только `error` |

Ловушки:

- `pnpm lint` может быть no-op: у пакета нет скрипта `lint`, turbo молча пропускает,
  pnpm внутри пакета печатает help с нулевым кодом. Гейт lint это `biome check`
  по явному пути.
- turbo кэширует результаты: после merge гонять тесты пакета напрямую, а не через
  кэшированную задачу.

## test_conventions

- Поведение: `*.test.ts`, `*.test.tsx`.
- Доступность UI-компонентов: `*.a11y.test.tsx` (vitest-axe плюс ручные ассерты;
  контраст не тестируется юнитами).
- Варианты и конфигурация компонентов: `*.variants.test.tsx`.
- Визуальные: `*.visual.test.tsx`, отдельный гейт в браузере, в `test` не входит.
- Тестовая поддержка (правит tester, исполнитель фикса ревью — по ней же): `__mocks__/`,
  `fixtures/`, `test/` и `test-utils/` пакета, файлы `setupFiles` конфига vitest; те же
  каталоги — `tests.support` фронтматтера (`plan.py files` не считает их кодом). Проект
  с другой раскладкой называет свои каталоги в правилах tester'а и в `tests.support`
  расширения адаптера (`.claude/omixflow/lang/ts.md`, `extends: omixflow:ts`); расширение
  только добавляет глобы — проект, у которого в `test/` или `fixtures/` лежит продуктовый код
  (опубликованный пакет хелперов, сиды), заменяет адаптер (`adapters.md`, «Три уровня кастомизации»).
- Один файл: `pnpm test {Name}` или `pnpm exec vitest run {Name}`; один тест:
  `pnpm test -t "{name}"`. **Никогда `pnpm test -- {X}`**: с `--` pnpm искажает
  аргументы, и vitest тихо прогоняет всё. **Никогда `--filter={X}`** для vitest.
- Машиночитаемый вывод (`--reporter=json`, `junit`, `blob`, `--coverage`) — только с явным путём
  в `SCRATCH_DIR`: `--outputFile={SCRATCH_DIR}/{метка}/vitest.json`; при нескольких файловых
  репортерах — по одному на каждый (`--outputFile.json=…/vitest.json --outputFile.junit=…/junit.xml`:
  строковый путь получают все, и отчёты затирают друг друга); у покрытия
  `--coverage.reportsDirectory={SCRATCH_DIR}/{метка}/coverage`. Без пути отчёт ложится в пакет
  (Swarga AI Studio T-16: `packages/catalog/.vitest/json/output.json` в `git status` после
  `--reporter=json`).

## suppressions

Запрещено добавлять как «фикс»: `@ts-ignore`; `@ts-expect-error` без комментария
причины; `as any`, `as unknown as`; `!` non-null assertion для обхода ошибки;
`// biome-ignore` без обоснования; `.skip`, `.only`, `.todo` в тестах; `eslint-disable`.

## navigation

- serena для всех операций с символами: `get_symbols_overview`, `find_symbol`,
  `find_referencing_symbols`, `rename_symbol`.
- ts-morph (`mcp__mcp-tsmorph-refactor__*`) для многофайловых рефакторингов через
  type checker: rename, move, change signature, find references, unused exports.
  Применим только при наличии `tsconfig.json` в пакете; путь передавать абсолютный.
- ast-grep через Bash для структурного поиска.
- SolidJS: `splitProps()` обязателен, деструктуризация props ломает реактивность.
  Правила фреймворка проект уточняет расширением адаптера.

## deps_setup

`pnpm install`. В worktree после хука проверить, что симлинки пакетов
материализовались; при `Cannot find module` повторить установку в самом worktree.

## workspace_layout

Монорепо определяется по `pnpm-workspace.yaml`; пакеты по его globs. Гейт в одном
пакете: `pnpm --dir {пакет} {скрипт}` (каталог — опцией, без `cd`), а не фильтр turbo.
Не все пакеты имеют все скрипты: перед запуском прочитать `package.json` пакета.

## long_running

`e2e`, `build`, полный прогон vitest по монорепо: запускать отсоединённо через
`scripts/gate.py` и ждать опросами (`protocol/runtime.md`, «Гейты»); в foreground
не дольше двух-трёх минут. Тесты гонять по пакетам.
