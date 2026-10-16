"""Tests for plan.py: the plan's files and steps against the tier thresholds."""
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
import plan as planpy  # noqa: E402

CFG = ("version: 1\ntracker: none\nforge: none\nlang: [ts]\n"
       "workspace: {base: main, branch: 'task/{id}'}\nverify:\n  test: tt\n")
PLAN = """# Plan: T-1

## Steps

### Step 1: types

**Files:**

- CREATE: `packages/schemas/src/action.ts` — schema
- MODIFY: `packages/schemas/src/index.ts` — export
- CREATE: `packages/schemas/src/action.test.ts` — tests

### Step 2: server

**Files:**

- MODIFY: `packages/server/src/http/app.ts` — route
- MODIFY: `packages/schemas/src/index.ts` — again, counted once
- **CREATE:** `packages/server/test/actions.ts` — test support
- DELETE: `packages/server/src/old.ts` — gone

## Verification

- [ ] gates
"""


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = planpy.main(list(args))
    return code, out.getvalue(), err.getvalue()


class PlanFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "omixflow").mkdir(parents=True)
        self.cfg(CFG)
        self.task = self.root / ".tasks" / "T-1"
        self.task.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def cfg(self, text: str) -> None:
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text(text)

    def state(self, tier: str | None) -> None:
        (self.task / "state.yaml").write_text(f"id: T-1\nkind: task\ntier: {tier}\n")

    def files(self, *extra: str):
        code, out, err = run("files", "--task", str(self.task), "--json", *extra)
        return code, (json.loads(out) if out.strip() else None), err

    def test_files_are_unique_tests_apart_and_compared_with_the_tier_threshold(self):
        self.state("M")
        (self.task / "plan.md").write_text(PLAN)
        self.cfg(CFG + "tiers: {m_max_files: 5}\n")
        code, r, _ = self.files()
        self.assertEqual(code, 0, r)
        # test support under test/ (the ts adapter's tests.support, G-67) counts neither as code nor as
        # a test; the bold `**CREATE:**` counts
        self.assertEqual((r["files"], r["non_test"], r["tests"], r["support"], r["threshold"], r["over"]),
                         (6, 4, 1, 1, 5, False))
        self.assertEqual(r["paths"][0], "packages/schemas/src/action.ts")
        self.assertIn("packages/server/src/old.ts", r["paths"])
        self.assertIn("packages/server/test/actions.ts", r["paths"])
        self.cfg(CFG + "tiers: {m_max_files: 4}\n")
        self.assertEqual(self.files()[0], 0)        # SwAIS T-10: 31 by the script, 29 in fact, threshold 30
        self.cfg(CFG + "tiers: {m_max_files: 3}\n")
        code, out, _ = run("files", "--task", str(self.task))
        self.assertEqual(code, 1, out)
        self.assertIn("over: yes", out)
        self.assertIn("test packages/schemas/src/action.test.ts", out)
        self.assertIn("supp packages/server/test/actions.ts", out)
        self.assertIn("non-test 4, tests 1, test support 1", out)

    def test_a_test_file_under_a_support_directory_is_a_test(self):
        """`packages/server/test/x.test.ts` matches both globs: a test, not support (review F11)."""
        self.state("M")
        (self.task / "plan.md").write_text("### Step 1\n\n- MODIFY `packages/server/test/x.test.ts`\n"
                                           "- MODIFY `packages/server/test/db.ts`\n- MODIFY `src/a.ts`\n")
        code, r, _ = self.files()
        self.assertEqual((r["non_test"], r["tests"], r["support"]), (1, 1, 1))

    def test_a_project_extension_adds_its_own_test_support(self):
        """A layout the plugin adapter does not know: the project's extension of the ts adapter
        names it, `plan.py` takes the union of the chain."""
        self.state("M")
        (self.task / "plan.md").write_text("### Step 1\n\n- MODIFY `src/a.ts`\n- MODIFY `e2e/helpers/login.ts`\n")
        code, r, _ = self.files()
        self.assertEqual((r["non_test"], r["support"]), (2, 0))
        ext = self.root / ".claude" / "omixflow" / "lang" / "ts.md"
        ext.parent.mkdir(parents=True)
        ext.write_text("---\nport: lang\nname: ts\nextends: omixflow:ts\ntests:\n  support: [\"e2e/helpers/**\"]\n---\n")
        code, r, _ = self.files()
        self.assertEqual((r["non_test"], r["support"]), (1, 1))

    def test_every_form_the_architect_and_the_orchestrator_write_is_read(self):
        """SwAIS T-2/T-3: `- MODIFY `p``; mewria MEW-11: `Файлы: `p` (MODIFY)`; several
        paths per line (T-1: 17 missed); bold `**CREATE**:`; indented items."""
        self.state("M")
        (self.task / "plan.md").write_text(
            "### Step 1\n\n- MODIFY `src/a.ts` — a\n  - **CREATE**: `src/b.ts`, `src/c.ts` и `src/d.ts` — three\n"
            "Файлы: `src/e.ts` (MODIFY), `src/f.ts` (CREATE)\n- `src/not-a-file-line.ts` — no keyword\n")
        code, r, _ = self.files()
        self.assertEqual(code, 0)
        self.assertEqual(r["paths"], ["src/a.ts", "src/b.ts", "src/c.ts", "src/d.ts", "src/e.ts", "src/f.ts"])

    def test_identifiers_in_the_description_are_not_files(self):
        """MEW-9 counted 26 files for 11 listed: `account.created`, `pool.connect()`,
        `Type.IsEnum` after the dash were taken for paths."""
        self.state("M")
        (self.task / "plan.md").write_text(
            "### Шаг 1\n\n- ИЗМЕНИТЬ: `src/a.ts` — emits `account.created`, calls `pool.connect()` and `\"./pipeline\"`\n"
            "- CREATE: `src/b.ts`, `src/c.ts` — uses `Type.IsEnum` and `Entity.Null`\n")
        code, r, _ = self.files()
        self.assertEqual((code, r["paths"]), (0, ["src/a.ts", "src/b.ts", "src/c.ts"]))

    def test_a_plan_without_a_recognised_file_line_is_not_zero_files(self):
        self.state("M")
        (self.task / "plan.md").write_text("### Step 1\n\nTouch `src/a.ts` and `src/b.ts` somehow.\n")
        code, r, err = self.files()
        self.assertEqual((code, r), (2, None))
        self.assertIn("no file line recognised", err)

    def test_s_tier_reads_the_steps_section_only_and_plan_md_wins_when_present(self):
        self.state("S")
        (self.task / "spec.md").write_text(
            "# Spec\n\n## Research\n\n| File | Role |\n|---|---|\n| `src/x.ts` | implementation |\n"
            "- MODIFY `src/research-only.ts` — a map line, not a step\n\n## Scenarios\n\n- S1 — ok.\n\n"
            "## Steps\n\n### Step 1\n\n- CREATE: `src/a.ts` — a\n- MODIFY: `src/b.ts` — b\n")
        code, r, _ = self.files()
        self.assertEqual((code, r["files"], r["threshold"]), (0, 2, 5))
        self.assertNotIn("src/research-only.ts", r["paths"])
        self.cfg(CFG + "tiers: {s_max_files: 1}\n")
        code, _, _ = self.files()
        self.assertEqual(code, 1)
        (self.task / "plan.md").write_text("### Step 1\n\n- CREATE: `src/only.ts` — p\n")
        code, r, _ = self.files()
        self.assertEqual((code, r["paths"]), (0, ["src/only.ts"]))
        (self.task / "plan.md").unlink()
        (self.task / "spec.md").write_text("# Spec\n\n## Delta\n\n- CREATE: `src/a.ts`\n")
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.assertIn("no `## Steps` section", err)

    def test_more_than_eight_steps_is_over_for_every_tier(self):
        self.state("L")
        (self.task / "plan.md").write_text("".join(f"### Step {i}: s\n\n- MODIFY: `src/f{i}.ts` — x\n\n" for i in range(1, 10)))
        code, r, _ = self.files()
        self.assertEqual((code, r["threshold"], r["steps"], r["over_files"], r["over_steps"], r["over"]), (1, None, 9, False, True, True))
        (self.task / "plan.md").write_text("".join(f"### Step {i}: s\n\n- MODIFY: `src/f{i}.ts` — x\n\n" for i in range(1, 9)))
        code, r, _ = self.files()
        self.assertEqual((code, r["over"]), (0, False))

    def test_test_globs_are_the_union_over_languages_and_extensions(self):
        self.state("M")
        (self.task / "plan.md").write_text("### Step 1\n\n- CREATE: `src/a.test.ts` — t\n- CREATE: `tests/test_b.py` — t\n"
                                           "- CREATE: `src/c.spec.ts` — t\n- CREATE: `src/d.ts` — code\n")
        lang = self.root / ".claude" / "omixflow" / "lang"
        lang.mkdir()
        (lang / "py.md").write_text("---\nport: lang\nname: py\ncapabilities: [verify, test_conventions, suppressions, navigation, deps_setup]\n"
                                    "tests:\n  files: ['tests/test_*.py']\n  declaration: '^\\s*def test_'\n---\n# py\n")
        (lang / "ts.md").write_text("---\nport: lang\nname: ts\nextends: omixflow:ts\n"
                                    "capabilities: [verify, test_conventions, suppressions, navigation, deps_setup]\n"
                                    "tests:\n  files: ['**/*.spec.ts']\n---\n# ts ext\n")
        self.cfg(CFG.replace("lang: [ts]", "lang: [ts, py]") + "tiers: {m_max_files: 1}\n")
        code, r, _ = self.files()
        self.assertEqual((code, r["tests"], r["non_test"]), (0, 3, 1), r)   # ts base, ts extension and py globs all count

    def test_without_test_globs_everything_counts_and_the_output_says_so(self):
        self.state("M")
        (self.task / "plan.md").write_text("### Step 1\n\n- CREATE: `src/a.test.ts` — t\n- CREATE: `src/b.ts` — c\n")
        lang = self.root / ".claude" / "omixflow" / "lang"
        lang.mkdir()
        (lang / "x.md").write_text("---\nport: lang\nname: x\ncapabilities: [verify, test_conventions, suppressions, navigation, deps_setup]\n---\n# x\n")
        self.cfg(CFG.replace("lang: [ts]", "lang: [x]") + "tiers: {m_max_files: 1}\n")
        code, r, _ = self.files()
        self.assertEqual((code, r["tests"], r["non_test"]), (1, None, 2))
        code, out, _ = run("files", "--task", str(self.task))
        self.assertIn("tests not told apart", out)

    def test_unreadable_inputs_are_exit_2_never_over(self):
        self.state("L")
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.assertIn("no plan", err)
        (self.task / "plan.md").write_text(PLAN)
        (self.task / "state.yaml").write_text("id: [unclosed\n")
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.assertIn("state.yaml", err)
        (self.task / "state.yaml").write_text("- not\n- a mapping\n")
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.assertIn("not a mapping", err)
        (self.task / "state.yaml").unlink()
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.state("M")
        (self.task / "plan.md").write_text("## Steps\n\n- MODIFY: `src/a.ts` — no `### Step N` heading\n")
        code, _, err = self.files()
        self.assertEqual(code, 2)
        self.assertIn("no step heading recognised", err)
        (self.task / "plan.md").write_text(PLAN)
        self.cfg(CFG + "tiers: {m_max_files: many}\n")
        code, _, err = self.files()
        self.assertEqual(code, 2)


