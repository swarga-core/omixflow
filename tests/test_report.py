"""Tests for report.py: an agent's report against the tree and the gate logs. Fixtures follow
the shape of real reports (SwAIS T-18 step 2, T-8 fix pass 1): indented TREE STATE with a
note, GATES lines with extra text and the gate.py run, a MUTATIONS preamble before the lines."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import report  # noqa: E402

CFG = ("version: 1\ntracker: none\nforge: none\nlang: [ts]\n"
       "workspace: {base: main, branch: 'task/{id}'}\n"
       "verify:\n  typecheck: tc\n  test: tt\n  build: { cmd: bb, background: true }\n")
TEST_FILE = "import { it } from 'vitest'\nit('adds', () => {})\nit('subtracts', () => {})\n"
MUTATION_LINES = ("  - a.test.ts: adds ← M1 a.ts: `a + b` → `a - b` → RED\n"
                  "  - a.test.ts: subtracts ← M2 a.ts: `a - b` → `a + b` → RED\n")
MUTATIONS_BLOCK = ("MUTATIONS:\n  Probes by a script in SCRATCH_DIR; checksums matched afterwards, no .orig left.\n"
                   + MUTATION_LINES)
REPORT = """STEP: 1 — add
FILES CREATED:
  - src/a.test.ts (2 tests)
FILES MODIFIED:
  - src/a.ts (add, sub)
PROJECT SPECS UPDATED:
  - none
GATES (`resolve.py verify --at step`: typecheck, test; build named by the checkpoint):
  - typecheck: PASS (`pnpm typecheck`)
  - test: PASS (2/2, 1 file)
  - build: PASS (`pnpm build`, gate.py implement-step1-build, EXIT 0)
FIX ITERATIONS: 0/7
DESIGN NOTES (how it is built):
  - plain functions
MUTATIONS:
  Probes by a script in SCRATCH_DIR; checksums matched afterwards, no .orig left.
{mutations}BYTES CHECK: n/a: ASCII only
SUPPRESSIONS CHECK: clean (no `as`, `!`, `@ts-*` in the two files)
SCRATCH: clean
TREE STATE:
{tree}
  (снято перед записью отчёта)
SUMMARY: done
NOTES:
  - none
