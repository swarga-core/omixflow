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
SPEC = ("# Spec: T-1\n\n## Summary\n\nadd and sub\n\n## Intent\n\n- callers can add\n\n## Scenarios\n\n"
        "- S1 — adds. Given two numbers, when add, then the sum.\n\n## Contracts\n\n- `add` (a) — new\n\n"
        "## Decisions\n\n- D1: plain functions — simple; rests on: nothing\n\n## Out of Scope\n\n- mul\n")
REPORT = """STEP: 1 — add
FILES CREATED:
  - src/a.test.ts (2 tests)
FILES MODIFIED:
  - src/a.ts (add, sub)
PROJECT SPECS UPDATED:
  - none
SPEC AMENDMENTS:
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
        (self.root / ".tasks" / "T-1" / "spec.md").write_text(SPEC)
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

    def real_tree(self) -> str:
        """TREE STATE as the agent takes it: `git status --short --untracked-files=all`, indented."""
        out = subprocess.run(["git", "-C", str(self.root), "status", "--short", "--untracked-files=all"],
                             capture_output=True, text=True, check=True).stdout
        return "\n".join("  " + l for l in out.splitlines())

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

    def test_a_probe_copy_left_in_the_git_directory_is_flagged(self):
        """G-69: probe.py keeps its copies out of the tree, in `{git-dir}/omixflow-probes`;
        `git status` no longer shows one left behind, report.py looks there."""
        self.write()
        self.assertEqual(self.check("--also", "build")[0], 0)
        copy = self.root / ".git" / "omixflow-probes" / "src" / "a.ts.orig"
        copy.parent.mkdir(parents=True)
        copy.write_text("x")
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("пробы не восстановлены", out)
        self.assertIn("src/a.ts", out)
        self.assertIn("probe.py restore --root", out)

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

    def test_each_only_and_concurrent_declarations_are_counted(self):
        """G-78, SwAIS T-13: «новых тестов 5» at 7 — the ts adapter's regex missed `it.each(…)(…)`."""
        (self.root / "src" / "a.test.ts").write_text(
            TEST_FILE + "it.each([1, 2])('n %s', (n) => {})\ntest.each`a`('t', () => {})\n"
                        "it.only('o', () => {})\ntest.concurrent('c', () => {})\nconst item = list.items(1)\n"
                        "test.describe('group', () => {})\ntest.beforeEach(() => {})\n")
        self.write(mutations=MUTATION_LINES)
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("новых тестов 6 (src/a.test.ts: новых тестов 6), строк с исходом 2", out)

    def sync_in_progress(self) -> None:
        """A task branch and a moved base, both adding tests to one file; the merge stops on the
        conflict and the coder resolves it keeping both sides plus one test of his own (SwAIS T-14:
        the base brought 93 tests of T-13)."""
        self.git("checkout", "-q", "--", "src/a.ts", ".tasks/T-1/state.yaml")
        (self.root / "src" / "a.test.ts").unlink()
        common = "import { it } from 'vitest'\nit('base', () => {})\n"
        (self.root / "src" / "b.test.ts").write_text(common)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "shared")
        self.git("checkout", "-q", "-b", "task/T-1")
        (self.root / "src" / "b.test.ts").write_text(common + "it('task', () => {})\n")
        self.git("commit", "-q", "-am", "task step")
        self.git("checkout", "-q", "main")
        (self.root / "src" / "b.test.ts").write_text(common + "it('neighbour', () => {})\n")
        (self.root / "src" / "c.test.ts").write_text("import { it } from 'vitest'\n"
                                                     + "".join(f"it('n{i}', () => {{}})\n" for i in range(5)))
        (self.root / "docs.md").write_text("# Заметка соседа\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "neighbour")
        self.git("checkout", "-q", "task/T-1")
        subprocess.run(["git", "-C", str(self.root), "merge", "main"], capture_output=True)   # stops on the conflict
        (self.root / "src" / "b.test.ts").write_text(
            common + "it('task', () => {})\nit('neighbour', () => {})\nit('both — сшивка', () => {})\n")
        self.git("add", "src/b.test.ts")

    def sync_report(self, **changes: str) -> str:
        body = REPORT.format(tree=self.real_tree(), mutations="  - b.test.ts: both ← M1 b.ts → RED\n")
        body = body.replace("STEP: 1 — add\nFILES CREATED:\n  - src/a.test.ts (2 tests)\nFILES MODIFIED:\n  - src/a.ts (add, sub)\n",
                            "STEP: sync1 — merge main into task/T-1\nRESOLUTIONS:\n  - src/b.test.ts — both sides kept, a seam test added\n")
        body = body.replace("BYTES CHECK: n/a: ASCII only", "BYTES CHECK:\n  - src/b.test.ts: Cyrillic; invisible and escapes: none")
        for old, new in changes.items():
            self.assertIn(old, body)
            body = body.replace(old, new)
        return body

    def test_a_sync_report_counts_only_what_neither_side_had(self):
        """G-88: the sync report has RESOLUTIONS instead of FILES, and the tests the base brought
        are not the coder's: 1 new test, not 7; the neighbour's Cyrillic file is not his either."""
        self.sync_in_progress()
        self.write(text=self.sync_report())
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("RESOLUTIONS: все 1 конфликтных файлов названы", out)
        self.assertIn("MUTATIONS: новых тестов 1", out)
        self.assertIn("синхронизация: идёт слияние с MERGE_HEAD", out)  # three-way
        self.write(text=self.sync_report(**{"  - b.test.ts: both ← M1 b.ts → RED\n": ""}).replace(
            "MUTATIONS:\n  Probes by a script in SCRATCH_DIR; checksums matched afterwards, no .orig left.\n",
            "MUTATIONS: none: no new tests\n"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("MUTATIONS: none, но новых тестов 1 (src/b.test.ts: новых тестов 1)", out)
        self.write(text=self.sync_report(**{"  - src/b.test.ts — both sides kept, a seam test added\n": "  - all merged\n"}))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("RESOLUTIONS не называет конфликтные файлы: ['src/b.test.ts']", out)
        code, out = self.check("--also", "build", "--conflicts", "src/x.ts")     # the orchestrator's list wins
        self.assertIn("['src/x.ts']", out)

    def test_a_line_both_sides_added_and_the_merge_keeps_twice_is_not_new(self):
        """Review F1, SwAIS T-16: `it.each([` — base 6, HEAD 7, MERGE_HEAD 7, merged 8: the larger
        side gave 7 and one false new test in an auto-merged file the coder never touched."""
        self.git("checkout", "-q", "--", "src/a.ts", ".tasks/T-1/state.yaml")
        (self.root / "src" / "a.test.ts").unlink()
        head = "import { it } from 'vitest'\nit.each([1])('a %s', () => {})\n"
        (self.root / "src" / "d.test.ts").write_text(head + "// middle\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "shared")
        self.git("checkout", "-q", "-b", "task/T-1")
        # a multi-line `it.each([` — the same line on both sides, as in T-16's props.test.ts
        (self.root / "src" / "d.test.ts").write_text("it.each([\n  2,\n])('t %s', () => {})\n" + head + "// middle\n")
        self.git("commit", "-q", "-am", "task adds an each at the top")
        self.git("checkout", "-q", "main")
        (self.root / "src" / "d.test.ts").write_text(head + "// middle\nit.each([\n  3,\n])('n %s', () => {})\n")
        (self.root / "src" / "e.ts").write_text("export const e = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "neighbour adds an each at the bottom")
        self.git("checkout", "-q", "task/T-1")
        subprocess.run(["git", "-C", str(self.root), "merge", "--no-ff", "--no-commit", "main"], capture_output=True)
        merged = (self.root / "src" / "d.test.ts").read_text()
        self.assertEqual(merged.count("it.each(["), 3)         # clean auto-merge: both added an `it.each([` line
        body = REPORT.format(tree=self.real_tree(), mutations="")
        body = body.replace("STEP: 1 — add\nFILES CREATED:\n  - src/a.test.ts (2 tests)\nFILES MODIFIED:\n  - src/a.ts (add, sub)\n",
                            "STEP: sync1 — merge main into task/T-1\nRESOLUTIONS:\n  - none: no conflicts\n")
        body = body.replace("MUTATIONS:\n  Probes by a script in SCRATCH_DIR; checksums matched afterwards, no .orig left.\n",
                            "MUTATIONS: none: no new tests\n")
        self.write(text=body)
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertNotIn("новых тестов 1", out)
        self.assertEqual(report.sync_new_lines(self.root, "src/d.test.ts", "MERGE_HEAD",
                                               report.sync_base(self.root, "MERGE_HEAD")), [])
        self.assertEqual(report.sync_new_lines(self.root / "src", "d.test.ts", "MERGE_HEAD",   # review F10: a nested
                                               report.sync_base(self.root, "MERGE_HEAD")), [])  # root reads `./{path}`

    def test_conflicts_after_the_merge_is_committed_say_so(self):
        self.write()
        code, out = self.check("--also", "build", "--conflicts", "src/a.ts")
        self.assertIn("--conflicts без идущего слияния", out)

    def test_a_step_report_outside_a_merge_still_needs_files(self):
        self.write(text=REPORT.format(tree=self.tree(), mutations=MUTATION_LINES).replace(
            "FILES CREATED:\n  - src/a.test.ts (2 tests)\nFILES MODIFIED:\n  - src/a.ts (add, sub)\n", ""))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("нет разделов: FILES", out)

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
        # a run prints the runner's summary: the ts adapter's `tests.ran` wants a «N passed» line (G-85)
        (self.root / "t.py").write_text("import sys\nsys.path.insert(0, sys.argv[1])\nfrom mod import add\n"
                                        "assert add(2, 3) == 5\nprint(' Tests  1 passed (1)')\n")
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

    def test_bytes_check_per_file_form_covers_cyrillic_and_every_such_file_is_named(self):
        """G-71, SwAIS T-12: Cyrillic comments, test names and ADRs in six files; the coder wrote
        `n/a` meaning «checked, nothing invisible», the step came back with no code change."""
        src = self.root / "src" / "a.ts"
        src.write_text(src.read_text() + "// сумма — итог\n")
        test = self.root / "src" / "a.test.ts"
        test.write_text(test.read_text() + "// проверка\n")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "T-12-run-model.md").write_text("# Модель прогона\n")
        tree = self.real_tree()
        self.write(text=REPORT.format(tree=tree, mutations=MUTATION_LINES).replace(
            "BYTES CHECK: n/a: ASCII only",
            "BYTES CHECK: n/a: escapes нет; не-ASCII — только кириллица и видимые типографские символы"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("`n/a` только при ASCII-диффе", out)
        for f in ("src/a.ts", "src/a.test.ts", "docs/T-12-run-model.md"):   # every file, not the first five
            self.assertIn(f, out)
        per_file = ("BYTES CHECK:\n  - src/a.ts: Cyrillic, typographic (—); invisible and escapes: none — verified by bytes\n"
                    "  - a.test.ts: Cyrillic; invisible and escapes: none — verified by bytes")
        self.write(text=REPORT.format(tree=tree, mutations=MUTATION_LINES).replace("BYTES CHECK: n/a: ASCII only", per_file))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("не называет файлы диффа с не-ASCII строками: ['docs/T-12-run-model.md']", out)
        self.assertIn("по файлу:", out)
        self.write(text=REPORT.format(tree=tree, mutations=MUTATION_LINES).replace(
            "BYTES CHECK: n/a: ASCII only", per_file + "\n  - docs/T-12-run-model.md: Cyrillic; invisible and escapes: none"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("BYTES CHECK соответствует диффу", out)

    def test_a_file_name_shared_by_two_files_or_a_longer_name_does_not_cover(self):
        (self.root / "lib").mkdir()
        for d in ("src", "lib"):
            (self.root / d / "keys.ts").write_text("// ключи\n")
        tree = self.real_tree()
        body = REPORT.format(tree=tree, mutations=MUTATION_LINES)
        self.write(text=body.replace("BYTES CHECK: n/a: ASCII only",
                                     "BYTES CHECK:\n  - keys.ts: Cyrillic; invisible and escapes: none"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("'lib/keys.ts', 'src/keys.ts'", out)
        self.write(text=body.replace("BYTES CHECK: n/a: ASCII only",
                                     "BYTES CHECK:\n  - src/keys.tsx: Cyrillic\n  - lib/keys.ts: Cyrillic"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("['src/keys.ts']", out)

    def test_bytes_check_takes_a_unique_tail_an_absolute_path_and_dot_slash(self):
        """Review F3: T-10's per-file lines named `http/actions.test.ts` and `…/registry.ts`."""
        deep = self.root / "packages" / "server" / "src" / "http"
        deep.mkdir(parents=True)
        for name in ("actions.test.ts", "registry.ts", "snap.ts"):
            (deep / name).write_text("// кириллица\n")
        tree = self.real_tree()
        src = self.root / "src" / "a.ts"
        body = REPORT.format(tree=tree, mutations=MUTATION_LINES)
        lines = ("BYTES CHECK:\n  - http/actions.test.ts:1 — Cyrillic\n  - …/registry.ts: Cyrillic\n"
                 f"  - {self.root}/packages/server/src/http/snap.ts: Cyrillic")
        self.write(text=body.replace("BYTES CHECK: n/a: ASCII only", lines))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        src.write_text(src.read_text() + "// сумма\n")
        self.write(text=REPORT.format(tree=self.real_tree(), mutations=MUTATION_LINES).replace(
            "BYTES CHECK: n/a: ASCII only", lines + "\n  - src/a.ts.snap: Cyrillic"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("['src/a.ts']", out)                  # `a.ts.snap` does not name `a.ts`
        self.write(text=REPORT.format(tree=self.real_tree(), mutations=MUTATION_LINES).replace(
            "BYTES CHECK: n/a: ASCII only", lines + "\n  - ./src/a.ts: Cyrillic"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)

    def test_bytes_check_does_not_take_another_path_for_the_file(self):
        """Re-review N1: a unique tail inside a different path is not the file."""
        for d in ("packages/server/src", "lib"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / "packages" / "server" / "src" / "index.ts").write_text("// индекс\n")
        (self.root / "lib" / "b.ts").write_text("// б\n")
        body = REPORT.format(tree=self.real_tree(), mutations=MUTATION_LINES)
        for named in ("packages/ui/src/index.ts", "lib/index.ts", "vendor/server/src/index.ts"):
            with self.subTest(named=named):
                self.write(text=body.replace("BYTES CHECK: n/a: ASCII only",
                                             f"BYTES CHECK:\n  - {named}: Cyrillic\n  - lib/b.ts: Cyrillic"))
                code, out = self.check("--also", "build")
                self.assertEqual(code, 1, out)
                self.assertIn("['packages/server/src/index.ts']", out)
        self.write(text=body.replace("BYTES CHECK: n/a: ASCII only",
                                     "BYTES CHECK:\n  - `server/src/index.ts:1` — Cyrillic\n  - Cyrillic only, in b.ts."))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "My File.md").write_text("# Заметка\n")        # re-review N8
        body = REPORT.format(tree=self.real_tree(), mutations=MUTATION_LINES)
        lines = "BYTES CHECK:\n  - server/src/index.ts: Cyrillic\n  - b.ts: Cyrillic\n"
        self.write(text=body.replace("BYTES CHECK: n/a: ASCII only", lines + "  - docs/My File.md: Cyrillic"))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        for other in ("docs/My File.mdx", "docs/My File.md.bak"):
            self.write(text=body.replace("BYTES CHECK: n/a: ASCII only", lines + f"  - {other}: Cyrillic"))
            self.assertEqual(self.check("--also", "build")[0], 1, other)

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

    def test_spec_amendments_are_checked_against_the_snapshot_and_a_decision_or_contract_change_is_a_stop(self):
        """0.9 step 6: the coder amends the spec and says so; a change to a contract, a
        decision's choice (however it wraps or is labelled), the intent or the scope is a
        stop. The base is the baseline's snapshot of spec.md (untracked artifacts, earlier
        uncommitted edits), else HEAD."""
        spec = self.root / ".tasks" / "T-1" / "spec.md"
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC AMENDMENTS: none, spec.md не менялся (против HEAD)", out)
        # an amendment of a scenario, unreported
        spec.write_text(SPEC.replace("then the sum.", "then the sum; NaN inputs give NaN (S1a)."))
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("SPEC AMENDMENTS: none, а spec.md изменён в секциях «Scenarios»", out)
        amended = "SPEC AMENDMENTS:\n  - spec.md «Scenarios»: S1 names NaN inputs — vitest showed add(NaN, 1)"
        self.write(**{"SPEC AMENDMENTS:\n  - none": amended})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC AMENDMENTS: - spec.md «Scenarios»", out)
        self.assertIn("правки названы", out)
        # an earlier uncommitted edit (the orchestrator's, before the assignment) is not the coder's: the snapshot is the base
        base = self.root / ".git" / "baseline-step.json"
        code, out, _ = run("baseline", "--out", str(base), "--root", str(self.root), "--task", str(spec.parent))
        self.assertEqual(code, 0, out)
        self.assertIn("spec.md snapshot", out)
        self.write()
        code, out = self.check("--also", "build", "--baseline", str(base))
        self.assertEqual(code, 0, out)
        self.assertIn("не менялся (против снимка baseline)", out)
        code, out = self.check("--also", "build")                       # against HEAD the same edit is a problem
        self.assertEqual(code, 1, out)
        # a claim without a change
        spec.write_text(SPEC)
        self.write(**{"SPEC AMENDMENTS:\n  - none": amended})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("называет правки, а spec.md против HEAD не изменён", out)
        # decisions: the `rests on` fact may change on its own line, the choice may not — however it wraps or is labelled
        wrapped = SPEC.replace("- D1: plain functions — simple; rests on: nothing",
                               "- D1 (A1, D-283): plain\n  functions — simple;\n  rests on: nothing")
        spec.write_text(wrapped)
        self.git("add", ".tasks/T-1/spec.md")
        self.git("commit", "-qm", "wrapped decision")
        spec.write_text(wrapped.replace("rests on: nothing", "rests on: vitest 2 runs ESM"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: D1 rests on vitest ESM"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        spec.write_text(wrapped.replace("plain\n  functions", "plain\n  classes"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: D1 classes"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("правка в «Decisions D1» — это смена объёма, решения или контракта", out)
        spec.write_text(wrapped.replace("rests on: nothing", "rests on: nothing\n- D2: cache results — faster"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: D2 added"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("«Decisions D2»", out)
        # bold labels and `###` decisions (mewria MEW-8/10/15) are decisions too; unrecognised items are a stop
        bold = wrapped.replace("- D1 (A1, D-283): plain\n  functions — simple;\n  rests on: nothing",
                               "- **D1 — plain functions.** simple;\n  rests on: nothing\n\n### D2: no cache\n\nnever;\nrests on: perf")
        spec.write_text(bold)
        self.git("add", ".tasks/T-1/spec.md")
        self.git("commit", "-qm", "bold decisions")
        spec.write_text(bold.replace("rests on: perf", "rests on: perf probe 2026"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: D2 rests on probe"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        spec.write_text(bold.replace("**D1 — plain functions.**", "**D1 — classes.**"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: D1 classes"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("«Decisions D1»", out)
        unlabelled = bold.replace("- **D1 — plain functions.** simple;\n  rests on: nothing\n\n### D2: no cache\n\nnever;\nrests on: perf",
                                  "plain functions, no cache")
        spec.write_text(unlabelled)
        self.git("add", ".tasks/T-1/spec.md")
        self.git("commit", "-qm", "unlabelled")
        spec.write_text(unlabelled.replace("plain functions, no cache", "classes, no cache"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Decisions»: classes"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("пункты решений не распознаны", out)
        spec.write_text(wrapped)
        self.git("add", ".tasks/T-1/spec.md")
        self.git("commit", "-qm", "back")
        for section, old, new in (("Contracts", "- `add` (a) — new", "- `add` (a) — new, async"),
                                  ("Out of Scope", "- mul", "- mul\n- div"),
                                  ("Intent", "- callers can add", "- callers can add and sub")):
            spec.write_text(wrapped.replace(old, new))
            self.write(**{"SPEC AMENDMENTS:\n  - none": f"SPEC AMENDMENTS:\n  - spec.md «{section}»: changed"})
            code, out = self.check("--also", "build")
            self.assertEqual(code, 1, out)
            self.assertIn(f"правка в «{section}» — это смена объёма, решения или контракта", out)
        # a blank line or trailing whitespace in a protected section is no change at all
        spec.write_text(wrapped.replace("## Contracts\n\n- `add` (a) — new", "## Contracts\n\n\n- `add` (a) — new   "))
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("spec.md не менялся", out)
        # a heading inside a code fence opens no section: an example in Scenarios is a Scenarios amendment
        spec.write_text(wrapped.replace("then the sum.", "then the sum.\n\n  ```\n  ## Intent\n  ```"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Scenarios»: example block"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("изменён в «Scenarios», правки названы", out)
        spec.write_text(wrapped)
        # artifacts kept outside git (mewria, SwAIS): without a snapshot the section is unchecked, with one it is checked
        self.git("rm", "-q", "--cached", ".tasks/T-1/spec.md")
        self.git("commit", "-qm", "untrack")
        spec.write_text(wrapped)
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("НЕ СВЕРЕНО: SPEC AMENDMENTS не сверены: нет снимка spec.md", out)
        code, out, _ = run("baseline", "--out", str(base), "--root", str(self.root), "--task", str(spec.parent))
        self.assertEqual(code, 0, out)
        blob = json.loads(base.read_text())["spec"]["blob"]
        self.assertIn(f"refs/omixflow/snapshots/T-1/{blob}", self.git("for-each-ref", "--format=%(refname)"))   # gc-proof
        spec.write_text(wrapped.replace("- `add` (a) — new", "- `add` (a) — new, async"))
        self.write(**{"SPEC AMENDMENTS:\n  - none": "SPEC AMENDMENTS:\n  - spec.md «Contracts»: add is async"})
        code, out = self.check("--also", "build", "--baseline", str(base))
        self.assertEqual(code, 1, out)
        self.assertIn("правка в «Contracts»", out)
        self.assertNotIn("НЕ СВЕРЕНО", out)

    def test_a_project_root_nested_in_a_larger_repository_is_diffed_with_a_relative_head_path(self):
        outer = Path(self.tmp.name) / "outer"
        proj = outer / "proj"
        (proj / ".claude" / "omixflow").mkdir(parents=True)
        subprocess.run(["git", "-C", str(outer), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(outer), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(outer), "config", "user.name", "t"], check=True)
        (proj / ".claude" / "omixflow" / "flow.yaml").write_text(CFG)
        (proj / ".tasks" / "T-1" / "reports").mkdir(parents=True)
        (proj / ".tasks" / "T-1" / "spec.md").write_text(SPEC)
        (proj / "src").mkdir()
        (proj / "src" / "a.ts").write_text("export const add = (a, b) => a + b\n")
        subprocess.run(["git", "-C", str(outer), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(outer), "commit", "-qm", "base"], check=True)
        (proj / "src" / "a.ts").write_text("export const add = (a, b) => a + b\nexport const sub = (a, b) => a - b\n")
        (proj / "src" / "a.test.ts").write_text(TEST_FILE)
        (proj / ".tasks" / "T-1" / "spec.md").write_text(SPEC.replace("then the sum.", "then the sum; NaN gives NaN."))
        report = proj / ".tasks" / "T-1" / "reports" / "implement-step1.md"
        report.write_text(REPORT.format(tree="   M src/a.ts\n  ?? src/a.test.ts", mutations=MUTATION_LINES)
                          .replace("SPEC AMENDMENTS:\n  - none", "SPEC AMENDMENTS:\n  - spec.md «Scenarios»: NaN"))
        (outer / ".git" / "omixflow-gates").mkdir()
        (outer / ".git" / "omixflow-gates" / "implement-step1-build.exit").write_text("0\n")
        code, out, err = run("check", "--role", "coder", "--report", str(report), "--root", str(proj), "--also", "build")
        self.assertEqual(code, 0, out + err)
        self.assertIn("правки названы", out)

    def test_project_specs_updated_follows_specs_mode(self):
        """0.9 step 7: under `adr` the listed paths are records in adr_dir, new on this step;
        under `none` the section is none; `descriptions` is the reviewer's judgement."""
        cfg_path = self.root / ".claude" / "omixflow" / "flow.yaml"
        (self.root / "docs" / "decisions").mkdir(parents=True)
        cfg_path.write_text(CFG + "specs: {mode: adr}\n")
        self.git("add", ".claude/omixflow/flow.yaml")
        self.git("commit", "-qm", "adr mode")
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("none — шаг без записи решения (specs.mode adr)", out)
        record = self.root / "docs" / "decisions" / "T-1-add.md"
        record.write_text("date: 2026-10-13\ntask: T-1\ndecision: D1\n\nadd is a plain function.\n")
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `docs/decisions/T-1-add.md` (D1)",
                      "  (снято перед записью отчёта)": "  ?? docs/decisions/T-1-add.md"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("записи решений в docs/decisions/ на месте", out)
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `packages/schemas/spec.md` (add)",
                      "  (снято перед записью отчёта)": "  ?? docs/decisions/T-1-add.md"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("вне docs/decisions/", out)
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `docs/decisions/T-1-nope.md`",
                      "  (снято перед записью отчёта)": "  ?? docs/decisions/T-1-add.md"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("записи `docs/decisions/T-1-nope.md` нет в дереве", out)
        # mewria's report form: a bare path followed by backticked code, a trailing colon, an absolute path
        for line in ("- docs/decisions/T-1-add.md — D1: `add` is plain", "- docs/decisions/T-1-add.md:",
                     f"- {self.root}/docs/decisions/T-1-add.md (D1)"):
            self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  " + line,
                          "  (снято перед записью отчёта)": "  ?? docs/decisions/T-1-add.md"})
            code, out = self.check("--also", "build")
            self.assertEqual(code, 0, out)
        # a record added on the branch may be refined until the merge
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\nbase: main\n")
        self.git("checkout", "-q", "-b", "task/T-1")
        self.git("add", "docs/decisions/T-1-add.md")
        self.git("commit", "-qm", "record on the branch")
        committed = record.read_text()
        record.write_text(committed + "\nrefined\n")
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `docs/decisions/T-1-add.md` (D1 refined)",
                      "  (снято перед записью отчёта)": "   M docs/decisions/T-1-add.md\n   M .tasks/T-1/state.yaml"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("записи решений в docs/decisions/ на месте", out)
        # one that existed at the base may not
        record.write_text(committed)
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\n")
        self.git("checkout", "-q", "main")              # the record is the branch's: main has neither it nor its dir
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(committed)
        self.git("add", "docs/decisions/T-1-add.md")
        self.git("commit", "-qm", "record at the base")
        self.git("checkout", "-q", "-b", "task/T-2")
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\nbase: main\n")
        record.write_text(committed + "\nrefined\n")
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `docs/decisions/T-1-add.md` (D1 refined)",
                      "  (снято перед записью отчёта)": "   M docs/decisions/T-1-add.md\n   M .tasks/T-1/state.yaml"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("была в базе ветки и правлена", out)
        record.write_text(committed)
        (self.root / ".tasks" / "T-1" / "state.yaml").write_text("id: T-1\n")
        # none: nothing beyond spec.md
        cfg_path.write_text(CFG + "specs: {mode: none}\n")
        self.git("add", ".claude/omixflow/flow.yaml")
        self.git("commit", "-qm", "none mode")
        self.write(**{"PROJECT SPECS UPDATED:\n  - none": "PROJECT SPECS UPDATED:\n  - `packages/schemas/spec.md` (add)"})
        code, out = self.check("--also", "build")
        self.assertEqual(code, 1, out)
        self.assertIn("при specs.mode none секция — `none`", out)
        self.write()
        code, out = self.check("--also", "build")
        self.assertEqual(code, 0, out)
        self.assertIn("PROJECT SPECS UPDATED: none (specs.mode none)", out)

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
