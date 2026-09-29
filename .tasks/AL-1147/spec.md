# Spec: AL-1147

## Summary

Introduce the **pipeline profile**: a named subset of phases with derived properties,
orthogonal to `kind` and tier. Two profiles ship: `full` (today's behaviour, the
default for everything that does not declare a profile) and `research` (Refine,
Start, Research, Finalize; never mutates code). On top of `research` the plugin gains
a same-session event-driven scheduler of read-only multitask parts (named
continuation researchers, blocking/deferred design questions, Handoff, synthesis) and
cross-repo research over `workspace.repos` pinned to a sha. Legacy blocks and
`state.yaml` files without a profile keep working byte-for-byte as `full`.

Binding inputs: `task.md` (final statement), `research.md` (Source Files Map,
findings 1–23, answers A1–A6). Paths below are relative to `PROJECT_ROOT`.

## Changes

### 1. Profiles canon — `scripts/state.py`

#### New contracts

- `PROFILES: Dict[str, Dict[str, Any]]`, the single canon of profiles. Shape
  (exact keys; values below are the shipped canon):

  | key | type | `full` | `research` | meaning |
  |---|---|---|---|---|
  | `phases` | `List[str]` | `[refine, start, research, spec, plan, implement, review, finalize]` | `[refine, start, research, finalize]` | ordered phase subset; order always follows the global phase order |
  | `mutates` | `bool` | `true` | `false` | whether the profile changes code in the repository |
  | `part_isolation` | `str` enum `worktree` \| `shared` | `worktree` | `shared` | `worktree`: part gets branch `{branch}-{part}` + worktree; `shared`: only `.tasks/{id}/{part}/` on the multitask branch in the main tree |
  | `part_integration` | `str` enum `integrate` \| `commit` | `integrate` | `commit` | `integrate`: workspace adapter `integrate` (`workspace.integration`); `commit`: path-scoped commit of the part directory onto `task/{id}` |
  | `finalize_artifact` | `str` enum `code` \| `research` | `code` | `research` | what Finalize fixes and proposes: code branch + PR, or `research.md` + PR with artifacts |
  | `triage` | `bool` | `true` | `false` | whether the tier is triaged; `false` = researcher always as agent on `models.strong`, always `research.md` |
  | `part_runner` | `str` enum `sequential` \| `scheduler` | `sequential` | `scheduler` | how develop runs the parts of a multitask: `sequential` = develop M2–M3 part by part; `scheduler` = delegation to `research {id} --parts` (researcher-only: Research then Finalize of each part) |

  Skills branch on these **properties**, never on the profile name. A future
  profile (`design`, `audit`) needs no skill edits **only if it reuses existing
  property values**; a new value of any property (e.g. a new `part_runner` or
  `finalize_artifact`) is a skill change.
- `DEFAULT_PROFILE = "full"`.
- `PHASES` stays as the global phase order and equals `PROFILES["full"]["phases"]`
  (kept as a module constant for existing callers).
- `profile_of(state) -> str`: `state.get("profile") or DEFAULT_PROFILE`; unknown
  name raises `OmixflowError`.
- `phases_of(state) -> List[str]`: `PROFILES[profile_of(state)]["phases"]`.

#### Modified contracts

- `next_phase(state)`: first phase of `phases_of(state)` not in `completed`, else
  `"done"`.
- `state.py init`: new `--profile NAME` (validated against `PROFILES`). New states
  always persist `profile`. For `--kind part` the profile is inherited from the parent
  state `DIR/../state.yaml`, which must exist with `kind: multitask` and
  `id == --multitask-id` (otherwise exit 2); an explicit `--profile` that differs
  from the parent's profile is an error (exit 2). For a profile with
  `triage: false` an explicit `--tier` is rejected (exit 2) and `tier: null` is
  stored. `phase` initialises to the profile's first phase.
- `state.py set`: `phase=` must be in `phases_of(state) + ["done"]`;
  `profile=` must be a `PROFILES` key and is rejected when `completed` holds a phase
  outside the new profile. Other keys unchanged (free-form dotted, JSON for `[`/`{`).
- `state.py complete DIR PHASE`: rejects a phase outside `phases_of(state)`;
  `completed` re-ordered by the profile's phase list.
- `state.py get DIR profile`: prints the **effective** profile (`full` for legacy
  states) with exit 0. `get` of any other missing key and whole-state `get` are
  unchanged.
- Legacy `state.yaml` without `profile`: `next`, `set`, `complete`, `get profile`
  behave as `full`; the file is not rewritten just for reading. `test_lifecycle`
  passes unchanged.
- `state.yaml` of `kind: multitask` may carry `repos: {name: {ref, sha}}`, written
  as **one JSON object per entry** (`set DIR repos.{name}={"ref":"…","sha":"…"}`) so
  that `parse_value` keeps `ref` and `sha` as strings (a dotted scalar `sha=` could be
  parsed as an integer for an all-digit value). No script validation of its content.

### 2. Multitask block — `scripts/multitask.py`

#### Modified contracts

