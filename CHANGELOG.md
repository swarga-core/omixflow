# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии по SemVer.
Изменения протокола (`protocol/`) и контрактов портов (`adapters/*/PORT.md`) помечаются
как **protocol** и **port**: проект, пинящий версию плагина, читает именно их.

## [0.2.0] — 2026-09-24

Перенос пайплайна из `eps-omix-lib/.claude/` и `omix-pr-review`.

### Added
- Скилы `develop`, `create`, `refine`, `start`, `research`, `spec`, `plan`,
  `implement`, `review`, `finalize`, `pr-review`.
- Агенты `researcher`, `architect`, `coder`, `tester`, `reviewer`, `web-fetcher`:
  языконезависимые, инструменты и гейты берут из адаптеров, переданных при спавне.
- **protocol**: `runtime.md` (пролог скила, спавн агентов, режим pipeline/manual).
- Скрипты `state.py` (state.yaml), `multitask.py` (блок мультизадачи, карта
  зависимостей, волны, готовность частей).
- Скрипты адаптеров: `forge/github/pr.py` (view, files, reviews-mine, threads,
  build-payload, validate, submit, reply, permalink), `tracker/local/backlog-index.py`.
- `resolve.py adapter-script`, `resolve.py agent` печатает `subagent_type`;
  проектный агент с тем же именем перекрывает плагинного.
- Линт: агенты объявляют фронтматтер; тело агентов и скилов не называет инструментов;
  у каждого адресата SendMessage есть именованный спавн.

### Changed
- **protocol**: `artifacts.md` — `state.yaml` получил `mode`, `completed`,
  `steps_done`, `session`; управляется скриптом.
- `develop` тонкий: вызывает фазовые скилы, дублирования логики фаз нет.
- Тир и лимиты читаются из конфига, а не зашиты в скилы.

### Fixed (относительно предыдущего поколения)
- architect спавнится с `name`, FIX-цикл spec/plan идёт ему, а не reviewer'у.
- Статистика finalize считается от base из состояния, а не от литерала `main`.
- Раунды re-review считаются по настоящим ревью (ответы в треды не раунды).
- Отсутствие артефактов пайплайна у автора PR не считается spec drift.
- Review-worktree получает setup (submodule, зависимости) до гейтов.
- Probe-правки файлов PR запрещены явно; APPROVE-раунд без находок описан.

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
