---
port: lang
name: ts
capabilities: [verify, test_conventions, suppressions, navigation, deps_setup, workspace_layout, long_running]
requires:
  tools: [mcp__serena__*]
  bin: [node]
scripts: {}
---

# Адаптер lang: TypeScript / JavaScript

Стек по умолчанию: pnpm, vitest, biome, tsc. Проект переопределяет команды
в `verify.*`; адаптер задаёт критерии и идиомы.

## verify

| Гейт | Дефолт команды | Критерий | Примечания |
|---|---|---|---|
| typecheck | `pnpm check-types` | exit-code | в монорепо запускается через turbo; отдельный пакет: команда из каталога пакета |
| test | `pnpm test` | exit-code | e2e и visual в него не входят |
| lint | `pnpm exec biome check {path}` | zero-diagnostics или no-new-diagnostics | вывод biome обрезан на двадцати диагностиках: маленькое число из него это артефакт обрезки, не факт; для `no-new-diagnostics` baseline замеряется на базовой ветке в начале задачи с `--max-diagnostics` достаточного размера |
| build | `pnpm build` | exit-code | долгий |
| e2e | по проекту | rerun-compare-set | не входит в `test`; обязателен, когда правка тронула словарь, разметку, стили или моки API |
| visual | по проекту | exit-code | снимки в браузере; не входит в `test`; обновление baseline только осознанно и только на хосте, где baseline воспроизводим |

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
- Один файл: `pnpm test {Name}` или `pnpm exec vitest run {Name}`; один тест:
  `pnpm test -t "{name}"`. **Никогда `pnpm test -- {X}`**: с `--` pnpm искажает
  аргументы, и vitest тихо прогоняет всё. **Никогда `--filter={X}`** для vitest.

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
пакете: команда из каталога пакета, а не фильтр turbo. Не все пакеты имеют все
скрипты: перед запуском прочитать `package.json` пакета.

## long_running

`e2e`, `build`, полный прогон vitest по монорепо: запускать отсоединённо через
`scripts/gate.py` и ждать опросами (`protocol/runtime.md`, «Гейты»); в foreground
не дольше двух-трёх минут. Тесты гонять по пакетам.