- **Marker grammar.** Start marker:
  `<!-- omixflow:multitask:start{ATTRS} -->` where `ATTRS` is zero or more
  `␠key=value`, `key` = `[a-z][a-z0-9_-]*`, `value` = one or more characters other
  than whitespace and `>`; no quoting. Whitespace inside the comment around the
  marker name and before `-->` is tolerated. The end marker is unchanged
  (`<!-- omixflow:multitask:end -->`, no attributes).
  - **Both markers occupy a whole line**: located by a multiline regular expression
    anchored `^\s*<!-- … -->\s*$` (start and end alike), not by exact substring. A
    marker quoted inline in prose (e.g. in backticks inside a sentence, as task.md
    l.30 does) is not a marker. `MARK_START` remains as the canonical
    attribute-less form used by `render`.
  - A second start-marker line anywhere in the text is an error ("больше одного
    блока"). Start without end is an error (unchanged).
  - Known attribute keys: `profile` only. Unknown or duplicate keys and an unknown
    `profile` value are **marker errors** (a typo such as `profle=research` must not
    silently degrade to `full`); see `marker_errors` below for which commands reject
    and which tolerate them. Absent attribute = `full`.
- `find_block(text)`: returns the span (unchanged signature) using the regex.
- `Row` gains `repo: Optional[str]`: `None` = home repository. Parsed from an
  optional `repo` column; `—`, `-`, empty normalise to `None`. `extract` JSON rows
  therefore carry `repo`.
- `render(rows, profile="full")`: canonical writer (used by `seed`, `render` CLI and
  append path of `replace_block`). Emits the marker with ` profile={name}` only for a
  non-`full` profile; emits the `repo` column only when at least one row has a
  non-`None` `repo`, placed right after `title`:
  `| # | part | title | repo | depends | owner | status | branch | commit |`.
  Output for rows without `repo` and profile `full` is byte-identical to today.
- **Surgical `set` (A1).** `set --part P k=v…` rewrites **only the target row line**:
  the marker line (with attributes), header, separator, every other row and all text
  outside the block are kept byte-for-byte. The target line is rebuilt from its own
  original cells in the header's column order: changed cells get the new value,
  unchanged cells keep their original (stripped) content, the line is joined in the
  canonical `| a | b | … |` form. If no cell value changes, the output is byte-identical
  to the input. Setting a key whose column is absent from the header is an error.
  Validation of the resulting rows runs before output (unchanged).
- `set` editable keys: `status, owner, branch, commit, title, depends, repo`.
  `repo=` is accepted only while the target row is `pending` (after the part started
  `repo` is immutable, exit 2); `—` clears it.
- `validate(rows, profile="full", repos=None) -> List[str]`: **rows only**; existing
  checks plus
  - `repo` value must be a slug (`SLUG_RE`); when `repos` (list of names) is given,
    it must be one of them;
  - a non-`None` `repo` in a block of a profile with `mutates: true` is an error.
- Marker checks are separate: `marker_errors(text) -> List[str]` (unknown or
  duplicate attribute key, unknown `profile` value). Every CLI command takes the
  profile from the parsed marker.
  - **Reject** marker errors: `validate` (listed with the row errors, exit 1),
    `meta`, `ready`, `file` (exit 2 with the message; unknown profile →
    exit 2 "неизвестный профиль {name}").
  - **Tolerate** them (attributes preserved verbatim): `extract`, `has`, `set`,
    `waves`. Row validation uses the declared `profile` when it is a known
    `PROFILES` key and falls back to `full` only for an unknown profile value.
- `validate` CLI: `validate --from F [--repos a,b]`; profile comes from the marker,
  `--repos` is the comma-separated list of `workspace.repos` names (skills obtain it
  from `resolve.py repo --list`). Without `--repos` name existence is not checked.
- `set` and `seed` accept the same optional `--repos` and pass it to `validate`.
- `ready(rows, owner=None, parallel=None)`; output keeps every existing key and adds:
  - `slots`: when `--parallel N` is given, `max(0, N - len(mine_active))`, else `null`;
  - `ready_by_repo`: ready parts grouped by repo, keys in order of first appearance
    in the block, home repo key `—`;
  - `active_repos`: distinct repos (`—` for home) of `mine_active` parts.
  The script enforces no limit itself; the caller passes `parallel_per_owner` for
  `part_runner: sequential` and `multitask.parallel_parts` for
  `part_runner: scheduler`. A pending
  part whose dependency is `blocked` stays not ready (unchanged).
- `seed`: new `--profile NAME` (default `full`) and `--repo` (`nargs="*"`, one value
  per part in `--parts` order, `—` = home), mirroring `--depends`. Still refuses when a
  block exists.
- `render` CLI: `render --rows ROWS.json [--profile NAME]`.
- `multitask_file(rows, task_id, title, profile="full")`: each part lists
  `- Репозиторий: {repo | домашний}` when the block has a `repo` column; the
  "## Интеграция" section is profile-specific: `part_integration: integrate` keeps
  today's text; `commit` states "части коммитятся по пути `.tasks/{id}/{part}/` в
  `task/{id}`, веток и worktree частей нет, сообщение
  `docs({id}): research {part} — {title}`". `file` CLI reads the profile from the
  marker.

#### New contracts

- `block_meta(text) -> {"profile": str, "attrs": Dict[str, str], "repos": List[str]}`
  (`repos` = distinct non-home repo names in block order) and CLI
  `multitask.py meta --from F` printing it as JSON (rejects `marker_errors`). Used by develop/start/research to
  read the profile and the repos to snapshot.

### 3. Config, `resolve.py`, library

#### Modified contracts

- `schema/flow.schema.json`:
  - `workspace.repos`: object; `additionalProperties` = entry schema
    `{type: object, additionalProperties: false, required: [path, remote],
    properties: {path: string, remote: string, ref: string (default "auto"),
    setup: boolean (default false)}}`. Key slugs are **not** enforced by the schema
    (the light validator has no `propertyNames`); doctor enforces them.
  - `multitask.parallel_parts`: integer, minimum 1, default 4. `parallel_per_owner`
    description notes it applies to `part_runner: sequential`.
- `templates/flow.yaml`: commented `workspace.repos` example (one entry with `path`,
  `remote`, `ref`, `setup` and a one-line comment per key) and
  `multitask.parallel_parts: 4` with comment "одновременных researcher'ов в
  немутирующем профиле". Template stays schema-valid.
- Semantics of an entry: `path` relative to the home project root; `remote` is the
  identity checked by doctor; `ref` = branch, tag, sha or `auto` (absent = `auto` =
  the foreign project's base branch); `setup` runs the foreign `workspace.setup` in a
  research-worktree.
- `resolve.py`: new `--fallback-project HOME` (A5), meaningful together with
  `--project FOREIGN`. With the flag, the foreign root is `FOREIGN` itself and its
  config is detected by checking `FOREIGN/.claude/omixflow/flow.yaml` directly (no
  ancestor walk, so a foreign repo nested under another configured project never
  picks up that project's config). When `FOREIGN` has its own flow.yaml the flag changes nothing
  except for `agent` (below). When it has none:
  - `adapter` / `adapter-script`: adapter names come from the HOME config; each
    name resolves to the FOREIGN project-layer file if present, otherwise to the chain
    HOME would produce (HOME project layer, else plugin). A one-line notice goes to
    stderr, exit 0.
  - `base`: resolved as `auto` (remote default branch) in the FOREIGN git repository;
    the HOME `workspace.base` never applies to a foreign repo.
  - `agent`: see below.
  - `agent` with `--fallback-project` (regardless of FOREIGN config): `agent`,
    `subagent_type`, `layer`, `replaced` are resolved against HOME with the HOME
    mapping (the session registers only the home project's agents, a foreign
    project agent is not spawnable); `rules` come from FOREIGN
    (`.claude/omixflow/agents/{role}.md` when present, else empty; HOME rules are not
    used for a foreign repo).
  Without the flag behaviour is unchanged (exit 2 on missing flow.yaml).
- `omixflow_lib`:
  - `resolve_repo_ref(repo_root, ref, fallback_cfg=None) -> Optional[str]`: full commit
    sha or `None`. `auto`/absent → base of the foreign project (its own config via
    `resolve_base_branch`, else remote default branch, else `main`/`master`). A branch
    name resolves to `origin/{name}` when that remote-tracking ref exists, else the
    local branch (the snapshot must be reproducible for other executors); tags and
    shas as given. No implicit fetch.
  - `repo_checkout_state(repo_root) -> {"head": sha|None, "dirty": bool}`: dirty
    counts tracked changes only (untracked files ignored, `.claude/worktrees/`
    excluded).
  - `normalize_remote(url) -> str`: `host/owner/repo` lower-cased host, scheme, user,
    port-less ssh `git@host:owner/repo` form, trailing `.git` and `/` removed.

#### New contracts

- `resolve.py repo NAME [--json]`: reads `workspace.repos.NAME` from the home config
  and prints `{name, path (absolute), remote, ref (as configured, default auto),
  sha (resolved, null if unresolvable), head, dirty, has_config}`. Unknown name →
  exit 2; unresolvable ref → `sha: null`, exit 1. Used by start (snapshot) and the
  scheduler (HEAD recheck), and shares its library functions with doctor.
- `resolve.py repo --list`: prints the `workspace.repos` names comma-separated (empty
  line when none), exit 0. Skills pass its output as `--repos` to `multitask.py
  validate`/`set`/`seed`.

### 4. Doctor — `scripts/doctor.py`

#### New contracts

New checks, run from `check_workspace` only when `workspace.repos` is configured,
section `repo:{name}` per entry, statuses only OK/WARN/FAIL (A4; doctor JSON
contract and `skills/doctor/SKILL.md` unchanged):

| name | OK | WARN | FAIL |
|---|---|---|---|
| `slug` | name matches `SLUG_RE` | | name is not kebab-case |
| `path` | directory exists outside the home root | | missing, or lies inside the home project root (detail says which; remaining checks for the entry skipped) |
| `git` | path is a git repository | | not a git repository (remaining skipped) |
| `remote` | `normalize_remote(origin) == normalize_remote(remote)`; detail shows both | | no `origin`, or mismatch |
| `ref` | detail `{ref} → {sha[:12]}` | | does not resolve |
| `flow.yaml` | detail "flow.yaml есть" / "flow.yaml нет, фолбэк на цепочку домашнего проекта" | | |
| `research worktrees` | emitted only when the foreign repo has `.claude/worktrees/research-*`; detail lists names; a worktree whose task state is unknown is OK with "состояние неизвестно" in the detail | any `research-{id}` whose home task state has `phase: done` (detail names them, hints teardown order from the workspace adapter), or more than `RESEARCH_WORKTREE_WARN = 3` | |

Task state lookup for `research-{id}`: home `{artifacts.dir}/{id}/state.yaml` in the
working tree; if absent, the same path read from the task branch (`workspace.branch`
with `{id}`) through the library git helper; neither → state unknown.

`RESEARCH_WORKTREE_WARN` is a module constant next to `REVIEW_WORKTREE_WARN`.

### 5. Protocol documents — `protocol/`

#### New contracts

- `protocol/profiles.md`: the human-readable canon. One Markdown table whose header
  is exactly `| profile | phases | mutates | part_isolation | part_integration |
  finalize_artifact | triage | part_runner |`; `phases` comma-separated lower-case names;
  booleans `true`/`false`. Rows must equal `state.PROFILES` (lint). Prose: profile is
  orthogonal to `kind` and tier; how a task gets its profile (single task: `--profile`
  of develop/start persisted in state; multitask: marker attribute, persisted in the
  multitask state at Start, inherited by parts; absent = `full`); per-property effect
  on phases/skills; the `research` profile's specifics (no triage, researcher on
  `models.strong`, always `research.md`, deferred questions not required to be
  answered); adding a profile = one `PROFILES` entry + one row, with no skill edits
  only when every property value already exists; a new property value is a skill
  change.

#### Modified contracts (rewritten rules)

- `phases.md`: l.3 "Восемь фаз, всегда в одном порядке" → phases always run in the
  global order; the set of phases is given by the profile (`profiles.md`); `full`
  contains all eight. Invariant 7 → **«Одна задача мутирует один репозиторий;
  немутирующие фазы читают репозитории из `workspace.repos`.»** The decomposition
  rule for mutating changes across two repos is kept as its second sentence.
  Invariant 2 and 9 (Implement/Review mandatory) are scoped to profiles that contain
  those phases. Phase table, Research row, column "Внешние действия": "нет" →
  "в режиме планировщика tracker: блок и комментарии; workspace: research-worktree
  (с подтверждением)".
- `tiers.md`: a profile with `triage: false` is not triaged (tier stays `null`);
  researcher is always an agent on `models.strong`, always `research.md`; S inline
  research does not apply. "Мультизадача сама тиру не подлежит; каждая часть
  триажится…" scoped to triaged profiles. Model-table row `researcher` gets a note
  for `triage: false`.
- `runtime.md`: ports table — the `research` row becomes lang, workspace, tracker
  (workspace: cross-repo research-worktree; tracker: block and comments in scheduler
  mode). Named-spawn rule l.41-44 → architect, coder, tester, reviewer
  always named; **researcher is named when it is continued**: every researcher spawned
  by the `research` skill (`researcher-{id}`, `researcher-{id}-{part}`; synthesis uses
  `researcher-{id}`); researcher of `create` and web-fetcher stay one-shot. Spawn
  template: cross-repo spawn (`PROJECT_ROOT` = foreign root, read-only; `TASK_DIR` in
  home; `ADAPTERS.lang` via `resolve.py adapter lang --project {foreign}
  --fallback-project {home}`; `RULES` from `resolve.py agent researcher --project
  {foreign} --fallback-project {home}`); new optional researcher params `MODE`,
  `REPO`, `INPUTS`, `HANDOFF`, `ANSWERS`, `CONTINUABLE` (only named spawns pass
  `yes`; standalone `research "{тема}"` stays one-shot).
- `review-cycle.md` l.56: same "named when continued" rule; researcher listed with
  its continuation use (blocking answer via SendMessage).
- `multitask.md`:
  - intro l.3-7: each part runs the pipeline of the multitask's profile; branch and
    worktree only for `part_isolation: worktree`.
  - Identification: marker attributes (`profile=`), second example block with
    `profile=research` and a `repo` column; column list gains `repo` (name from
    `workspace.repos`, `—` = home, only for non-mutating profiles, immutable after the
    part starts); `branch` is `—` for `shared` parts.
  - l.63-66 Source Files Map overlap check (`PARTS_IN_FLIGHT`): mutating profiles only.
  - "Выбор части" and `parallel_per_owner` (l.104-112): profiles with
    `part_runner: sequential`; profiles with `part_runner: scheduler` are driven by
    the scheduler (below) with `multitask.parallel_parts`.
  - New subsection "Часть профиля research": take (owner + `in-work`), part directory
    on `task/{id}` in the main tree, researcher, completion dialog (Handoff questions),
    path-scoped commit `docs({id}): research {part} — {title}` (never "all changes":
    sibling parts write next to it), push at `multitask.push`, `done` with hash.
    Rules of the subsection:
    - **Explicit paths.** In a `part_isolation: shared` multitask every commit
      (start, part finalize, synthesis, multitask finalize) names its paths
      explicitly: the part directory `.tasks/{id}/{part}/`, or the multitask
      `state.yaml`, `multitask.md`, `research.md`, `log.md`; never "all changes".
    - **Tracker `none`.** The block lives in `multitask.md`; the scheduler commits
      `multitask.md` path-scoped right after each block update
      (`docs({id}): multitask board`).
    - **Push on the shared branch.** Before each push: fetch; if `origin/task/{id}`
      is not an ancestor of HEAD, rebase with autostash onto `origin/task/{id}`; a
      conflict is a STOP (developer resolves), the block stays as it is. The block's
      `done` short hash and the tracker comment are taken only after a successful
      push (the hash is the post-rebase one). Push happens in the scheduler's
      completion step of the finished part while other researchers keep running.
      This is safe: a running researcher writes only untracked files inside its own
      part directory (`research.md`), which rebase does not touch; the tracked
      mid-run edits (part `log.md`, multitask state and log) are the orchestrator's
      own and are covered by autostash.
  - New subsection "Планировщик": the cycle, repo grouping, `INPUTS`, blocked
    handling, resume (as in slice 7 contracts).
  - New subsection "Кросс-репо": snapshot `repos: {name: {ref, sha}}` in the multitask
    state, HEAD recheck before each part launch, research-worktree rule, teardown at
    Finalize.
  - l.130-131 "blocked останавливает мультизадачу для владельца": profile `full`; in a
    non-mutating profile a blocked part stops only its dependents.
  - Reconciliation l.140-142: kept for `integrate`; for `commit` parts the integration
    sign is a commit with subject prefix `docs({id}): research {part} — ` in the
    history of `task/{id}` (not branch absence).
  - Synthesis: `.tasks/{id}/research.md` written after all parts are terminal.
- `artifacts.md`: state.yaml example gains `profile: full  # full | research …` and,
  for `kind: multitask`, `repos: {name: {ref, sha}}`; `phase` comment "фазы профиля";
  layout: `.tasks/{id}/research.md` = synthesis for a research multitask; research.md
  description: `## Handoff`, cross-repo header, `{repo}:` path prefix, typed design
  questions.
- `dialog.md` canon table, new rows: researcher's blocking question → hybrid
  (context text, options AUQ, "Other" → text); part completion in a non-mutating
  profile (Handoff open questions) → text/AUQ per question kind; deferred questions at
  synthesis → as design questions; creating a research-worktree → AUQ; scheduler
  end-of-run summary → text, no answer awaited.
- `glossary.md`: new terms профиль (profile), передача (handoff), блокирующий вопрос
  (blocking question), отложенный вопрос (deferred question), синтез (synthesis),
  планировщик (scheduler), репозиторий workspace (workspace repo), снимок (snapshot),
  research-worktree. Explicit distinction: `STATUS: blocked` of a researcher report
  (agent alive, waiting for an answer) vs part status `blocked` (part stopped).
  Rewritten: фаза ("этап пайплайна…; набор фаз задачи задаёт профиль"), мультизадача
  ("…каждая с пайплайном профиля мультизадачи…"), ветка части (only
  `part_isolation: worktree`), интеграция части (by profile: squash/merge or
  path-scoped commit). Addressing: synthesis agent `researcher-{id}`.
  (Invariant 7 is not in the glossary — finding 17.)
- `worktree.md`: new kind **research-worktree**: root
  `{repo_path}/.claude/worktrees/research-{id}`, detached at the snapshot sha, one per
  foreign repo per multitask, shared by that repo's parts, never entered (no
  EnterWorktree, hook does not fire), setup and teardown by the orchestrator per the
  workspace adapter; doctor warns about accumulation.

### 6. Ports — `adapters/`

#### Modified contracts

- `adapters/tracker/PORT.md` "Управляемые блоки" (**port** tracker): start marker is
  `<!-- omixflow:{kind}:start[ key=value…] -->`; start and end markers each occupy a
  whole line (a marker quoted inline in prose is not a marker); an adapter finds the
  block by the start-marker line prefix regardless of attributes, and when replacing
  content between markers
  keeps the start marker line (with its attributes) verbatim. Attribute grammar
  referenced from `protocol/multitask.md`.
- `adapters/workspace/PORT.md` (**port** workspace): frontmatter `config:` gains
  `workspace.repos`; config example gains a `repos:` entry; the `worktree` capability
  description covers research-worktrees (no new capability).
- `adapters/workspace/git.md`: new section "research-worktree" under `worktree`:
  create detached at sha in the foreign repo (with confirmation); setup (A6): always
  recursive submodule initialisation (with a reference clone when known, as in
  `setup`), then the
  foreign `workspace.setup` only when `workspace.repos.{name}.setup: true` (read from
  the foreign config; absent → warn and skip); teardown reuses the existing
  submodule-worktree order. `integrate` gains a note that `part_integration: commit`
  does not use it (path-scoped commit, never "add all").
- `adapters/lang/PORT.md` "Навигация" (**port** lang): one line — navigation tools are
  activated on the absolute `PROJECT_ROOT` passed at spawn, not on the cwd (the
  session may sit in another repository).

### 7. Skills and researcher agent

#### Modified contracts

- `agents/researcher.md`:
  - frontmatter `tools` gains `Write` (it rewrites its own `research.md`,
    finding 19); still never writes anything but its report; with a foreign
    `PROJECT_ROOT` it writes only under `TASK_DIR`.
  - Tooling: activate navigation on `PROJECT_ROOT`, not cwd (no tool names).
  - Inputs: `MODE` (`task` default | `synthesis`); `REPO` (`{name} ref={ref}
    sha={sha}`, cross-repo only); `INPUTS` (absolute paths of dependency parts'
    research.md, read `## Handoff` first; in synthesis = all parts); `HANDOFF`
    (`required` | `optional`); `ANSWERS` (previously answered blocking questions on
    restart); `CONTINUABLE` (`yes` | `no`, default `no`); `PARTS_IN_FLIGHT` unchanged
    but only sent for mutating profiles.
  - **Report contract.** The response starts with `STATUS: done` or
    `STATUS: blocked`. `STATUS: blocked` is allowed **only when `CONTINUABLE: yes`**
    (named spawns of the research skill for a task or a part). One-shot spawns
    (`create`, standalone `research "{тема}"`, `OUTPUT: inline`) put blocking
    questions into `## Design Questions` and always return `STATUS: done`.
    `blocked` is followed by
    ```
    ## Blocking Question
    Question: …
    Options: 1) … 2) …
    Depends: what in this part depends on the answer
    Established: what is already established
    ```
    and **no research.md is written** (research.md exists only after `done`; resume
    relies on this). The orchestrator answers via SendMessage; the agent continues
    with the same context. Criterion: blocking = changes the direction or scope of
    this part/task; deferred = affects a future decision, written to
    `## Design Questions` without an answer. Questions are tagged
    `Q{n} [blocking]:` (followed by `A{n}:` with the given answer) and
    `Q{n} [deferred]:`.
  - Output format additions: cross-repo header right after the title
    (`Repository: {name}` / `Ref: {ref}` / `Sha: {sha}`); Source Files Map paths
    prefixed `{repo}:` for a foreign repo; `## Handoff` with `### Facts`,
    `### Decisions`, `### Affected Files and Contracts`, `### Open Questions for
    Dependents` (mandatory when `HANDOFF: required`).
  - Synthesis mode: reads `INPUTS`, writes `TASK_DIR/research.md` (multitask dir):
    Task Summary; Source Files Map grouped per repository (home first, then
    `{repo}:`-prefixed); merged Findings attributed to parts; all deferred questions,
    deduplicated, renumbered, attributed `(from {part})`; conflicts between parts
    become findings or deferred questions. Synthesis never returns `blocked`.
- `skills/research/SKILL.md`:
  - Port line: lang, workspace, tracker (workspace for cross-repo research-worktrees,
    tracker for block and comments in scheduler mode).
  - Every researcher spawn for a task or a part is named (`researcher-{id}`,
    `researcher-{id}-{part}`), gets `CONTINUABLE: yes` and handles `STATUS: blocked`
    by dialog + SendMessage. Standalone `research "{тема}"` has no id, hence no name:
    one-shot, no `CONTINUABLE`.
  - **Blocking-question limit**: two per part (per task for a single task), counted
    from the answered blocking questions recorded in the part (task) `log.md` — the
    same source as `ANSWERS` — including those answered before a restart. A third →
    part `blocked` in a scheduler-run part, otherwise stop and ask the developer.
  - **log.md format** for blocking questions, used both for writing and for building
    `ANSWERS`: under the `## Research` section, one entry per question
    ```
    ### Blocking Q{n}
    {question}
    A{n}: {answer}
    ```
    On `STATUS: done` the section becomes `## Research ✅` with the usual facts.
  - Profile with `triage: false`: no S inline, agent on `models.strong`.
  - `PARTS_IN_FLIGHT` and step 4 only when `mutates: true`.
  - Step 5 "Ответы обязательны": required only when the profile contains `spec`;
    otherwise deferred questions are offered (answer now / leave deferred) and stay
    unanswered in research.md.
  - "Единственная фаза с параллельными агентами" kept, extended by the scheduler.
  - **Scheduler mode** `research {id} --parts` (multitask of a profile with
    `part_runner: scheduler`). The scheduler is researcher-only: per part it runs
    Research and then Finalize of the part, nothing else:
    1. `multitask.py ready --owner {me} --parallel {multitask.parallel_parts}` on the
       fresh description.
    2. Repo grouping: one repo active at a time (home `—` included); the active repo is
       `active_repos` if non-empty, else the first key of `ready_by_repo`; launch up to
       `slots` ready parts of the active repo, each via nested `start {id} --part
       {part}` then a background named researcher with `PROJECT_ROOT` of that repo
       (home root, the foreign checkout, or its research-worktree — the same root for
       all parts of the repo), `INPUTS` from `depends`, `HANDOFF: required` if some
       part depends on it, `REPO` for foreign parts.
    3. Before each foreign part launch: `resolve.py repo` recheck against the snapshot
       sha; HEAD ≠ sha or dirty → research-worktree (create with confirmation if
       absent). If other parts of the repo are running on the checkout, no new parts
       of that repo launch until they finish, then the group switches to the
       research-worktree.
    4. On `STATUS: blocked`: dialog, answer appended to the part `log.md` in the
       `### Blocking Q{n}` format, SendMessage to the same agent. On `STATUS: done`:
       part `log.md` entry `## Research ✅`, `state.py complete {part} research`,
       nested `finalize {id} --part {part}`, recompute `ready`.
    5. Failure or limit exceeded: `multitask.py set status=blocked`, reason in a
       tracker comment and the part `log.md`; dependents wait, independents continue.
    6. Loop until nothing is running and nothing is launchable; print the summary
       (done, blocked with reasons, waiting). If `all_terminal`: synthesis
       (`researcher-{id}`, `MODE: synthesis`), deferred-question dialog, answers
       written into `.tasks/{id}/research.md`, commit, `state.py complete {id}
       research`.
    7. Resume in a new session: parts `in-work` owned by me — commit present in
       `task/{id}` → reconcile to `done`; research.md present but uncommitted →
       `finalize --part`; no research.md → restart a fresh named researcher with
       `ANSWERS` from the part `log.md`. Restarts are grouped by repo, one repo at a
       time, with the same selection rule (first repo in block order among
       `active_repos`). Blocked parts are shown (hybrid: unblock → `pending` /
       `skipped` / leave) without stopping independents.
    8. Commits: every scheduler commit names its paths explicitly (part directory;
       multitask `research.md`, `state.yaml`, `log.md`), never "all changes". With
       tracker `none` the scheduler commits `multitask.md` path-scoped right after
       each block update (multitask.md rule).
- `skills/start/SKILL.md`:
  - `--profile=NAME` for a single task → `state.py init --profile`; Start itself as in
    `full`. For a profile with `triage: false` start passes no tier (single task and
    parts); `--tier` together with such a profile is an error.
  - Multitask start: profile from `multitask.py meta`, `validate --repos`,
    `state.py init --kind multitask --profile`; for each repo in `meta.repos`:
    `resolve.py repo`, unresolvable → STOP; write the entry as one JSON object
    `repos.{name}={"ref":"…","sha":"…"}`; `--repos` for `validate` from
    `resolve.py repo --list`; commit;
    `state.py complete` refine, start. A repo first appearing in a pending part after
    start is snapshotted when its first part starts. In a `part_isolation: shared`
    multitask the start commits name their paths explicitly (multitask `state.yaml`,
    `multitask.md`, `log.md`; the part directory for part start), never "all
    changes" (multitask.md rule).
  - Part start: branch/worktree only for `part_isolation: worktree`; for `shared` the
    part directory on `task/{id}` in the main tree, `branch` cell `—`; limit check
    keyed on `part_runner`: `parallel_per_owner` for `sequential`,
    `multitask.parallel_parts` for `scheduler`; part state init inherits profile
    and then **completes `refine` and `start`** for every profile (finding 16).
  - Errors row "несколько репозиториев" → new invariant 7 wording.
- `skills/develop/SKILL.md`: `--profile=NAME` (single task; skips triage when
  `triage: false`); frontmatter description mentions profiles; multitask M0 reads the
  profile via `meta`, `--profile` contradicting the marker → STOP; a profile with
  `part_runner: scheduler` delegates `start {id}` → `research {id} --parts` →
  `finalize {id} --multitask` (when `all_terminal`); M2–M3 (incl. M2.1 "blocked =
  стоп", M2.5 limit) scoped to `part_runner: sequential`; l.83-84 and error table l.147 → new invariant 7
  wording; rules l.157-163: parallel researchers inside Research (web-fetcher, and
  parts in the scheduler); "одна активная часть на владельца" → "лимит
  параллельности по `part_runner`: `parallel_per_owner` для `sequential`,
  `multitask.parallel_parts` для `scheduler`".
- `skills/finalize/SKILL.md`:
  - Single task with `finalize_artifact: research`: log.md, commit of research.md and
    artifacts, tracker comment, status (AUQ unchanged), PR offer with artifacts; no
    diff/test statistics.
  - `--part` with `part_integration: commit`: no rebase/squash; reconciliation by the
    commit subject prefix; dialog on `### Open Questions for Dependents` (answers
    written into the part research.md Handoff) before commit; path-scoped commit of
    `.tasks/{id}/{part}/` with message `docs({id}): research {part} — {title}`; push
    at `multitask.push` per the shared-branch push rule (fetch; rebase with autostash
    onto `origin/task/{id}` only if it is not an ancestor of HEAD; conflict → STOP);
    `state.py complete {part} finalize`; block `done` + short hash and comment only
    after a successful push. Runs in the scheduler's completion step of the
    finished part while other researchers keep running (safe per the multitask.md
    rule: their writes are untracked files in their own part directories; tracked
    orchestrator edits are covered by autostash).
  - `--multitask`: for `finalize_artifact: research` also teardown of each
    research-worktree of `state.repos` (existence probed at the deterministic path;
    order from the workspace adapter; with confirmation), PR offer from `task/{id}`.
  - Description frontmatter and rule "Часть: squash в один коммит" scoped by profile.
  - In a `part_isolation: shared` multitask all finalize commits (part and
    `--multitask`) name their paths explicitly, never "all changes"; push per the
    shared-branch push rule (multitask.md).
- `skills/refine/SKILL.md` `--multitask` (A3): asks the profile once (AUQ, `full`
  Recommended); for a non-mutating profile asks the repo of each part from
  `workspace.repos` (home = `—`); passes `--profile`, `--repo`, `--repos` (from
  `resolve.py repo --list`) to `seed` and `--repos` to `validate`. Step 1 wording
  "свой полный пайплайн, ветка, worktree" → the part runs the pipeline of the chosen
  profile; branch and worktree only for `part_isolation: worktree`. l.83-84
  "разбивается" → mutating profile: a part changing two repos is split;
  non-mutating: a part reads exactly one repo.

### 8. Tests and lints — `tests/`

#### New contracts

- `tests/test_state_multitask.py`: phase sequence per profile (`research`: next after
  start = research, then finalize; `set phase=spec` and `complete spec` rejected);
  legacy state without `profile` behaves as `full`, `get profile` → `full` exit 0;
  part inherits parent profile, conflicting `--profile` rejected; part init without a
  parent `kind: multitask` state or with a mismatching `--multitask-id` rejected
  (the existing `test_part_requires_multitask_fields` gains a parent multitask state
  in its temp dir; its assertions are otherwise unchanged); `--tier` rejected for
  `research`, `tier: null` stored; unknown profile rejected. Marker with attribute found by `has`/`extract`/`meta`; `set` preserves the
  marker attribute and the `repo` column; hand-written attribute-less block
  (`|---|------|` separator) survives `set` byte-for-byte outside the target row;
  no-op `set` byte-identical; canonical attribute-less block round-trips; second
  start marker rejected; a marker quoted inline in backticks inside prose → `has`
  exits 1 and is not treated as a second block; unknown attribute rejected by
  `validate`/`meta`/`ready`/`file` and tolerated by `extract`/`has`/`set`/`waves`
  (declared known profile used for row validation, `full` only for an unknown
  value); `repo` unknown with
  `--repos` and non-home `repo` in `full` rejected; `repo=` via `set` only while
  `pending`; `seed --profile research --repo`; `ready --parallel` slots,
  `ready_by_repo`, `active_repos`; `file` integration text per profile.
  `test_lifecycle` unchanged and green.
- `tests/test_scripts.py`: schema accepts a valid `workspace.repos` and rejects bad
  entries (missing `remote`, unknown key, non-boolean `setup`), `parallel_parts < 1`
  rejected; template valid; `resolve.py --fallback-project` (adapter chain from home
  config when foreign lacks flow.yaml; foreign project-layer file preferred; `base`
  resolves in the foreign repo; `agent` rules from foreign, subagent from home);
  `resolve.py repo` (incl. `--list`); doctor `repo:{name}` checks (slug FAIL, path FAIL, remote
  ssh-vs-https OK, mismatch FAIL, `ref` OK/FAIL, `flow.yaml` OK detail,
  `research worktrees` WARN for a done home task, including state read from the task
  branch, OK for unknown state; `path` FAIL inside the home root; `--fallback-project`
  ignores an ancestor's flow.yaml) following the existing temp-git
  pattern of `test_doctor_warns_about_accumulated_review_worktrees`.
- `tests/test_lint.py`: "profiles table == `PROFILES`" (parses the table in
  `protocol/profiles.md` identified by its header, compares names, phase lists and
  every property including `part_runner`). Existing SendMessage/named-spawn lint must stay green (spawn and
  SendMessage for `researcher-{…}` both live in `skills/research/SKILL.md`; any other
  skill mentioning SendMessage to a researcher must also carry the named spawn).

### 9. Docs — `README.md`, `CHANGELOG.md`

- `README.md`: intro phase list → phases and profiles (`full`, `research`), link to
  `protocol/profiles.md`; scheduler and cross-repo research in the skills section;
  `resolve.py repo` / `--fallback-project` in the scripts section.
- `CHANGELOG.md` `[Unreleased]`: **protocol** entries (profiles.md, phases invariant 7
  and phase set, tiers, runtime named-when-continued and ports table, multitask
  research parts/scheduler/cross-repo/reconciliation, artifacts, dialog, glossary,
  worktree research-worktree, review-cycle); **port** entries (tracker: attributed
  marker; workspace: `workspace.repos`, `config`, research-worktree in git; lang:
  navigation on `PROJECT_ROOT`); non-protocol entries for scripts, schema, doctor,
  skills, researcher. A compatibility note: blocks with `profile=` are invisible to
  older plugin versions; projects using non-`full` profiles should pin
  `plugin.min_version` to the release that ships this change.

## Dependencies

- `multitask.py` → `state.py`: imports `PROFILES`/`DEFAULT_PROFILE` (canon stays in
  `state.py` per task; no reverse import).
- `resolve.py`, `doctor.py` → `omixflow_lib`: shared `resolve_repo_ref`,
  `repo_checkout_state`, `normalize_remote`.
- `tests/test_lint.py` → `state.PROFILES` and `protocol/profiles.md`.
- Skills develop → start/research/finalize (delegation for `part_runner: scheduler`);
  research (scheduler) → start `--part`, finalize `--part` as nested skills.
- Research phase → workspace port (new edge in the runtime ports table).
- Foreign repositories are read-only inputs; no plugin code writes into them except
  research-worktree creation/teardown under `{repo}/.claude/worktrees/`.

## Decisions

- D1 (A1): `set` is surgical — only the target row line is rewritten; marker line with
  attributes, header, separator, other rows and outside text are byte-preserved.
  `render` remains the canonical writer for `seed`/`render`.
- D2 (A2): a blocked research part keeps the `full` convention — status `blocked` in
  the block, reason in a tracker comment and the part `log.md`, plus the scheduler's
  end-of-run summary. No `note` column.
- D3 (A3): `seed --profile` and per-part `--repo`; `refine --multitask` asks the
  profile once and, for a non-`full` profile, the repo per part. Scripts are the only
  writer of the block.
- D4 (A4): doctor reports foreign flow.yaml presence as `OK` with a detail; no new
  status level.
- D5 (A5): `resolve.py --fallback-project HOME`. Clarification made here: with the
  flag, `agent`/`subagent_type` always resolve against HOME (only the session's
  project agents are spawnable) while `rules` come from the foreign root; `base`
  without foreign config resolves `auto` in the foreign repo.
- D6 (A6): research-worktree setup always initialises submodules; foreign
  `workspace.setup` runs only with `setup: true`.
- D7: research-worktree `root` is **not** persisted in `state.yaml` (finding 14):
  state is committed and shared across machines, absolute paths are machine-specific.
  The path is deterministic (`{repo_path}/.claude/worktrees/research-{id}`), existence
  is probed; the choice checkout vs worktree is made per launch by the HEAD recheck,
  with all running parts of a repo sharing one root.
- D8: `start --part` completes `refine` and `start` in the part state for every
  profile (finding 16), so `state.py next` gives `research` for a fresh part.
- D9: no version bump in this task; CHANGELOG notes `plugin.min_version` for projects
  that use attributed markers (finding 1).
- D10: `PROFILES` shape as in slice 1 (including `part_runner`, which keys develop's
  delegation instead of `mutates`); skills branch on properties, not on names; a new
  profile is skill-free only when it reuses existing property values; legacy state
  without `profile` resolves to `full` in every command.
- D11: part profile inheritance is done by `state.py init` reading the parent state
  (finding 15), not by skills passing the flag; the parent must be `kind: multitask`
  with the matching id; a contradicting flag is an error. `triage: false` profiles
  store `tier: null` and reject an explicit tier.
- D12: marker attributes are strict — unknown/duplicate keys and unknown profile are
  `marker_errors`, separate from row validation; `validate`, `meta`, `ready`, `file`
  reject them; `extract`, `has`, `set`, `waves` tolerate them, using the declared
  `profile` when it is a known `PROFILES` key and `full` only for an unknown value;
  `set` preserves the marker line verbatim. Markers are recognised only as whole lines.
- D13: `repo` column is emitted by `render` only when used, placed after `title`;
  `set repo=` only while the row is `pending`; a non-home `repo` is invalid in a
  mutating profile.
- D14: research part commit message `docs({id}): research {part} — {title}`;
  synthesis commit `docs({id}): research synthesis`; reconciliation greps the prefix
  `docs({id}): research {part} — ` in `task/{id}`.
- D15: every researcher spawned by the `research` skill for a task or a part is named
  and gets `CONTINUABLE: yes` (only such runs may return `blocked`); researcher of
  `create`, standalone `research "{тема}"` and inline runs stay one-shot, put
  blocking questions into `## Design Questions` and return `STATUS: done`.
  Researcher gets `Write`.
- D16: research.md is written only with `STATUS: done`; blocked runs keep state in the
  agent and the part log.md. The resume rule "in-work without research.md → restart"
  depends on this.
- D17: new `resolve.py repo NAME`; branch refs resolve to `origin/{name}` when it
  exists, else local; no implicit fetch.
- D18: synthesis runs at the end of `research {id} --parts` (spawn and SendMessage stay
  in one skill); the multitask state completes `research` after synthesis. In a
  single task of a profile without `spec`, deferred questions may stay unanswered.
- D19: blocking/deferred typing and `STATUS` are profile-agnostic; in profiles
  containing `spec` all questions are still answered in Research before Spec.
- D20: research-worktrees fall under the existing optional `worktree` capability of
  the workspace port; no new capability.
- D21: the scheduler rechecks HEAD before each foreign part; when a repo's parts must
  switch from checkout to research-worktree mid-run, new parts of that repo wait until
  running ones finish (one root per active repo, LSP constraint, finding 22).

## Out of Scope

- Profiles other than `full` and `research` (`design`, `audit`); the table and
  properties only make them addable.
- Profiles declared by a project in its config.
- Adding/removing parts on repeated `refine --multitask` (`set` adds no rows, `seed`
  refuses an existing block): known gap, separate task.
- Per-machine override of `workspace.repos` paths.
- Parallelism of `full` profile parts (worktree flow unchanged).
- A live run with several executors on one research multitask (protocol allows it).
- Edits of `flow.yaml` in foreign projects (`eps-omix-lib`, `eps-eal-omix`); the
  developer adds `workspace.repos` manually after Finalize. Manual acceptance (live
  run, doctor in three projects) is not part of the automated pipeline.
- Changes to `skills/doctor/SKILL.md`, the doctor JSON contract, `skills/create`,
  `skills/spec`, `agents/architect.md`, tracker adapters (`youtrack.md`, `local.md`),
  `hooks/hooks.json`, `scripts/wt-setup.sh`.
- Extending the light JSON-schema validator (`propertyNames`/`patternProperties`).
- A plugin version bump / release.
