# Plan: AL-1147

## Overview

Bottom-up: profile canon in `state.py` first, then the multitask block script, then
config/library/resolve, doctor, protocol and port documents, agent and skills, and
finally README and CHANGELOG consolidation. Cross-step rules:

- One step = one atomic commit that leaves the test gate green; a step that changes
  script behaviour lands with its tests (tester writes them from the checkpoint, coder
  runs them).
- SDD invariant of this repo (lang adapter `py`): a step that changes a contract
  updates its protocol/port document in the same commit and adds a CHANGELOG
  `[Unreleased]` line marked **protocol** or **port** (plain line for scripts,
  schema, skills, agents).
- `tests/test_state_multitask.py::StateTests.test_lifecycle` is never edited.
- The lint gate runs after every step that touches `skills/`, `agents/` or manifests.
- Spec references: `spec.md` slices 1–9 and decisions D1–D21 are binding; this plan
  does not restate them.

## Steps

### Step 1: Profile canon in state.py

**Goal:** `PROFILES` (with `part_runner`), `DEFAULT_PROFILE`, `profile_of`,
`phases_of`; profile-aware `init`/`set`/`complete`/`next`/`get profile`; strict
part-parent inheritance; `triage: false` tier rule (spec slice 1, D10, D11). Human
table in `protocol/profiles.md` with the lint that compares it to `PROFILES`.

**Files:**
- MODIFY: `scripts/state.py` — `PROFILES`, `DEFAULT_PROFILE`, `PHASES` alias,
  `profile_of`, `phases_of`, `next_phase` by profile; `init --profile`, parent lookup
  for `--kind part` (must be `kind: multitask` with matching id, else exit 2),
  conflicting `--profile` exit 2, `--tier` rejected and `tier: null` for
  `triage: false`; `set phase=`/`profile=` validation; `complete` by profile;
  `get DIR profile` effective value, exit 0; module docstring usage lines.
- CREATE: `protocol/profiles.md` — table with header
  `| profile | phases | mutates | part_isolation | part_integration | finalize_artifact | triage | part_runner |`
  and the prose from spec slice 5 (incl. the narrowed extensibility claim).
- MODIFY: `tests/test_state_multitask.py` — new profile tests (spec slice 8, state
  part); `test_part_requires_multitask_fields` gains a parent `kind: multitask`
  state in its temp dir, assertions otherwise unchanged.
- MODIFY: `tests/test_lint.py` — `ProfilesLint`: parse the table identified by its
  header in `protocol/profiles.md`, compare names, phase lists and every property
  (incl. `part_runner`) with `state.PROFILES`.
- MODIFY: `CHANGELOG.md` — **protocol** `profiles.md`; `state.py` profiles line.

**Test checkpoint:**
- [ ] `research` profile: after `start`, `next` = research, then finalize; `set
      phase=spec` and `complete spec` exit 2.
- [ ] Legacy state without `profile`: `next`/`complete`/`set` as `full`; `get
      profile` prints `full`, exit 0.
- [ ] Part inherits parent profile; missing parent, non-multitask parent,
      mismatching `--multitask-id`, conflicting `--profile` → exit 2.
- [ ] `--tier` with `research` → exit 2; `tier: null` stored; unknown profile → exit 2.
- [ ] Profiles lint passes; changing a table cell makes it fail (verified once
      locally, not committed).
- [ ] `test_lifecycle` untouched and green; test gate green.

### Step 2: Multitask marker, meta, surgical set

**Depends on:** Step 1
**Goal:** Whole-line marker regex with attributes, single-block rule,
`marker_errors`, `block_meta` + `meta` CLI, per-command reject/tolerate behaviour
with the declared-profile rule, surgical `set` (spec slice 2 marker parts, D1, D12).
Tracker port contract for attributed markers.

