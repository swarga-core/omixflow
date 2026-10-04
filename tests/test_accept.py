"""Tests for accept.py: git side of the lead's merge acceptance."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "accept.py"), *args], capture_output=True, text=True)


class AcceptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@t")
        self.write("src/a.py", "a = 1\n")
        self.commit("init")
        git(self.root, "branch", "task/T-1")
        self.task_tree = self.root / ".claude" / "worktrees" / "T-1"
        git(self.root, "worktree", "add", "-q", str(self.task_tree), "task/T-1")
        self.write("src/a.py", "a = 2\n", tree=self.task_tree)
        self.write("src/new.py", "n = 1\n", tree=self.task_tree)
        self.commit("step 1", tree=self.task_tree)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str, tree: Path = None) -> None:
        path = (tree or self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, msg: str, tree: Path = None) -> None:
        git(tree or self.root, "add", "-A")
        git(tree or self.root, "commit", "-q", "-m", msg)

    def plan(self) -> dict:
        proc = run("plan", "task/T-1", "--into", "main", "--project", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_plan_uses_tree_where_into_is_checked_out(self):
        info = self.plan()
        self.assertEqual(Path(info["tree"]).resolve(), self.root.resolve())
        self.assertTrue(info["tree_clean"])
        self.assertIsNone(info["temp"])
        self.assertEqual((info["synced"], info["into_ahead"]), (True, 0))
        self.assertEqual(info["files"], ["src/a.py", "src/new.py"])

    def test_plan_synced_when_into_moved_in_artifacts_only(self):
        self.write(".tasks/backlog/x.md", "status: done\n")
        git(self.root, "add", ".tasks/backlog/x.md")
        git(self.root, "commit", "-q", "-m", "lead: tracker local")
        info = self.plan()
        self.assertEqual((info["synced"], info["into_ahead"], info["into_code_files"]), (True, 1, []))

    def test_plan_reports_moved_into_and_dirty_tree(self):
        self.write("src/b.py", "b = 1\n")
        self.commit("neighbour")
        self.write("src/b.py", "dirty\n")
        info = self.plan()
        self.assertEqual((info["synced"], info["into_ahead"], info["tree_clean"]), (False, 1, False))

    def test_merge_commit_happy_path(self):
        proc = run("merge", "task/T-1", "--tree", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout),
                         {"status": "staged", "files": ["src/a.py", "src/new.py"], "already_in_into": []})
        proc = run("commit", "--tree", str(self.root), "--message", "feat(T-1): x")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), git(self.root, "rev-parse", "--short", "HEAD"))
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "feat(T-1): x")
        self.assertEqual((self.root / "src" / "a.py").read_text(encoding="utf-8"), "a = 2\n")

    def test_conflict_resets_tree(self):
        self.write("src/a.py", "a = 3\n")
        self.commit("neighbour changed a")
        head = git(self.root, "rev-parse", "HEAD")
        proc = run("merge", "task/T-1", "--tree", str(self.root))
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"status": "conflict", "conflicts": ["src/a.py"]})
        self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=no"), "")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)

    def test_dirty_tree_refused_and_commit_needs_staged(self):
        self.write("src/a.py", "dirty\n")
        proc = run("merge", "task/T-1", "--tree", str(self.root))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("не чистое", proc.stderr)
        git(self.root, "checkout", "--", "src/a.py")
        proc = run("commit", "--tree", str(self.root), "--message", "x")
        self.assertEqual(proc.returncode, 2)

    def test_abort_resets_staged_squash(self):
        run("merge", "task/T-1", "--tree", str(self.root))
        self.assertEqual(run("abort", "--tree", str(self.root)).returncode, 0)
        self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=no"), "")

    def test_identical_change_on_into_is_listed_not_fatal(self):
        """A file INTO already has identically is not staged: benign, listed, not a stop."""
        self.write("src/shared.py", "s = 1\n", tree=self.task_tree)
        self.commit("task adds shared", tree=self.task_tree)
        self.write("src/shared.py", "s = 1\n")
        self.commit("neighbour adds the same shared")
        proc = run("merge", "task/T-1", "--tree", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual((result["status"], result["already_in_into"]), ("staged", ["src/shared.py"]))

    def test_temp_worktree_when_into_checked_out_nowhere(self):
        git(self.root, "checkout", "-q", "--detach")
        info = self.plan()
        self.assertIsNone(info["tree"])
        self.assertTrue(info["temp"].endswith(".claude/worktrees/accept-main"))
        proc = run("prepare", "--into", "main", "--path", info["temp"], "--project", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(run("merge", "task/T-1", "--tree", info["temp"]).stdout)["status"], "staged")
        run("commit", "--tree", info["temp"], "--message", "feat(T-1): x")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "feat(T-1): x")
        self.assertEqual(run("cleanup", "--path", info["temp"], "--project", str(self.root)).returncode, 0)
        self.assertFalse(Path(info["temp"]).exists())

    def test_retire_removes_worktree_and_branch(self):
        tip = git(self.root, "rev-parse", "--short", "task/T-1")
        proc = run("retire", "--branch", "task/T-1", "--worktree", str(self.task_tree), "--project", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["tip"], tip)
        self.assertFalse(self.task_tree.exists())
        self.assertEqual(git(self.root, "branch", "--list", "task/T-1"), "")

    def test_retire_refusals(self):
        self.write("src/a.py", "dirty\n", tree=self.task_tree)
        proc = run("retire", "--branch", "task/T-1", "--worktree", str(self.task_tree), "--project", str(self.root))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("незакоммиченные", proc.stderr)
        git(self.task_tree, "checkout", "--", "src/a.py")
        proc = run("retire", "--branch", "task/T-1", "--project", str(self.root))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("открыта", proc.stderr)
        self.write(".gitmodules", "[submodule \"x\"]\n", tree=self.task_tree)
        self.commit("submodule", tree=self.task_tree)
        proc = run("retire", "--branch", "task/T-1", "--worktree", str(self.task_tree), "--project", str(self.root))
        self.assertEqual(proc.returncode, 5)
        self.assertTrue(self.task_tree.exists())

    def test_prepare_refused_when_into_is_checked_out(self):
        proc = run("prepare", "--into", "main", "--path", str(self.root / "x"), "--project", str(self.root))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("уже открыта", proc.stderr)


if __name__ == "__main__":
    unittest.main()
