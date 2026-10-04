"""Tests for lead.py: the lead journal (protocol/lead.md, «Журнал»)."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lead  # noqa: E402


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Path(self.tmp.name) / "lead" / ".tasks" / "_lead" / "journal.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lead.main(["--journal", str(self.journal), *args])
        return code, out.getvalue().strip(), err.getvalue().strip()

    def ok(self, *args: str) -> str:
        code, out, err = self.call(*args)
        self.assertEqual(code, 0, err)
        return out

    def decide(self, task="AL-1", q="1", item="Q1", by="lead") -> str:
        return self.ok("decide", "--task", task, "--q", q, "--item", item, "--point", "design-question",
                       "--choice", "b", "--basis", "суждение", "--by", by)

    def records(self, *filters: str) -> list:
        return json.loads(self.ok("list", *filters))

    def test_ids_are_sequential_per_type(self):
        self.assertEqual(self.decide(), "D-1")
        self.assertEqual(self.decide(item="Q2"), "D-2")
        self.assertEqual(self.ok("escalate", "--task", "AL-1", "--q", "1", "--item", "F3",
                                 "--point", "finding", "--summary", "граница модуля"), "E-1")
        self.assertEqual(self.ok("rule", "--text", "UI-тексты из словаря", "--task", "AL-1",
                                 "--decision", "D-1"), "R-1")
        self.assertEqual(self.ok("oblige", "--trigger", "мерж AL-2", "--action", "сообщить AL-3"), "O-1")
        self.assertEqual(self.decide(), "D-3")
        lines = self.journal.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 6)
        self.assertTrue(all(json.loads(line)["ts"] for line in lines))

    def test_escalation_resolve_and_open_filter(self):
        self.ok("escalate", "--task", "AL-1", "--q", "2", "--item", "F3", "--point", "finding",
                "--summary", "x")
        self.ok("escalate", "--task", "AL-2", "--q", "1", "--item", "P1", "--point", "tracker.comment",
                "--summary", "y")
        d = self.decide(q="2", item="F3")
        self.assertEqual(self.ok("resolve", "E-1", "--answer", "принять, но без миграции",
                                 "--decision", d), "E-1")
        open_esc = self.records("--type", "escalation", "--open")
        self.assertEqual([r["id"] for r in open_esc], ["E-2"])
        closed = self.records("--type", "escalation", "--task", "AL-1")[0]
        self.assertEqual(closed["resolved"]["answer"], "принять, но без миграции")
        self.assertEqual(closed["resolved"]["decision"], "D-1")

    def test_replace_marks_decision_superseded(self):
        self.decide()
        local = self.decide(by="AL-1")
        self.assertEqual(self.ok("replace", "D-1", "--with", local), "D-1")
        rec = {r["id"]: r for r in self.records("--type", "decision")}
        self.assertEqual(rec["D-1"]["replaced_by"], "D-2")
        self.assertEqual(rec["D-2"]["by"], "AL-1")
        self.assertEqual([r["id"] for r in self.records("--type", "decision", "--open")], ["D-2"])

    def test_rules_obligations_and_trigger_filter(self):
        self.ok("rule", "--text", "даты в UTC", "--task", "AL-1")
        self.ok("rule-use", "R-1", "--task", "AL-4")
        rule = self.records("--type", "rule", "--task", "AL-1")[0]
        self.assertEqual(rule["uses"], [{"task": "AL-4", "decision": None}])
        self.ok("oblige", "--trigger", "мерж AL-2", "--action", "перенести V", "--task", "AL-2")
        self.ok("oblige", "--trigger", "старт AL-5", "--action", "сообщить W")
        self.assertEqual([r["id"] for r in self.records("--type", "obligation", "--trigger", "МЕРЖ")], ["O-1"])
        self.ok("fulfil", "O-1", "--note", "перенесено")
        self.assertEqual([r["id"] for r in self.records("--type", "obligation", "--open")], ["O-2"])

    def test_register_upserts_session(self):
        self.ok("register", "AL-1", "--task", "AL-1", "--phase", "refine", "--asked", "2")
        self.ok("register", "AL-1", "--asked", "3")
        self.assertEqual(self.records("--type", "session")[0]["asked"], 3)
        self.ok("register", "AL-1", "--phase", "start", "--branch", "task/AL-1",
                "--file", "src/a.ts", "--file", "src/b.ts")
        sessions = self.records("--type", "session")
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual((s["task"], s["phase"], s["branch"]), ("AL-1", "start", "task/AL-1"))
        self.assertEqual(s["files"], ["src/a.ts", "src/b.ts"])

    def test_bad_references_are_rejected_and_not_written(self):
        self.decide()
        before = self.journal.read_text(encoding="utf-8")
        for args in (("resolve", "E-9", "--answer", "x"),
                     ("replace", "D-1", "--with", "D-9"),
                     ("replace", "D-9", "--with", "D-1"),
                     ("rule", "--text", "x", "--decision", "D-9"),
                     ("rule-use", "R-1", "--task", "AL-1"),
                     ("fulfil", "O-1")):
            with self.subTest(args=args):
                code, _, err = self.call(*args)
                self.assertEqual(code, 2)
                self.assertIn("нет записи", err)
        self.assertEqual(self.journal.read_text(encoding="utf-8"), before)

    def test_double_close_is_rejected(self):
        self.ok("escalate", "--task", "AL-1", "--q", "1", "--item", "P1", "--point", "resume", "--summary", "x")
        self.ok("resolve", "E-1", "--answer", "да")
        self.assertEqual(self.call("resolve", "E-1", "--answer", "нет")[0], 2)
        self.decide()
        self.decide()
        self.ok("replace", "D-1", "--with", "D-2")
        self.assertEqual(self.call("replace", "D-1", "--with", "D-2")[0], 2)

    def test_approval_and_merge_records(self):
        self.assertEqual(self.ok("approve", "--action", "приёмка AL-1 → main", "--answer", "да, вливай",
                                 "--task", "AL-1"), "A-1")
        self.assertEqual(self.ok("accept", "--task", "AL-1", "--branch", "task/AL-1", "--into", "main",
                                 "--commit", "abc1234", "--approval", "A-1"), "M-1")
        merge = self.records("--type", "merge", "--task", "AL-1")[0]
        self.assertEqual((merge["commit"], merge["approval"]), ("abc1234", "A-1"))
        code, _, err = self.call("accept", "--task", "AL-2", "--branch", "b", "--into", "main",
                                 "--commit", "x", "--approval", "A-9")
        self.assertEqual(code, 2)
        self.assertIn("нет записи A-9", err)
        text = self.ok("show")
        self.assertIn("## Санкции", text)
        self.assertIn("M-1 AL-1: task/AL-1 → main @ abc1234 (A-1)", text)

    def test_board_renders_block_from_journal(self):
        self.ok("register", "AL-2", "--task", "AL-2", "--phase", "implement", "--branch", "task/AL-2")
        self.ok("register", "AL-1", "--task", "AL-1", "--phase", "done", "--branch", "task/AL-1")
        self.ok("escalate", "--task", "AL-2", "--q", "3", "--item", "F1", "--point", "finding", "--summary", "x")
        self.ok("approve", "--action", "приёмка AL-1", "--answer", "да")
        self.ok("accept", "--task", "AL-1", "--branch", "task/AL-1", "--into", "release/2.2.3",
                "--commit", "a1b2c3d", "--approval", "A-1")
        desc = Path(self.tmp.name) / "desc.md"
        desc.write_text("Родительская задача.\n", encoding="utf-8")
        out = self.ok("board", "--from", str(desc))
        self.assertTrue(out.startswith("Родительская задача."))
        self.assertIn("| AL-1 | AL-1 | done | task/AL-1 | M-1 a1b2c3d → release/2.2.3 | — |", out)
        self.assertIn("| AL-2 | AL-2 | implement | task/AL-2 | — | 1 |", out)
        self.assertLess(out.index("| AL-1 |"), out.index("| AL-2 |"))
        desc.write_text(out + "\n", encoding="utf-8")
        self.assertEqual(self.ok("board", "--from", str(desc)).count("omixflow:lead:start"), 1)
        local = Path(self.tmp.name) / "local.md"
        local.write_text("Описание.\n\n## Журнал\n- запись\n", encoding="utf-8")
        out = self.ok("board", "--from", str(local), "--task", "AL-2", "--before", "## Журнал")
        self.assertLess(out.index("omixflow:lead:end"), out.index("## Журнал"))
        self.assertIn("| AL-2 |", out)
        self.assertNotIn("| AL-1 |", out)

    def test_gotchas_dedup_and_route(self):
        self.assertEqual(self.ok("gotcha", "--text", "refine с tracker local пишет в основное дерево",
                                 "--task", "AL-1", "--route", "plugin", "--by", "AL-1"), "G-1")
        self.ok("gotcha-link", "G-1", "--task", "AL-2")
        self.ok("gotcha-link", "G-1", "--task", "AL-2")
        self.assertEqual(self.ok("gotcha", "--text", "doctest расходится", "--task", "AL-2"), "G-2")
        self.assertEqual([g["id"] for g in self.records("--type", "gotcha", "--open")], ["G-1", "G-2"])
        self.ok("gotcha-route", "G-1", "--route", "plugin", "--where", ".tasks/backlog/x.md")
        self.ok("gotcha-route", "G-2", "--route", "reject", "--where", "дубль известного")
        g1 = self.records("--type", "gotcha", "--task", "AL-2")[0]
        self.assertEqual((g1["tasks"], g1["routed"]["where"]), (["AL-1", "AL-2"], ".tasks/backlog/x.md"))
        self.assertEqual(self.records("--type", "gotcha", "--open"), [])
        self.assertEqual(self.call("gotcha-route", "G-1", "--route", "memory", "--where", "x")[0], 2)
        self.assertEqual(self.call("gotcha-link", "G-9", "--task", "AL-3")[0], 2)
        self.assertIn("G-1 [AL-1, AL-2] refine с tracker local пишет в основное дерево — plugin: .tasks/backlog/x.md",
                      self.ok("show"))

    def test_precedents_are_developer_decisions_only(self):
        self.ok("decide", "--task", "AL-1", "--q", "1", "--item", "P1", "--point", "statement",
                "--choice", "a", "--basis", "developer E-1 «a»")
        self.ok("decide", "--task", "AL-1", "--q", "2", "--item", "P1", "--point", "statement",
                "--choice", "b", "--basis", "суждение")
        self.ok("decide", "--task", "AL-2", "--q", "1", "--item", "P1", "--point", "statement",
                "--choice", "c", "--basis", "разработчик в сессии", "--by", "AL-2")
        self.ok("decide", "--task", "AL-2", "--q", "1", "--item", "F1", "--point", "finding",
                "--choice", "a", "--basis", "developer E-2 «a»")
        self.ok("decide", "--task", "AL-3", "--q", "1", "--item", "P1", "--point", "statement",
                "--choice", "d", "--basis", "developer E-3 «d»")
        self.ok("decide", "--task", "AL-3", "--q", "1", "--item", "P1", "--point", "statement",
                "--choice", "e", "--basis", "разработчик в сессии", "--by", "AL-3")
        self.ok("replace", "D-5", "--with", "D-6")
        self.ok("rule", "--text", "вырожденный ввод → пустая строка", "--decision", "D-1")
        found = json.loads(self.ok("precedents", "--point", "statement"))
        self.assertEqual([d["id"] for d in found["decisions"]], ["D-1", "D-3", "D-6"])
        self.assertEqual([r["id"] for r in found["rules"]], ["R-1"])

    def test_overlaps_of_active_sessions(self):
        self.ok("register", "AL-1", "--task", "AL-1", "--phase", "implement", "--file", "src/a.py", "--file", "src/b.py")
        self.ok("register", "AL-2", "--task", "AL-2", "--phase", "research", "--file", "src/b.py", "--file", "src/c.py")
        self.ok("register", "AL-3", "--task", "AL-3", "--phase", "done", "--file", "src/a.py")
        self.ok("register", "AL-4", "--task", "AL-4", "--phase", "spec", "--file", "src/z.py")
        self.assertEqual(json.loads(self.ok("overlaps")), [{"a": "AL-1", "b": "AL-2", "files": ["src/b.py"]}])
        self.assertEqual(json.loads(self.ok("overlaps", "--task", "AL-4")), [])

    def test_veto_cost_classes(self):
        cases = [
            ({"phase": "research", "completed": ["refine", "start"]}, 1, "reread"),
            ({"phase": "plan", "completed": ["refine", "start", "research", "spec"]}, 2, "restart"),
            ({"phase": "implement", "completed": ["refine", "start", "research", "spec", "plan"],
              "steps_done": []}, 2, "restart"),
            ({"phase": "implement", "completed": ["refine", "start", "research", "spec", "plan"],
              "steps_done": [1]}, 3, "iteration"),
            ({"phase": "done", "completed": ["refine", "start", "research", "spec", "plan", "implement",
                                              "review", "finalize"]}, 3, "iteration"),
        ]
        for state, klass, action in cases:
            with self.subTest(phase=state["phase"]):
                path = Path(self.tmp.name) / "state.yaml"
                path.write_text(json.dumps(state), encoding="utf-8")
                result = json.loads(self.ok("veto-cost", "--state", str(path)))
                self.assertEqual((result["class"], result["action"]), (klass, action))

    def test_show_groups_records(self):
        self.ok("register", "AL-1", "--task", "AL-1", "--phase", "research")
        self.decide()
        self.ok("escalate", "--task", "AL-1", "--q", "1", "--item", "F3", "--point", "finding", "--summary", "x")
        text = self.ok("show")
        self.assertIn("## Сессии", text)
        self.assertIn("D-1 AL-1#1 Q1 [design-question]: b — суждение", text)
        self.assertIn("E-1 AL-1#1 F3 [finding]: x — ждёт разработчика", text)

    def test_concurrent_writers_get_unique_ids(self):
        """Sessions write to one journal at once: separate processes, one lock."""
        self.journal.parent.mkdir(parents=True)

        def write(i: int) -> str:
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "lead.py"), "--journal", str(self.journal), "decide",
                 "--task", f"AL-{i}", "--q", "1", "--item", "Q1", "--point", "finding",
                 "--choice", "a", "--basis", "разработчик в сессии", "--by", f"AL-{i}"],
                capture_output=True, text=True)
            return proc.stdout.strip()

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(write, range(16)))
        self.assertEqual(sorted(ids, key=lambda x: int(x[2:])), [f"D-{n}" for n in range(1, 17)])
        self.assertEqual(len(self.journal.read_text(encoding="utf-8").splitlines()), 16)

    def test_default_journal_lives_under_artifacts_dir(self):
        project = Path(self.tmp.name) / "proj"
        (project / ".claude" / "omixflow").mkdir(parents=True)
        (project / ".claude" / "omixflow" / "flow.yaml").write_text(
            "version: 1\nartifacts: {dir: work}\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "lead.py"), "list"],
                              cwd=project, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        subprocess.run([sys.executable, str(SCRIPTS / "lead.py"), "oblige", "--trigger", "t", "--action", "a"],
                       cwd=project, capture_output=True, text=True, check=True)
        self.assertTrue((project / "work" / "_lead" / "journal.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
