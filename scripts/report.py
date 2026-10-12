#!/usr/bin/env python3
"""Check an agent's report against the tree and the gate logs (skills implement 2.2/2.3,
review 4): the orchestrator reads a verdict instead of the report.

    report.py baseline --out FILE [--root DIR] [--artifacts DIR]
    report.py check --role coder|tester --report REPORT_PATH [--root DIR] [--artifacts DIR]
                    [--baseline FILE] [--verify FILE | --also GATE ...] [--test-glob GLOB ...]
                    [--declaration REGEX] [--json]

`baseline` records the uncommitted tree before an assignment (the paths of `git status` with
the hash of each file's content) so that `check --baseline` charges the agent only with what
changed since: in implement the tester works on top of the coder's uncommitted step, in
review the coder, the tester and the coder again share one uncommitted fix pass. Without a
baseline the whole uncommitted tree is the agent's.

What `check` verifies, each against evidence the agent cannot write:
- the file exists and ends with its last section (coder: NOTES, tester: SUMMARY); a reply
  that starts with `REPORT_PATH refused by the harness` is the report (runtime.md, «Отказ
  записи») — the first line is dropped and the verdict says so;
- every section of the role's format is present (`NAME:` or `NAME (…):`);
- TREE STATE equals `git status --short` of ROOT: the claimed lines are normalised (the
  format's indentation and notes are dropped, only porcelain lines count, the artifacts
  directory is left out on both sides), and both the collapsed form (`?? dir/`) and the
  expanded one (`--untracked-files=all`) are accepted; a `*.orig` or `*.rej` leftover is a
  problem;
- MUTATIONS: new test declarations (lang adapter `tests.declaration`, else --declaration)
  in the agent's changed test files (`tests.files` globs across the lang adapters, else
  --test-glob; a binary file is not a test) are counted as added minus removed; that many
  MUTATIONS lines are due (`none` is allowed when the count is zero); an outcome is RED, or
  GREEN followed by a strengthening that ends in RED, or `no probe possible: {why}` — the
  excuses of 0.7.1 («schema unchanged», «existing behaviour», «not requested») and the
  `PROBE NOT RUN` messages of probe.py are a FAIL. Without known globs the verdict says
  MUTATIONS were not checked;
- gates: `STATUS: stopped` with `GATES: not run — …` is a stop, reported as such; else every
  gate of the step set (`resolve.py verify --at step` plus --also, or --verify FILE) has an
  outcome (coder: GATES; tester: RUN RESULT for test, CHECKPOINT GATES for the rest); a
  background gate names its `gate.py` run (coder: on the gate's line; tester: in BACKGROUND
  GATES) and, for the exit-code criterion, the run's exit file agrees with the outcome; the
  script runs no gate itself;
- BYTES CHECK is not `n/a` when the agent's diff adds non-ASCII text lines;
- SUPPRESSIONS CHECK is present; SCRATCH not `clean` becomes the log.md line.

The verdict always carries what the orchestrator acts on without reading the report: each
gate with its outcome, NOTES (when not `none`), `not declared` gates, the tester's FAILURES
and CODE BUGS FOUND, the untracked lines of TREE STATE.

Exit 0 — ok, or a stop (`VERDICT: ok` / `VERDICT: stopped`); exit 1 — return the report to
the agent: the output holds the message to send, point by point; exit 2 — the report is
missing or broken; exit 3 — the orchestrator's own error (config, --also, --verify,
--baseline), nothing about the agent. --json prints one object. The script checks claims
against git and gate logs; it replaces neither `resolve.py verify` nor the orchestrator's
checks.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402
import probe  # noqa: E402

OK, RETURN, BROKEN, USAGE = 0, 1, 2, 3
REFUSED = "REPORT_PATH refused by the harness"
SECTIONS = {
    "coder": ["STEP", "FILES", "PROJECT SPECS UPDATED", "GATES", "FIX ITERATIONS", "MUTATIONS", "BYTES CHECK",
              "SUPPRESSIONS CHECK", "SCRATCH", "TREE STATE", "SUMMARY", "NOTES"],
    "tester": ["TESTS WRITTEN", "RUN RESULT", "BACKGROUND GATES", "CHECKPOINT GATES", "ITERATIONS", "MUTATIONS",
               "BYTES CHECK", "SUPPRESSIONS CHECK", "SCRATCH", "TREE STATE", "SUMMARY"],
}
OPTIONAL = ["FAILURES", "CODE BUGS FOUND", "STATUS"]
LAST = {"coder": "NOTES", "tester": "SUMMARY"}
KNOWN = sorted({s for names in SECTIONS.values() for s in names} | set(OPTIONAL) | {"FILES CREATED", "FILES MODIFIED"},
               key=len, reverse=True)
EXCUSES = ("schema is unchanged", "schema unchanged", "existing behaviour", "existing behavior",
           "no probe was requested", "not requested", "none was requested")
NOT_RUN_REASONS = probe.NOT_RUN_PHRASES     # an input error of probe.py pasted as a reason
SECTION_HEAD_RE = re.compile(r"^(" + "|".join(re.escape(k) for k in KNOWN) + r")(?: \([^\n]*\))?:(.*)$")
PORCELAIN_RE = re.compile(r"^[ MADRCU?!]{2} \S")
OUTCOME_RE = re.compile(r"(?:→|->)\s*(RED|GREEN)\b")
GATE_LINE_RE = re.compile(r"^\s*-?\s*([a-z0-9]+):\s*(PASS|FAIL|n/a|not declared)\b(.*)$", re.I)
GATE_RUN_RE = re.compile(r"gate\.py\s+([A-Za-z0-9._-]+)(?:,?\s*EXIT\s+(\d+))?")
BACKGROUND_RE = re.compile(r"^\s*-?\s*([a-z0-9]+):\s*gate\.py\s+([A-Za-z0-9._-]+)(?:,?\s*EXIT\s+(\d+))?", re.I)
MUTATION_LINE_RE = re.compile(r"^\s*-\s+(.+)$")


# ------------------------------------------------------------------ report parsing

def parse_report(text: str) -> Dict[str, List[str]]:
    """Sections of the fixed report format: a known `NAME:` (or `NAME (…):`) at line start
    opens a section; FILES CREATED and FILES MODIFIED fold into FILES."""
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        m = SECTION_HEAD_RE.match(line)
        if m:
            name = m.group(1)
            if name.startswith("FILES "):
                name = "FILES"
            current = name
            sections.setdefault(current, [])
            rest = m.group(2).strip()
            if rest:
                sections[current].append(rest)
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def section_text(sections: Dict[str, List[str]], name: str) -> str:
    return "\n".join(sections.get(name, [])).strip()


def is_none(body: str) -> bool:
    """`none`, `- none`, `none: …` — an empty section in the agents' formats."""
    return body.lstrip("-* ").lower().startswith("none")


