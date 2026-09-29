---
port: lang
name: py
capabilities: [verify, test_conventions, suppressions, navigation, deps_setup]
requires:
  tools: [mcp__serena__*]
  bin: [python3]
scripts: {}
---

# Адаптер lang: Python (проектная замена для репозитория плагина)

Репозиторий OMIXFlow: скрипты `scripts/*.py` на стандартной библиотеке плюс PyYAML,
тесты `unittest`, остальное Markdown (скилы, агенты, протокол, адаптеры) и JSON
(манифесты, схема). Гейты дешёвые, фоновых нет.

## verify

| Гейт | Команда | Критерий | Примечания |
|---|---|---|---|
| test | `python3 -m unittest discover tests` | exit-code | включает линт терминологии и линт «инструменты адаптеров не в ядре» (`tests/test_lint.py`) |
| lint | `claude plugin validate .` | exit-code | манифесты, фронтматтер скилов и агентов |

Один тестовый модуль: `python3 -m unittest tests.test_scripts`; один тест:
`python3 -m unittest tests.test_scripts.TestX.test_y`.

Изменения в `protocol/` и `adapters/*/PORT.md` обязаны сопровождаться записью
в `CHANGELOG.md` с пометкой **protocol** или **port** в том же коммите: это
SDD-инвариант проекта, проверяет ревью.

## test_conventions

- Файлы `tests/test_*.py`, классы `unittest.TestCase`, фикстуры в `tests/fixtures/`.
- Скрипты тестируются через `main(argv)` и временные каталоги (`tempfile`), не через
  subprocess, если нет причины проверять именно CLI.
- Новое правило протокола, которое можно проверить механически, получает тест
  в `tests/test_lint.py`.

## suppressions

Запрещено добавлять как «фикс»: `# type: ignore`, `# noqa` без обоснования,
`unittest.skip`/`expectedFailure` для зелёности, `except Exception: pass`,
ослабление регулярных выражений линта в `tests/test_lint.py` под конкретный текст.

## navigation

- serena для символов Python: `get_symbols_overview`, `find_symbol`,
  `find_referencing_symbols`. Проект активировать по абсолютному `PROJECT_ROOT`.
- Markdown (протокол, скилы, адаптеры) читается целиком: правило живёт в одном
  месте, остальные ссылаются, поэтому перед правкой найти это место `Grep`
  по ключевому термину и проверить `protocol/glossary.md`.
- ast-grep через Bash для структурного поиска по Python.

## deps_setup

`python3 -m pip install pyyaml`. Других зависимостей нет; `claude` CLI для гейта lint.
