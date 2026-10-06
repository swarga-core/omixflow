---
id: omixflow-profiles-multitask-gaps
title: Хвосты профилей и мультизадачи после AL-1147
status: draft
type: bug
created: 2026-10-06
updated: 2026-10-06
origin: прогон AL-1147 (черновик issues-al-1147, разобран 2026-10-06)
target: omixflow
external:
links: [omixflow-part-reads-repos]
---

**Проблемы и предложения.**
1. **Свойства профиля — из Markdown-таблицы.** Скилы ветвятся по `mutates`, `part_isolation`,
   `finalize_artifact` и т. д., но берут их «по таблице `profiles.md`» глазами
   (`skills/research/SKILL.md:35-36`, `skills/finalize/SKILL.md:26-27`); `state.py get DIR
   profile` печатает только имя (`scripts/state.py:271-275`), `multitask.py meta` тоже.
   → `state.py get DIR profile --json` со свойствами; скилы вызывают команду.
2. **Повторный refine мультизадачи.** `protocol/multitask.md:131-132` обещает добавление
   частей `pending` и `skipped` для исчезнувших, но команды нет: `seed` на существующем блоке
   отказывает (`scripts/multitask.py:552-553`), `set repo=` на блоке без колонки `repo` падает
   (`:404-406`). → `multitask.py add-part` / `remove-part` (или `seed --merge`), сохраняющие
   статусы и добавляющие колонку `repo` при первом непустом значении.
3. **Integrate-поток части не закрывает finalize.** `skills/finalize/SKILL.md:180-186`
   не вызывает `state.py finish {PART_DIR} finalize` (commit-поток вызывает, `:208`);
   squash несёт `phase: finalize`. → вызвать перед коммитом в worktree части.
4. **`init --forced` при `triage: false`** даёт `tier: null, tier_forced: true`
   (`scripts/state.py:235-246`). → отклонять, как `--tier`; тест.
5. **`phases.md:13`, строка Research:** внешние действия только планировщика, для одиночной
   задачи не сказано «нет». → дописать.
6. **doctor считает research-worktree по каталогам** (`scripts/doctor.py:265`, glob, а не
   `git worktree list`) — выбор осознанный (путь фиксирован), но не объяснён. → фраза
   в докстринге.

**Критерии приёмки.** Тесты на 1, 2, 4; правки текста 3, 5, 6.