**Files:**
- MODIFY: `scripts/multitask.py` — marker regex (start/end anchored to whole
  lines), attribute parsing, second-start-marker error, `marker_errors`,
  `block_meta`, `meta` subcommand; reject in `validate`/`meta`/`ready`/`file`,
  tolerate in `extract`/`has`/`set`/`waves` (declared known profile, `full` only for
  unknown value); `set` rewrites only the target row line, no-op `set`
  byte-identical, error for a key whose column is absent; `render(rows,
  profile)` emits `profile=` for non-`full`; imports `PROFILES`/`DEFAULT_PROFILE`
  from `state.py` (needed by `marker_errors` and the declared-profile rule);
  module docstring.
- MODIFY: `adapters/tracker/PORT.md` — "Управляемые блоки": attributed start
  marker, whole-line markers, adapter keeps the start marker line verbatim.
- MODIFY: `protocol/multitask.md` — "Идентификация": marker attribute grammar,
  whole-line rule, known key `profile`, absent = `full`.
- MODIFY: `tests/test_state_multitask.py` — marker tests (spec slice 8, marker part).
- MODIFY: `CHANGELOG.md` — **port** tracker: attributed marker; **protocol**
  multitask marker attributes; `multitask.py` line (`meta`, surgical `set`).

**Test checkpoint:**
- [ ] `profile=research` marker found by `has`/`extract`/`meta`; `meta` returns
      the profile.
- [ ] `set` preserves the attributed marker line; hand-written block with
      `|---|------|` separator survives `set` byte-for-byte outside the target row;
      no-op `set` output byte-identical; canonical attribute-less block round-trips.
- [ ] Second start marker → error; inline backticked marker in prose → `has` exit 1,
      not a second block.
- [ ] Unknown/duplicate attribute and unknown profile rejected by
      `validate`/`meta`/`ready`/`file`, tolerated by `extract`/`has`/`set`/`waves`.
- [ ] Existing multitask tests unchanged and green; test gate green.

### Step 3: Multitask repo column, profile-aware validate/ready/seed/file

**Depends on:** Step 2
**Goal:** `Row.repo`, `render` repo column after `title`, `set repo=` only while
`pending`, `validate(rows, profile, repos)` with `--repos` on
`validate`/`set`/`seed`, `ready --parallel` (`slots`, `ready_by_repo`,
`active_repos`), `seed --profile --repo`, `render --profile`, profile-specific
`multitask_file` (spec slice 2, D13, D14).

**Files:**
- MODIFY: `scripts/multitask.py` — the items above.
- MODIFY: `protocol/multitask.md` — "Идентификация": second example block with
  `profile=research` and `repo`; column list gains `repo` (home `—`, non-mutating
  only, immutable after part start), `branch` `—` for `shared` parts.
- MODIFY: `tests/test_state_multitask.py` — repo/validate/ready/seed/file tests
  (spec slice 8).
- MODIFY: `CHANGELOG.md` — **protocol** multitask `repo` column; `multitask.py`
  line (`--repos`, `--parallel`, `seed --profile/--repo`).

**Test checkpoint:**
- [ ] `repo` parsed, rendered only when used, after `title`; rows without `repo` and
      profile `full` render byte-identical to before.
- [ ] Unknown `repo` with `--repos` and non-home `repo` in `full` → validate errors.
- [ ] `set repo=` accepted on `pending`, exit 2 otherwise.
- [ ] `seed --profile research --repo …` writes attributed marker and column.
- [ ] `ready --parallel N` gives `slots`, `ready_by_repo` (home key `—`, block
      order), `active_repos`; without `--parallel` `slots` is null.
- [ ] `file` "## Интеграция" text differs for `integrate` vs `commit`; each part
      gets `- Репозиторий: {repo | домашний}` when the block has a `repo` column,
      and no such line otherwise.
- [ ] `render --rows … --profile research` emits the attributed marker
      `profile=research`.
- [ ] Test gate green.

### Step 4: Config schema, library helpers, resolve.py

**Depends on:** Step 1
**Goal:** `workspace.repos` and `multitask.parallel_parts` in schema and template;
`resolve_repo_ref`, `repo_checkout_state`, `normalize_remote` in the library;
`resolve.py --fallback-project`, `resolve.py repo NAME`, `resolve.py repo --list`
(spec slice 3, D5, D17). Workspace port `config` list.

