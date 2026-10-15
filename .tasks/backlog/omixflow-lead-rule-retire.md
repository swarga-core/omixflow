---
id: omixflow-lead-rule-retire
title: Правило-прецедент R-n нельзя снять — list, brief и precedents отдают его после замены решения-основания
status: draft
type: bug
created: 2026-10-15
updated: 2026-10-15
origin: Swarga AI Studio, переход на 0.9.0 (G-61 лида swais-lead, 2026-10-15), сверено по scripts/lead.py и журналу лида SwAIS
target: omixflow
external:
links: [omixflow-tier-ceiling, omixflow-tier-from-statement]
---

**Контекст.** Правило лида — запись `rule` в журнале (`lead.py rule --text … --decision D-n`),
поле `decisions` — решения-основания. Бриф берёт «действующие правила» из
`lead.py list --type rule` (`skills/lead/SKILL.md:131`), `lead.py precedents` отдаёт все
правила вместе с решениями (`scripts/lead.py:377`). Вето, меняющее правило-прецедент,
`protocol/lead.md:550-552` проводит заменой решений по нему (`lead.py replace`), «чтобы
`precedents` не отдавал устаревшее» — о самом правиле там ничего нет.

**Проблема.**
- Журнал SwAIS: R-1 (2026-10-11, T-8, основание D-163 по E-28) — «план превышает
  `tiers.m_max_files`, по остальным критериям M — тир остаётся M, лид решает сам». Применено
  в T-18 и T-11. С 0.9.0 это противоречит протоколу: продолжение сверх порога файлов —
  исключение разработчика (`lead.py decide --exception`), не прецедент
  (`protocol/lead.md:271-275`).
- Разработчик правило снял, порог в flow.yaml поднят до 30 (SwAIS main `0615fff`). Лид
  записал D-238 («R-1 снято…», точка `scope-change`) и `replace D-163 --with D-238`.
- `lead.py replace R-1 …` отказывает: «нет записи R-1 (decision)» — `cmd_replace` ищет только
  среди решений (`scripts/lead.py:205-212`). У `rule` нет состояния «снято»: `fold`
  (`scripts/lead.py:115-116`) держит только `uses`, `is_open` для правил всегда `True`
  (`:160`), `precedents` отдаёт `records["rule"]` целиком.
- Итог: `list --type rule` и `precedents` по-прежнему показывают R-1 как действующее, хотя
  его единственное основание D-163 заменено. Новый лид после перезапуска возьмёт R-1 в брифы,
  сессии — в решения по прецеденту.

**Предложение.**
1. `lead.py rule-retire R-n --decision D-m`: событие `{"type": "rule-retire", "ref": "R-n",
   "decision": "D-m"}`; `fold` ставит правилу `retired: D-m`; повторное снятие — ошибка, как
   у `replace`.
2. `is_open` для правила — `retired is None`; `precedents` отдаёт только действующие правила;
   `describe` пишет «(снято D-m)».
3. Бриф (`skills/lead/SKILL.md:131`) и проверка журнала перед решением (`:260`) — `list --type
   rule --open`. Протокол «Вето» (`protocol/lead.md:550-552`): вето, меняющее правило, снимает
   его `rule-retire` решением вето, затем заменяет решения по нему.
4. Подсказка: `replace D-n` для решения, на котором держится действующее правило, печатает
   в stderr «R-k держится на D-n: снять — `lead.py rule-retire R-k --decision D-m`» (сам не
   снимает: правило могло держаться и на других решениях).

**Критерии приёмки.** Снятое правило не попадает в brief, в `list --type rule --open` и
в `precedents`; `list` без `--open` показывает его со ссылкой на решение; `rule-use` снятого
правила — ошибка; тесты на `rule-retire`, повторное снятие и фильтр `precedents`.
