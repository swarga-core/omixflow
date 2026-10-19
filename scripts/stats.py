#!/usr/bin/env python3
"""Rework and cost of finished tasks from their log.md: the numbers to compare a pair of
similar tasks run under different pipeline settings (the 0.9 experiment).

    stats.py task TASK_DIR [TASK_DIR ...] [--json]

Per task, from state.yaml and log.md (the forms the phase skills write; nothing is
inferred from prose beyond the markers below):
- tier, steps (distinct `### Шаг N` / `### Step N` after the first `## Implement`, also those a
  restarted session appended after `## Finalize` — counted, and named under the table), artifact
  sizes in characters (task, research, spec, plan);
- review passes per phase (the largest N of «проход N» / «Проходов: N» / «N прохода» under
  `## Spec`, `## Plan`, `## Review`), findings by severity (the fullest
  `(C critical, W warning, S suggestion)` or `critical C, warning W, suggestion S` of each phase,
  a count wrapped over lines too, summed over phases); a phase that names only the total
  («findings 4 — …», «18 находок») adds it to `total`, shown as «+N» after C/W/S;
- rounds of `plan.py check` fixes before the plan review («plan.py check: кругов N» under Spec
  and Plan; JSON `plan_check_rounds`);
- rework: step returns (`возвращ`/`вернул`/`по возврату задания`), fix iterations above
  zero (`FIX ITERATIONS k/`), red gates after a step (`FAIL` on a `Гейты:` line);
- decisions: `scope-change` points, questions to the developer or the lead (`- Вопрос #N`),
  escalations (distinct `E-{n}`), spec amendments by the coder (`спека поправлена`);
- cost: the `- Стоимость:` lines (0.8+; «- Стоимость (Spec + Plan):» too, not the Finalize total
  «- Стоимость задачи:»), cost_eq summed over phases.

Prints one row per task, `--json` one object per task. Comparing is the developer's: a
task is a sample of one, so the script reports, it does not score.
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

PHASE_RE = re.compile(r"^## (Refine|Start|Research|Spec|Plan|Implement|Review|Finalize)\b", re.M)
STEP_RE = re.compile(r"^### (?:Шаг|Step) (\d+[a-zа-я]?)\b", re.M)   # a split step 3a/3b is two (plan.py too)
BLOCK_END_RE = re.compile(r"^#{2,3} ", re.M)
PASS_RE = re.compile(r"(?:[Пп]роход(?:ов)?[:\s]+(\d+)\b)|(?:(\d+) проход)")   # «проход 1», «Проходов: 2», «3 прохода»
# severities in both orders, a [category] and a parenthesis after the warnings allowed:
# «(0 critical, 1 warning [plan], 2 suggestion)», «critical 0, warning 4 (#1–#3 spec, #4 plan), suggestion 7»
_TAIL = r"(?:\s*\[\w+\])?(?:\s*\([^)]*\))?[^,()]*,\s*"
FINDINGS_RES = (re.compile(r"(\d+) critical,\s*(\d+) warning" + _TAIL + r"(\d+) suggestion"),
                re.compile(r"critical (\d+),\s*warning (\d+)" + _TAIL + r"suggestion (\d+)"))
# a total without severities: «findings 4 — #1 warning …», «Итого findings 4», «18 находок»;
# not a range of finding numbers («с findings 8–10», «findings 8, 9», AL-1151)
TOTAL_RE = re.compile(r"(?:\b[Ff]indings:?\s+(\d+)\b(?!\s*[–-]\s*\d|,\s*\d))"
                      r"|(?:\b(\d+)\s+(?:findings|находок|находки|находка)\b)")
# «plan.py check: кругов 1», «`plan.py check`: кругов 2», «`plan.py check`: ok, кругов 0» (T-10…T-15)
PLAN_CHECK_RE = re.compile(r"plan\.py check`?:\s*(?:ok,\s*)?кругов (\d+)")
RETURN_RE = re.compile(r"возвращ|вернул|по возврату задания", re.I)
FIX_ITER_RE = re.compile(r"FIX ITERATIONS (\d+)/")
GATE_FAIL_RE = re.compile(r"^\s*-\s*Гейты:.*\bFAIL\b", re.M)
SCOPE_RE = re.compile(r"`scope-change`")
QUESTION_RE = re.compile(r"^\s*-\s*Вопрос #\d+", re.M)
ESCALATION_RE = re.compile(r"\bE-(\d+)\b")
AMEND_RE = re.compile(r"спека поправлена", re.I)
# «- Стоимость: …» and a phase pair the orchestrator named in the head, «- Стоимость (Spec + Plan): …»;
# not the Finalize total «- Стоимость задачи: …»
COST_RE = re.compile(r"^\s*-\s*Стоимость(?:\s*\([^)\n]*\))?:\s*([\d.,]+)M cost_eq", re.M)


def spans(text: str) -> List[Tuple[str, int, int]]:
    """`(phase, start, end)` of each `## Phase…` section, in log order."""
    heads = list(PHASE_RE.finditer(text))
    return [(m.group(1), m.start(), heads[i + 1].start() if i + 1 < len(heads) else len(text))
            for i, m in enumerate(heads)]


def sections(text: str) -> Dict[str, str]:
    """Phase name → text of its `## Phase…` sections (several per phase: Implement and Implement ✅)."""
    out: Dict[str, List[str]] = {}
    for phase, start, end in spans(text):
        out.setdefault(phase, []).append(text[start:end])
    return {k: "\n".join(v) for k, v in out.items()}


def implement_text(text: str) -> Tuple[str, List[str], int]:
    """The Implement sections and every `### Шаг N` block outside them — a session restarted after
    Finalize appends its steps at the end of the log (SwAIS T-10: seven steps after `## Finalize ✅`).
    Returns the text, the distinct step numbers after the first `## Implement` and how many step
    heads stand after the first `## Finalize`."""
    parts = spans(text)
    implement = [(s, e) for phase, s, e in parts if phase == "Implement"]
    if not implement:
        return "", [], 0
    first = implement[0][0]
    finalize = next((s for phase, s, _ in parts if phase == "Finalize"), None)
    chunks = [text[s:e] for s, e in implement]
    numbers: List[str] = []
    late = 0
    for m in STEP_RE.finditer(text, first):
        if m.group(1) not in numbers:
            numbers.append(m.group(1))
        if finalize is not None and m.start() > finalize:
            late += 1
        if not any(s <= m.start() < e for s, e in implement):
            nxt = BLOCK_END_RE.search(text, m.end())
            chunks.append(text[m.start():nxt.start() if nxt else len(text)])
    return "\n".join(chunks), numbers, late


def phase_findings(section: str) -> Tuple[int, Tuple[int, int, int]]:
    """The total and (critical, warning, suggestion) of a phase: the fullest severity count in
    either form (a summary line repeats the passes), the total at least their sum — a line may
    name only the total («findings 4 — #1 warning [plan] …», T-10)."""
    flat = " ".join(section.split())        # a count wrapped onto the next line (T-12, T-14)
    best = max((tuple(int(x) for x in m.groups()) for rx in FINDINGS_RES for m in rx.finditer(flat)),
               key=sum, default=(0, 0, 0))
    total = max((int(a or b) for a, b in TOTAL_RE.findall(flat)), default=0)
    return max(total, sum(best)), best  # type: ignore[return-value]


def size(p: Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def task_stats(task_dir: Path) -> Dict[str, Any]:
    lib.require_yaml()
    state: Dict[str, Any] = {}
    try:
        state = lib.yaml.safe_load((task_dir / "state.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        pass
    log = ""
    try:
        log = (task_dir / "log.md").read_text(encoding="utf-8")
    except OSError:
        pass
    by_phase = sections(log)
    implement, steps, late = implement_text(log)
    passes = {ph: max((int(a or b) for a, b in PASS_RE.findall(by_phase.get(ph, ""))), default=0)
              for ph in ("Spec", "Plan", "Review")}
    findings = {"total": 0, "critical": 0, "warning": 0, "suggestion": 0}
    for ph in ("Spec", "Plan", "Review"):
        total, best = phase_findings(by_phase.get(ph, ""))
        for key, val in zip(("critical", "warning", "suggestion"), best):
            findings[key] += val
        findings["total"] += total
    costs = [float(c.replace(",", ".")) for c in COST_RE.findall(log)]
    return {
        "task": task_dir.name,
        "tier": state.get("tier"),
        "profile": state.get("profile", "full"),
        "steps": len(steps),
        "steps_after_finalize": late,
        # rounds of `plan.py check` fixes before the plan review (G-79: are the missing step fields common?)
        "plan_check_rounds": sum(int(n) for n in PLAN_CHECK_RE.findall(by_phase.get("Spec", "") + by_phase.get("Plan", ""))),
        "chars": {k: size(task_dir / f"{k}.md") for k in ("task", "research", "spec", "plan")},
        "review_passes": passes,
        "findings": findings,
        "rework": {
            "step_returns": len(RETURN_RE.findall(implement)),
            "fix_iterations": sum(int(k) for k in FIX_ITER_RE.findall(implement) if int(k) > 0),
            "red_gates": len(GATE_FAIL_RE.findall(implement)),
        },
        "decisions": {
            "scope_changes": len(SCOPE_RE.findall(log)),
            "questions": len(QUESTION_RE.findall(log)),
            "escalations": len(set(ESCALATION_RE.findall(log))),
            "spec_amendments": len(AMEND_RE.findall(log)),
        },
        "cost_eq_m": round(sum(costs), 1) if costs else None,
        "cost_lines": len(costs),
    }


def render(rows: List[Dict[str, Any]]) -> str:
    head = (f"{'task':<30}{'tier':<5}{'steps':>6}{'spec k':>7}{'rsch k':>7}{'plan k':>7}{'passes S/P/R':>14}"
            f"{'find C/W/S':>12}{'returns':>8}{'fixit':>6}{'red':>4}{'scope':>6}{'quest':>6}{'esc':>4}{'amend':>6}{'cost M':>8}")
    lines = [head]
    notes = []
    for r in rows:
        p, f, w, d = r["review_passes"], r["findings"], r["rework"], r["decisions"]
        rest = f["total"] - f["critical"] - f["warning"] - f["suggestion"]     # named only as a total
        find = f"{f['critical']}/{f['warning']}/{f['suggestion']}" + (f"+{rest}" if rest > 0 else "")
        lines.append(f"{r['task'][:28]:<30}{str(r['tier']):<5}{r['steps']:>6}{r['chars']['spec'] // 1000:>7}"
                     f"{r['chars']['research'] // 1000:>7}{r['chars']['plan'] // 1000:>7}"
                     f"{f'{p['Spec']}/{p['Plan']}/{p['Review']}':>14}{find:>12}"
                     f"{w['step_returns']:>8}{w['fix_iterations']:>6}{w['red_gates']:>4}{d['scope_changes']:>6}"
                     f"{d['questions']:>6}{d['escalations']:>4}{d['spec_amendments']:>6}"
                     f"{(str(r['cost_eq_m']) if r['cost_eq_m'] is not None else '—'):>8}")
        if rest > 0:
            notes.append(f"{r['task']}: findings {rest} без разбивки по severity (+{rest})")
        if r["steps_after_finalize"]:
            notes.append(f"{r['task']}: шагов после ## Finalize {r['steps_after_finalize']} — учтены")
    return "\n".join(lines + notes)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("task")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    rows = []
    for d in ns.dirs:
        path = Path(d).resolve()
        if not (path / "log.md").exists():
            print(f"stats.py: {path}: no log.md", file=sys.stderr)
            return 2
        rows.append(task_stats(path))
    print(json.dumps(rows, ensure_ascii=False, indent=1) if ns.json else render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