**Files:**
- MODIFY: `schema/flow.schema.json` — `workspace.repos` entry schema,
  `multitask.parallel_parts`, `parallel_per_owner` description.
- MODIFY: `templates/flow.yaml` — commented `workspace.repos` example,
  `multitask.parallel_parts: 4`.
- MODIFY: `scripts/omixflow_lib.py` — the three helpers.
- MODIFY: `scripts/resolve.py` — `--fallback-project` (direct
  `FOREIGN/.claude/omixflow/flow.yaml` check, no ancestor walk; adapter names from
  home with foreign project layer preferred; `base` as `auto` in the foreign repo;
  `agent` from home with foreign `rules`; stderr notice), `repo` kind with `--list`
  and `--json`; docstring.
- MODIFY: `adapters/workspace/PORT.md` — frontmatter `config:` gains
  `workspace.repos`; config example gains a `repos:` entry.
- MODIFY: `tests/test_scripts.py` — schema, template, resolve tests (spec slice 8).
- MODIFY: `CHANGELOG.md` — **port** workspace: `workspace.repos`, `config`;
  schema/template line; `resolve.py` line.

**Test checkpoint:**
- [ ] Valid `workspace.repos` accepted; missing `remote`, unknown key, non-boolean
      `setup` rejected; `parallel_parts: 0` rejected; template valid.
- [ ] Foreign repo without flow.yaml: adapter chain from home config, foreign
      project-layer file preferred when present; an ancestor's flow.yaml is ignored.
- [ ] `base` with fallback resolves in the foreign repo; `agent` returns home
      `subagent_type` and foreign `rules`.
- [ ] `repo NAME --json` gives path, ref, sha, head, dirty, has_config; branch ref
      prefers `origin/{name}`; unknown name exit 2; unresolvable ref `sha: null`
      exit 1; `repo --list` prints names comma-separated.
- [ ] `normalize_remote` equates ssh and https forms.
- [ ] `auto`/absent `ref` resolves to the foreign project's base (its own config,
      else remote default, else `main`/`master`), both with and without a foreign
      flow.yaml.
- [ ] `repo_checkout_state`: dirty = false with only untracked files or a
      research-worktree present; dirty = true with a tracked modification.
- [ ] `adapter-script` with `--fallback-project` uses the home adapter names.
- [ ] Without `--fallback-project` existing resolve tests unchanged and green; test
      gate green.

### Step 5: Doctor checks for workspace repos

**Depends on:** Step 4
**Goal:** `repo:{name}` section with `slug`, `path`, `git`, `remote`, `ref`,
`flow.yaml`, `research worktrees`; `RESEARCH_WORKTREE_WARN = 3`; task-state lookup
tree → task branch → unknown (spec slice 4, D4).

**Files:**
- MODIFY: `scripts/doctor.py` — checks run from `check_workspace` when
  `workspace.repos` is configured; constant next to `REVIEW_WORKTREE_WARN`.
- MODIFY: `tests/test_scripts.py` — doctor tests on temp git repos following
  `test_doctor_warns_about_accumulated_review_worktrees`.
- MODIFY: `CHANGELOG.md` — `doctor` line.

**Test checkpoint:**
- [ ] Bad slug FAIL; missing path FAIL; path inside home root FAIL; not a git repo
      FAIL.
- [ ] ssh-vs-https remote OK, mismatch FAIL; `ref` OK with short sha, unresolvable
      FAIL; `flow.yaml` OK with either detail.
- [ ] `research-{id}` of a home task with `phase: done` → WARN (also when the state
      is only on the task branch); unknown state → OK with detail; more than 3 →
      WARN.
- [ ] Doctor exit code and JSON shape unchanged for configs without `repos`; test
      gate green.

### Step 6: Protocol documents and port rules

**Depends on:** Steps 1–5
**Goal:** Rewrite the protocol rules listed in spec slice 5 and the remaining port
text of slice 6.

