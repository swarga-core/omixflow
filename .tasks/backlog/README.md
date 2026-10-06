# Backlog — хвосты плагина, найденные в ходе задач

Каждый документ — самодостаточное описание проблемы или улучшения для последующего
оформления в трекер (`/omixflow:create` из файла или вручную). Формат: контекст
и происхождение, проблема с доказательствами, предлагаемое решение, критерии приёмки,
ограничения.

После заведения задачи дописать в документ ссылку на issue либо удалить документ, если
постановка перенесена целиком.

| Документ | Происхождение |
|---|---|
| [omixflow-part-reads-repos.md](omixflow-part-reads-repos.md) | AL-1147, запуск аудита паритета legacy → eal — часть research-мультизадачи читает ровно один репозиторий; нужна колонка `reads` (read-only корни у части, `REPOS` у researcher'а) вместо двухэтапной декомпозиции |
| [omixflow-lead-coordinator.md](omixflow-lead-coordinator.md) **[РЕАЛИЗОВАНО 0.3.0]** | обсуждение после AL-1147 — лид как реактивный координатор сессий: маршрут вопросов по политике, прецеденты, единое окно, бэклог и память, ветка лида; реализация по плану работ в документе (18 шагов, без отдельных задач в трекере), начиная со спайка межсессионных сообщений |
| [omixflow-local-tracker-worktree.md](omixflow-local-tracker-worktree.md) | живой прогон лида 2026-10-04 — Refine с трекером `local` пишет в основное дерево на защищённой базе, worktree задачи этой правки не видит; перенос в ветку задачи штатным шагом Start |
| [omixflow-review-passes-closing.md](omixflow-review-passes-closing.md) | живой прогон лида 2026-10-04 — как закрывать фикс, принятый после исчерпания `limits.review_passes`: без прохода, если исходник не тронут, иначе дополнительный проход с разрешения разработчика |
| [omixflow-protocol-diet.md](omixflow-protocol-diet.md) | повторный прогон лида 2026-10-04 (10b) — сессия тира S читает ~100K токенов протокола до первого действия; обязательный минимум по скилам, остальное по требованию с условием |
| [omixflow-agent-escape-bytes.md](omixflow-agent-escape-bytes.md) | третий прогон лида 2026-10-04 (гоча G-2 журнала лида) — агенты пишут литерал вместо escape-последовательности в параметрах инструментов и отчитываются по намерению, а не по байтам файла |
| [omixflow-coder-mutation-report.md](omixflow-coder-mutation-report.md) | третий прогон лида 2026-10-04 (G-3) — coder обобщает мутационную проверку в отчёте вместо перечня проб и их исходов |
| [omixflow-findings-prefix.md](omixflow-findings-prefix.md) | третий прогон лида 2026-10-04 (G-10) — findings Research в spec.md и findings ревью делят префикс `F`, метки в сообщениях лида путаются |
| [omixflow-iteration-tracker-sync.md](omixflow-iteration-tracker-sync.md) | третий прогон лида 2026-10-04 (G-7) — итерация после вето меняет постановку, но не обновляет уточнённую формулировку в трекере |
| [omixflow-kanban-tracker.md](omixflow-kanban-tracker.md) **[В РАБОТЕ]** | обсуждение 2026-10-04 после 0.3.0 — трекер kanban: доска на отдельной ветке в `.tasks/board/`, колонки-папки, карточка как досье задачи (`task.md`, `state.yaml`, артефакты), сквозные номера, несколько разработчиков, эпики; план работ из 11 шагов |
| [omixflow-cfg-schema-defaults.md](omixflow-cfg-schema-defaults.md) | настройка OMIXFlow в mewria 2026-10-05 — `cfg.py` не подставляет умолчания схемы: без явных `limits` в `flow.yaml` скилы читают `null`, хотя протокол обещает «дефолты в схеме» |
| [omixflow-artifacts-tracker-commits.md](omixflow-artifacts-tracker-commits.md) | настройка OMIXFlow в mewria 2026-10-05 (переезд на kanban) — implement, spec, plan, research, review и finalize коммитят артефакты безусловно, а при трекере с `artifacts` `.tasks/` игнорируется и `git add` падает |
| [omixflow-orchestrator-gates.md](omixflow-orchestrator-gates.md) | настройка OMIXFlow в mewria 2026-10-05 — проверка, которую выполняет оркестратор инструментом (Unity через MCP: компиляция, `.meta`, EditMode-тесты), не выражается гейтом `verify` и не имеет места в шагах implement, review и finalize |
| [omixflow-agent-tools-lsp.md](omixflow-agent-tools-lsp.md) | настройка OMIXFlow в mewria 2026-10-05 — `tools` агентов зашиты на serena и ts-morph, LSP-инструмент Claude Code агентам недоступен; порт lang приравнивает LSP к serena |
| [omixflow-gate-when-semantics.md](omixflow-gate-when-semantics.md) | настройка OMIXFlow в mewria 2026-10-05 — `when` у гейта: «дополнительно обязателен» в порту lang, допускает чтение-фильтр в `runtime.md`; области изменений нигде не заданы машинно, `doctor` их не проверяет |
| [omixflow-kanban-board-invariants.md](omixflow-kanban-board-invariants.md) | ревью ветки kanban 2026-10-05, открыто и на main после 0.4.0 — `checkout --force` не удаляет лишние файлы рабочей копии; `set` пишет резолюцию вне `done` и даёт эпику самого себя в родители; `set title=` не трогает `task.md`; формальные поля карточки в трёх списках; git 2.31+ |
| [omixflow-skill-text-contradictions.md](omixflow-skill-text-contradictions.md) | ревью ветки kanban 2026-10-05, открыто и на main после 0.4.0 — «Правила» doctor запрещают трогать `.gitignore`, разделы 3 и 4a велят его править и коммитить; spec называет синоним `complete` вместо `state.py finish`, линт это пропускает |
