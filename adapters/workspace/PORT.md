---
port: workspace
required: [resolve_base, branch, setup, integrate]
optional: [worktree, submodules, protected, sync]
config: [workspace.base, workspace.branch, workspace.worktree, workspace.setup, workspace.submodules, workspace.integration, workspace.protected, workspace.repos, workspace.sync, workspace.delivery, multitask.push]
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
| integrate | да | влить часть мультизадачи в ветку мультизадачи или ветку одиночной задачи в базу (`workspace.delivery: integrate`) по `workspace.integration` | finalize |
| worktree | нет | создать, войти, выйти, снести worktree; также создать, подготовить и снести research-worktree чужого репозитория (без входа) | start, finalize, research |
| submodules | нет | инициализировать submodule'ы, соблюдать их правила | setup, coder, review |
| protected | нет | список веток, куда коммитить напрямую запрещено | start, finalize |
| sync | нет | подтянуть ушедшую вперёд базу в ветку задачи или части: rebase или merge, разрешение конфликтов, гейты на слитом дереве | implement, review, finalize |

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

## sync

Сдвиг базы и стратегию определяет `sync.py check TASK_DIR` (JSON: ref базы, её
голова, отставание, есть ли в ветке что-то кроме артефактов, грязное ли дерево,
стратегия). Стратегия по `workspace.sync`:

| `workspace.sync` | Ветка только с артефактами | Ветка с кодом |
|---|---|---|
| `auto` (дефолт) | rebase | merge |
| `merge` | merge | merge |
| `rebase` | rebase | rebase |

Rebase многих кодовых шагов останавливается почти на каждом коммите, а один merge
даёт один раунд конфликтов и сохраняет хеши шагов в log.md. База, ушедшая вперёд
только в каталоге артефактов (записи трекера `local`, сводный блок, заметки),
синхронизации не требует: `moved` считает изменения вне него.

Порядок для любого адаптера:

1. Только на границе и на чистом дереве: до Implement, после коммита шага Implement,
   в начале Review, перед Finalize. Посреди шага не синхронизироваться: незакоммиченное
   дерево под rebase требует stash, а он общий для всех worktree.
2. Слияние запускает оркестратор. Конфликты разрешает coder в режиме `MODE: sync`
   (`git add`, без коммита и без отмены слияния). Конфликт, требующий решения по
   дизайну, идёт в точку `deadlock`.
3. Коммит слияния делает оркестратор; сообщение перечисляет конфликты «файл — как
   разрешено». Поломки вне конфликтных файлов чинятся отдельным коммитом после слияния.
4. После синхронизации полный набор гейтов, а не только конфликтные файлы. Базовые
   наборы критериев сравнения (`rerun-compare-set`, `no-new-diagnostics`) переснимаются
   на новой голове базы.
5. Синхронизация до Implement: ссылки `path:line` в spec.md и plan.md сверяет с новой
   головой владелец артефакта (architect, в S оркестратор).
6. След: `sync.py record TASK_DIR --how … --base-sha … --commit …` (список `syncs`
   в `state.yaml`) и секция `### Синхронизация с {base} @ {sha} ✅` в log.md
   с перечнем конфликтов.

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
  sync: auto                  # auto | merge | rebase (подтягивание базы, возможность sync)
  delivery: pr                # pr | integrate | lead (сдача одиночной задачи на Finalize)
  protected: [master, "release/*"]
  repos:                      # чужие репозитории для исследования
    omix-lib:
      path: ../eps-omix-lib   # относительно корня домашнего проекта
      remote: git@github.com:org/eps-omix-lib.git
      ref: auto               # ветка | тег | sha | auto (базовая ветка того проекта)
      setup: false            # выполнять его workspace.setup в research-worktree
multitask:
  push: true                  # пушить ветки мультизадачи и частей
```

## Авторинг адаптера

Git-специфика (worktree, submodule, squash) описывается в адаптере `git`; ядро
знает только имена возможностей. Ловушки worktree и cwd задокументированы
в `protocol/worktree.md`, адаптер на них ссылается.
