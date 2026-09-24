---
name: research
description: Research phase of the OMIXFlow pipeline — investigates the codebase (and web sources when needed) for a started task, produces research.md with a Source Files Map, then walks the developer through design questions. Tier-aware (S inline, M/L via the researcher agent). Use after /omixflow:start or when the user says "исследуй задачу", "research".
---

# OMIXFlow research

Исследование кодовой базы и, при необходимости, внешних источников. Результат:
Source Files Map, текущее состояние, паттерны, findings, ответы на design questions.

Пролог: `${CLAUDE_PLUGIN_ROOT}/protocol/runtime.md`. Порт: lang. Тиры:
`${CLAUDE_PLUGIN_ROOT}/protocol/tiers.md`.

## Активация

- `/omixflow:research {id}` или `{id}/{part}`.
- `/omixflow:research "{тема}"`: standalone исследование без задачи; результат
  возвращается текстом, артефакты не создаются.

## Предусловия

`TASK_DIR/task.md` и `state.yaml` существуют; `state.py next` даёт `research`
(иначе показать состояние и спросить, пересоздавать ли research).

## Алгоритм

### 1. Контекст

`task.md`: финальная формулировка, scope. Тир из `state.py get TASK_DIR tier`
(нет → M). Цепочка адаптеров lang. Для части мультизадачи собрать
`PARTS_IN_FLIGHT`: для каждой другой части со статусом не терминальным, у которой
есть `{artifacts.dir}/{id}/{other}/research.md`, взять файлы из её Source Files Map.

### 2. Нужен ли веб-ресёрч

Баг или рефакторинг: обычно нет. Новая фича с нестандартными паттернами: возможно.
Стандарты, спецификации, RFC: да. Веб-ресёрч не по умолчанию.

### 3. Исследование

**S-тир (инлайн).** Оркестратор исследует сам, read-only, инструментами навигации
из адаптера lang. Результат: секция `## Research` (mini Source Files Map + findings)
в `TASK_DIR/spec.md`; отдельный research.md не создаётся. Если вскрылся масштаб
больше S: повысить тир (`state.py set tier=M`), записать причину в log.md
и выполнить фазу заново через агента.

**M и L.** Спавн `researcher` по шаблону runtime.md: `TASK_DIR`, `ADAPTERS.lang`,
`RULES`, `SCOPE`, `PARTS_IN_FLIGHT`, `OUTPUT: file`; на L `model: {models.strong}`.
При веб-ресёрче параллельно второй агент `web-fetcher` с конкретным QUERY,
MAX_SOURCES 3, MAX_CHARS_PER_SOURCE 8000; его результат добавить секцией
`## External Research`. Это единственная фаза с параллельными агентами.

### 4. Необъявленные зависимости (часть мультизадачи)

Пересечение Source Files Map части с `PARTS_IN_FLIGHT`: остановиться, показать
файлы и части, спросить разработчика: объявить зависимость (обновить блок через
`multitask.py set … depends=…` и `multitask.md`) / продолжить осознанно / изменить
scope. Молча не продолжать.

### 5. Design questions

Секция `## Design Questions` из research.md (или из инлайн-исследования).
Перечислимые через AskUserQuestion (до четырёх за вызов, варианты из research
с контекстом в description, рекомендуемый первым), остальные текстом. Ответы
записать в артефакт:

```markdown
Q1: {вопрос}
Context: {контекст}
A1: {ответ разработчика}
```

Ответы обязательны для architect: без них spec не пишется.

### 6. Состояние и журнал

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" complete "{TASK_DIR}" research
```

`log.md`: `## Research ✅` с числом файлов в карте, вопросов и ответов, веб-ресёрч
да/нет, пометка `(inline)` для S. Коммит артефактов.

### 7. Итог (mode manual)

```
Research завершён: {артефакт}, файлов в карте: {N}, вопросов: {N} (все отвечены).
Следующий шаг: /omixflow:spec {id}
```

## Масштаб

| Задача | Глубина | Файлов в карте |
|---|---|---|
| точечный баг | несколько файлов вокруг симптома | до 8 |
| изменение API | пакет и потребители | 10–15 |
| новая фича | несколько пакетов и паттерны | 15–25 |
| архитектурное изменение | всё затронутое плюс документация | 25+ |

## Правила

- Source Files Map обязателен: без него spec и plan не имеют контекста.
- Исследование read-only.
- Вопросы лучше предположений.
- Веб-ресёрч только когда действительно нужен.
- В worktree агентам только абсолютные пути внутри него.
