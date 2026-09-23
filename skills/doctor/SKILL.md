---
name: doctor
description: Checks or bootstraps an OMIXFlow project config (.claude/omixflow/flow.yaml) — adapters resolve, required capabilities are covered, base branch and verify gates exist. Use when setting up OMIXFlow in a project, when a pipeline skill reports a config or adapter problem, or when the user asks to "check omixflow setup", "init omixflow", "configure the pipeline for this repo".
---

# OMIXFlow doctor

Проверяет конфиг проекта и окружение или создаёт конфиг с нуля. Ничего в проекте
не меняет без подтверждения, кроме файлов внутри `.claude/omixflow/`.

## Активация

- `/omixflow:doctor` — проверить текущий проект.
- `/omixflow:doctor --init` — создать `.claude/omixflow/flow.yaml` черновиком
  и довести его диалогом.

## Алгоритм

### 1. Проверка

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --json
```

Разобрать JSON: `checks[]` с `section`, `name`, `status` (OK, WARN, FAIL), `detail`.
Показать разработчику компактную таблицу: сначала FAIL, затем WARN, OK одной строкой
счётчиком. Для каждого FAIL предложить конкретное действие из `detail`.

Если конфига нет, а `--init` не передан: предложить `--init` через AskUserQuestion
(Создать черновик (Recommended) / Не сейчас).

### 2. Инициализация (`--init`)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --init --json
```

Скрипт пишет черновик с автодетектом: трекер по известным MCP-серверам, forge по
remote и наличию CLI хостинга, языки по файлам-маркерам экосистем, гейты по скриптам
пакетного манифеста, submodule'ы по `.gitmodules`. Что именно детектируется, знает
скрипт, не скил. Затем довести черновик диалогом по `protocol/dialog.md`:

1. Прочитать созданный `flow.yaml` и результаты проверки.
2. Перечислимое через AskUserQuestion, до четырёх вопросов за вызов:
   - адаптер трекера (варианты из `adapters/tracker/` плагина плюс «свой»);
   - ключ проекта трекера, если адаптер его требует и в черновике `CHANGE-ME`;
   - base branch: детект (Recommended) / фиксированное имя / шаблон `release/*:latest`;
   - политика worktree: optional (Recommended) / off / always.
3. Неперечислимое текстом: команды гейтов, которые не удалось определить; статусы
   трекера для `status_map`.
4. Внести ответы в `flow.yaml` (Edit), повторить проверку без `--init`, показать итог.

Ответы разработчика в `flow.yaml` записываются как значения; правила и пояснения
туда не пишутся, для них есть CLAUDE.md проекта и проектные адаптеры.

### 3. Проблемы адаптеров

- «адаптер не найден»: показать список доступных в плагине
  (`ls "${CLAUDE_PLUGIN_ROOT}/adapters/{port}/"`) и напомнить про свой адаптер
  в `.claude/omixflow/{port}/{name}.md` по `protocol/adapters.md`.
- «не покрыты обязательные»: показать `required` из `PORT.md` порта и предложить
  либо `extends` плагинного адаптера, либо дописать возможности.
- «MCP-сервер не найден»: сказать, какой сервер нужен, и что подключение делается
  через `claude mcp add` или `.mcp.json` проекта; сам скил серверы не настраивает.

### 4. Итог

Одним сообщением: путь к конфигу, число FAIL и WARN, что осталось сделать руками.

## Правила

- Скил не редактирует ничего вне `.claude/omixflow/`. Изменение `.gitignore`
  (например, когда `artifacts.tracked: true`, а каталог игнорируется) только
  предлагается.
- Не угадывать ключ проекта трекера и статусы: спросить.
- `doctor.py` без `--json` пригоден для чтения человеком; в скиле использовать
  `--json`.
