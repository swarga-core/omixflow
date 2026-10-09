---
id: omixflow-rotation-context-teammates
title: Ротация по контексту слепа — уведомления именованных агентов не несут usage
status: draft
type: bug
created: 2026-10-09
updated: 2026-10-09
origin: разбор прогона MEW-2 в mewria 2026-10-09 (первый прогон на 0.5.0, тир L), сессия omixflow-lead
target: omixflow
external:
links: [omixflow-agent-rotation-context]
---

**Контекст.** 0.5.0 ввёл ротацию continuation-агентов по `limits.agent_rotation_context`
(350k): `tiers.md` берёт объём контекста «по уведомлению о последнем завершении» агента.
Проверено было на безымянном фоновом агенте: его `task-notification` несёт
`<usage><subagent_tokens>`.

**Проблема.** Все агенты пайплайна спавнятся с `name`. С `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
они становятся teammates (`taskKind: in_process_teammate` в `subagents/*.meta.json`),
и о конце хода сообщает `idle_notification` без usage. Оркестратору MEW-2 не на что было
опереться, проверку он пропустил молча — ни ротации, ни строки в log.md. Контекст перед
заданиями (из транскриптов агентов):
- coder: 161k после шага 1, 243k, 292k, 437k перед шагом 5, 531k, 624k, 683k, 718k к концу Review;
- architect: 355k на переходе Spec → Plan, 419k к концу Plan;
- reviewer Spec и Plan: 350k перед третьим проходом Plan, 358k в конце;
- reviewer кода: 354k перед третьим проходом.
Порог шагов (10) при 7 шагах не сработал тоже.

**Решение (0.5.1).** `scripts/agent_ctx.py NAME` читает объём контекста агента из его
транскрипта: `{CLAUDE_CONFIG_DIR|~/.claude}/projects/*/{CLAUDE_CODE_SESSION_ID}/subagents/*.meta.json`
с этим `name`, последний ответ ассистента, сумма `input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`. Работает в обоих режимах (teammate и фоновый агент).
Если транскрипт не найден — `context: null` с причиной; тогда usage из уведомления, а без
него строка в log.md «контекст {имя} неизвестен» и ротация только по шагам.

**Критерии приёмки.** Скрипт с тестом на фикстуре транскрипта; `tiers.md` называет его
источником объёма; молчаливый пропуск проверки невозможен — неизвестный объём пишется
в log.md.
