"""Tests for state.py and multitask.py."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import multitask as mt  # noqa: E402
import omixflow_lib as lib  # noqa: E402


def run(script: str, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, input=stdin)


class StateTests(unittest.TestCase):
    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / ".tasks" / "AL-1")
            self.assertEqual(run("state.py", "init", d, "--id", "AL-1", "--kind", "task",
                                 "--tier", "M", "--mode", "pipeline", "--session", "s1").returncode, 0)
            self.assertEqual(run("state.py", "next", d).stdout.strip(), "refine")
            run("state.py", "complete", d, "refine")
            run("state.py", "complete", d, "start")
            self.assertEqual(run("state.py", "next", d).stdout.strip(), "research")
            self.assertEqual(run("state.py", "get", d, "phase").stdout.strip(), "research")
            run("state.py", "set", d, "agents.coder=coder-AL-1", "steps_total=3")
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertEqual(state["agents"]["coder"], "coder-AL-1")
            self.assertEqual(state["steps_total"], 3)
            run("state.py", "step", d, "start", "1", "--total", "3")
            run("state.py", "step", d, "done", "1")
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertEqual(state["steps_done"], [1])
            self.assertEqual(state["step"], 2)
            run("state.py", "step", d, "done", "3")
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertIsNone(state["step"])
            # agents from another session are dropped
            self.assertEqual(run("state.py", "agents", d, "--session", "s2").stdout.strip(), "cleared")
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertEqual(state["agents"], {})
            # invalid values are rejected
            self.assertEqual(run("state.py", "set", d, "phase=lunch").returncode, 2)
            self.assertEqual(run("state.py", "init", d, "--id", "AL-1", "--kind", "task").returncode, 2)

    def test_part_requires_multitask_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / "p")
            self.assertEqual(run("state.py", "init", d, "--id", "AL-9/auth", "--kind", "part").returncode, 2)
            proc = run("state.py", "init", d, "--id", "AL-9/auth", "--kind", "part",
                       "--multitask-id", "AL-9", "--part", "auth")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run("state.py", "get", d, "multitask.part").stdout.strip(), "auth")


DESCRIPTION = """Описание задачи.

## Уточнённая формулировка
Текст.