**Files:**
- MODIFY: `protocol/phases.md` — intro "Восемь фаз…", invariant 7 new wording,
  invariants 2 and 9 scoped by profile, Research row "Внешние действия".
- MODIFY: `protocol/tiers.md` — `triage: false` rule, multitask rule scoped,
  researcher row note.
- MODIFY: `protocol/runtime.md` — ports table research row (lang, workspace,
  tracker); named-when-continued rule; cross-repo spawn template and researcher
  params incl. `CONTINUABLE`.
- MODIFY: `protocol/review-cycle.md` — continuation principle includes researcher.
- MODIFY: `protocol/multitask.md` — intro; `PARTS_IN_FLIGHT` mutating only; "Выбор
  части" by `part_runner`; new subsections "Часть профиля research" (explicit
  paths, tracker `none`, shared-branch push rule), "Планировщик", "Кросс-репо";
  blocked rule scoped; reconciliation for `commit`; synthesis.
- MODIFY: `protocol/artifacts.md` — state.yaml `profile`, `repos`; layout synthesis
  research.md; research.md description.
- MODIFY: `protocol/dialog.md` — new canon rows.
- MODIFY: `protocol/glossary.md` — new terms, rewritten фаза/мультизадача/ветка
  части/интеграция части, `STATUS: blocked` vs part `blocked`, synthesis agent
  address.
- MODIFY: `protocol/worktree.md` — research-worktree kind.
- MODIFY: `adapters/workspace/PORT.md` — `worktree` capability description covers
  research-worktrees (no new capability).
- MODIFY: `adapters/workspace/git.md` — "research-worktree" section (create, A6
  setup, teardown order), `integrate` note for `commit`.
- MODIFY: `adapters/lang/PORT.md` — "Навигация": activation on `PROJECT_ROOT`.
- MODIFY: `CHANGELOG.md` — **protocol** lines per document; **port** lang
  navigation; **port** workspace: `worktree` capability covers research-worktrees,
  research-worktree section in git.

**Test checkpoint:**
- [ ] Terminology lint and "no tool names in core" lint green (no forbidden terms,
      no tool names in `protocol/`).
- [ ] Profiles lint still green (profiles.md untouched or consistent).
- [ ] Invariant 7 old wording "Одна задача, один репозиторий" absent from
      `protocol/`; "Восемь фаз, всегда в одном порядке" absent.
- [ ] Test gate green.

### Step 7: Researcher agent and skills

**Depends on:** Step 6
**Goal:** Researcher report contract, inputs, synthesis mode; research skill with
named continuable spawns, blocking-question limit and log format, scheduler mode;
start, develop, finalize, refine per spec slice 7 (D7, D8, D15, D16, D18, D19, D21).

**Files:**
- MODIFY: `agents/researcher.md` — frontmatter `tools` gains `Write`; description
  mentions synthesis; inputs (`MODE`, `REPO`, `INPUTS`, `HANDOFF`, `ANSWERS`,
  `CONTINUABLE`); `PROJECT_ROOT` navigation line; report contract; output format
  additions; synthesis mode.
- MODIFY: `skills/research/SKILL.md` — description and port line; named spawn
  template (`name: "researcher-{id}"`, `"researcher-{id}-{part}"`) with SendMessage
  continuation; `triage: false`; `PARTS_IN_FLIGHT` scoped; answers rule; limit and
  log format; scheduler mode steps 1–8.
- MODIFY: `skills/start/SKILL.md` — `--profile`, tier rule, multitask profile and
  repo snapshot (JSON entries, `--repos` from `repo --list`), part start by
  `part_isolation`, limit by `part_runner`, part completes refine/start, explicit
  commit paths, errors row.
- MODIFY: `skills/develop/SKILL.md` — `--profile`, description, M0 profile via
  `meta`, delegation for `part_runner: scheduler`, M2–M3 scoped, invariant 7
  wording (l.83-84, errors table), rules l.157-163.
