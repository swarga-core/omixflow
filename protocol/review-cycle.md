# Ревью-цикл

Общий протокол для фаз Spec, Plan и Review и для любого места, где артефакт или код
проверяет reviewer.

## Цикл

1. Спавн **reviewer** через Agent tool с параметром `name` (`reviewer-{id}` или
   `reviewer-{id}-{part}`), MODE: review, с ASPECTS и ARTIFACT_PATHS фазы
   и `FINDINGS_PATH: {TASK_DIR}/review/{phase}-pass{N}.json`.
2. Reviewer пишет полный контракт в `FINDINGS_PATH`, а в ответе даёт сводку и путь:
   длинный ответ агента обрезается в канале сообщений. Оркестратор читает файл.
   Решения принимаются программно по `severity` и `category`:
   - `suggestion` любой категории: auto-accept;
   - `warning` категорий `spec`, `plan`, `code`, `tests`, `spec-sync` с понятным
     фиксом: auto-accept;
   - `warning [architecture]` и любой `critical`: эскалация в точке `finding`
     (`dialog.md`).
3. FIX выполняет **исполнитель по категории**: `spec` и `plan` идут architect'у задачи,
   `code` и `spec-sync` идут coder'у, `tests` идут tester'у (после coder). Reviewer
   в MODE fix только когда правка тривиальна и своего исполнителя у задачи нет.
   `spec-sync` — правка кода и проектных спецификаций; текст spec.md задачи coder правит
   тоже, если контракт не меняется (формулировка, ссылка, пометка), — иначе architect.
   Исполнитель получает принятые findings с решениями через SendMessage, потому что
   он уже существует как continuation-агент.
4. Re-review: SendMessage тому же reviewer по имени, не новый спавн, с новым
   `FINDINGS_PATH` прохода. Проверяются только исправленные findings по тем же id;
   новые дефекты, внесённые фиксами, получают новые id.
5. Не больше `limits.review_passes` проходов, затем эскалация нерешённых findings
   в точке `finding` (раздел «Лимит проходов»).

## Лимит проходов

- **Счётчик — на объём.** Scope-change, принятый в фазе (`dialog.md`, точка `scope-change`),
  открывает ревью нового объёма со своим счётчиком проходов: ревью дельты не продлевает
  и не исчерпывает цикл исходного объёма. В log.md: «ревью дельты scope-change, проход 1/N».
- **Approve с новыми не-blocking findings на последнем проходе.** Их применяет исполнитель
  по категории без нового прохода; проверяет ревью следующей фазы (Spec и Plan → Review).
  Если фаз с ревью не осталось — гейты зелёные и строка в log.md «применено после
  лимита: #{id}, без прохода».
- **Фикс, принятый в точке `finding` после лимита.** Не трогает исходный код (только тесты
  или артефакты), гейты зелёные, мутация новых тестов красная — закрывается без прохода.
  Меняет исходный код — один дополнительный проход только по этим id, с явного разрешения
  разработчика в той же точке `finding`. Решение — строкой в log.md.
- Прочие исключения из `limits.review_passes` — эскалация в точке `finding`.

## Контракт findings

```json
{
  "findings": [
    {
      "id": 1,
      "severity": "critical | warning | suggestion",
      "category": "code | tests | spec-sync | spec | plan | architecture",
      "file": "path:line или artifact: name",
      "problem": "что не так",
      "recommendation": "что сделать"
    }
  ],
  "recommendation": "approve | request_changes",
  "blocking": [1]
}
```

`critical` всегда блокирует. Пустой список findings означает approve.

## Continuation-принцип

Действует для всех агентов задачи: один спавн с `name`, далее SendMessage. Coder
получает шаги 2+ и fix-пакеты сообщениями; architect получает fix-пакеты по spec
и plan; reviewer получает re-review. При обрыве агента SendMessage возобновляет его
из транскрипта; перед продолжением попросить сверить фактическое состояние файлов
(`git status`, `git diff`), потому что мутационные пробы могли остаться в дереве.

Для этого каждый спавн architect, coder, tester и reviewer обязан иметь `name`.
Researcher именуется, когда его продолжают: спавны скила `research` для задачи
и части (`researcher-{id}`, `researcher-{id}-{part}`) получают ответ на блокирующий
вопрос через SendMessage и продолжают с тем же контекстом. Спавн без имени там,
где агента продолжают, это дефект скила.