SPEC_FOR_CHECK = """# Spec: T-1

## Scenarios

- S1 — adds. Given two numbers, when add, then the sum.
- S2 — rejects strings (D1). Given a string, when add, then `invalid`.
- S3 — subtracts. Given…
- ~~S4~~ — removed: folded into S1 (fix pass 1).

## Contracts

- `add()` (schemas) — new: (a, b) → number; project spec: `packages/schemas/spec.md`
- `OldThing<T>` (schemas) — removed, replaced by `add`

## Decisions

- D1: reject strings — explicit; rests on: zod 4 refuses coercion (checked)
"""
GOOD_PLAN = """# Plan: T-1

## Steps

### Step 1: schema

**Goal:** the add schema
**Covers:** S1–S3, `add`, `OldThing` (D1)
**Design:** `add` in action.ts; `OldThing` deleted. Unlike the `address` field, nothing else moves.
**Files:**

- CREATE: `packages/schemas/src/action.ts` — schema, replaces `packages/schemas/src/old.ts`
- MODIFY: `packages/schemas/src/index.ts` — re-export `packages/schemas/src/action.ts`
- DELETE: `packages/schemas/src/old.ts` — gone
  **Test checkpoint:**
- [ ] `typecheck` and `test` green; снимки визуального регресса обновлены
**Commit:** feat(schemas): add

### Step 2: wire

**Goal:** use the schema
**Covers:** S1
**Design:** import `add`
**Files:**

- MODIFY: `packages/schemas/src/action.ts` — created by step 1, exists for this step
  **Test checkpoint:**
- [ ] `test` green

## Project Specs to Update

- `packages/schemas/spec.md` — add

### Шаг 1: not a step, a subsection of the specs list

## Verification

- [ ] gates
"""


class PlanCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "omixflow").mkdir(parents=True)
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text(
            CFG + "  typecheck: tc\nworkspace:\n  base: main\n  branch: 'task/{id}'\n"
            "  submodules:\n    - path: omix\n      readonly: true\n")
        self.task = self.root / ".tasks" / "T-1"
        self.task.mkdir(parents=True)
        (self.task / "state.yaml").write_text("id: T-1\nkind: task\ntier: M\n")
        (self.task / "spec.md").write_text(SPEC_FOR_CHECK)
        (self.root / "packages" / "schemas" / "src").mkdir(parents=True)
        (self.root / "packages" / "schemas" / "src" / "index.ts").write_text("export {}\n")
        (self.root / "packages" / "schemas" / "src" / "old.ts").write_text("export const OldThing = 1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, plan: str, *extra: str) -> tuple[int, list[str]]:
        (self.task / "plan.md").write_text(plan)
        code, out, err = run("check", "--task", str(self.task), "--json", *extra)
        return code, (json.loads(out)["problems"] if out.strip() else [err])

    def test_a_sound_plan_passes_with_the_real_forms(self):
        """A file created by step 1 and modified by step 2; a path named in a description;
        `**Commit:**` inside a field; a range S1–S3; a removed scenario; `add()` and
        `OldThing<T>` in the spec; «визуального» next to a declared visual gate."""
        code, problems = self.check(GOOD_PLAN)
        self.assertEqual((code, problems), (0, []))
        code, out, _ = run("check", "--task", str(self.task))
        self.assertIn("PLAN CHECK: ok", out)
        code, out, _ = run("files", "--task", str(self.task), "--json")
        self.assertEqual(json.loads(out)["steps"], 2)             # the `### Шаг 1` under the specs list is not a step

    def test_each_mechanical_defect_is_a_line_for_the_architect(self):
        cases = [
            ("**Design:** `add` in action.ts; `OldThing` deleted. Unlike the `address` field, nothing else moves.\n", "",
             "step 1: no **Design:**"),
            ("`typecheck` and `test` green;", "`e2e` green and `typecheck`;", "names gate `e2e` the project does not declare"),
            ("- [ ] `test` green", "- [ ] the dialog opens", "checkpoint names no gate in backticks"),
            ("`typecheck` and `test` green;", "`test` green, затем проверить вручную;", "a check an agent cannot run («вручную»)"),
            ("`typecheck` and `test` green;", "`test` green, ручная проверка в headed Chrome;", "a check an agent cannot run"),
            ("- MODIFY: `packages/schemas/src/index.ts` — re-export", "- MODIFY: `omix/docs/arch.md` — bump",
             "is inside the read-only submodule `omix/`"),
            ("- CREATE: `packages/schemas/src/action.ts` — schema", "- CREATE: `packages/schemas/src/index.ts` — schema",
             "the file already exists (MODIFY?)"),
            ("- MODIFY: `packages/schemas/src/index.ts` — re-export", "- MODIFY: `packages/schemas/src/nope.ts` — re-export",
             "`packages/schemas/src/nope.ts` is not in the tree"),
            ("**Covers:** S1–S3, `add`, `OldThing` (D1)", "**Covers:** S1, S3, `add`, `OldThing` (D1)",
             "scenario S2 of spec.md is in no step's **Covers:**"),
            ("**Covers:** S1–S3, `add`, `OldThing` (D1)\n**Design:** `add` in action.ts; `OldThing` deleted.",
             "**Covers:** S1–S3, `add` (D1)\n**Design:** `add` in action.ts; OldThing deleted.",
             "contract `OldThing<T>` of spec.md is quoted in no step's Covers, Design or Files"),
            ("- `packages/schemas/spec.md` — add", "- `packages/server/spec.md` — x",
             "is stated by project spec `packages/schemas/spec.md`, which is not in «Project Specs to Update»"),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(old, GOOD_PLAN)
                code, problems = self.check(GOOD_PLAN.replace(old, new))
                self.assertEqual(code, 1, problems)
                self.assertTrue(any(expected in p for p in problems), (expected, problems))

    def test_read_only_matches_files_under_the_submodule_not_the_word_or_the_package_scope(self):
        """eps-eal-omix: `@eps-eal-omix/…` imports, `@omix/…` and «`omix/` не тронут» in a
        checkpoint are not edits of the submodule (pass-2 finding 18)."""
        plan = GOOD_PLAN.replace("**Design:** `add` in action.ts;", "**Design:** imports `@omix/core` and `@eps-eal-omix/schemas`; `add` in action.ts;") \
                        .replace("- [ ] `test` green", "- [ ] `test` green; `omix/` не тронут")
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))
        plan = GOOD_PLAN.replace("- [ ] `test` green", "- [ ] `test` green after patching `omix/docs/arch.md` temporarily")
        code, problems = self.check(plan)
        self.assertEqual(code, 1)
        self.assertTrue(any("touches the read-only submodule `omix/`" in p for p in problems), problems)
        plan = GOOD_PLAN.replace("**Design:** import `add`", "**Design:** temporarily edit `omix/docs/architecture/` to check the hash")
        code, problems = self.check(plan)                   # a directory under the submodule (AL-1138)
        self.assertTrue(any("touches the read-only submodule" in p for p in problems), problems)
        plan = GOOD_PLAN.replace("**Design:** import `add`", "**Design:** reads `omix/docs/arch.md` for the layout")
        code, problems = self.check(plan)                   # a mention without an edit verb
        self.assertEqual((code, problems), (0, []))
        plan = GOOD_PLAN.replace("**Design:** import `add`", "**Design:** update `@omix/docs/arch.md` mapping")
        code, problems = self.check(plan)                   # the lookbehind: a package scope, not the submodule
        self.assertEqual((code, problems), (0, []))

    def test_only_the_strike_form_marks_a_removed_scenario(self):
        spec = SPEC_FOR_CHECK.replace("- S3 — subtracts. Given…", "- S3 — subtracts; the old flag is removed. Given…")
        (self.task / "spec.md").write_text(spec)
        plan = GOOD_PLAN.replace("**Covers:** S1–S3, `add`, `OldThing` (D1)", "**Covers:** S1, S2, `add`, `OldThing` (D1)")
        code, problems = self.check(plan)
        self.assertEqual(code, 1)
        self.assertTrue(any("scenario S3 of spec.md" in p for p in problems), problems)

    def test_a_returned_task_s_iteration_section_holds_the_steps_to_check(self):
        """artifacts.md: a returned task adds `## Итерация N`; its steps are the ones not
        done — `check` reads the latest iteration, `files` counts every step (finding 20)."""
        (self.root / "packages" / "schemas" / "src" / "action.ts").write_text("done by iteration 1\n")
        plan = GOOD_PLAN + """
## Итерация 2

Замечания: NaN inputs.

### Step 3: nan

**Goal:** reject NaN
**Covers:** S1–S3, `add`, `OldThing`
**Design:** guard in `add`
**Files:**

- MODIFY: `packages/schemas/src/action.ts` — guard
  **Test checkpoint:**
- [ ] `test` green
"""
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))          # step 1's CREATE of an existing file is iteration 1, done
        code, out, _ = run("files", "--task", str(self.task), "--json")
        self.assertEqual(json.loads(out)["steps"], 3)
        # the iteration step covers only its own remark; coverage counts every step section (finding 21)
        plan2 = plan.replace("**Covers:** S1–S3, `add`, `OldThing`\n**Design:** guard in `add`", "**Covers:** S1\n**Design:** guard in `add`")
        plan2 += "\n### Verification (iteration 2)\n\n- [ ] проверить вручную в headed Chrome `e2e`\n"
        code, problems = self.check(plan2)
        self.assertEqual((code, problems), (0, []))          # the trailing `###` section is not step 3's checkpoint
        plan3 = plan2.replace("- MODIFY: `packages/schemas/src/action.ts` — guard", "- MODIFY: `packages/schemas/src/old.ts` — guard")
        code, problems = self.check(plan3)
        self.assertEqual(code, 1)
        self.assertTrue(any("old.ts` is not in the tree" in p for p in problems), problems)   # deleted by iteration 1

    def test_a_hash_comment_inside_a_fenced_block_does_not_end_the_step_and_lettered_steps_count(self):
        plan = GOOD_PLAN.replace("**Design:** import `add`",
                                 "**Design:** import `add`:\n\n```python\n# a comment, not a heading\nx = add(1, 2)\n```")
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))
        plan = GOOD_PLAN.replace("### Step 2: wire", "### Step 1a: wire")
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))
        code, out, _ = run("files", "--task", str(self.task), "--json")
        self.assertEqual(json.loads(out)["steps"], 2)
        code, problems = self.check(plan.replace("**Covers:** S1\n**Design:** import `add`", "**Design:** import `add`"))
        self.assertEqual(code, 1)
        self.assertIn("step 1a: no **Covers:**", problems)   # a lettered step is checked and named by its id
        # an iteration whose step heading repeats an earlier one: the current steps are found by position
        plan = GOOD_PLAN + "\n## Итерация 2\n\n### Step 1: schema\n\n**Goal:** again\n**Covers:** S1\n**Design:** d\n**Files:**\n\n" \
                           "- MODIFY: `packages/schemas/src/index.ts` — x\n  **Test checkpoint:**\n- [ ] `test` green\n"
        (self.root / "packages" / "schemas" / "src" / "action.ts").write_text("done by iteration 1\n")
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))          # iteration 1's CREATE of the now existing action.ts is not re-checked

    def test_mutations_the_pass_2_review_found_surviving(self):
        # a scenario named only in Design is not covered
        plan = GOOD_PLAN.replace("**Covers:** S1–S3, `add`, `OldThing` (D1)\n**Design:** `add` in action.ts;",
                                 "**Covers:** S1, S3, `add`, `OldThing` (D1)\n**Design:** S2 handled in `add` in action.ts;")
        code, problems = self.check(plan)
        self.assertTrue(any("scenario S2" in p for p in problems), problems)
        # an empty Covers
        code, problems = self.check(GOOD_PLAN.replace("**Covers:** S1\n**Design:** import `add`", "**Covers:**\n**Design:** import `add`"))
        self.assertTrue(any("step 2: no **Covers:**" in p for p in problems), problems)
        # a file line after an unknown bold label inside Files still belongs to Files
        plan = GOOD_PLAN.replace("- DELETE: `packages/schemas/src/old.ts` — gone",
                                 "**Note:** keep the order\n- MODIFY: `packages/schemas/src/nope.ts` — x\n- DELETE: `packages/schemas/src/old.ts` — gone")
        code, problems = self.check(plan)
        self.assertTrue(any("nope.ts` is not in the tree" in p for p in problems), problems)
        # «headed Chrome» on its own
        code, problems = self.check(GOOD_PLAN.replace("- [ ] `test` green", "- [ ] `test` green, then check in headed Chrome"))
        self.assertTrue(any("headed Chrome" in p for p in problems), problems)
        # DELETE then CREATE of the same path is fine
        plan = GOOD_PLAN.replace("- MODIFY: `packages/schemas/src/action.ts` — created by step 1, exists for this step",
                                 "- CREATE: `packages/schemas/src/old.ts` — anew after step 1 deleted it\n- MODIFY: `packages/schemas/src/old.ts` — and touched again")
        code, problems = self.check(plan)
        self.assertEqual((code, problems), (0, []))

    def test_a_deleted_then_modified_path_and_a_description_path_are_read_from_the_head_of_the_line(self):
        plan = GOOD_PLAN.replace("- MODIFY: `packages/schemas/src/action.ts` — created by step 1, exists for this step",
                                 "- MODIFY: `packages/schemas/src/old.ts` — deleted by step 1")
        code, problems = self.check(plan)
        self.assertEqual(code, 1)
        self.assertTrue(any("`packages/schemas/src/old.ts` is not in the tree" in p for p in problems), problems)

    def test_s_tier_steps_need_covers_files_and_a_checkpoint_only_and_no_spec_file(self):
        (self.task / "state.yaml").write_text("id: T-1\nkind: task\ntier: S\n")
        (self.task / "spec.md").write_text(
            "# Spec\n\n## Scenarios\n\n- S1 — adds. Given…\n\n## Steps\n\n### Step 1: fix\n\n**Covers:** S1\n**Files:**\n\n"
            "- MODIFY: `packages/schemas/src/index.ts` — x\n  **Test checkpoint:**\n- [ ] `test` green\n")
        code, out, err = run("check", "--task", str(self.task), "--json")
        self.assertEqual((code, json.loads(out)["problems"]), (0, []), err)

    def test_missing_spec_is_not_read_for_m_and_for_an_explicit_spec(self):
        (self.task / "spec.md").unlink()
        code, problems = self.check(GOOD_PLAN)
        self.assertEqual(code, 2)
        self.assertIn("no spec", problems[0])
        (self.task / "spec.md").write_text(SPEC_FOR_CHECK)
        code, problems = self.check(GOOD_PLAN, "--spec", str(self.task / "nope.md"))
        self.assertEqual(code, 2)

    def test_no_steps_is_reported_and_thresholds_are_not_rechecked(self):
        code, problems = self.check("# Plan\n\nno steps\n")
        self.assertEqual((code, problems), (1, ["no step heading recognised (`### Step N: …`)"]))
        many = "# Plan\n\n## Steps\n\n" + "".join(
            f"### Step {i}: s\n\n**Goal:** g\n**Covers:** S1–S3, `add`, `OldThing`\n**Design:** d\n**Files:**\n\n"
            f"- MODIFY: `packages/schemas/src/index.ts` — x\n  **Test checkpoint:**\n- [ ] `test`\n\n" for i in range(1, 10))
        many += "## Project Specs to Update\n\n- `packages/schemas/spec.md` — add\n"
        code, problems = self.check(many)
        self.assertEqual((code, problems), (0, []))          # nine steps are `files`' business, not `check`'s


if __name__ == "__main__":
    unittest.main()
