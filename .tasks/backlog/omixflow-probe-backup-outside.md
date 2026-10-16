---
id: omixflow-probe-backup-outside
title: probe.py кладёт копию PATH.orig рядом с файлом — в каталогах с автозагрузкой (миграции) копия становится вторым модулем
status: draft
type: bug
created: 2026-10-16
updated: 2026-10-16
origin: Swarga AI Studio T-12 (G-69 лида swais-lead, 2026-10-16, сессия на 0.9.0), сверено по scripts/probe.py, CLAUDE.md SwAIS и reports/implement-step2.md T-12
target: omixflow
external:
links: [omixflow-mutation-restore-mtime]
---

**Контекст.** `scripts/probe.py` (0.8.0): копия `PATH` → `PATH.orig` рядом с файлом
(`probe.py:20`, `ORIG = ".orig"` `:89`, запись `:274`), мутация, прогон, восстановление
`cp`, удаление копии; `probe.py restore --file PATH` ищет копию там же (`:344-353`).
`report.py check` считает оставшийся `*.orig` проблемой дерева.

**Проблема.**
- SwAIS: node-pg-migrate грузит любой файл в `packages/server/migrations/`, в том числе
  `*.orig` (CLAUDE.md SwAIS, стр. 51–52: «копии класть только вне каталога»). Копия рядом
  с мутируемой миграцией — вторая миграция на время пробы.
- T-12, Implement, шаг 2: 65 проб, из них 48 через `probe.py batch` и 17 проб миграции —
  своим скриптом coder'а в `SCRATCH_DIR` «по рецепту probe.py, потому что probe.py кладёт
  копию `.orig` рядом с файлом» (reports/implement-step2.md, стр. 88): копия вне каталога,
  восстановление записью байт со сверкой, БД пересоздавалась на каждом прогоне.
  Скрипт-самоделка повторил то, что probe.py уже делает (даты mtime, сверка байт), —
  ровно то, ради чего probe.py заводили.
- Тот же класс: любой каталог, где загрузчик берёт все файлы (плагины, `conf.d`, Unity
  `Assets/` с импортом новых файлов и `.meta`).

**Предложение.**
1. Копия — в git-каталоге дерева, как логи `gate.py`: `{git-dir}/omixflow-probes/{путь
   с заменой / на __}.orig` (детерминированно: `restore --file PATH` находит её и после
   обрыва). Каталог рядом с файлом не трогается.
2. `probe.py restore` без `--file` — восстановить все копии из `omixflow-probes/`
   с перечнем; `report.py check` (TREE STATE) — оставшаяся копия в `omixflow-probes/` —
   проблема «проба не восстановлена: `probe.py restore --root …`».
3. Сохранить сверку байт после восстановления и правила mtime (MEW-6) без изменений;
   тест на файл в каталоге, где появление любого нового файла — ошибка.

**Критерии приёмки.** probe.py не создаёт файлов рядом с мутируемым файлом; проба файла
в каталоге миграций проходит `probe.py batch` без ручных скриптов; `restore` находит копию
после обрыва; тесты в `tests/`.
