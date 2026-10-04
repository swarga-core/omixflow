"""Tests for sync.py: base drift of a task branch (port workspace, capability sync)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CFG = ("version: 1\ntracker: none\nforge: none\nlang: [ts]\n"
       "workspace: {{base: main, branch: 'task/{{id}}'{extra}}}\nverify: {{test: 'true'}}\n")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "sync.py"), *args], capture_output=True, text=True)


class SyncCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.write_cfg("")
        self.commit_file("src/a.py", "a = 1\n", "init")
        git(self.root, "checkout", "-q", "-b", "task/T-1")
        self.task = self.root / ".tasks" / "T-1"
        subprocess.run([sys.executable, str(SCRIPTS / "state.py"), "init", str(self.task), "--id", "T-1",
                        "--kind", "task", "--base", "main", "--branch", "task/T-1"], check=True,
                       capture_output=True)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "start: artifacts")

    def tearDown(self):
        self.tmp.cleanup()

    def write_cfg(self, extra: str) -> None:
        path = self.root / ".claude" / "omixflow" / "flow.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CFG.format(extra=extra), encoding="utf-8")

    def commit_file(self, rel: str, text: str, msg: str) -> str:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)
        return git(self.root, "rev-parse", "HEAD")

    def advance_main(self) -> str:
        git(self.root, "checkout", "-q", "main")
        sha = self.commit_file("src/b.py", "b = 1\n", "neighbour merged")
        git(self.root, "checkout", "-q", "task/T-1")
        return sha

    def check(self, *extra: str) -> dict:
        proc = run("check", str(self.task), *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_not_moved(self):
        info = self.check()
        self.assertEqual((info["moved"], info["behind"], info["ahead"]), (False, 0, 1))
        self.assertEqual(info["ref"], "refs/heads/main")
        self.assertFalse(info["code_changed"])

    def test_artifacts_only_branch_rebases(self):
        head = self.advance_main()
        info = self.check()
        self.assertEqual((info["moved"], info["behind"], info["base_head"]), (True, 1, head))
        self.assertEqual((info["code_changed"], info["strategy"]), (False, "rebase"))

    def test_base_moved_in_artifacts_only_needs_no_sync(self):
        git(self.root, "checkout", "-q", "main")
        self.commit_file(".tasks/backlog/x.md", "status: done\n", "lead: tracker local")
        git(self.root, "checkout", "-q", "task/T-1")
        info = self.check()
        self.assertEqual((info["behind"], info["moved"], info["moved_artifacts_only"]), (1, False, True))
        self.advance_main()
        info = self.check()
        self.assertEqual((info["moved"], info["moved_artifacts_only"], info["base_code_files"]),
                         (True, False, ["src/b.py"]))

    def test_branch_with_code_merges(self):
        self.commit_file("src/a.py", "a = 2\n", "step 1")
        self.advance_main()
        info = self.check()
        self.assertEqual((info["code_changed"], info["strategy"], info["code_files"]), (True, "merge", ["src/a.py"]))

    def test_configured_mode_wins(self):
        self.write_cfg(", sync: merge")
        git(self.root, "commit", "-q", "-am", "cfg")
        self.advance_main()
        info = self.check()
        self.assertEqual((info["mode"], info["strategy"]), ("merge", "merge"))
        self.assertTrue(info["code_changed"], "flow.yaml lies outside the artifacts directory")

    def test_remote_base_when_no_local_branch(self):
        origin = Path(self.tmp.name) / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.root), str(origin)], check=True)
        git(self.root, "remote", "add", "origin", str(origin))
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "branch", "-D", "main")
        self.assertEqual(self.check()["ref"], "refs/remotes/origin/main")

    def test_dirty_tree_and_missing_base(self):
        (self.root / "src" / "a.py").write_text("dirty\n", encoding="utf-8")
        self.assertTrue(self.check()["dirty"])
        proc = run("check", str(self.task), "--ref", "nope")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("не найдена", proc.stderr)

    def test_bad_mode_rejected(self):
        self.write_cfg(", sync: sometimes")
        proc = run("check", str(self.task))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("workspace.sync", proc.stderr)

    def test_record_appends_syncs(self):
        self.assertEqual(run("record", str(self.task), "--how", "merge", "--base-sha", "abc",
                             "--commit", "def").stdout.strip(), "1")
        self.assertEqual(run("record", str(self.task), "--how", "rebase", "--base-sha", "123",
                             "--commit", "456").stdout.strip(), "2")
        state = json.loads(subprocess.run([sys.executable, str(SCRIPTS / "state.py"), "get", str(self.task)],
                                          capture_output=True, text=True).stdout)
        self.assertEqual([(s["how"], s["base_sha"], s["commit"]) for s in state["syncs"]],
                         [("merge", "abc", "def"), ("rebase", "123", "456")])
        self.assertEqual(run("record", str(self.task), "--how", "squash", "--base-sha", "a",
                             "--commit", "b").returncode, 2)


if __name__ == "__main__":
    unittest.main()
