"""Tests for adapter scripts: forge/github/pr.py pure logic, tracker/local index."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "ts-youtrack"
sys.path.insert(0, str(ROOT / "scripts"))
import omixflow_lib as lib  # noqa: E402


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


pr = load(ROOT / "adapters" / "forge" / "github" / "pr.py", "gh_pr")


class PrScriptTests(unittest.TestCase):
    def test_parse_pr_ref(self):
        self.assertEqual(pr.parse_pr_ref("https://github.com/acme/app/pull/42"), ("acme", "app", 42))
        self.assertEqual(pr.parse_pr_ref("#7", remote=("acme", "app")), ("acme", "app", 7))
        with self.assertRaises(pr.GhError):
            pr.parse_pr_ref("feature-branch", remote=("acme", "app"))

    def test_real_reviews_ignore_reply_phantoms(self):
        reviews = [
            {"id": 1, "user": {"login": "me"}, "state": "CHANGES_REQUESTED", "body": "round 1", "commit_id": "aaa", "submitted_at": "2026-01-01T00:00:00Z"},
            {"id": 2, "user": {"login": "me"}, "state": "COMMENTED", "body": "", "commit_id": "bbb", "submitted_at": "2026-01-02T00:00:00Z"},
            {"id": 3, "user": {"login": "me"}, "state": "COMMENTED", "body": "", "commit_id": "bbb", "submitted_at": "2026-01-02T00:01:00Z"},
            {"id": 4, "user": {"login": "other"}, "state": "APPROVED", "body": "lgtm", "commit_id": "ccc", "submitted_at": "2026-01-03T00:00:00Z"},
            {"id": 5, "user": {"login": "me"}, "state": "COMMENTED", "body": "round 2 body", "commit_id": "ddd", "submitted_at": "2026-01-04T00:00:00Z"},
            {"id": 6, "user": {"login": "me"}, "state": "APPROVED", "body": "", "commit_id": "eee", "submitted_at": "2026-01-05T00:00:00Z"},
        ]
        mine = pr.real_reviews(reviews, "me")
        self.assertEqual([r["id"] for r in mine], [1, 5, 6])
        self.assertEqual(mine[-1]["commit_id"], "eee")

    def test_valid_lines_from_patch(self):
        patch = "@@ -10,4 +10,5 @@ ctx\n ctx1\n-old\n+new1\n+new2\n ctx2\n@@ -30,2 +31,2 @@\n a\n b\n"
        self.assertEqual(pr.valid_lines_from_patch(patch), {10, 11, 12, 13, 31, 32})

    def test_parse_comments_with_nested_fences(self):
        text = (
            "### A1 — `src/a.ts`, line 12\n\n````\n**A1. Title**\n\n```ts\nconst x = 1;\n```\n\ntext\n````\n\n"
            "### B2 — `src/b.ts`, lines 5-9\n\n````\nbody\n````\n\n"
            "### B3 — `src/c.ts`, lines 7-7\n\n````\nsame\n````\n"
        )
        comments = pr.parse_comments(text)
        self.assertEqual(len(comments), 3)
        self.assertEqual(comments[0]["line"], 12)
        self.assertIn("```ts", comments[0]["body"])
        self.assertEqual(comments[1]["start_line"], 5)
        self.assertEqual(comments[1]["line"], 9)
        self.assertEqual(comments[2]["line"], 7)
        self.assertNotIn("start_line", comments[2])
        with self.assertRaises(pr.GhError):
            pr.parse_comments("### X — `f`, line 1\n\n```\nthree backticks\n```\n")

    def test_find_problems(self):
        files = [{"filename": "src/a.ts", "patch": "@@ -1,2 +1,3 @@\n a\n+b\n c\n"}]
        comments = [
            {"path": "src/a.ts", "line": 2, "body": "ok"},
            {"path": "src/a.ts", "line": 9, "body": "out"},
            {"path": "src/z.ts", "line": 1, "body": "missing"},
        ]
        problems = pr.find_problems(comments, files)
        self.assertEqual([(p["path"], p["end"]) for p in problems], [("src/a.ts", 9), ("src/z.ts", 1)])

    def test_adapter_script_resolution(self):
        path = lib.resolve_adapter_script("forge", "github", "pr", FIXTURE)
        self.assertTrue(str(path).endswith("adapters/forge/github/pr.py"))
        self.assertIsNone(lib.resolve_adapter_script("forge", "none", "pr", FIXTURE))
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "resolve.py"), "adapter-script", "forge", "pr",
                               "--project", str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip().endswith("pr.py"))


class BacklogIndexTests(unittest.TestCase):
    def test_index_generation_and_check(self):
        script = ROOT / "adapters" / "tracker" / "local" / "backlog-index.py"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "fix-thing.md").write_text(
                "---\nid: fix-thing\ntitle: Починить\nstatus: draft\ntype: bug\ntarget: lib\norigin: AL-1\n---\nтело\n",
                encoding="utf-8")
            (d / "notes.md").write_text("no frontmatter\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(script), "--dir", str(d)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            readme = (d / "README.md").read_text(encoding="utf-8")
            self.assertIn("[fix-thing](fix-thing.md)", readme)
            self.assertIn("| Починить | draft | bug | lib | AL-1 | — |", readme)
            self.assertNotIn("notes.md", readme)
            self.assertEqual(subprocess.run([sys.executable, str(script), "--dir", str(d), "--check"],
                                            capture_output=True, text=True).returncode, 0)
            (d / "fix-thing.md").write_text((d / "fix-thing.md").read_text(encoding="utf-8").replace("draft", "done"), encoding="utf-8")
            self.assertEqual(subprocess.run([sys.executable, str(script), "--dir", str(d), "--check"],
                                            capture_output=True, text=True).returncode, 1)


if __name__ == "__main__":
    unittest.main()
