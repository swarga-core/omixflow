---
port: workspace
required: [resolve_base, branch, setup, integrate]
optional: [worktree, submodules, protected]
config: [workspace.base, workspace.branch, workspace.worktree, workspace.setup, workspace.submodules, workspace.integration, workspace.protected, multitask.push]
---

# Порт workspace

Устройство репозитория и git-флоу: от чего ветвиться, как называть ветки, как
изолировать задачу, как ставить зависимости, как вливать части мультизадачи.

## Возможности

| Возможность | Обязательна | Что делает | Кто использует |
|---|---|---|---|
| resolve_base | да | вычислить базовую ветку по `workspace.base`: фиксированное имя, шаблон с выбором последней, или default-ветка remote | start, finalize, doctor |
| branch | да | имя ветки задачи и части по шаблонам; создать идемпотентно | start |
| setup | да | установить зависимости и подготовить дерево к гейтам | хук worktree, start |
| integrate | да | влить часть мультизадачи в ветку мультизадачи по `workspace.integration` | finalize части |
| worktree | нет | создать, войти, выйти, снести worktree | start, finalize |
| submodules | нет | инициализировать submodule'ы, соблюдать их правила | setup, coder, review |
| protected | нет | список веток, куда коммитить напрямую запрещено | start, finalize |

## resolve_base

Формы `workspace.base`:

| Форма | Значение |
|---|---|
| `main` | фиксированное имя |
| `release/*:latest` | среди веток по шаблону выбрать последнюю по версии в имени |
| `auto` | default-ветка remote |

Скрипт `resolve.py base` реализует это одинаково для всех адаптеров; адаптер
описывает, как обращаться с результатом.

## Шаблоны веток

`workspace.branch` для задачи (`task/{id}`), часть мультизадачи получает
`{branch}-{part}`. Слэш между id и частью невозможен.

## Конфиг

```yaml
workspace:
  base: "release/*:latest"
  branch: "task/{id}"
  worktree: optional          # off | optional | always
  setup: pnpm install
  submodules:
    - path: omix
      readonly: true          # правки внутри запрещены, только bump указателя
  integration: squash         # squash | merge
  protected: [master, "release/*"]
multitask:
  push: true                  # пушить ветки мультизадачи и частей
```

## Авторинг адаптера

Git-специфика (worktree, submodule, squash) описывается в адаптере `git`; ядро
знает только имена возможностей. Ловушки worktree и cwd задокументированы
в `protocol/worktree.md`, адаптер на них ссылается.
