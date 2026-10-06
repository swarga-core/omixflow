---
id: omixflow-lang-python
title: Адаптер lang python в плагине; doctor не узнаёт Python и не ловит расхождение языка
status: draft
type: feature
created: 2026-10-06
updated: 2026-10-06
origin: прогон TK-6 в песочнице kanban 2026-10-05 (черновик issues-tk-6 №1, разобран 2026-10-06)
target: omixflow
external:
links: [omixflow-gate-when-semantics]
---

**Контекст.** Песочница TK-6 на Python 3 (`unittest`, `verify.test: python3 -m unittest
discover -s tests -q`) получила `lang: [ts]`; гейты, конвенции `*.test.ts` и подавления TS
к ней неприменимы, оркестратор вручную переопределял их в промпте каждого агента.

**Проблема.** В `adapters/lang/` только `ts.md`. `doctor --init` узнаёт go, rust, php, csharp,
но не Python, и без маркеров подставляет `ts` (`scripts/doctor.py:435-447`); `check_ports`
не сверяет язык с кодом. У самого плагина есть проектная замена
`.claude/omixflow/lang/py.md` — готовая основа.

**Предложение.** `adapters/lang/python.md`: test (unittest / pytest), опционально typecheck
(mypy, pyright) и lint (ruff); `tests/test_*.py`, запуск одного теста; подавления
(`# type: ignore` без причины, `# noqa`, `skip`/`xfail`/`expectedFailure`). `doctor --init`
узнаёт `pyproject.toml` и `*.py`, не подставляет `ts` вслепую; `doctor` предупреждает
о расхождении языка адаптера и маркеров кода. Вопрос «гейты = ключи `verify.*`» —
`omixflow-gate-when-semantics`.

**Критерии приёмки.** Адаптер в плагине (плагин переходит на него); тесты doctor на детект
и предупреждение.
