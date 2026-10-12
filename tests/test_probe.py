"""Tests for probe.py: a mutation probe of a test in one call — baseline, mutate, run,
restore, verify."""
from __future__ import annotations

import contextlib
import io
import json
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
sys.path.insert(0, str(SCRIPTS))
import probe  # noqa: E402

SOURCE = "def add(a, b):\n    return a + b\n"
TEST = "import sys\nsys.path.insert(0, sys.argv[1])\nfrom mod import add\nassert add(2, 3) == 5\nprint('ok')\n"
WEAK = "import sys\nsys.path.insert(0, sys.argv[1])\nfrom mod import add\nadd(2, 3)\nprint('ok')\n"


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = probe.main(list(args))
    return code, out.getvalue(), err.getvalue()


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / "mod.py").write_text("def add(a, b):\n    return 0\n")
        (self.root / "other.py").write_text("X = 1\n")
        self.git("add", "mod.py", "other.py")
        self.git("commit", "-q", "-m", "base")
        (self.root / "mod.py").write_text(SOURCE)                 # the step's uncommitted change
        (self.root / "test_add.py").write_text(TEST)
        self.cmd = f"{sys.executable} test_add.py {self.root}"

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def diff(self) -> str:
        return self.git("diff", "--", "mod.py")

    def probe_run(self, *extra: str, old: str = "return a + b", new: str = "return a - b") -> tuple[int, str, str]:
        return run("run", "--root", str(self.root), "--test", "test_add", "--file", "mod.py", "--cmd", self.cmd,
                   "--replace", old, "--with", new, *extra)

    def assert_clean(self):
        self.assertEqual((self.root / "mod.py").read_text(), SOURCE)
        self.assertFalse((self.root / "mod.py.orig").exists())
        self.assertEqual((self.root / "other.py").read_text(), "X = 1\n")

    # ------------------------------------------------------------------ outcomes

    def test_a_caught_mutant_is_red_and_the_file_is_restored_with_a_fresh_mtime(self):
        # `a - b` has the size of `a + b` and lands within the same second as the baseline's
        # __pycache__ entry: Python would run the original unless the mutant's mtime moves.
        before = self.diff()
        old_mtime = os.stat(self.root / "mod.py").st_mtime
        code, out, _ = self.probe_run()
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip().splitlines()[-1], "- test_add ← mod.py: 'return a + b' → 'return a - b' → RED")
        self.assert_clean()
        self.assertEqual(self.diff(), before)
        pyc = next((self.root / "__pycache__").glob("mod.*.pyc"))          # the mutant's build output
        restored = os.stat(self.root / "mod.py").st_mtime
        self.assertGreater(restored, os.stat(pyc).st_mtime)                 # MEW-6: newer than it
        self.assertGreater(restored, old_mtime)
        self.assertGreater(restored, time.time())      # dated ahead, not plain "now": the restore is the last action

    def test_a_build_that_rebuilds_only_a_newer_source_sees_the_mutant_and_the_restore(self):
        """make, MSBuild, tsc -b: an earlier draft dated the mutant into the past, and every
        such build kept the original — a false GREEN on each probe (finding 34)."""
        build = ("import os, sys, shutil\n"
                 "src, out = sys.argv[1] + '/mod.py', sys.argv[1] + '/built.py'\n"
                 "if not os.path.exists(out) or os.stat(src).st_mtime > os.stat(out).st_mtime:\n"
                 "    shutil.copyfile(src, out)\n"
                 "    os.utime(out, None)\n"
                 "sys.path.insert(0, sys.argv[1])\n"
                 "import built\n"
                 "assert built.add(2, 3) == 5\n")
        (self.root / "test_build.py").write_text(build)
        cmd = f"{sys.executable} -B test_build.py {self.root}"
        run_probe = lambda: run("run", "--root", str(self.root), "--test", "t", "--file", "mod.py", "--cmd", cmd,  # noqa: E731
                                "--replace", "return a + b", "--with", "return a - b")
        code, out, _ = run_probe()
        self.assertEqual(code, 0, out)       # the build picked the mutant up
        self.assertIn("→ RED", out)
        built = self.root / "built.py"       # holds the mutant until the next build, which the restore must trigger
        self.assertGreater(os.stat(self.root / "mod.py").st_mtime, os.stat(built).st_mtime)
        code, out, _ = run_probe()           # the second probe's baseline rebuilds the original and is green
        self.assertEqual(code, 0, out)
        self.assertNotIn("PROBE NOT RUN", out)

    def test_a_missed_mutant_is_green_with_exit_1(self):
        (self.root / "test_add.py").write_text(WEAK)
        code, out, _ = self.probe_run()
        self.assertEqual(code, 1, out)
        self.assertIn("→ GREEN (false-green", out)
        self.assert_clean()

    def test_a_mutant_that_fails_the_check_is_no_probe_and_a_passing_check_lets_the_test_run(self):
        check = f"{sys.executable} -m py_compile mod.py"
        code, out, _ = self.probe_run("--check", check, new="return a +")
        self.assertEqual(code, 3, out)
        self.assertIn("- test_add — no probe possible: the mutant does not pass --check", out)
        self.assert_clean()
        code, out, _ = self.probe_run("--check", check)
        self.assertEqual(code, 0, out)
        self.assertIn("→ RED", out)

    def test_an_endless_mutant_times_out_as_red(self):
        code, out, _ = self.probe_run("--timeout", "1", new="import time; time.sleep(30); return a + b")
        self.assertEqual(code, 0, out)
        self.assertIn("timed out after 1 s", out)
        self.assertIn("→ RED", out)
        self.assert_clean()

    # ------------------------------------------------------------------ not run (input errors)

    def test_a_red_baseline_is_not_a_probe(self):
        code, out, _ = run("run", "--root", str(self.root), "--test", "t", "--file", "mod.py",
                           "--cmd", f"{sys.executable} test_addd.py {self.root}",     # a typo: never green
                           "--replace", "return a + b", "--with", "x")
        self.assertEqual(code, 2, out)
        self.assertIn("PROBE NOT RUN: t — the test is not green without the mutant", out)
        self.assertIn("No such file", out)       # the baseline's tail explains why
        self.assert_clean()
        code, out, _ = run("run", "--root", str(self.root), "--test", "t", "--file", "mod.py",
                           "--cmd", f"{sys.executable} test_addd.py {self.root}", "--no-baseline",
                           "--replace", "return a + b", "--with", "return a - b")
        self.assertEqual(code, 0, out)      # --no-baseline: the agent vouches for the command

    def test_an_ambiguous_or_missing_old_text_is_not_run_and_leaves_the_tree_as_it_was(self):
        for old in ("a", "nothing here"):          # "a" occurs several times, the other never
            code, out, _ = self.probe_run(old=old, new="x")
            self.assertEqual(code, 2, out)
            self.assertIn("PROBE NOT RUN", out)
            self.assertNotIn("no probe possible", out)
            self.assert_clean()

    def test_a_patch_may_touch_only_the_probed_file(self):
        good = self.root / "good.diff"
        good.write_text("--- a/mod.py\n+++ b/mod.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a + b\n+    return a * b\n")
        bad = self.root / "bad.diff"
        bad.write_text("--- a/mod.py\n+++ b/mod.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a + b\n+    return a * b\n"
                       "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-X = 1\n+X = 2\n")
        code, out, _ = run("run", "--root", str(self.root), "--test", "test_add", "--file", "mod.py", "--cmd", self.cmd,
                           "--patch", "bad.diff")
        self.assertEqual(code, 2, out)
        self.assertIn("the patch touches ['mod.py', 'other.py']", out)
        self.assert_clean()
        code, out, _ = run("run", "--root", str(self.root), "--test", "test_add", "--file", "mod.py", "--cmd", self.cmd,
                           "--patch", "good.diff", "--json")
        self.assertEqual(code, 0, out)
        r = json.loads(out.strip().splitlines()[-1])
        self.assertEqual((r["outcome"], r["restored"], r["mutation"]), ("RED", True, "patch good.diff"))
        self.assert_clean()

    def test_a_failed_rebuild_or_a_broken_restore_is_reported_as_not_run(self):
        code, out, _ = self.probe_run("--rebuild", "false")
        self.assertEqual(code, 2, out)
        self.assertIn("--rebuild after the restore failed", out)
        self.assert_clean()
        # a command that corrupts the backup: the restore no longer matches the original
        cmd = f"echo corrupt >> mod.py.orig; {self.cmd}"
        code, out, _ = run("run", "--root", str(self.root), "--test", "t", "--file", "mod.py", "--cmd", cmd,
                           "--no-baseline", "--replace", "return a + b", "--with", "return a - b")
        self.assertEqual(code, 2, out)
        self.assertIn("differs from before the probe", out)

    def test_a_leftover_copy_blocks_the_probe_and_restore_puts_the_file_back(self):
        (self.root / "mod.py.orig").write_text(SOURCE)
        (self.root / "mod.py").write_text("mutant")
        code, out, _ = self.probe_run()
        self.assertEqual(code, 2, out)
        self.assertIn("probe.py restore", out)
        self.assertEqual((self.root / "mod.py").read_text(), "mutant")
        code, out, _ = run("restore", "--root", str(self.root), "--file", "mod.py")
        self.assertEqual(code, 0, out)
        self.assert_clean()

    def test_sigterm_restores_the_file_and_kills_the_test_process(self):
        """A Bash timeout: the file comes back, the endless mutant's process dies with it, and
        the exit code is 128+15 — never 1, the GREEN code (finding 35)."""
        marker = self.root / "child.pid"
        cmd = f"sh -c 'echo $$ > {marker}; sleep 30'"
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "probe.py"), "run", "--root", str(self.root),
                                 "--test", "t", "--file", "mod.py", "--cmd", cmd, "--no-baseline",
                                 "--replace", "return a + b", "--with", "return a - b"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (marker.exists() and marker.read_text().strip()):
            time.sleep(0.05)
        time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM, err)
        self.assertNotIn("Traceback", err.decode())
        self.assertEqual(out, b"")
        # a batch killed after its first probe keeps that probe's line (finding 43)
        (self.root / "probes.json").write_text(json.dumps([
            {"test": "first", "file": "mod.py", "cmd": self.cmd, "replace": "return a + b", "with": "return a - b"},
            {"test": "endless", "file": "mod.py", "cmd": cmd, "replace": "return a + b", "with": "return a - b"}]))
        marker.unlink()
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "probe.py"), "batch", "--root", str(self.root),
                                 "--spec", "probes.json", "--no-baseline"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (marker.exists() and marker.read_text().strip()):
            time.sleep(0.05)
        time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM)
        self.assertIn("- first ← mod.py: 'return a + b' → 'return a - b' → RED", out.decode())
        self.assert_clean()
        child = int(marker.read_text())
        time.sleep(0.3)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    # ------------------------------------------------------------------ text handling

    def test_escapes_and_line_endings(self):
        code, out, _ = self.probe_run(old="def add(a, b):\\n    return a + b", new="def add(a, b):\\n    return a - b")
        self.assertEqual(code, 0, out)
        self.assert_clean()
        (self.root / "mod.py").write_bytes(b"def add(a, b):\r\n    return a + b  # x\\n\r\n")
        (self.root / "test_add.py").write_text(TEST)
        code, out, _ = self.probe_run("--json", old="# x\\\\n", new="# y")     # a literal backslash-n in the code
        self.assertEqual(code, 1, out)                                           # a comment mutant: GREEN
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["mutation"], "mod.py: '# x\\\\n' → '# y'")
        self.assertEqual((self.root / "mod.py").read_bytes(), b"def add(a, b):\r\n    return a + b  # x\\n\r\n")

    # ------------------------------------------------------------------ batch

    def test_batch_checks_the_spec_first_then_runs_every_probe_and_rebuilds_once(self):
        (self.root / "test_weak.py").write_text(WEAK)
        marker = self.root / "rebuilds.log"
        spec = self.root / "probes.json"
        spec.write_text(json.dumps([
            {"test": "test_add", "file": "mod.py", "cmd": self.cmd, "replace": "return a + b", "with": "return a - b"},
            {"test": "broken", "file": "mod.py", "cmd": self.cmd, "replace": "zzz", "with": "y"},
            {"test": "test_weak", "file": "mod.py", "cmd": f"{sys.executable} test_weak.py {self.root}",
             "replace": "return a + b", "with": "return 0"},
        ]))
        code, out, err = run("batch", "--root", str(self.root), "--spec", "probes.json", "--rebuild", f"echo run >> {marker}")
        self.assertEqual(code, 1, out + err)         # GREEN is never hidden by a probe that was not run
        lines = out.splitlines()
        self.assertEqual([l for l in lines if l.startswith("- ") or l.startswith("PROBE NOT RUN")],
                         ["- test_add ← mod.py: 'return a + b' → 'return a - b' → RED",
                          "PROBE NOT RUN: broken — OLD occurs 0 times in mod.py, needs exactly 1: b'zzz'",
                          "- test_weak ← mod.py: 'return a + b' → 'return 0' → GREEN (false-green: strengthen the test and probe again)"])
        self.assertEqual(lines.count("ok"), 1)          # the GREEN probe's tail; a RED tail is not printed
        self.assertNotIn("AssertionError", out)
        self.assertIn("probes: 3, RED 1, GREEN 1, no probe 0, not run 1", err)
        self.assertEqual(marker.read_text().count("run"), 1)   # once, after the probes
        self.assert_clean()
        # a malformed spec runs nothing
        spec.write_text(json.dumps([{"test": "a", "file": "mod.py", "cmd": self.cmd, "replace": "return a + b", "with": "x"},
                                    {"test": "b", "file": "mod.py"}]))
        marker.unlink()
        code, out, err = run("batch", "--root", str(self.root), "--spec", "probes.json", "--rebuild", f"echo run >> {marker}")
        self.assertEqual(code, 2)
        self.assertNotIn("- a", out)
        self.assertFalse(marker.exists())
        code, _, _ = run("batch", "--root", str(self.root), "--spec", "missing.json")
        self.assertEqual(code, 2)

    def test_every_not_run_message_carries_a_phrase_report_py_recognises(self):
        """report.py bounces a `no probe possible` line that quotes one of these; the phrases
        must therefore stay in the messages (finding 39)."""
        cases = [self.probe_run(old="nothing", new="x"), self.probe_run(old="a", new="x"),
                 self.probe_run("--rebuild", "false")]
        (self.root / "mod.py.orig").write_text(SOURCE)
        cases.append(self.probe_run())
        (self.root / "mod.py.orig").unlink()
        cases.append(run("run", "--root", str(self.root), "--test", "t", "--file", "nope.py", "--cmd", self.cmd,
                         "--replace", "a", "--with", "b"))
        cases.append(run("run", "--root", str(self.root), "--test", "t", "--file", "mod.py",
                         "--cmd", f"{sys.executable} test_addd.py {self.root}", "--replace", "a", "--with", "b"))
        for code, out, _ in cases:
            self.assertEqual(code, 2, out)
            line = [l for l in out.splitlines() if l.startswith("PROBE NOT RUN")][-1]
            self.assertTrue(any(p in line for p in probe.NOT_RUN_PHRASES), line)
        self.assert_clean()

    def test_batch_runs_the_baseline_of_a_command_once(self):
        log = self.root / "runs.log"
        cmd = f"echo run >> {log}; {self.cmd}"
        (self.root / "probes.json").write_text(json.dumps([
            {"test": "t1", "file": "mod.py", "cmd": cmd, "replace": "return a + b", "with": "return a - b"},
            {"test": "t2", "file": "mod.py", "cmd": cmd, "replace": "return a + b", "with": "return a * b"},
        ]))
        code, out, _ = run("batch", "--root", str(self.root), "--spec", "probes.json")
        self.assertEqual(code, 0, out)
        self.assertEqual(log.read_text().count("run"), 3)    # one baseline, two mutants


if __name__ == "__main__":
    unittest.main()
