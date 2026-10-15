"""Tests for stats.py: rework and cost of a task from its log.md (the 0.9 experiment)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import stats  # noqa: E402

LOG = """# Log: T-1

## Start ✅
- Ветка task/T-1
- Стоимость: 0.4M cost_eq, запросов 12

## Spec ✅
- `reviewer-T-1`, проход 1: request_changes — 0 critical, 3 warning [spec] (#1–#3, blocking), 12 suggestion
- Проход 2: approve, #1–#15 закрыты; новый #16 (suggestion)
- Проход 3 (последний): approve, #16 закрыт
- Итого: 3 прохода, 18 находок (0 critical, 3 warning, 15 suggestion); эскалаций — 1 вопрос (#5, 2 пункта).
- Вопрос #5 лиду: P1 → ack E-12, E-13 → decision
- Стоимость: 6.1M cost_eq, запросов 140

## Plan ✅ (combined, M)
- Ревью общее со spec.

## Implement

### Шаг 1: типы ✅
- Гейты: typecheck PASS, test PASS, lint PASS
- FIX ITERATIONS 0/7
- Коммит: aaa

- Решение `scope-change`: план — 28 файлов при пороге 15 → a) остаётся M. Решил: разработчик, E-14

### Шаг 2: сервер ✅
- Гейты: typecheck PASS, test FAIL → починка, test PASS
- FIX ITERATIONS 2/7; задание возвращено coder'у по TREE STATE
- спека поправлена coder'ом на шаге 2: S1 называет NaN
- Коммит: bbb

## Implement ✅
- Стоимость: 20.0M cost_eq, запросов 400

## Review ✅
- Ревью кода: свежий `reviewer-T-1-code`, проход 1: approve, 4 findings — 0 critical, 1 warning, 3 suggestion
- Проход 2: approve, #1–#4 закрыты
- Findings: 4 total (0 critical, 1 warning, 3 suggestion)
- Проходов: 2
- Стоимость: 5.5M cost_eq, запросов 90

## Finalize ✅
- Findings ревью: spec+plan — 18 total; код — 4 total
"""


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = stats.main(list(args))
    return code, out.getvalue(), err.getvalue()


class StatsTests(unittest.TestCase):
    def test_a_task_row_counts_passes_findings_rework_decisions_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "T-1"
            task.mkdir()
            (task / "state.yaml").write_text("id: T-1\ntier: M\n")
            (task / "log.md").write_text(LOG)
            (task / "spec.md").write_text("x" * 2500)
            (task / "research.md").write_text("y" * 1200)
            code, out, _ = run("task", str(task), "--json")
            self.assertEqual(code, 0, out)
            r = json.loads(out)[0]
            self.assertEqual(r["tier"], "M")
            self.assertEqual(r["steps"], 2)
            self.assertEqual(r["chars"], {"task": 0, "research": 1200, "spec": 2500, "plan": 0})
            self.assertEqual(r["review_passes"], {"Spec": 3, "Plan": 0, "Review": 2})
            self.assertEqual(r["findings"], {"total": 22, "critical": 0, "warning": 4, "suggestion": 18})
            self.assertEqual(r["rework"], {"step_returns": 1, "fix_iterations": 2, "red_gates": 1})
            self.assertEqual(r["decisions"], {"scope_changes": 1, "questions": 1, "escalations": 3, "spec_amendments": 1})
            self.assertEqual((r["cost_eq_m"], r["cost_lines"]), (32.0, 4))
            code, out, _ = run("task", str(task))
            self.assertEqual(code, 0)
            self.assertIn("3/0/2", out)
            self.assertIn("0/4/18", out)
            code, _, err = run("task", str(Path(tmp) / "nope"))
            self.assertEqual(code, 2)
            self.assertIn("no log.md", err)


if __name__ == "__main__":
    unittest.main()
