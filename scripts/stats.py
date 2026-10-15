#!/usr/bin/env python3
"""Rework and cost of finished tasks from their log.md: the numbers to compare a pair of
similar tasks run under different pipeline settings (the 0.9 experiment).

    stats.py task TASK_DIR [TASK_DIR ...] [--json]

Per task, from state.yaml and log.md (the forms the phase skills write; nothing is
inferred from prose beyond the markers below):
- tier, steps (`### Шаг N` / `### Step N` under Implement), artifact sizes in characters
  (task, research, spec, plan);
- review passes per phase (the largest N of «проход N» / «Проходов: N» / «N прохода» under
  `## Spec`, `## Plan`, `## Review`), findings by severity (the fullest
  `(C critical, W warning, S suggestion)` of each phase, summed over phases);
- rework: step returns (`возвращ`/`вернул`/`по возврату задания`), fix iterations above
  zero (`FIX ITERATIONS k/`), red gates after a step (`FAIL` on a `Гейты:` line);
- decisions: `scope-change` points, questions to the developer or the lead (`- Вопрос #N`),
  escalations (distinct `E-{n}`), spec amendments by the coder (`спека поправлена`);
- cost: the `- Стоимость:` lines (0.8+), cost_eq summed over phases.

Prints one row per task, `--json` one object per task. Comparing is the developer's: a
task is a sample of one, so the script reports, it does not score.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

PHASE_RE = re.compile(r"^## (Refine|Start|Research|Spec|Plan|Implement|Review|Finalize)\b", re.M)
STEP_RE = re.compile(r"^### (?:Шаг|Step) \d+", re.M)
PASS_RE = re.compile(r"(?:[Пп]роход(?:ов)?[:\s]+(\d+)\b)|(?:(\d+) проход)")   # «проход 1», «Проходов: 2», «3 прохода»
FINDINGS_RE = re.compile(r"(\d+) critical, (\d+) warning(?: \[\w+\])?[^,\n]*, (\d+) suggestion")   # with or without parentheses
RETURN_RE = re.compile(r"возвращ|вернул|по возврату задания", re.I)
FIX_ITER_RE = re.compile(r"FIX ITERATIONS (\d+)/")
GATE_FAIL_RE = re.compile(r"^\s*-\s*Гейты:.*\bFAIL\b", re.M)
SCOPE_RE = re.compile(r"`scope-change`")
QUESTION_RE = re.compile(r"^\s*-\s*Вопрос #\d+", re.M)
ESCALATION_RE = re.compile(r"\bE-(\d+)\b")
AMEND_RE = re.compile(r"спека поправлена", re.I)
COST_RE = re.compile(r"^\s*-\s*Стоимость:\s*([\d.,]+)M cost_eq", re.M)


def sections(text: str) -> Dict[str, str]:
    """Phase name → text of its `## Phase…` sections (several per phase: Implement and Implement ✅)."""
    out: Dict[str, List[str]] = {}
    heads = list(PHASE_RE.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.setdefault(m.group(1), []).append(text[m.start():end])
    return {k: "\n".join(v) for k, v in out.items()}


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
    implement = by_phase.get("Implement", "")
    passes = {ph: max((int(a or b) for a, b in PASS_RE.findall(by_phase.get(ph, ""))), default=0)
              for ph in ("Spec", "Plan", "Review")}
    findings = {"total": 0, "critical": 0, "warning": 0, "suggestion": 0}
    for ph in ("Spec", "Plan", "Review"):        # per phase the fullest count (a summary line repeats the passes)
        best = max((tuple(int(x) for x in m.groups()) for m in FINDINGS_RE.finditer(by_phase.get(ph, ""))),
                   key=sum, default=(0, 0, 0))
        for key, val in zip(("critical", "warning", "suggestion"), best):
            findings[key] += val
        findings["total"] += sum(best)
    costs = [float(c.replace(",", ".")) for c in COST_RE.findall(log)]
    return {
        "task": task_dir.name,
        "tier": state.get("tier"),
        "profile": state.get("profile", "full"),
        "steps": len(STEP_RE.findall(implement)),
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
    for r in rows:
        p, f, w, d = r["review_passes"], r["findings"], r["rework"], r["decisions"]
        lines.append(f"{r['task'][:28]:<30}{str(r['tier']):<5}{r['steps']:>6}{r['chars']['spec'] // 1000:>7}"
                     f"{r['chars']['research'] // 1000:>7}{r['chars']['plan'] // 1000:>7}"
                     f"{f'{p['Spec']}/{p['Plan']}/{p['Review']}':>14}{f'{f['critical']}/{f['warning']}/{f['suggestion']}':>12}"
                     f"{w['step_returns']:>8}{w['fix_iterations']:>6}{w['red_gates']:>4}{d['scope_changes']:>6}"
                     f"{d['questions']:>6}{d['escalations']:>4}{d['spec_amendments']:>6}"
                     f"{(str(r['cost_eq_m']) if r['cost_eq_m'] is not None else '—'):>8}")
    return "\n".join(lines)


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
