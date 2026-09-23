# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии по SemVer.
Изменения протокола (`protocol/`) и контрактов портов (`adapters/*/PORT.md`) помечаются
как **protocol** и **port**: проект, пинящий версию плагина, читает именно их.

## [0.1.0] — 2026-09-23

Скелет плагина. Скилы фаз и агенты ещё не перенесены из `eps-omix-lib/.claude/`.

### Added
- Манифесты плагина и marketplace.
- **protocol**: glossary, phases, tiers, dialog, review-cycle, artifacts, worktree, multitask, adapters.
- **port**: контракты `tracker`, `forge`, `lang`, `workspace` (`adapters/*/PORT.md`).
- Стартовые адаптеры: `tracker/{youtrack,local,none}`, `forge/{github,none}`, `lang/ts`, `workspace/git`.
- Схема конфига `schema/flow.schema.json`, шаблон `templates/flow.yaml`.
- Скрипты `scripts/doctor.py`, `scripts/resolve.py`, `scripts/cfg.py`, библиотека `scripts/omixflow_lib.py`.
- Хук `PostToolUse[EnterWorktree]` → `scripts/wt-setup.sh` (setup worktree по `workspace.setup`).
- Скил `doctor`.
- Тесты `tests/`.

### Changed
- Терминология: «эпик» заменён на «мультизадача», «подзадача» на «часть» (см. `protocol/glossary.md`).
