# Research: AL-1147

## Task Summary
Introduce pipeline profiles (`full`, `research`) as an axis orthogonal to `kind` and tier, and build on `research` a same-session scheduler of parallel read-only multitask parts (named continuation researchers, blocking/deferred questions, Handoff, synthesis) plus cross-repo research over `workspace.repos` pinned to a sha. Touches scripts, schema, protocol, five skills, the researcher agent, four ports, tests and docs.

## Source Files Map

| File | Role | Relevance |
|------|------|-----------|
| `scripts/state.py` | implementation | `PHASES` hard list (l.29) drives `init` (phase=`PHASES[0]`), `next_phase`, `set phase=` validation, `complete`; `PROFILES` goes here |
| `scripts/multitask.py` | implementation | `MARK_START` exact string, fixed `COLUMNS`, `parse_rows`/`render`/`replace_block`/`validate`/`ready`/`cmd_set`/`cmd_seed`/`multitask_file`; marker attrs, `repo` column, profile-aware validation |
| `scripts/resolve.py` | implementation | Already has `--project` for every kind; exits 2 on missing flow.yaml; fallback for foreign repos |
| `scripts/doctor.py` | implementation | `Doctor.check_workspace` holds the review-worktree accumulation check (closest pattern); new `workspace.repos` checks |
| `scripts/omixflow_lib.py` | implementation | `find_project_root`, `load_config`, `normalize_config`, light JSON-schema `validate` (no `patternProperties`/`propertyNames`), `resolve_base_branch`, `git()` helper |
| `scripts/cfg.py` | implementation | Reads config values by dotted key; `--project` supported; how skills read `workspace.repos`, `multitask.parallel_parts` |
| `scripts/wt-setup.sh` | related | EnterWorktree hook: submodule init + `workspace.setup` from the worktree's own flow.yaml; reusable for research-worktree setup (hook does not fire for `git worktree add`) |
| `schema/flow.schema.json` | config | `workspace` has `additionalProperties: false` (must add `repos`); `multitask` object (add `parallel_parts`) |
| `templates/flow.yaml` | config | Commented template; `test_template_is_valid` validates it against the schema |
| `.claude/omixflow/flow.yaml` | config | This repo's own config; `multitask.parallel_per_owner: 1` |
| `hooks/hooks.json` | reference | Only `PostToolUse[EnterWorktree]`; confirms orchestrator must do setup for `git worktree add --detach` |
| `protocol/phases.md` | spec | "Восемь фаз, всегда в одном порядке" (l.3), phase table, invariant 7 (l.32-34) |
| `protocol/tiers.md` | spec | S = inline research; model table `researcher: S не спавнится, L сильная`; research profile bypasses triage |
| `protocol/runtime.md` | spec | Ports-per-phase table (research: lang only, l.25); "Researcher и web-fetcher одноразовые, имя не обязательно" (l.44); spawn template |
| `protocol/review-cycle.md` | spec | Continuation principle lists architect/coder/tester/reviewer only (l.56) |
| `protocol/multitask.md` | spec | Block example and columns, part lifecycle (worktree+squash), `parallel_per_owner` (l.112), `blocked` stops owner (l.130-131), reconciliation "no part branch => integrated" (l.140-142), PARTS_IN_FLIGHT overlap rule (l.63-66) |
| `protocol/artifacts.md` | spec | state.yaml example (add `profile`, `repos`), research.md description, layout |
| `protocol/dialog.md` | spec | Canon table of interaction points; needs rows for blocking questions and part-completion dialog |
| `protocol/glossary.md` | spec | Terms: фаза "один из восьми этапов" (l.12), мультизадача "каждая со своим полным пайплайном, веткой" (l.39), интеграция части = squash (l.47); new terms go here |
| `protocol/worktree.md` | spec | Worktree roots `.claude/worktrees/{id}`/`{id}-{part}`; research-worktree is a new kind; submodule traps |
| `protocol/adapters.md` | reference | Core-without-tools rule, ports table, "what doctor checks" list |
| `skills/develop/SKILL.md` | implementation | Single-task triage/phase loop; M0-M4 multitask loop; M2.1 blocked=stop; M2.5 and rules "одна активная часть на владельца"; invariant 7 in l.83-84 and errors table l.147 |
| `skills/start/SKILL.md` | implementation | Single task (branch, state init, complete refine/start); multitask start; part start with worktree + `parallel_per_owner` (l.110); invariant 7 in errors l.135 |
| `skills/research/SKILL.md` | implementation | Tier S inline vs agent; PARTS_IN_FLIGHT; "answers mandatory"; unnamed researcher spawn; scheduler mode lands here |
| `skills/finalize/SKILL.md` | implementation | Single-task finalize; `--part` reconciliation by branch absence + squash; `--multitask` finalize |
| `skills/refine/SKILL.md` | implementation | `--multitask` seeds the block via `multitask.py seed`; invariant 7 at l.83-84 ("разбивается"); no profile/repo input today |
| `skills/create/SKILL.md` | related | Spawns researcher one-shot, `OUTPUT: inline` (l.34); must stay one-shot |
| `skills/spec/SKILL.md` | related | "research.md ... answers binding" consumer; not in research profile but reads the same research.md format |
| `skills/doctor/SKILL.md` | related | Parses `checks[]` statuses OK/WARN/FAIL; any new status level changes its contract |
| `agents/researcher.md` | implementation | Inputs, Output format; gets MODE synthesis, `STATUS: done \| blocked`, `## Handoff`, cross-repo header, INPUTS, PROJECT_ROOT navigation line; tools lack `Write` |
| `agents/architect.md` | reference | Treats research.md answered design questions as binding (l.19-20, 43-44); deferred-unanswered questions must not reach it in `full` |
| `adapters/tracker/PORT.md` | spec | "Управляемые блоки" contract: markers `<!-- omixflow:{kind}:start -->` exact form (l.31-37) |
| `adapters/tracker/youtrack.md` | related | Multitask search by substring `omixflow:multitask` (l.68); still matches attributed marker |
| `adapters/tracker/local.md` | related | Shows the marker in its file layout (l.39-41); has a `target:` frontmatter field "репозиторий, если задача не про этот" (l.31) |
| `adapters/workspace/PORT.md` | spec | Frontmatter `config:` list (l.5) to extend with `workspace.repos`; config example |
| `adapters/workspace/git.md` | implementation | `integrate` uses `add -A` + squash (l.46-53); submodule worktree removal order (l.72-88) reused for research-worktree teardown |
| `adapters/lang/PORT.md` | spec | "Навигация" section (l.53-58) gets the PROJECT_ROOT activation line |
| `adapters/lang/ts.md` | reference | Concrete navigation section (named tools allowed in adapters) |
| `.claude/omixflow/lang/py.md` | reference | Project lang adapter: gates, test conventions, CHANGELOG protocol/port rule |
| `tests/test_state_multitask.py` | tests | `test_lifecycle` (must keep passing), multitask tests with inline `DESCRIPTION` fixture; new profile/marker/repo tests go here |
| `tests/test_scripts.py` | tests | Schema tests (`test_unknown_keys_and_bad_enums_are_rejected` pattern), doctor tests incl. `test_doctor_warns_about_accumulated_review_worktrees` (git temp repo pattern), resolve/cfg tests |
| `tests/test_lint.py` | tests | Forbidden terms, `TOOL_NAMES` in core, SendMessage-vs-named-spawn per SKILL.md; new "profiles table == PROFILES" lint |
| `tests/test_adapter_scripts.py` | tests | Adapter scripts; untouched but part of the green suite |
| `tests/fixtures/ts-youtrack/.claude/omixflow/flow.yaml` | tests | The only config fixture; `multitask.parallel_per_owner: 1`; candidate for `workspace.repos` sample or a new fixture |
| `README.md` | reference | Intro lists eight phases (l.3-4); "Скилы"/"Термины" sections; needs phases+profiles |
| `CHANGELOG.md` | reference | `[Unreleased]` with **protocol**/**port** bold prefixes per bullet |
| `.claude-plugin/plugin.json` | config | Version 0.2.0; `plugin.min_version` interplay with the new marker |

## Current State

### `state.py` and `PHASES`
- `PHASES = [refine, start, research, spec, plan, implement, review, finalize]` (l.29). `KINDS`, `MODES`, `TIERS` tuples next to it.
- `cmd_init`: validates kind/mode/tier, writes `phase: PHASES[0]`, `completed: []`; `kind=part` requires `--multitask-id` and `--part` and writes `multitask: {id, part}`. No profile, no parent lookup.
- `next_phase(state)`: first of `PHASES` not in `completed`, else `"done"`.
- `cmd_set`: `phase` must be in `PHASES + ["done"]`; also validates `tier`, `mode`; everything else is free-form via `set_dotted` (so `profile=`/`repos=` would be accepted unvalidated today; JSON values allowed for `[`/`{`).
- `cmd_complete`: rejects phases not in `PHASES`, re-orders `completed` by `PHASES`, sets `phase = next_phase`.
- `cmd_get KEY` prints `null` and **exits 1** for a missing key: a legacy state.yaml without `profile` will return exit 1 on `state.py get DIR profile`, so skills need either a default in the script or explicit null handling.
- Errors: `OmixflowError` -> exit 2.
- Tests: `StateTests.test_lifecycle` drives everything through subprocess (`run("state.py", ...)`): init M/pipeline -> `next`=refine -> complete refine, start -> `next`=research -> set/step/agents -> `set phase=lunch` exit 2 -> re-init without `--force` exit 2. `test_part_requires_multitask_fields` covers part init. No other consumer of `PHASES` in scripts (only state.py).

### `multitask.py`
- Block located by `text.find(MARK_START)` with `MARK_START = "<!-- omixflow:multitask:start -->"` exactly; verified: a marker `<!-- omixflow:multitask:start profile=research -->` gives `find_block == None`, so `has` exits 1 (develop/start treat the task as single), `extract` raises, and `seed --from` would append a second block.
- `parse_rows`: header from the first `|` line, lower-cased; builds a fixed dict (`n, part, title, depends, depends_raw, owner, status, branch, commit`); **any other column (e.g. `repo`) is silently dropped**. `—`, `-`, `""` normalize to `None` for owner/branch/commit.
- `render(rows)`: always emits `MARK_START`, header from fixed `COLUMNS`, separator `|---|---|...|`, renumbers `#` from 1, `MARK_END`. It drops: marker attributes, unknown columns, the original separator style, original `#` values, whitespace/padding.
- `replace_block`: replaces span between markers (or appends with blank-line separation).
- Round-trip probe: `render(extract(render(rows))) == render(rows)` is true (canonical); `replace_block(DESCRIPTION, extract(DESCRIPTION)) == DESCRIPTION` is **false** for the test fixture and the protocol example because they use `|---|------|-------|...` separators.
- `validate(rows)`: slug, title, empty depends cell, unknown/self deps, status in `STATUSES`, `ACTIVE` without owner, duplicates, then cycle via `waves`. No profile/repo awareness, no args.
- `ready(rows, owner)`: `ready` = pending parts whose deps are all `done`; `blocked_by_skipped_dependency`; `blocked` list; `active` list; `mine_active` = ACTIVE parts with `owner == owner` (only when owner is given); `all_terminal`. **No limit enforcement**: `parallel_per_owner` is enforced only in skill prose (develop M2.5, start part step 1, multitask.md l.112). A pending part whose dependency is `blocked` is simply not ready (waits), which matches the research-profile rule.
- `cmd_set`: editable keys `status, owner, branch, commit, title, depends`; rejects others with exit 2 (`n=9` test); validates, then `replace_block` (full re-render). `--in-place` writes the file.
- `cmd_seed`: builds rows from `--parts "slug — title"` and `--depends`; refuses when a block exists. No profile/repo flags.
- `multitask_file`: "## Интеграция" section hard-codes squash and part branches `task/{id}-{part}` - wrong for the research profile.

### `resolve.py`
- `--project DIR` exists today for all kinds (`adapter`, `adapter-script`, `agent`, `script`, `base`). Root = `lib.find_project_root(ns.project)`: nearest ancestor with `.claude/omixflow/flow.yaml`, else git toplevel, else start.
- Missing flow.yaml: `lib.load_config` raises -> **exit 2** with `omixflow: конфиг не найден: ...`. Verified for `adapter lang --project /tmp` and `agent researcher --project /tmp`. Note that `adapter` loads config even when the adapter name is passed explicitly (l.50), and `agent` also needs config (mapping) so "RULES from the foreign project" fails the same way.
- Both target repos (`eps-omix-lib`, `eps-eal-omix`) currently have flow.yaml; their parent `/Users/andreynitsenko/omi` has none, so parent-walk does not leak.

### `doctor.py`
- `Doctor` collects `Check(section, name, status, detail)`; statuses only `OK/WARN/FAIL`; exit 1 iff any FAIL. `run()`: env, config (schema) -> ports, workspace, verify, artifacts, agents.
- Closest pattern: end of `check_workspace` (l.166-176): `git worktree list --porcelain`, filter `/.claude/worktrees/pr-`, WARN above `REVIEW_WORKTREE_WARN = 3`, else OK. Test `test_doctor_warns_about_accumulated_review_worktrees` builds a temp git repo, writes a minimal flow.yaml, adds 4 detached worktrees, asserts WARN and detail contains `pr-4`.
- Submodule check parses `.gitmodules` with regex; `setup` checks first word in PATH.
- `skills/doctor/SKILL.md` parses `checks[]` with statuses OK, WARN, FAIL.

### `omixflow_lib.py` / `cfg.py`
- `load_config` -> `normalize_config` (shorthands; `workspace.adapter` default git). `validate` supports: type, required, properties, additionalProperties (bool or schema), enum, items, pattern, minimum, minItems, `$ref`, definitions. **No `patternProperties`, `propertyNames`, `oneOf/anyOf`**: repo-name slug keys cannot be enforced by the schema without extending the validator (additionalProperties-as-schema validates values only).
- `resolve_base_branch(cfg, root)`: `auto` = origin/HEAD then main/master; `pattern:latest`; literal.
- `git(root, *args)` returns stdout or `None` on failure; good for origin/ref/HEAD/dirty checks.
- `cfg.py KEY --project DIR` prints scalars, JSON for objects, `null`+exit 1 for missing, exit 2 without config.

### Protocol/skills today
- Multitask part = full pipeline, own branch and worktree, squash integration (multitask.md l.114-128, finalize `--part`, git.md `integrate` with `add -A`).
- Reconciliation: "no part branch while block says in-work/in-review => integrated" (multitask.md l.140; finalize `--part` "Реконсиляция" greps `feat({id}): {part}`).
- PARTS_IN_FLIGHT overlap stop (multitask.md l.63-66, research skill steps 1 and 4, researcher Inputs).
- Research skill: S inline into spec.md; M/L spawn researcher without name; step 5 "Ответы обязательны для architect".
- Named spawn rule: runtime.md l.41-44 and review-cycle.md l.56 require names for architect/coder/tester/reviewer; researcher "одноразовые, имя не обязательно".
- Lint `SkillLint`: `SEND_RE` captures the prefix before `-{` after `SendMessage`; `SPAWN_RE` captures `name: <prefix>-{`; per SKILL.md the SendMessage prefixes must be a subset of spawn prefixes. `researcher-{id}-{part}` yields prefix `researcher` for both.
- Lint `test_core_does_not_name_tools`: `TOOL_NAMES` regex (package managers, runners, `gh api|pr|repo`, `mcp__*__`) over `protocol/`, `skills/`, `agents/` (agent frontmatter exempt). It does **not** include LSP tool names, so "no tool names" for the new navigation line is enforced by review, not by this regex.
- **No existing lint parses a Markdown table from protocol/**. The only table parser in the repo is `multitask._split_row`/`parse_rows`.
- `start --part` does not call `state.py complete ... refine/start` for the part (single-task start does). `develop` M3 resume uses `state.py next PART_DIR`, which would return `refine` for a fresh part. Pre-existing gap that becomes visible once profiles validate phases.

## Existing Patterns
- Canon-in-code + lint against docs: `lib.PORTS` vs `adapters/*` (`AdapterLint`), `lib.ROLES` vs `agents/*.md` (`test_plugin_agents_exist_for_all_roles`), `lib.GATES` vs schema `verify`. A `PROFILES` vs `protocol/profiles.md` table lint follows this; table parsing can reuse the `_split_row` approach (strip leading/trailing pipes, split on `|`).
- Script CLI shape: argparse subcommands, `OmixflowError` -> stderr `omixflow: ...` exit 2, validation errors listed with exit 1 (`multitask.py validate`).
- Tests: `unittest`, subprocess `run(script, *args)` helper plus direct module import (`mt.extract`); tempfile dirs; doctor tests build throwaway git repos. Schema-rejection pattern: mutate a loaded config and assert paths appear in joined errors.
- Doctor checks: section/name/detail strings, thresholds as module constants (`REVIEW_WORKTREE_WARN`).
- Named continuation spawn + SendMessage in one SKILL.md (spec, plan, implement, review).
- CHANGELOG `[Unreleased]` bullets prefixed `**protocol**` / `**port** {port}:`; README has "Устройство", "Скилы", "Скрипты" sections and a one-line phase list in the intro.
- Worktree teardown with submodules: `adapters/workspace/git.md` l.72-88 (the order Finalize must reuse for research-worktrees in `eps-eal-omix`, which has submodule `omix` -> `eps-omix-lib`).
- Hook setup logic in `scripts/wt-setup.sh` reads `workspace.submodules`/`workspace.setup` from the target tree's own flow.yaml via `cfg.py --project`; can be invoked with a synthetic `{"cwd": path}` payload.

## Findings
1. **Marker regression risk is total, not partial.** With the attribute, today's code finds no block at all. All of `has/extract/validate/ready/set/seed/file` depend on `find_block`; the new regex must also keep `MARK_END` pairing and reject a second start marker. `render` must take the attributes (or a profile) as input; `cmd_set`/`replace_block` must pass through the parsed marker line. Older plugin versions will not see attributed blocks (consider noting `plugin.min_version` in CHANGELOG).
2. **Byte-for-byte round-trip** is only achievable today for canonically rendered blocks; the protocol example and the test fixture use a different separator. See Q1.
3. **`repo` column**: `parse_rows` drops it, `render` never emits it; render must emit it only when present (otherwise legacy blocks change). "Immutable after start" needs an explicit rule in `cmd_set` (e.g. allowed only while `pending`), and `validate` needs profile + home/repo list parameters (`--repos` CLI arg) to reject unknown names and non-home `repo` in `full`.
4. **`multitask_file` "Интеграция"** text is profile-specific (squash/branches vs commit-by-path on `task/{id}`).
5. **Reconciliation grep** for research parts depends on the fixed commit message format; the task fixes that a format exists but not its text (existing full-profile format `feat({id}): {part} — {title}`). The commit must be path-scoped (`git add .tasks/{id}/{part}/`, `git commit -- <path>`), never `add -A` as in git.md `integrate`.
6. **`blocked` reason**: the block has no reason column; today the reason lives in a tracker comment (develop M2.1). Task says "blocked в блоке с причиной". See Q2.
7. **Profile/repo entry point**: nothing writes `profile=` or `repo` into a block today (`refine --multitask` -> `seed` has no such flags; `set` cannot add rows). See Q3.
8. **Schema**: `workspace.additionalProperties: false` rejects `repos` until added. Entry schema can be `additionalProperties: {type: object, additionalProperties: false, required: [path, remote], properties: {path, remote, ref, setup}}`. Slug keys are not expressible with the current light validator; either extend `lib.validate` (`propertyNames`/`patternProperties`) or leave slug to doctor (the task assigns it to doctor). `multitask.parallel_parts` (integer, minimum 1, default 4) goes next to `parallel_per_owner`.
9. **`ref: auto`** means "the foreign project's base" and collides in wording with `workspace.base: auto` (= remote default branch). Resolution naturally is `resolve.py base --project {repo}` (honours e.g. `release/*:latest` in both target repos), falling back to origin/HEAD when the foreign repo has no flow.yaml.
10. **Doctor remote comparison** needs URL normalization (ssh `git@github.com:omi-enjoy/eps-omix-lib.git` vs https forms, trailing `.git`). "flow.yaml presence (info)" has no status level today (OK/WARN/FAIL only). See Q4.
11. **Doctor `research-*` check** must scan worktrees of each foreign repo (`git -C {repo} worktree list --porcelain`, filter `/.claude/worktrees/research-`), map `research-{id}` to home `{artifacts.dir}/{id}/state.yaml` and flag `phase: done`. The existing pr-* test is the template (temp git repos for home and foreign; `path` relative to home root).
12. **resolve.py fallback**: both `adapter` and `agent` fail with exit 2 without flow.yaml, so a skill-side "handle code 2" must handle two commands; a script flag centralizes it. See Q5.
13. **Research-worktree setup**: the EnterWorktree hook does not fire for `git worktree add --detach`; `wt-setup.sh` could be reused with a synthetic payload, but it reads setup from the target tree's flow.yaml (the foreign one), silently skipping if absent. `eps-eal-omix` needs submodule init (`omix`). See Q6.
14. **Research-worktree path persistence**: task stores only `repos: {name: {ref, sha}}` in multitask state.yaml; the worktree path is deterministic (`{repo}/.claude/worktrees/research-{id}`), so existence can be probed, but whether PROJECT_ROOT for a repo is the checkout or the worktree is decided per part launch (HEAD recheck). Architect should decide whether to persist `root` next to `sha`.
15. **Profile inheritance for parts**: `state.py init --kind part` does not read the parent state; either start passes `--profile` from the multitask state or `init` reads `../state.yaml`. Legacy states without `profile` must behave as `full` in `next/complete/set` (acceptance criterion); `get profile` returns exit 1 today.
16. **Part start does not complete refine/start** in the part state (pre-existing). With profile-validated phases and scheduler resume ("parts in-work without research.md restart"), the part's `next` should be `research`; fixing this is cheap and relevant.
17. **Invariant 7 locations**: phases.md l.32-34; develop l.83-84 and errors table l.147; start errors table l.135; refine l.83-84. **glossary.md does not contain invariant 7** (task statement says it does); only the new term "репозиторий workspace" and adjusted "мультизадача"/"интеграция части"/"фаза" definitions belong there.
18. **Other hard-coded assumptions to update**: phases.md l.3 "Восемь фаз, всегда в одном порядке"; glossary фаза "один из восьми этапов", мультизадача "полный пайплайн, веткой", интеграция части = squash; README intro phase list; develop description frontmatter and rules l.157-163 ("одна активная часть на владельца", "параллельны только researcher и web-fetcher"); research skill "единственная фаза с параллельными агентами", S inline, "Ответы обязательны"; tiers.md model table row researcher; runtime.md l.41-44 and ports table; review-cycle.md l.56; multitask.md l.3-7 (intro), l.63-66, l.104-112, l.130-131, l.140-142; artifacts.md state.yaml example and research.md line; `parallel_per_owner` in schema, template, both configs, develop M2.5, start part step 1, multitask.md l.112.
19. **Researcher agent has no `Write` tool** (frontmatter `tools: Read, Glob, Grep, Bash, Agent, mcp__serena__*`) yet `OUTPUT: file` writes `research.md`: writing works only via Bash. Relevant because the continuation contract (`STATUS`, Handoff, append after blocking answer) makes the agent rewrite its file several times.
20. **Lint coverage**: moving the named spawn into the research skill's scheduler keeps the SendMessage lint satisfied only if spawn and SendMessage texts both sit in `skills/research/SKILL.md`. If finalize/start (nested) or develop mention `SendMessage researcher-{...}`, they need a spawn mention too.
21. **Port contract `config:` lists** are documentary only: `lib.port_contract` returns them but no test or doctor check uses them. A new lint (config keys in PORT.md exist in schema) would be optional.
22. **LSP single active project**: both foreign repos are separate git checkouts; a research-worktree is a third project path, so repo-grouping must treat "repo" (not path) as the activation unit and all parts of a repo must share the same PROJECT_ROOT (checkout or the one research-worktree).
23. **Baseline**: `python3 -m unittest discover tests` = 43 tests OK on this branch.

## Design Questions

Answered by the developer on 2026-09-28. Answers are binding for spec and plan.

Q1: What exactly must "блок без атрибута round-trip байт-в-байт" guarantee?
Context: `render` normalizes the separator line, `#` numbering and cell padding; the protocol example and the test fixture (`|---|------|...`) do not survive `set` byte-for-byte today. Options: (a) guarantee only `render(extract(x)) == x` for canonically rendered blocks, test on a rendered block; (b) make `set` surgical: rewrite only the changed row cells and keep header/separator/other lines verbatim (true byte-preservation for hand-written blocks, more code); (c) preserve the original header and separator lines but re-render data rows.
A1: (b) Surgical `set`: only the cells of the changed row are rewritten; the marker line (with its attributes), header, separator and every other row are kept verbatim. Hand-written blocks (protocol example, test fixture) must survive `set` byte-for-byte outside the changed row. `render` stays the canonical writer for `seed`.

Q2: Where does the `blocked` reason of a research part live?
Context: the block has no reason column; the full profile keeps it in a tracker comment plus log.md. Options: (a) keep the convention: status `blocked` in the block, reason in tracker comment and part log.md, end-of-run summary; (b) add an optional `note` column rendered only when non-empty (another column that `render` must preserve).
A2: (a) Keep the `full` convention: status `blocked` in the block, the reason in a tracker comment and in the part's log.md, plus the end-of-run summary printed by the scheduler. No new column.

Q3: How do `profile=research` and the `repo` column get into a block?
Context: `refine --multitask` writes the block through `multitask.py seed`, which has neither a profile nor a repo input, and `set` cannot touch the marker. Options: (a) `seed --profile research --repo {name|—} ...` and refine asks profile once and repo per part (refine gains a dialog step and `workspace.repos` reading); (b) only `seed` flags, refine unchanged, developer passes them explicitly; (c) manual edit of the description, scripts only parse.
A3: (a) `seed` gets `--profile` and per-part `--repo` flags; `refine --multitask` asks the profile once (AskUserQuestion, default `full`) and, for a non-`full` profile, the repository of each part from `workspace.repos` (home = `—`). Scripts remain the only writer of the block.

Q4: How does doctor report "foreign repo has flow.yaml" (info)?
Context: statuses are OK/WARN/FAIL; `skills/doctor/SKILL.md` parses those three. Options: (a) OK with detail "flow.yaml есть/нет, фолбэк на цепочку домашнего проекта" and WARN reserved for the resolve fallback case; (b) introduce an `INFO` status (touches render totals, JSON contract and the doctor skill).
A4: (a) `OK` with a detail string ("flow.yaml есть" / "flow.yaml нет, фолбэк на цепочку домашнего проекта"); `WARN` and `FAIL` stay reserved for real problems. The doctor JSON contract and `skills/doctor/SKILL.md` do not change.

Q5: Resolve fallback for a foreign repo without flow.yaml: script flag or skill-side exit-code handling?
Context: both `resolve.py adapter lang` and `resolve.py agent researcher` exit 2 without config. Options: (a) `--fallback-project {home}` (or similar) on resolve.py: adapters/agent mapping from the home config, project-layer files and RULES still looked up in the foreign root when present; (b) scheduler catches exit 2 and re-runs without `--project`, no script change.
A5: (a) `resolve.py … --project {foreign} --fallback-project {home}`: when the foreign root has no flow.yaml, adapter chains and agent mapping come from the home config, while project-layer files and RULES are still looked up in the foreign root when present. One mechanism for both `adapter` and `agent`, covered by script tests; the skill never parses exit codes.

Q6: What does `workspace.repos.{name}.setup: true` run in a research-worktree?
Context: the hook does not fire; `wt-setup.sh` reads `workspace.submodules`/`workspace.setup` from the worktree's own flow.yaml. Options: (a) orchestrator runs `wt-setup.sh` with a synthetic `{"cwd": worktree}` payload, i.e. the foreign project's own setup and submodules; skip with warning if the foreign repo has no flow.yaml; (b) always initialize submodules regardless of `setup`, run the foreign `workspace.setup` only when `setup: true` (research navigation of `eps-eal-omix` needs the `omix` submodule even without installing dependencies).
A6: (b) The orchestrator always initializes submodules in a research-worktree (`git submodule update --init --recursive`, with `--reference` when known, per the workspace adapter); the foreign project's `workspace.setup` runs only when `workspace.repos.{name}.setup: true`. Navigation is complete without installing dependencies.
