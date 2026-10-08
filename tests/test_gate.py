"""Tests for gate.py: long gates detached from the caller, waited for in short polls."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "gate.py"), *args], capture_output=True, text=True)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.r = str(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, name: str, *command: str) -> subprocess.CompletedProcess:
        return run("start", name, "--root", self.r, "--", *command)

    def poll(self, name: str, timeout: str = "20") -> subprocess.CompletedProcess:
        return run("poll", name, "--root", self.r, "--timeout", timeout)

    def test_shell_line_runs_in_root_and_reports_exit_code_and_tail(self):
        self.assertEqual(self.start("t", "pwd && echo two; exit 5").returncode, 0)
        res = self.poll("t")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        self.assertTrue(lines[0].startswith("EXIT 5"), lines)
        self.assertEqual(Path(lines[1]).resolve(), self.root.resolve())
        self.assertEqual(lines[2], "two")

    def test_output_lives_in_the_git_dir_not_in_the_tree(self):
        self.start("t", "echo hi")
        self.poll("t")
        self.assertTrue((self.root / ".git" / "omixflow-gates" / "t.log").exists())
        status = subprocess.run(["git", "-C", self.r, "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "")

    def test_poll_reports_running_and_is_repeated_until_exit(self):
        self.start("slow", "sleep 2; echo done")
        first = self.poll("slow", timeout="0.3")
        self.assertEqual(first.returncode, 3)
        self.assertTrue(first.stdout.startswith("RUNNING"), first.stdout)
        second = self.poll("slow")
        self.assertEqual(second.returncode, 0)
        self.assertIn("EXIT 0", second.stdout)
        self.assertIn("done", second.stdout)

    def test_argv_form_keeps_inner_double_dash(self):
        self.start("argv", sys.executable, "-c", "import sys; print(sys.argv[1:])", "--", "x")
        res = self.poll("argv")
        self.assertIn("['--', 'x']", res.stdout)

    def test_restart_discards_the_previous_exit_code(self):
        self.start("t", "exit 1")
        self.poll("t")
        self.start("t", "sleep 2")
        self.assertEqual(self.poll("t", timeout="0.3").returncode, 3)

    def test_restart_while_running_kills_the_old_run_and_keeps_its_code_out(self):
        self.start("t", "echo OLD-RUN; sleep 1; exit 7")
        self.start("t", "sleep 2; echo NEW-RUN; exit 0")
        res = self.poll("t")
        self.assertEqual(res.returncode, 0)
        self.assertIn("EXIT 0", res.stdout)
        self.assertIn("NEW-RUN", res.stdout)
        self.assertNotIn("OLD-RUN", res.stdout)
        time.sleep(1.5)  # the old run would have finished by now
        self.assertIn("EXIT 0", self.poll("t").stdout)

    def test_dead_runner_without_exit_code_is_lost(self):
        self.start("t", "sleep 30")
        pid = int((self.root / ".git" / "omixflow-gates" / "t.pid").read_text().split()[0])
        os.killpg(pid, signal.SIGKILL)
        time.sleep(0.3)
        res = self.poll("t", timeout="5")
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertTrue(res.stdout.startswith("LOST"), res.stdout)

    def test_errors(self):
        self.assertEqual(self.poll("never").returncode, 2)
        self.assertEqual(self.start("bad/name", "true").returncode, 2)
        self.assertEqual(run("start", "t", "--root", self.r).returncode, 2)
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(run("start", "t", "--root", plain, "--", "true").returncode, 2)


if __name__ == "__main__":
    unittest.main()