# ------------------------------------------------------------------ evidence

def status_lines(root: Path, artifacts: str, expanded: bool) -> List[str]:
    args = ["status", "--short"] + (["--untracked-files=all"] if expanded else [])
    out = lib.git_raw(root, *args) or ""
    keep = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].split(" -> ")[-1].strip('"')
        if lib.outside_dir([path], artifacts):
            keep.append(line.rstrip())
    return keep


def normalise_claimed(lines: List[str], artifacts: str) -> List[str]:
    """The TREE STATE lines of a report as porcelain lines: indentation and notes dropped,
    the artifacts directory left out."""
    out = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.lstrip()
        # the format indents the snapshot by two spaces; a porcelain line keeps its own leading
        # space (` M path`) only when the indentation is exactly the format's
        candidate = line[2:] if line.startswith("  ") and PORCELAIN_RE.match(line[2:]) else stripped
        if not PORCELAIN_RE.match(candidate):
            if PORCELAIN_RE.match(" " + candidate):   # ` M path` whose leading space was trimmed
                candidate = " " + candidate
            else:
                continue
        path = candidate[3:].split(" -> ")[-1].strip('"')
        if lib.outside_dir([path], artifacts):
            out.append(candidate)
    return out


def changed_paths(root: Path, artifacts: str) -> List[str]:
    return lib.changed_files(root, None, artifacts)


def content_hash(root: Path, path: str, store: bool = False) -> Optional[str]:
    """The blob id of PATH's content; with STORE the blob is written to the object store
    (only the store changes, never the tree) so a later check can diff against it."""
    out = lib.git(root, "hash-object", *(["-w"] if store else []), "--", path)
    return out or None


def snapshot(root: Path, artifacts: str, store: bool = False) -> Dict[str, Optional[str]]:
    """Path → content hash of every uncommitted change (deleted: None)."""
    return {p: content_hash(root, p, store) for p in changed_paths(root, artifacts)}


