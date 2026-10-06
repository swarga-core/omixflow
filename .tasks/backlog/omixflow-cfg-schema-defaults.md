---
id: omixflow-cfg-schema-defaults
title: cfg.py не подставляет умолчания схемы — пропущенный ключ даёт null
status: draft
type: bug
created: 2026-10-05
updated: 2026-10-05
origin: настройка OMIXFlow в mewria 2026-10-05
target: omixflow
external:
links: []
---

**Контекст.** Настройка mewria: из `flow.yaml` убрали `limits`, `tiers` и `models`, равные
умолчаниям схемы. После этого `cfg.py limits.coder_iterations --project ~/swarga/mewria`
печатает `null` с кодом 1. Ключи вернули обратно с комментарием «нужны явно, cfg.py
умолчаний не знает».

**Проблема.** Протокол обещает умолчания из схемы, а скрипт, через который их велено
читать, их не знает:

- `protocol/phases.md:35` — «Значения из конфига, дефолты в схеме»;
- `protocol/runtime.md:18` — значения читать через `cfg.py`, «не парсить YAML в голове»;
- `skills/implement/SKILL.md:39` — лимиты через `cfg.py limits.coder_iterations`,
  `cfg.py limits.agent_rotation_steps`;
- `scripts/cfg.py:31-34` — отсутствующий ключ печатает `null` и выходит с кодом 1.

Проект с минимальным конфигом получает `null` вместо лимита, и оркестратор либо угадывает
значение, либо открывает схему. Прецедент решения уже есть: умолчания `lead` живут
в `omixflow_lib` (`LEAD_DEFAULT_*`), линт сверяет их со схемой.

**Предложение.** `cfg.py` при отсутствии ключа в конфиге берёт `default` из
`schema/flow.schema.json` по пути `properties` (помощник `schema_default(dotted)`
в `omixflow_lib`); единственный источник умолчаний — схема. Флаг `--raw` отдаёт значение
только из конфига (для `doctor` и проверок «задано ли явно»). Делать вместе с пунктом 4
черновика `issues-tk-6.md` (терпимость к `cfg.py get KEY`): тот же скрипт.

**Критерии приёмки.**
- `cfg.py limits.coder_iterations` на конфиге без `limits` печатает `7` с кодом 0.
- Ключ без умолчания в схеме по-прежнему даёт `null` и код 1; `--raw` игнорирует умолчания.
- Тест на оба случая; `templates/flow.yaml` больше не обязан перечислять умолчания.
