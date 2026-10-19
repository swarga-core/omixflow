#!/usr/bin/env python3
"""The plan against the tier: which files it touches and whether their number, or the
number of steps, exceeds the threshold (protocol/tiers.md, «Порог файлов после плана»).

    plan.py files --task TASK_DIR [--plan FILE] [--json]
    plan.py check --task TASK_DIR [--plan FILE] [--spec FILE] [--json]

Reads the plan's file lines (plan.md; S tier: the `## Steps` section of spec.md) in the
forms the architect and the orchestrator write — `- CREATE: `p``, `- MODIFY `p``,
`- **CREATE:** `p``, `Файлы: `p` (MODIFY)`, several paths on one line — and the task's
tier from state.yaml, counts the unique paths, test files apart (the `tests.files` globs
of every lang adapter in the chain, project extensions included), test support apart
(`tests.support`: fixtures, mocks, helpers — neither counts) and, under `specs.mode: adr`,
the decision records apart (files under `specs.adr_dir`, default docs/decisions: each
decision adds a record, the threshold was calibrated on code — in SwAIS T-10 and T-12
six or seven records took a quarter of the threshold 30), and compares the non-test
count with the tier's threshold from the config (`tiers.s_max_files`,
`tiers.m_max_files`; L has no file threshold) and the step count with MAX_STEPS.

Prints `tier`, `files`, `non_test`, `tests`, `support`, `adr` (None unless `specs.mode`
is adr), `steps`, `threshold`, `over` and the paths;
exit 0 under the thresholds, 1 over either (the orchestrator opens the `scope-change`
point), 2 when the plan or the state cannot be read or the plan has no recognisable
file line (a form the script does not know is not «zero files»). The number is a signal
for a decision point, never a silent tier change: in SwAIS, M-tier plans touched 20–53
non-test files against a threshold of 15, and nothing in the flow said so.

`check` is the mechanical part of the plan review (protocol/review-cycle.md; 0.9 step 4):
every step has its fields (Goal, Covers, Design, Files, Test checkpoint; the S tier's
inline steps need Covers, Files and the checkpoint); every checkpoint names at least one
gate in backticks and every gate named is one the project declares in `verify`; no
checkpoint asks for a manual check an agent cannot run («вручную», «by hand», «headed
Chrome» — a heuristic: the architect may answer «agent-runnable: …» and the skill passes
the line to the reviewer); no step touches a read-only submodule, in Files or in a
checkpoint; every scenario of spec.md (ranges `S1–S3` expanded, `~~S3~~ removed` left
out) is in some step's Covers and every contract is quoted in some step's Covers, Design
or Files (`add()` and `Foo<T>` match `add` and `Foo`); a contract marked `project spec:
{path}` has that path in «Project Specs to Update»; MODIFY and DELETE paths exist in the
tree or are created by an earlier step, CREATE paths do not. The file and step thresholds
are `files`' alone: a developer may have chosen to continue over them. Prints `PLAN
CHECK: ok` or the problems, one per line, ready for the architect's MODE: fix; exit 0 ok,
1 problems, 2 not read (no spec.md for M and L, a missing --spec). Granularity, ordering,
the Design against the spec, the Decision test, an external resource in a functional
step, seams with live branches and transitional notes stay with the reviewer: the
script checks what has a yes or no answer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

KEYWORDS = r"CREATE|MODIFY|DELETE|СОЗДАТЬ|ИЗМЕНИТЬ|УДАЛИТЬ"
KEYWORD_RE = re.compile(r"\b(?:" + KEYWORDS + r")\b")
PATH_RE = re.compile(r"`([^`\s]+)`")
STEP_RE = re.compile(r"^### (?:Step|Шаг) \d+[a-z]?\b", re.M)
MAX_STEPS = 8                    # skills/plan «Калибровка»: more than eight steps is a decomposition signal
THRESHOLD_KEY = {"S": "tiers.s_max_files", "M": "tiers.m_max_files"}
OK, OVER, NOT_READ = 0, 1, 2


def plan_text(task_dir: Path, plan: Optional[str]) -> Tuple[Path, str]:
    """plan.md, or the `## Steps` section of spec.md (S tier: the combined artifact)."""
    if plan:
        p = Path(plan)
        return p, p.read_text(encoding="utf-8")
    p = task_dir / "plan.md"
    if p.exists():
        return p, p.read_text(encoding="utf-8")
    spec = task_dir / "spec.md"
    if spec.exists():
        found = lib.section_lines(spec.read_text(encoding="utf-8"), "Steps")
        if found:
            return spec, "\n".join(found[1])
        raise lib.OmixflowError(f"no plan: {spec} has no `## Steps` section and there is no {p}")
    raise lib.OmixflowError(f"no plan: neither {p} nor a `## Steps` section of {spec}")


def plan_files(text: str) -> List[str]:
    """Unique paths of the lines that name a file operation; every backticked path on
    such a line counts, in order of first appearance."""
    seen: Dict[str, None] = {}
    for line in text.splitlines():
        if not KEYWORD_RE.search(line):
            continue
        head = line.split(" — ", 1)[0]       # the description after the dash names identifiers, not files
        for path in PATH_RE.findall(head):
            if ("/" in path or "." in path) and not re.search(r"[()\"']", path):
                seen.setdefault(path.strip(), None)
    return list(seen)


def test_globs(root: Path, key: str = "files") -> Optional[List[str]]:
    """The union of `tests.{key}` over every lang adapter and its extensions; None when no
    adapter declares any (for `files`: then test files cannot be told apart). `tests.support`
    — the test support (fixtures, mocks, helpers) the adapter's test_conventions name: no
    tests, but not code either (SwAIS T-10: helpers under `test/` pushed an M plan over the
    threshold, the developer was asked for an exception with no code beyond it)."""
    globs: List[str] = []
    try:
        cfg = lib.load_config(root)
        for name in lib.adapters_for(cfg, "lang"):
            for adapter in lib.resolve_adapter("lang", name, root):
                tests = adapter.meta.get("tests") or {}
                if isinstance(tests, dict) and tests.get(key):
                    for g in tests[key]:
                        if str(g) not in globs:
                            globs.append(str(g))
    except lib.OmixflowError:
        pass
    return globs or None


def threshold_for(cfg: Dict[str, Any], tier: Optional[str]) -> Optional[int]:
    key = THRESHOLD_KEY.get(str(tier or "").upper())
    if not key:
        return None
    value = lib.config_value(cfg, key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        raise lib.OmixflowError(f"{key}: not an integer: {value!r}")


def cmd_files(ns: argparse.Namespace) -> int:
    task_dir = Path(ns.task).resolve()
    try:
        lib.require_yaml()
        state = lib.yaml.safe_load((task_dir / "state.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(state, dict):
            raise ValueError("not a mapping")
    except Exception as e:  # a missing or malformed state is the orchestrator's error, never «over»
        print(f"plan.py: state.yaml: {e}", file=sys.stderr)
        return NOT_READ
    root = lib.find_project_root(task_dir)
    try:
        source, text = plan_text(task_dir, ns.plan)
        cfg = lib.load_config(root)
    except Exception as e:
        print(f"plan.py: {e}", file=sys.stderr)
        return NOT_READ
    files = plan_files(text)
    steps = len(STEP_RE.findall(steps_text(text)))
    if not files:
        print(f"plan.py: {source}: no file line recognised (`- CREATE: `path``, `- MODIFY `path``, "
              f"`Файлы: `path` (MODIFY)`): fix the plan's Files lines, or the script", file=sys.stderr)
        return NOT_READ
    if not steps:
        print(f"plan.py: {source}: no step heading recognised (`### Step N: …`): fix the plan's headings, or the script",
              file=sys.stderr)
        return NOT_READ
    try:
        threshold = threshold_for(cfg, state.get("tier"))
    except lib.OmixflowError as e:
        print(f"plan.py: {e}", file=sys.stderr)
        return NOT_READ
    globs = test_globs(root)
    tests = set(lib.area_files(globs, files)) if globs else set()
    support_globs = test_globs(root, "support")
    support = set(lib.area_files(support_globs, files)) - tests if support_globs else set()
    adr_mode = str(lib.config_value(cfg, "specs.mode") or "descriptions") == "adr"
    adr_dir = str(lib.config_value(cfg, "specs.adr_dir") or "docs/decisions").strip("/")
    rest = [f for f in files if f not in tests and f not in support]
    adr = set(rest) - set(lib.outside_dir(rest, adr_dir)) if adr_mode else set()   # decision records: not code
    non_test = [f for f in rest if f not in adr]
    tier = state.get("tier")
    over_files = threshold is not None and len(non_test) > threshold
    over_steps = steps > MAX_STEPS
    result = {"plan": str(source), "tier": tier, "files": len(files), "non_test": len(non_test),
              "tests": len(tests) if globs else None, "support": len(support),
              "adr": len(adr) if adr_mode else None, "steps": steps, "max_steps": MAX_STEPS,
              "threshold": threshold, "over": over_files or over_steps, "over_files": over_files,
              "over_steps": over_steps, "paths": files}
    if ns.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"plan: {source}")
        tests_note = f"tests {len(tests)}" if globs else "tests not told apart: no tests.files in the lang adapters"
        if support:
            tests_note += f", test support {len(support)}"
        if adr_mode:
            tests_note += f", adr {len(adr)} in {adr_dir}/"
        print(f"tier: {tier}, files: {len(files)} (non-test {len(non_test)}, {tests_note}), "
              f"threshold: {threshold if threshold is not None else 'none'}, steps: {steps}/{MAX_STEPS}, "
              f"over: {'yes' if result['over'] else 'no'}")
        for f in files:
            print(f"  {'test ' if f in tests else 'supp ' if f in support else 'adr  ' if f in adr else '     '}{f}")
    return OVER if result["over"] else OK


# ------------------------------------------------------------------ check

STEP_HEAD_RE = re.compile(r"^### (?:Step|Шаг) (\d+[a-z]?)\b[^\n]*$", re.M)    # `Step 5a` (T-8) is a step too
KNOWN_FIELDS = ("Goal", "Covers", "Design", "Files", "Test checkpoint", "Depends on", "Transitional notes")
FIELD_RE = re.compile(r"^\s*\*\*(" + "|".join(re.escape(f) for f in KNOWN_FIELDS) + r"):\*\*\s*(.*)$")
CHECKPOINT_FIELD = "Test checkpoint"
REQUIRED_FIELDS = ("Goal", "Covers", "Design", "Files", CHECKPOINT_FIELD)
REQUIRED_FIELDS_S = ("Covers", "Files", CHECKPOINT_FIELD)
MANUAL_RE = re.compile(r"\b(manual(?:ly)?|by hand|eyeball|headed(?: chrome| browser)?|ask the developer)\b"
                       r"|(?<![а-яё])(вручную|руками|глазами|ручн(?:ая|ой|ую|ые)\s+(?:проверк|сверк)\w*)(?![а-яё])", re.I)
SCENARIO_RE = re.compile(r"^\s*-\s+(?:~~)?(S\d+)\b")
SCENARIO_REMOVED_RE = re.compile(r"^\s*-\s+~~S\d+~~")
CONTRACT_RE = re.compile(r"^\s*-\s+`([^`]+)`")
PROJECT_SPEC_RE = re.compile(r"project spec:\s*`?([^`\s,;)]+)`?")
GATE_RE = re.compile(r"`([a-z0-9]+)`")
OP_RE = re.compile(r"\b(CREATE|MODIFY|DELETE|СОЗДАТЬ|ИЗМЕНИТЬ|УДАЛИТЬ)\b")
OP_KIND = {"CREATE": "create", "СОЗДАТЬ": "create", "MODIFY": "modify", "ИЗМЕНИТЬ": "modify",
           "DELETE": "delete", "УДАЛИТЬ": "delete"}
RANGE_RE = re.compile(r"\bS(\d+)\s*[–-]\s*S?(\d+)\b")
EDIT_VERB_RE = re.compile(r"\b(edit|modify|modif|write|touch|update|patch|replace|revert|temporar)\w*"
                          r"|прав(?:к|ит|ят)|измен|замен|времен|запис|перезап", re.I)


ITERATION_RE = re.compile(r"^(Итерация|Iteration) \d+", re.I)


def steps_text(text: str, latest: bool = False) -> str:
    """The step-bearing sections: `## Steps` (a `### Шаг N` under «Project Specs to Update»
    is not a step) and every `## Итерация N` section a returned task added (artifacts.md);
    with LATEST only the last iteration — its steps are the ones not done yet. A plan
    without these sections is read whole."""
    sections = [s for s in lib.sections_of(text) if s["level"] == 2
                and (s["title"].rstrip(".") == "Steps" or ITERATION_RE.match(s["title"]))]
    if not sections:
        return text
    if latest and any(ITERATION_RE.match(s["title"]) for s in sections):
        sections = [s for s in sections if ITERATION_RE.match(s["title"])][-1:]
    lines = text.splitlines()
    return "\n".join("\n".join(lines[s["start"] - 1:s["end"] - 1]) for s in sections)


def split_steps(text: str) -> List[Dict[str, Any]]:
    """Steps of every step section of a plan (`## Steps` and the `## Итерация N` sections),
    each with `current: True` when it belongs to the last iteration — the steps not done
    yet — and the `**Field:**` blocks of the known fields (a field's text runs to the
    next known field or the next heading; other bold labels such as `**Commit:**` stay
    inside the current field). A step ends at the next heading of any level: a `###
    Verification (iteration N)` after the last step is not its checkpoint."""
    whole, latest = steps_text(text), steps_text(text, latest=True)
    latest_at = whole.find(latest) if latest else -1           # the latest iteration's span, by position
    heads = list(STEP_HEAD_RE.finditer(whole))
    steps: List[Dict[str, Any]] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(whole)
        body = whole[m.end():end]
        cut = heading_outside_fences(body)                     # `# comment` inside a code block is not a heading
        if cut is not None:
            body = body[:cut]
        fields: Dict[str, List[str]] = {}
        current: Optional[str] = None
        for line in body.splitlines():
            fm = FIELD_RE.match(line)
            if fm:
                current = fm.group(1).strip()
                fields[current] = [fm.group(2)] if fm.group(2).strip() else []
            elif current is not None:
                fields[current].append(line)
        steps.append({"n": m.group(1), "title": m.group(0)[4:].strip(), "body": body, "fields": fields,
                      "current": latest_at < 0 or latest_at <= m.start() < latest_at + len(latest)})
    return steps


def heading_outside_fences(body: str) -> Optional[int]:
    """Offset of the first heading line (`#`, `##`, `###`) that is not inside a ``` fence."""
    pos, fenced = 0, False
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"^#{1,3} ", line):
            return pos
        pos += len(line)
    return None


def file_ops(lines: List[str]) -> List[Tuple[str, str]]:
    """(kind, path) of the Files lines: the operation and the paths come from the head of
    the line, before the dash; a path named in the description is not an operation."""
    out: List[Tuple[str, str]] = []
    for line in lines:
        head = line.split(" — ", 1)[0]
        op = OP_RE.search(head)
        if not op:
            continue
        for path in PATH_RE.findall(head):
            if ("/" in path or "." in path) and not re.search(r"[()\"']", path):
                out.append((OP_KIND[op.group(1)], path.strip()))
    return out


def expand_covers(text: str) -> str:
    """`S1–S3` lists every id in between."""
    def expand(m: "re.Match[str]") -> str:
        a, b = int(m.group(1)), int(m.group(2))
        return " ".join(f"S{i}" for i in range(a, b + 1)) if a <= b else m.group(0)
    return RANGE_RE.sub(expand, text)


def spec_items(spec_text: str) -> Dict[str, Any]:
    scenarios: List[str] = []
    sec = lib.section_lines(spec_text, "Scenarios")
    if sec:
        for l in sec[1]:
            m = SCENARIO_RE.match(l)
            if m and not SCENARIO_REMOVED_RE.search(l):
                scenarios.append(m.group(1))
    contracts: List[str] = []
    spec_paths: Dict[str, str] = {}
    sec = lib.section_lines(spec_text, "Contracts")
    if sec:
        for l in sec[1]:
            m = CONTRACT_RE.match(l)
            if m:
                contracts.append(m.group(1))
            ps = PROJECT_SPEC_RE.search(l)
            if ps and contracts:
                spec_paths[contracts[-1]] = ps.group(1)
    return {"scenarios": scenarios, "contracts": contracts, "project_specs": spec_paths}


def contract_key(name: str) -> str:
    """`add()`, `Foo<T>`, `GET /actions` → the token the plan would quote."""
    return re.sub(r"<[^>]*>|\(\)$", "", name).strip()


def readonly_prefixes(cfg: Dict[str, Any]) -> List[str]:
    subs = (lib.config_value(cfg, "workspace.submodules") or []) if isinstance(cfg, dict) else []
    out = []
    for s in subs if isinstance(subs, list) else []:
        if isinstance(s, dict) and s.get("readonly") and s.get("path"):
            out.append(str(s["path"]).rstrip("/") + "/")
    return out


def check_plan(text: str, spec_text: Optional[str], cfg: Dict[str, Any], root: Path, tier: Optional[str]) -> List[str]:
    """The problems of a plan, each a line the architect can act on; empty when the plan
    passes every mechanical check (the docstring of this module lists them). The file and
    step thresholds are `files`' business: a developer may have decided to continue over
    them, and this check must not reopen that."""
    problems: List[str] = []
    steps = split_steps(text)
    if not steps:
        return ["no step heading recognised (`### Step N: …`)"]
    declared = {k for k, v in (lib.config_value(cfg, "verify") or {}).items()
                if isinstance(v, dict) and v.get("cmd")}            # a gate without a command is a schema default
    required = REQUIRED_FIELDS_S if str(tier or "").upper() == "S" else REQUIRED_FIELDS
    readonly = readonly_prefixes(cfg)
    created: set = set()          # paths earlier steps create: they exist for later steps
    deleted: set = set()
    for st in steps:              # earlier iterations' steps are done: their files are in the tree already
        if st["current"]:
            break
        for kind, path in file_ops(st["fields"].get("Files", [])):
            if kind == "create":
                created.add(path)
                deleted.discard(path)
            elif kind == "delete":
                deleted.add(path)
    covers_all: List[str] = []
    quoted_all: List[str] = []
    for st in steps:
        label = f"step {st['n']}"
        fields = st["fields"]
        covers_all.append(expand_covers(" ".join(fields.get("Covers", []))))
        quoted_all += re.findall(r"`([^`]+)`", " ".join(fields.get("Covers", []) + fields.get("Design", []) + fields.get("Files", [])))
        if not st["current"]:          # an earlier iteration's step: done, counted for coverage only
            continue
        for f in required:
            if f not in fields or not "\n".join(fields[f]).strip():
                problems.append(f"{label}: no **{f}:**")
        checkpoint = "\n".join(fields.get(CHECKPOINT_FIELD, []))
        gates = GATE_RE.findall(checkpoint)
        if checkpoint.strip() and not any(g in lib.GATES for g in gates):
            problems.append(f"{label}: checkpoint names no gate in backticks (`typecheck`, `test`, … — port names the project declares)")
        for gate in gates:
            if gate in lib.GATES and gate not in declared:
                problems.append(f"{label}: checkpoint names gate `{gate}` the project does not declare in `verify`")
        m = MANUAL_RE.search(checkpoint)
        if m:
            problems.append(f"{label}: checkpoint asks for a check an agent cannot run («{m.group(0)}»): a QA step "
                            "or a question to the developer at a decision point, not a checkpoint — or say why an "
                            "agent can run it")
        for pref in readonly:
            file_under = re.compile(r"(?<![\w@/.\-])" + re.escape(pref) + r"[\w./\-]*(?:\.\w+|/)")   # a file or a directory under it, not `@omix/…` or `omix/` as a word
            prose = "\n".join(fields.get("Design", []) + fields.get(CHECKPOINT_FIELD, []))
            for line in prose.splitlines():
                if file_under.search(line) and EDIT_VERB_RE.search(line):
                    problems.append(f"{label}: touches the read-only submodule `{pref}` (even a temporary edit in a checkpoint is one): {line.strip()[:80]}")
                    break
        for kind, path in file_ops(fields.get("Files", [])):
            for pref in readonly:
                if path.startswith(pref):
                    problems.append(f"{label}: `{path}` is inside the read-only submodule `{pref}`")
            exists = ((root / path).exists() or path in created) and path not in deleted
            if kind == "create" and exists:
                problems.append(f"{label}: CREATE `{path}` — the file already exists (MODIFY?)")
            elif kind in ("modify", "delete") and not exists:
                problems.append(f"{label}: `{path}` is not in the tree (a wrong path, or CREATE?)")
            if kind == "create":
                created.add(path)
                deleted.discard(path)
            elif kind == "delete":
                deleted.add(path)
    if spec_text is not None:
        items = spec_items(spec_text)
        covers = " ".join(covers_all)
        for s in items["scenarios"]:
            if not re.search(rf"\b{s}\b", covers):
                problems.append(f"scenario {s} of spec.md is in no step's **Covers:**")
        quoted = {contract_key(q) for q in quoted_all}
        for c in items["contracts"]:
            if contract_key(c) not in quoted:
                problems.append(f"contract `{c}` of spec.md is quoted in no step's Covers, Design or Files")
        found = lib.section_lines(text, "Project Specs to Update")
        to_update = " ".join(found[1]) if found else ""
        for c, p in items["project_specs"].items():
            if p not in to_update:
                problems.append(f"contract `{c}` is stated by project spec `{p}`, which is not in «Project Specs to Update»")
    return problems