def agent_delta(root: Path, artifacts: str, baseline: Optional[Dict[str, Optional[str]]]) -> List[str]:
    """The paths the agent changed: everything uncommitted, or, with a baseline, only what
    differs from it."""
    now = snapshot(root, artifacts)
    if baseline is None:
        return sorted(now)
    return sorted(p for p, h in now.items() if baseline.get(p, "∅") != h)


def is_binary(root: Path, path: str) -> bool:
    try:
        return b"\0" in (root / path).read_bytes()[:8192]
    except OSError:
        return False


def diff_lines(root: Path, path: str, baseline: Optional[Dict[str, Optional[str]]] = None) -> Tuple[List[str], List[str]]:
    """(added, removed) lines of PATH: against its blob in BASELINE when it has one (the
    agent extended a file an earlier agent left uncommitted: only its own lines count),
    else against HEAD; an untracked file without a baseline blob is all added."""
    try:
        current = (root / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        current = []
    before: Optional[List[str]] = None
    if baseline and baseline.get(path):
        blob = lib.git_raw(root, "cat-file", "-p", str(baseline[path]))
        if blob is not None:
            before = blob.splitlines()
    if before is None:
        tracked = lib.git(root, "ls-files", "--error-unmatch", "--", path) is not None
        if not tracked:
            return current, []
        diff = lib.git_raw(root, "diff", "HEAD", "--", path) or ""
        added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        return added, removed
    added, removed = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, current, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += before[i1:i2]
        if tag in ("replace", "insert"):
            added += current[j1:j2]
    return added, removed


def new_declarations_in(added: List[str], removed: List[str], rx: "re.Pattern[str]") -> int:
    """Added declaration lines without an identical (whitespace-normalised) removed one: a
    moved test is not new, a renamed or replaced one is (its body deserves a probe)."""
    gone = Counter(" ".join(l.split()) for l in removed if rx.search(l))
    n = 0
    for l in added:
        if not rx.search(l):
            continue
        key = " ".join(l.split())
        if gone[key] > 0:
            gone[key] -= 1
        else:
            n += 1
    return n


def lang_tests(root: Path) -> List[Tuple[List[str], Optional[str]]]:
    """(globs, declaration) per lang adapter chain (the leaf's values win within a chain);
    the globs of several languages are all test files."""
    out: List[Tuple[List[str], Optional[str]]] = []
    try:
        cfg = lib.load_config(root)
        for name in lib.adapters_for(cfg, "lang"):
            globs: List[str] = []
            declaration: Optional[str] = None
            for adapter in lib.resolve_adapter("lang", name, root):
                tests = adapter.meta.get("tests") or {}
                if isinstance(tests, dict):
                    if tests.get("files"):
                        globs = [str(g) for g in tests["files"]]
                    if tests.get("declaration"):
                        declaration = str(tests["declaration"])
            if globs:
                out.append((globs, declaration))
    except lib.OmixflowError:
        pass
    return out


def gate_exit(root: Path, name: str) -> Optional[str]:
    git_dir = lib.git(root, "rev-parse", "--absolute-git-dir")
    if not git_dir:
        return None
    try:
        return (Path(git_dir) / "omixflow-gates" / f"{name}.exit").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def verify_plan(root: Path, verify_file: Optional[str], also: List[str]) -> Dict[str, Any]:
    """The step set; an OmixflowError is the orchestrator's (config or --also), not the agent's."""
    if verify_file:
        try:
            return json.loads(Path(verify_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise lib.OmixflowError(f"--verify {verify_file}: {e}")
    also = [a for a in also if a and a.lower() != "none"]
    return lib.verify_plan(lib.load_config(root), root, "step", also=also or None)


def gate_criteria(root: Path) -> Dict[str, str]:
    try:
        verify = lib.load_config(root).get("verify") or {}
    except lib.OmixflowError:
        return {}
    return {name: str(gate.get("criterion", "exit-code")) for name, gate in verify.items() if isinstance(gate, dict)}


# ------------------------------------------------------------------ checks

def check(role: str, report_path: Path, root: Path, artifacts: str, plan: Optional[Dict[str, Any]],
          langs: List[Tuple[List[str], Optional[str]]], criteria: Dict[str, str],
          baseline: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"role": role, "report": str(report_path), "verdict": "ok", "problems": [],
                              "verified": [], "facts": [], "unchecked": [], "refused": False, "scratch_line": None}
    problems: List[str] = result["problems"]
    verified: List[str] = result["verified"]
    facts: List[str] = result["facts"]

    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        result.update(verdict="broken", problems=[f"отчёта нет: {report_path}"])
        return result
    lines = text.splitlines()
    if lines and lines[0].strip().startswith(REFUSED):
        result["refused"] = True
        text = "\n".join(lines[1:])
    sections = parse_report(text)
    if LAST[role] not in sections:
        result.update(verdict="broken", problems=[f"отчёт без последнего раздела {LAST[role]}: обрезан или не дописан"])
        return result
    missing = [s for s in SECTIONS[role] if s not in sections]
    if missing:
        problems.append("нет разделов: " + ", ".join(missing))
    else:
        verified.append("разделы формата на месте")

    # a stop is not a failed report
    status = section_text(sections, "STATUS").lower()
    gates_text = section_text(sections, "GATES") if role == "coder" else section_text(sections, "RUN RESULT")
    stopped = status.startswith("stopped") or gates_text.lower().startswith("not run")
    if stopped:
        facts.append(f"остановка агента: {section_text(sections, 'STATUS') or gates_text.splitlines()[0]}")

    # TREE STATE
    claimed = normalise_claimed(sections.get("TREE STATE", []), artifacts)
    short, expanded = status_lines(root, artifacts, False), status_lines(root, artifacts, True)
    if set(claimed) in (set(short), set(expanded)):
        verified.append(f"TREE STATE совпадает с git status ({len(claimed)} строк)")
    else:
        actual = expanded if len(set(claimed) ^ set(expanded)) < len(set(claimed) ^ set(short)) else short
        extra, absent = sorted(set(claimed) - set(actual)), sorted(set(actual) - set(claimed))
        problems.append("TREE STATE расходится с `git status --short`: "
                        + (f"лишние в отчёте {extra}; " if extra else "") + (f"нет в отчёте {absent}" if absent else ""))
    untracked = [l for l in claimed if l.startswith("??")]
    for l in expanded:          # the real tree, every file: a collapsed `?? dir/` line hides a copy inside
        if re.search(r"\.(orig|rej)$", l):
            problems.append(f"TREE STATE: остаток пробы в дереве — {l}")
    if untracked:
        facts.append("неотслеживаемые по TREE STATE: " + ", ".join(l[3:] for l in untracked))

    # MUTATIONS
    delta = agent_delta(root, artifacts, baseline)
    mutation_lines = [l for l in sections.get("MUTATIONS", []) if MUTATION_LINE_RE.match(l)
                      and (OUTCOME_RE.search(l) or "no probe possible" in l.lower())]
    mutations = section_text(sections, "MUTATIONS")
    if not langs:
        result["unchecked"].append("MUTATIONS не сверены: у адаптера lang нет tests.files — сверить руками "
                                   "(implement 2.2) и добавить tests во фронтматтер адаптера")
    else:
        new_declarations = 0
        per_file: List[str] = []
        for globs, declaration in langs:
            rx = re.compile(declaration) if declaration else None
            for path in lib.area_files(globs, delta):
                if is_binary(root, path):
                    continue
                if rx is None:
                    per_file.append(f"{path}: тестовый файл изменён (объявления не считаются: у адаптера нет tests.declaration)")
                    continue
                added, removed = diff_lines(root, path, baseline)
                n = new_declarations_in(added, removed, rx)
                if n > 0:
                    new_declarations += n
                    per_file.append(f"{path}: новых тестов {n}")
        if is_none(mutations) and new_declarations:
            problems.append(f"MUTATIONS: none, но новых тестов {new_declarations} ({'; '.join(per_file)})")
        elif new_declarations > len(mutation_lines):
            problems.append(f"MUTATIONS: новых тестов {new_declarations} ({'; '.join(per_file)}), строк с исходом "
                            f"{len(mutation_lines)}: проба на каждый новый тест и утверждение")
        for l in mutation_lines:
            low = l.lower()
            if "no probe possible" in low:
                if any(e in low for e in EXCUSES):
                    problems.append(f"MUTATIONS: отговорка вместо причины — {l.strip()}")
                elif any(r in low for r in NOT_RUN_REASONS):
                    problems.append(f"MUTATIONS: проба не была запущена (ошибка вызова probe.py), не причина — {l.strip()}")
                continue
            outcomes = OUTCOME_RE.findall(l)
            if outcomes and outcomes[-1] == "GREEN":
                problems.append(f"MUTATIONS: исход GREEN без усиления и повторной пробы до RED — {l.strip()}")
        if not any(p.startswith("MUTATIONS") for p in problems):
            verified.append(f"MUTATIONS: новых тестов {new_declarations}, строк с исходом {len(mutation_lines)}"
                            + (f" ({'; '.join(per_file)})" if per_file else ""))

    # gates
    reported: Dict[str, Tuple[str, str]] = {}
    runs: Dict[str, Tuple[str, Optional[str]]] = {}    # gate → (gate.py run name, claimed EXIT)
    if role == "coder":
        for l in sections.get("GATES", []):
            m = GATE_LINE_RE.match(l)
            if m:
                reported[m.group(1).lower()] = (m.group(2).upper(), m.group(3))
                r = GATE_RUN_RE.search(m.group(3))
                if r:
                    runs[m.group(1).lower()] = (r.group(1), r.group(2))
    else:
        rr = section_text(sections, "RUN RESULT")
        m = re.match(r"^\s*(PASS|FAIL)\b(.*)$", rr, re.I)
        if m:
            reported["test"] = (m.group(1).upper(), m.group(2))
        for l in sections.get("CHECKPOINT GATES", []):
            for m in re.finditer(r"([a-z0-9]+):\s*(PASS|FAIL|not declared|n/a)\b", l, re.I):
                reported[m.group(1).lower()] = (m.group(2).upper(), "")
        for l in sections.get("BACKGROUND GATES", []):
            m = BACKGROUND_RE.match(l)
            if m:
                runs[m.group(1).lower()] = (m.group(2), m.group(3))
    gate_section = "GATES" if role == "coder" else "RUN RESULT / CHECKPOINT GATES"
    for name, (outcome, _) in reported.items():
        facts.append(f"гейт {name}: {outcome}")
    if stopped:
        verified.append("гейты не сверялись: агент остановился до них")
    elif plan is None:
        result["unchecked"].append("набор гейтов не сверен: нет плана verify")
    else:
        due = [g["name"] for g in plan.get("gates", [])] if role == "coder" else (
            [g["name"] for g in plan.get("gates", []) if g.get("also")] + ["test"])
        absent = [n for n in due if n not in reported]
        if absent:
            problems.append(f"{gate_section}: нет исхода гейтов {', '.join(absent)}")
        else:
            verified.append(f"{gate_section}: исходы всех гейтов набора ({', '.join(due)})")
        for name in [g for g, (o, _) in reported.items() if o == "NOT DECLARED"]:
            facts.append(f"гейт {name}: not declared — дефект плана, строка в log.md")
        background = {g["name"] for g in plan.get("gates", []) if g.get("background")}
        for name in background:
            if name in reported and name not in runs:
                problems.append(f"{gate_section}: фоновый гейт {name} без имени gate.py ({{метка}}-{name})")
        for name, (run_name, claimed_exit) in runs.items():
            actual = gate_exit(root, run_name)
            outcome = reported.get(name, ("", ""))[0]
            if actual is None:
                problems.append(f"{gate_section}: лога gate.py {run_name} нет (не запускался или имя не то)")
            elif criteria.get(name, "exit-code") in ("exit-code", "rerun-compare-set") and outcome in ("PASS", "FAIL") \
                    and (actual == "0") != (outcome == "PASS"):
                problems.append(f"{gate_section}: {name} заявлен {outcome}, а EXIT {actual} у {run_name}")
            elif claimed_exit and claimed_exit != actual:
                problems.append(f"{gate_section}: {name}: в отчёте EXIT {claimed_exit}, в логе {actual}")
            else:
                verified.append(f"{gate_section}: {run_name} EXIT {actual} как заявлено")

    # BYTES CHECK
    non_ascii = [p for p in delta if not is_binary(root, p)
                 and any(any(ord(ch) > 127 for ch in l) for l in diff_lines(root, p, baseline)[0])]
    bytes_check = section_text(sections, "BYTES CHECK")
    if non_ascii and (not bytes_check or bytes_check.lstrip("-* ").lower().startswith("n/a")):
        problems.append(f"BYTES CHECK: n/a, а в диффе не-ASCII строки: {non_ascii[:5]}")
    elif "BYTES CHECK" in sections:
        verified.append("BYTES CHECK соответствует диффу")

    # SUPPRESSIONS CHECK, SCRATCH, the sections the orchestrator acts on
    if not section_text(sections, "SUPPRESSIONS CHECK"):
        problems.append("SUPPRESSIONS CHECK пуст")
    scratch = section_text(sections, "SCRATCH")
    if scratch and not scratch.lower().startswith("clean"):
        result["scratch_line"] = f"- SCRATCH {report_path.stem}: {scratch.splitlines()[0]}"
    notes = section_text(sections, "NOTES")
    if notes and not is_none(notes):
        facts.append("NOTES: " + " ".join(notes.split())[:400])
    for name in ("FAILURES", "CODE BUGS FOUND"):
        body = section_text(sections, name)
        if body and not is_none(body):
            facts.append(f"{name}: " + " ".join(body.split())[:400])

    result["verdict"] = "return" if problems else ("stopped" if stopped else "ok")
    return result


def render(result: Dict[str, Any]) -> str:
    head = f"VERDICT: {result['verdict']}"
    if result["refused"]:
        head += " (ответ REPORT_PATH refused by the harness: файл записал оркестратор)"
    out = [head]
    if result["verdict"] in ("ok", "stopped"):
        out += [f"- {v}" for v in result["verified"]]
    elif result["verdict"] == "broken":
        out += [f"- {p}" for p in result["problems"]]
        return "\n".join(out)
    else:
        out.append("Сообщение агенту (отправить как есть):")
        out.append("The report was checked against the tree and the gate logs; fix these points and report again "
                   "with the same REPORT_PATH:")
        out += [f"{i}. {p}" for i, p in enumerate(result["problems"], 1)]
    for f in result["facts"]:
        out.append(f"- {f}")
    for u in result["unchecked"]:
        out.append(f"- НЕ СВЕРЕНО: {u}")
    if result["scratch_line"]:
        out.append(result["scratch_line"])
    return "\n".join(out)


class Parser(argparse.ArgumentParser):
    def error(self, message: str):   # a usage error is the orchestrator's, exit 3
        print(f"report.py: {message}", file=sys.stderr)
        sys.exit(USAGE)


def cmd_baseline(ns: argparse.Namespace, root: Path, artifacts: str) -> int:
    snap = snapshot(root, artifacts, store=True)
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"root": str(root), "artifacts": artifacts, "files": snap}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"baseline: {len(snap)} uncommitted paths → {out}")
    return 0


def cmd_check(ns: argparse.Namespace, root: Path, artifacts: str) -> int:
    baseline = None
    if ns.baseline:
        try:
            baseline = json.loads(Path(ns.baseline).read_text(encoding="utf-8"))["files"]
        except (OSError, ValueError, KeyError) as e:
            print(f"report.py: --baseline {ns.baseline}: {e}", file=sys.stderr)
            return USAGE
    langs = lang_tests(root)
    if ns.test_glob:
        langs = [(list(ns.test_glob), ns.declaration)]
    elif ns.declaration:
        langs = [(g, ns.declaration) for g, _ in langs] or [([], ns.declaration)]
    try:
        plan = verify_plan(root, ns.verify, ns.also)
    except lib.OmixflowError as e:
        print(f"report.py: план гейтов не получен: {e}", file=sys.stderr)
        return USAGE
    result = check(ns.role, Path(ns.report), root, artifacts.strip("/"), plan, langs, gate_criteria(root), baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2) if ns.json else render(result))
    return {"ok": OK, "stopped": OK, "return": RETURN, "broken": BROKEN}[result["verdict"]]