"""


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = report.main(list(args))
        except SystemExit as e:        # argparse usage errors
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


class ReportCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.root / ".claude" / "omixflow").mkdir(parents=True)
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text(CFG)
        (self.root / "src").mkdir()
        (self.root / "src" / "a.ts").write_text("export const add = (a, b) => a + b\n")
        (self.root / ".tasks" / "T-1" / "reports").mkdir(parents=True)
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        # the step: a source change, a new test file with two tests, an artifact the orchestrator wrote
        (self.root / "src" / "a.ts").write_text("export const add = (a, b) => a + b\nexport const sub = (a, b) => a - b\n")
        (self.root / "src" / "a.test.ts").write_text(TEST_FILE)
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\nstep: 1\n")
        self.gates = self.root / ".git" / "omixflow-gates"
        self.gates.mkdir()
        (self.gates / "implement-step1-build.exit").write_text("0\n")
        self.report = self.root / ".tasks" / "T-1" / "reports" / "implement-step1.md"

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def tree(self) -> str:
        return "   M src/a.ts\n  ?? src/a.test.ts\n   M .tasks/T-1/state.yaml"   # indented as the format shows it

    def write(self, text: str | None = None, mutations: str = MUTATION_LINES, **changes: str) -> None:
        body = text if text is not None else REPORT.format(tree=self.tree(), mutations=mutations)
        for old, new in changes.items():
            self.assertIn(old, body)
            body = body.replace(old, new)
        self.report.write_text(body)

    def check(self, *extra: str, role: str = "coder") -> tuple[int, str]:
        code, out, err = run("check", "--role", role, "--report", str(self.report), "--root", str(self.root), *extra)
        return code, out + err

    # ------------------------------------------------------------------ the sound report

    def test_a_real_shaped_report_is_ok_and_the_verdict_carries_the_gates(self):
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("VERDICT: ok"), out)
        self.assertIn("TREE STATE совпадает", out)
        self.assertIn("implement-step1-build EXIT 0 как заявлено", out)
        self.assertIn("- гейт typecheck: PASS", out)
        self.assertIn("- гейт build: PASS", out)
        self.assertIn("новых тестов 2", out)
        self.assertIn("неотслеживаемые по TREE STATE: src/a.test.ts", out)
        self.assertNotIn("NOTES:", out)

    def test_notes_and_a_collapsed_untracked_directory_and_tracked_artifacts_are_fine(self):
        (self.root / "src" / "feat").mkdir()
        (self.root / "src" / "feat" / "x.ts").write_text("export const x = 1\n")
        self.write(**{"  (снято перед записью отчёта)": "  ?? src/feat/", "NOTES:\n  - none": "NOTES:\n  - out of scope: y"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("NOTES: - out of scope: y", out)
        (self.root / "src" / "feat" / "x.ts.orig").write_text("x")      # hidden behind the collapsed line (finding 37)
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("остаток пробы в дереве — ?? src/feat/x.ts.orig", out)

    # ------------------------------------------------------------------ TREE STATE

    def test_tree_state_from_memory_is_returned_to_the_agent_and_an_orig_leftover_is_flagged(self):
        self.write(text=REPORT.format(tree="   M src/a.ts\n   M src/b.ts", mutations=MUTATION_LINES))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("Сообщение агенту", out)
        self.assertIn("лишние в отчёте [' M src/b.ts']", out)
        self.assertIn("нет в отчёте ['?? src/a.test.ts']", out)
        (self.root / "src" / "a.ts.orig").write_text("x")
        self.write(**{"  (снято перед записью отчёта)": "  ?? src/a.ts.orig"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("остаток пробы в дереве — ?? src/a.ts.orig", out)

    # ------------------------------------------------------------------ MUTATIONS

    def test_every_new_test_declaration_needs_a_line_with_a_red_outcome(self):
        self.write(mutations=MUTATION_LINES.splitlines(keepends=True)[0])
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("новых тестов 2 (src/a.test.ts: новых тестов 2), строк с исходом 1", out)
        self.write(**{"`a - b` → `a + b` → RED": "no probe possible: it checks existing behaviour"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("отговорка вместо причины", out)
        self.write(**{"`a - b` → `a + b` → RED": "no probe possible: OLD occurs 0 times in a.ts, needs exactly 1"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("проба не была запущена", out)
        self.write(**{"`a - b` → `a + b` → RED": "`a - b` → `a + b` → GREEN, then the assertion was tightened"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("исход GREEN без усиления и повторной пробы до RED", out)
        self.write(**{"`a - b` → `a + b` → RED": "`a - b` → `a + b` → GREEN, then the assertion was tightened → RED"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.write(**{MUTATIONS_BLOCK: "MUTATIONS: none: no new tests or assertions\n"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("MUTATIONS: none, но новых тестов 2", out)

    def test_a_changed_test_file_without_new_tests_needs_no_line_but_a_replaced_test_does(self):
        self.git("add", "src/a.test.ts")
        self.git("commit", "-q", "-m", "tests")
        none = REPORT.format(tree="   M src/a.ts\n   M src/a.test.ts\n   M .tasks/T-1/state.yaml",
                             mutations=MUTATION_LINES).replace(MUTATIONS_BLOCK, "MUTATIONS: none: no new tests\n")
        # a moved declaration and a new comment line: nothing new
        lines = TEST_FILE.splitlines()
        (self.root / "src" / "a.test.ts").write_text("\n".join([lines[0], "// order", lines[2], lines[1]]) + "\n")
        self.write(text=none)
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("новых тестов 0", out)
        # one test deleted, another added in its place: the net count is 0, the new one is still new (finding 40)
        (self.root / "src" / "a.test.ts").write_text(TEST_FILE.replace("it('adds', () => {})", "it('brand new', () => {})"))
        self.write(text=none)
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("MUTATIONS: none, но новых тестов 1", out)

    def test_probe_py_batch_output_is_accepted_as_the_mutations_block(self):
        (self.root / "mod.py").write_text("def add(a, b):\n    return a + b\n")
        (self.root / "t.py").write_text("import sys\nsys.path.insert(0, sys.argv[1])\nfrom mod import add\nassert add(2, 3) == 5\n")
        (self.root / "probes.json").write_text(json.dumps([
            {"test": "a.test.ts: adds", "file": "mod.py", "cmd": f"{sys.executable} -B t.py {self.root}",
             "replace": "return a + b", "with": "return a - b"},
            {"test": "a.test.ts: subtracts", "file": "mod.py", "cmd": f"{sys.executable} -B t.py {self.root}",
             "replace": "return a + b", "with": "return 0"}]))
        batch = subprocess.run([sys.executable, str(SCRIPTS / "probe.py"), "batch", "--root", str(self.root),
                                "--spec", "probes.json"], capture_output=True, text=True)
        self.assertEqual(batch.returncode, 0, batch.stdout + batch.stderr)
        lines = "".join("  " + l + "\n" for l in batch.stdout.splitlines() if l.startswith("- "))
        self.write(mutations=lines, **{"   M .tasks/T-1/state.yaml": "   M .tasks/T-1/state.yaml\n  ?? mod.py\n  ?? probes.json\n  ?? t.py"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)

    def test_without_test_globs_mutations_are_reported_as_unchecked(self):
        (self.root / ".claude" / "omixflow" / "lang").mkdir()
        (self.root / ".claude" / "omixflow" / "lang" / "ts.md").write_text(
            "---\nport: lang\nname: ts\ncapabilities: [verify, test_conventions, suppressions, navigation, deps_setup]\n---\n# x\n")
        self.write(**{MUTATIONS_BLOCK: "MUTATIONS: none\n", "  (снято перед записью отчёта)": "  ?? .claude/omixflow/lang/"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("НЕ СВЕРЕНО: MUTATIONS не сверены", out)

    # ------------------------------------------------------------------ baseline

    def test_a_baseline_charges_the_agent_only_with_its_own_delta(self):
        base = self.root / ".git" / "baseline.json"      # outside the tree, as the scratchpad is
        code, out, _ = run("baseline", "--out", str(base), "--root", str(self.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(set(json.loads(base.read_text())["files"]), {"src/a.ts", "src/a.test.ts"})
        # the tester adds a file with one test and one test to the coder's uncommitted file (finding 41)
        (self.root / "src" / "b.test.ts").write_text("import { it } from 'vitest'\nit('b', () => {})\n")
        with (self.root / "src" / "a.test.ts").open("a") as f:
            f.write("it('c', () => {})\n")
        tester = ("TESTS WRITTEN:\n  - src/b.test.ts (1 test)\n  - src/a.test.ts (+1 test)\nRUN RESULT: PASS (4/4)\n"
                  "BACKGROUND GATES:\n  - build: gate.py implement-tests-step1-build, EXIT 0\nCHECKPOINT GATES: build: PASS\n"
                  "ITERATIONS: 1/7\nMUTATIONS:\n  - b.test.ts: b ← a.ts `a - b` → `a + b` → RED\n"
                  "  - a.test.ts: c ← a.ts `a + b` → `a * b` → RED\nBYTES CHECK: n/a: ASCII only\n"
                  "SUPPRESSIONS CHECK: clean\nSCRATCH: clean\nTREE STATE:\n   M src/a.ts\n  ?? src/a.test.ts\n  ?? src/b.test.ts\n"
                  "   M .tasks/T-1/state.yaml\nFAILURES:\n  - none\nCODE BUGS FOUND:\n  - CODE_BUG: sub('1', 2) returns NaN\n"
                  "SUMMARY: ok\n")
        (self.gates / "implement-tests-step1-build.exit").write_text("0\n")
        self.report = self.root / ".tasks" / "T-1" / "reports" / "implement-tests-step1.md"
        self.write(text=tester)
        code, out = self.check("--also", "build", role="tester")
        self.assertEqual(code, 1, out)                      # without the baseline the coder's 2 tests are charged too
        self.assertIn("новых тестов 4", out)
        code, out = self.check("--also", "build", "--baseline", str(base), role="tester")
        self.assertEqual(code, 0, out)
        self.assertIn("новых тестов 2", out)
        self.assertIn("implement-tests-step1-build EXIT 0", out)
        self.assertIn("CODE BUGS FOUND: - CODE_BUG: sub('1', 2) returns NaN", out)   # 2.3 routes it to the coder
        self.assertNotIn("FAILURES", out)
        (self.gates / "implement-tests-step1-build.exit").write_text("1\n")
        code, out = self.check("--also", "build", "--baseline", str(base), role="tester")
        self.assertEqual(code, 1, out)
        self.assertIn("build заявлен PASS, а EXIT 1 у implement-tests-step1-build", out)

    # ------------------------------------------------------------------ gates

    def test_gate_claims_are_checked_against_the_set_and_the_gate_logs(self):
        self.write(**{"  - typecheck: PASS (`pnpm typecheck`)\n": ""})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("нет исхода гейтов typecheck", out)
        (self.gates / "implement-step1-build.exit").write_text("1\n")
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("build заявлен PASS, а EXIT 1", out)
        self.write(**{"build: PASS (`pnpm build`, gate.py implement-step1-build, EXIT 0)": "build: PASS"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("фоновый гейт build без имени gate.py", out)
        (self.gates / "implement-step1-build.exit").write_text("0\n")
        self.write(**{"gate.py implement-step1-build, EXIT 0": "gate.py implement-step1-build, EXIT 2"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("build: в отчёте EXIT 2, в логе 0", out)
        # a gate read by its diagnostics, not its exit code: EXIT 1 with PASS is consistent
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text(
            CFG.replace("build: { cmd: bb, background: true }", "build: { cmd: bb, background: true, criterion: zero-diagnostics }"))
        self.git("add", ".claude/omixflow/flow.yaml")
        self.git("commit", "-qm", "criterion")
        (self.gates / "implement-step1-build.exit").write_text("1\n")
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("в отчёте EXIT 0, в логе 1", out)
        self.write(**{"gate.py implement-step1-build, EXIT 0": "gate.py implement-step1-build, EXIT 1"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("implement-step1-build EXIT 1 как заявлено", out)
        code, out = self.check("--also", "none")           # `none` is not a gate name: build is not in the set
        self.assertEqual(code, 0, out)
        self.assertIn("(typecheck, test)", out)
        code, out = self.check("--also", "nonsense")
        self.assertEqual(code, 3, out)
        self.assertIn("план гейтов не получен", out)

    def test_a_stopped_agent_is_a_stop_not_a_failed_report(self):
        self.write(**{"GATES (`resolve.py verify --at step`: typecheck, test; build named by the checkpoint):\n  - typecheck: PASS (`pnpm typecheck`)\n  - test: PASS (2/2, 1 file)\n  - build: PASS (`pnpm build`, gate.py implement-step1-build, EXIT 0)":
                      "STATUS: stopped — spec and plan conflict on the return type\nGATES: not run — stopped before the gates"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("VERDICT: stopped"), out)
        self.assertIn("остановка агента: stopped — spec and plan conflict", out)

    # ------------------------------------------------------------------ bytes, broken, refused, scratch

    def test_bytes_check_must_cover_non_ascii_text_lines_but_not_binary_files(self):
        src = self.root / "src" / "a.ts"
        src.write_text(src.read_text() + "// сумма\n")
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("BYTES CHECK: n/a, а в диффе не-ASCII", out)
        self.write(**{"BYTES CHECK: n/a: ASCII only": "BYTES CHECK:\n  - n/a: ASCII only"})    # T-18's bullet form
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.write(**{"BYTES CHECK: n/a: ASCII only": "BYTES CHECK:\n  - src/a.ts:3 — U+0441…, verified by bytes"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        src.write_text(src.read_text().replace("// сумма\n", ""))
        (self.root / "src" / "snap.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\xff\xfe")
        self.write(**{"  (снято перед записью отчёта)": "  ?? src/snap.png"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)

    def test_a_truncated_report_is_broken_and_a_refused_one_is_a_report(self):
        self.write(text=REPORT.format(tree=self.tree(), mutations=MUTATION_LINES).split("SUMMARY:")[0])
        code, out = self.check("--also", "build")
        self.assertEqual(code, 2, out)
        self.assertIn("без последнего раздела NOTES", out)
        self.write(text="REPORT_PATH refused by the harness: Subagents should return findings as text\n"
                        + REPORT.format(tree=self.tree(), mutations=MUTATION_LINES))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("refused by the harness", out)
        self.report.unlink()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 2, out)

    def test_scratch_becomes_a_log_line_and_json_carries_everything(self):
        self.write(**{"SCRATCH: clean": "SCRATCH: /tmp/x/probes 12 MB — left outside the tree, could not remove"})
        code, out = self.check("--also", "build", "--json")
        self.assertEqual(code, 0, out)
        r = json.loads(out)
        self.assertEqual(r["scratch_line"], "- SCRATCH implement-step1: /tmp/x/probes 12 MB — left outside the tree, could not remove")
        self.assertEqual(r["verdict"], "ok")
        self.assertIn("гейт test: PASS", r["facts"])


if __name__ == "__main__":
    unittest.main()