def cmd_check(ns: argparse.Namespace) -> int:
    task_dir = Path(ns.task).resolve()
    try:
        lib.require_yaml()
        state = lib.yaml.safe_load((task_dir / "state.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(state, dict):
            raise ValueError("not a mapping")
    except Exception as e:
        print(f"plan.py: state.yaml: {e}", file=sys.stderr)
        return NOT_READ
    root = lib.find_project_root(task_dir)
    tier = state.get("tier")
    try:
        source, text = plan_text(task_dir, ns.plan)
        cfg = lib.load_config(root)
        spec_path = Path(ns.spec) if ns.spec else task_dir / "spec.md"
        spec_text: Optional[str]
        if spec_path.exists():
            spec_text = spec_path.read_text(encoding="utf-8")
        elif ns.spec or str(tier or "").upper() != "S":
            raise lib.OmixflowError(f"no spec: {spec_path}")
        else:
            spec_text = None
    except Exception as e:
        print(f"plan.py: {e}", file=sys.stderr)
        return NOT_READ
    problems = check_plan(text, spec_text, cfg, root, tier)
    if ns.json:
        print(json.dumps({"plan": str(source), "problems": problems}, ensure_ascii=False))
    elif problems:
        print(f"PLAN CHECK: {len(problems)} problems in {source}")
        for p in problems:
            print(f"- {p}")
    else:
        print(f"PLAN CHECK: ok — {source}")
    return OVER if problems else OK


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("files", help="the plan's files and steps against the tier thresholds")
    p.add_argument("--task", required=True, help="TASK_DIR with state.yaml and plan.md (or spec.md with ## Steps)")
    p.add_argument("--plan", default=None, help="the plan file; default plan.md, else spec.md «Steps»")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_files)
    p = sub.add_parser("check", help="the mechanical part of the plan review")
    p.add_argument("--task", required=True)
    p.add_argument("--plan", default=None)
    p.add_argument("--spec", default=None, help="the spec; default TASK_DIR/spec.md")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_check)
    ns = ap.parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    sys.exit(main())