def main(argv: Optional[List[str]] = None) -> int:
    ap = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    p = sub.add_parser("baseline")
    p.add_argument("--out", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--artifacts", default=None)
    p.set_defaults(fn=cmd_baseline)
    p = sub.add_parser("check")
    p.add_argument("--role", required=True, choices=sorted(SECTIONS))
    p.add_argument("--report", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--artifacts", default=None, help="artifacts directory, default from flow.yaml (.tasks)")
    p.add_argument("--baseline", default=None, help="file of `report.py baseline` taken before the assignment")
    p.add_argument("--verify", default=None, help="JSON of resolve.py verify for the step; default: computed")
    p.add_argument("--also", nargs="+", action="extend", default=[], help="checkpoint gates of the step (`none` ignored)")
    p.add_argument("--test-glob", nargs="+", action="extend", default=[], help="test file globs; default: lang adapters' `tests.files`")
    p.add_argument("--declaration", default=None, help="regex of a test declaration; default: adapters' `tests.declaration`")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_check)
    ns = ap.parse_args(argv)
    root = lib.find_project_root(Path(ns.root) if ns.root else None)
    try:
        artifacts = ns.artifacts or str(lib.config_get(lib.load_config(root), "artifacts.dir") or ".tasks")
    except lib.OmixflowError:
        artifacts = ns.artifacts or ".tasks"
    return ns.fn(ns, root, artifacts.strip("/"))


if __name__ == "__main__":
    sys.exit(main())