<!-- omixflow:multitask:start -->
| # | part | title | depends | owner | status | branch | commit |
|---|------|-------|---------|-------|--------|--------|--------|
| 1 | auth-flow | Экран логина | — | swarga | done | task/AL-9-auth-flow | a1b2c3d |
| 2 | i18n-keys | Словарь | — | — | pending | — | — |
| 3 | profile-store | Стор профиля | auth-flow | ivanov | in-work | task/AL-9-profile-store | — |
| 4 | cabinet-ui | Кабинет | profile-store, i18n-keys | — | pending | — | — |
<!-- omixflow:multitask:end -->
"""


class MultitaskTests(unittest.TestCase):
    def test_extract_and_validate(self):
        rows = mt.extract(DESCRIPTION)
        self.assertEqual([r["part"] for r in rows], ["auth-flow", "i18n-keys", "profile-store", "cabinet-ui"])
        self.assertEqual(rows[3]["depends"], ["profile-store", "i18n-keys"])
        self.assertEqual(rows[0]["owner"], "swarga")
        self.assertIsNone(rows[1]["owner"])
        self.assertEqual(mt.validate(rows), [])

    def test_waves_and_ready(self):
        rows = mt.extract(DESCRIPTION)
        self.assertEqual(mt.waves(rows), [["auth-flow", "i18n-keys"], ["profile-store"], ["cabinet-ui"]])
        r = mt.ready(rows, owner="ivanov")
        self.assertEqual(r["ready"], ["i18n-keys"])
        self.assertEqual(r["mine_active"], ["profile-store"])
        self.assertFalse(r["all_terminal"])

    def test_cycle_and_missing_dependency(self):
        rows = mt.extract(DESCRIPTION)
        rows[0]["depends"] = ["cabinet-ui"]
        errors = mt.validate(rows)
        self.assertTrue(any("цикл" in e for e in errors), errors)
        rows = mt.extract(DESCRIPTION)
        rows[1]["depends"] = ["ghost"]
        self.assertTrue(any("не существует" in e for e in mt.validate(rows)))

    def test_empty_depends_cell_is_an_error(self):
        text = DESCRIPTION.replace("| 2 | i18n-keys | Словарь | — |", "| 2 | i18n-keys | Словарь |  |")
        rows = mt.extract(text)
        self.assertTrue(any("depends пуста" in e for e in mt.validate(rows)))

    def test_active_without_owner_is_an_error(self):
        text = DESCRIPTION.replace("| ivanov | in-work |", "| — | in-work |")
        self.assertTrue(any("без owner" in e for e in mt.validate(mt.extract(text))))

    def test_skipped_dependency_blocks(self):
        text = DESCRIPTION.replace("| swarga | done |", "| swarga | skipped |")
        rows = mt.extract(text)
        r = mt.ready(rows)
        self.assertIn("profile-store", [x["part"] for x in r["active"]])
        rows[2]["status"] = "pending"; rows[2]["owner"] = None
        r = mt.ready(rows)
        self.assertEqual(r["blocked_by_skipped_dependency"], ["profile-store"])

    def test_set_replaces_block_and_keeps_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.md"
            f.write_text(DESCRIPTION, encoding="utf-8")
            proc = run("multitask.py", "set", "--from", str(f), "--part", "i18n-keys",
                       "status=in-work", "owner=swarga", "branch=task/AL-9-i18n-keys")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = proc.stdout
            self.assertTrue(out.startswith("Описание задачи."))
            self.assertIn("## Уточнённая формулировка", out)
            rows = mt.extract(out)
            self.assertEqual(rows[1]["status"], "in-work")
            self.assertEqual(rows[1]["owner"], "swarga")
            self.assertEqual(rows[1]["branch"], "task/AL-9-i18n-keys")
            # unknown column and bad status are rejected
            self.assertEqual(run("multitask.py", "set", "--from", str(f), "--part", "i18n-keys", "n=9").returncode, 2)
            self.assertEqual(run("multitask.py", "set", "--from", str(f), "--part", "i18n-keys", "status=maybe").returncode, 2)

    def test_seed_appends_block_to_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.md"
            f.write_text("Описание без блока.\n", encoding="utf-8")
            proc = run("multitask.py", "seed", "--from", str(f),
                       "--parts", "Auth Flow — Экран логина", "profile-store — Стор",
                       "--depends", "—", "auth-flow")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rows = mt.extract(proc.stdout)
            self.assertEqual([r["part"] for r in rows], ["auth-flow", "profile-store"])
            self.assertEqual(rows[1]["depends"], ["auth-flow"])
            self.assertTrue(all(r["status"] == "pending" for r in rows))
            # seeding twice is refused
            f.write_text(proc.stdout, encoding="utf-8")
            self.assertEqual(run("multitask.py", "seed", "--from", str(f), "--parts", "x — y").returncode, 2)

    def test_file_skeleton_and_cli_waves(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.md"
            f.write_text(DESCRIPTION, encoding="utf-8")
            proc = run("multitask.py", "file", "--from", str(f), "--id", "AL-9", "--title", "Кабинет")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("### cabinet-ui — Кабинет", proc.stdout)
            self.assertIn("Волна 3: cabinet-ui ← profile-store, i18n-keys", proc.stdout)
            self.assertEqual(run("multitask.py", "validate", "--from", str(f)).returncode, 0)
            self.assertEqual(run("multitask.py", "has", "--from", str(f)).returncode, 0)
            self.assertEqual(run("multitask.py", "has", stdin="no block").returncode, 1)


if __name__ == "__main__":
    unittest.main()