- MODIFY: `skills/finalize/SKILL.md` — single task `finalize_artifact: research`,
  `--part` with `commit` (reconciliation, Handoff dialog, path-scoped commit, push
  rule, hash after push), `--multitask` research-worktree teardown, description and
  rules scoped.
- MODIFY: `skills/refine/SKILL.md` — profile question, per-part repo, seed/validate
  flags, step 1 wording, l.83-84 wording.
- MODIFY: `CHANGELOG.md` — skills and researcher lines.

**Test checkpoint:**
- [ ] SendMessage-vs-named-spawn lint green (researcher spawn and SendMessage both in
      `skills/research/SKILL.md`; no other skill sends to a researcher without a
      named spawn).
- [ ] "No tool names in core" lint green for `skills/` and `agents/` bodies.
- [ ] Old wording absent from skills: "одна активная часть на владельца", invariant
      7 old phrasing, "Ответы обязательны для architect" without profile scope.
- [ ] Lint gate green (skill and agent frontmatter); test gate green.

### Step 8: README, CHANGELOG consolidation, full verification

**Depends on:** Step 7
**Goal:** README reflects phases and profiles; CHANGELOG `[Unreleased]` consistent
and complete, with the `plugin.min_version` compatibility note (D9).

**Files:**
- MODIFY: `README.md` — intro phases → phases and profiles with link to
  `protocol/profiles.md`; scheduler and cross-repo research in the skills section;
  `resolve.py repo` and `--fallback-project` in the scripts section.
- MODIFY: `CHANGELOG.md` — dedupe/order lines from steps 1–7 under Added/Changed,
  verify every **protocol**/**port** marking, add the compatibility note.

**Test checkpoint:**
- [ ] Every file under `protocol/` and `adapters/*/PORT.md` changed on the branch has
      a matching CHANGELOG line with the right marking.
- [ ] Test gate and lint gate green.

## Project Specs to Update

- `protocol/profiles.md` — new (Step 1).
- `protocol/multitask.md` — "Идентификация" marker grammar (Step 2); columns and
  second example (Step 3); intro, overlap check, "Выбор части", "Часть профиля
  research", "Планировщик", "Кросс-репо", blocked rule, "Реконсиляция", synthesis
  (Step 6).
- `protocol/phases.md` — intro, invariants 2, 7, 9, phase table Research row (Step 6).
- `protocol/tiers.md` — rules, model table note (Step 6).
- `protocol/runtime.md` — ports table, "Спавн агентов", template (Step 6).
- `protocol/review-cycle.md` — "Continuation-принцип" (Step 6).
- `protocol/artifacts.md` — "Раскладка", "state.yaml", research.md description (Step 6).
- `protocol/dialog.md` — "Канон по точкам" (Step 6).
- `protocol/glossary.md` — "Процесс", "Мультизадача", "Адресация", new terms (Step 6).
- `protocol/worktree.md` — "Параметры" / new research-worktree section (Step 6).
- `adapters/tracker/PORT.md` — "Управляемые блоки" (Step 2).
- `adapters/workspace/PORT.md` — frontmatter `config`, "Конфиг" (Step 4);
  `worktree` capability description (Step 6).
- `adapters/workspace/git.md` — "worktree" research-worktree section, "integrate"
  note (Step 6).
- `adapters/lang/PORT.md` — "Навигация" (Step 6).
- `CHANGELOG.md` — `[Unreleased]` lines each step; consolidation Step 8.
- `README.md` — intro, skills, scripts (Step 8).

## Verification

- [ ] All gates from the lang adapter pass: test (incl. terminology, tool-names,
      SendMessage and profiles lints) and lint.
- [ ] `test_lifecycle` untouched and green; legacy blocks and states behave as
      `full`.
- [ ] Project specs consistent with code: profiles table = `PROFILES`, tracker
      marker grammar = `multitask.py`, workspace `config` includes
      `workspace.repos`, CHANGELOG marks every protocol/port change.
- [ ] Manual acceptance (live research multitask across `eps-omix-lib` and
      `eps-eal-omix`, doctor in three projects) left to the developer after Finalize.
