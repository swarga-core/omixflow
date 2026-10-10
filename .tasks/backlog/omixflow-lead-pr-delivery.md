---
id: omixflow-lead-pr-delivery
title: Под лидом при lead.delivery pr нет приёмки PR; имя лида не задаётся в конфиге
status: draft
type: feature
created: 2026-10-10
updated: 2026-10-10
origin: лид swais-lead 2026-10-10 — подключение OMIXFlow 0.5.1 к swarga-ai-studio, находки 4, 5
target: omixflow
external:
links: [omixflow-lead-delivery-default]
---

**Проблема.**
- `lead.delivery: pr` есть в схеме, но `protocol/lead.md` описывает приёмку только для
  сдачи `lead` («Приёмка мержа», `accept.py`): кто и как вливает PR задачи под лидом
  (CI, ревью, санкция, `M-{n}`), не сказано.
- Имя лида передаётся `--lead=NAME` в каждой задаче; ключа в `flow.yaml` нет.

**Предложение.**
- Раздел «Приёмка PR» в `lead.md`: проверки PR через порт forge (статус CI, ревью), санкция
  `A-{n}`, merge возможностью порта, запись `M-{n}`, статус и комментарий в трекере — или
  явная пометка, что при `pr` вливание вне протокола.
- `lead.name` — умолчание для `develop --lead`; явный `--lead` важнее; `--no-lead` — без.

**Критерии приёмки.** Протокол описывает, кто и как вливает PR задачи под лидом;
`/omixflow:develop T-n` без `--lead` при `lead.name` регистрируется у лида.
