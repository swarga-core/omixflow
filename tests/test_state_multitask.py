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
            self.assertEqual(run("state.py", "init", tmp, "--id", "AL-9", "--kind", "multitask").returncode, 0)
            d = str(Path(tmp) / "p")
            self.assertEqual(run("state.py", "init", d, "--id", "AL-9/auth", "--kind", "part").returncode, 2)
            proc = run("state.py", "init", d, "--id", "AL-9/auth", "--kind", "part",
                       "--multitask-id", "AL-9", "--part", "auth")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run("state.py", "get", d, "multitask.part").stdout.strip(), "auth")


class LeadStateTests(unittest.TestCase):
    def init(self, tmp: str, *extra: str) -> str:
        d = str(Path(tmp) / ".tasks" / "AL-7")
        self.assertEqual(run("state.py", "init", d, "--id", "AL-7", "--kind", "task", *extra).returncode, 0)
        return d

    def lead(self, d: str) -> dict:
        return json.loads(run("state.py", "get", d, "lead").stdout)

    def test_finish_advances_and_complete_stays_an_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.init(tmp)
            self.assertEqual(run("state.py", "finish", d, "refine").stdout.strip(), "start")
            self.assertEqual(run("state.py", "complete", d, "start").stdout.strip(), "research")
            self.assertEqual(run("state.py", "finish", d, "lunch").returncode, 2)

    def test_finish_reminds_about_lead_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = self.init(tmp)
            proc = run("state.py", "finish", plain, "refine")
            self.assertEqual((proc.stdout.strip(), proc.stderr.strip()), ("start", ""))
            led = str(Path(tmp) / ".tasks" / "AL-9")
            run("state.py", "init", led, "--id", "AL-9", "--kind", "task", "--lead", "lead-omix")
            proc = run("state.py", "finish", led, "refine")
            self.assertEqual(proc.stdout.strip(), "start")
            self.assertIn("под лидом lead-omix: отправь notice о фазе refine", proc.stderr)

    def test_init_without_lead_has_no_lead_and_ask_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.init(tmp)
            self.assertNotIn("lead", json.loads(run("state.py", "get", d).stdout))
            proc = run("state.py", "ask", d, "Q1:wait")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("без лида", proc.stderr)

    def test_ask_ack_close_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.init(tmp, "--lead", "lead-omix")
            self.assertEqual(self.lead(d), {"name": "lead-omix", "asked": 0, "open": []})
            self.assertEqual(run("state.py", "ask", d, "Q1:wait", "F3:nowait").stdout.strip(), "1")
            self.assertEqual(run("state.py", "ask", d, "P1:wait").stdout.strip(), "2")
            run("state.py", "ack", d, "1", "Q1=решаю", "F3=E-7")
            lead = self.lead(d)
            self.assertEqual(lead["asked"], 2)
            self.assertEqual(lead["open"][0], {"n": 1, "items": {"Q1": "wait", "F3": "nowait"},
                                               "ack": {"Q1": "решаю", "F3": "E-7"}})
            # partial decision closes one item; the question stays open
            self.assertEqual(json.loads(run("state.py", "close", d, "1", "Q1").stdout), {"F3": "nowait"})
            self.assertEqual(self.lead(d)["open"][0]["ack"], {"F3": "E-7"})
            # closing the rest removes the question; numbering survives
            run("state.py", "close", d, "1")
            self.assertEqual([q["n"] for q in self.lead(d)["open"]], [2])
            self.assertEqual(run("state.py", "ask", d, "P1:wait").stdout.strip(), "3")

    def test_init_continues_question_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.init(tmp, "--lead", "lead-omix", "--asked", "2")
            self.assertEqual(run("state.py", "ask", d, "P1:wait").stdout.strip(), "3")
            other = str(Path(tmp) / ".tasks" / "AL-8")
            proc = run("state.py", "init", other, "--id", "AL-8", "--kind", "task", "--asked", "2")
            self.assertEqual(proc.returncode, 2)

    def test_lead_commands_reject_bad_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.init(tmp, "--lead", "lead-omix")
            run("state.py", "ask", d, "Q1:wait")
            cases = [
                ("ask", d, "Q1"),                 # no wait flag
                ("ask", d, "Q1:maybe"),           # unknown wait flag
                ("ask", d, "Q1:wait", "Q1:nowait"),  # duplicate label
                ("ack", d, "1", "Q9=решаю"),      # unknown item
                ("ack", d, "1", "Q1"),            # no value
                ("ack", d, "5", "Q1=решаю"),      # question not open
                ("close", d, "1", "Q9"),          # unknown item
                ("close", d, "5"),                # question not open
            ]
            for args in cases:
                with self.subTest(args=args):
                    self.assertEqual(run("state.py", *args).returncode, 2)
            self.assertEqual(self.lead(d)["asked"], 1)


class ProfileTests(unittest.TestCase):
    def init(self, d: str, *args: str) -> subprocess.CompletedProcess:
        return run("state.py", "init", d, *args)

    def test_research_profile_phase_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / "R-1")
            proc = self.init(d, "--id", "R-1", "--kind", "task", "--profile", "research")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run("state.py", "get", d, "profile").stdout.strip(), "research")
            self.assertEqual(run("state.py", "get", d, "phase").stdout.strip(), "refine")
            run("state.py", "complete", d, "refine")
            self.assertEqual(run("state.py", "complete", d, "start").stdout.strip(), "research")
            self.assertEqual(run("state.py", "next", d).stdout.strip(), "research")
            self.assertEqual(run("state.py", "set", d, "phase=spec").returncode, 2)
            self.assertEqual(run("state.py", "complete", d, "spec").returncode, 2)
            self.assertEqual(run("state.py", "complete", d, "research").stdout.strip(), "finalize")
            self.assertEqual(run("state.py", "set", d, "phase=finalize").returncode, 0)
            self.assertEqual(run("state.py", "complete", d, "finalize").stdout.strip(), "done")
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertEqual(state["completed"], ["refine", "start", "research", "finalize"])

    def test_legacy_state_without_profile_is_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "L-1"
            d.mkdir()
            f = d / "state.yaml"
            f.write_text("schema: 1\nid: L-1\nkind: task\nphase: research\n"
                         "completed:\n- refine\n- start\n", encoding="utf-8")
            before = f.read_bytes()
            proc = run("state.py", "get", str(d), "profile")
            self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "full"))
            self.assertEqual(run("state.py", "next", str(d)).stdout.strip(), "research")
            self.assertEqual(f.read_bytes(), before)
            self.assertEqual(run("state.py", "set", str(d), "phase=spec").returncode, 0)
            self.assertEqual(run("state.py", "complete", str(d), "research").stdout.strip(), "spec")
            self.assertEqual(run("state.py", "complete", str(d), "spec").stdout.strip(), "plan")
            self.assertNotIn("profile", json.loads(run("state.py", "get", str(d)).stdout))

    def test_profile_json_and_forced_without_triage(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / "R-2")
            proc = self.init(d, "--id", "R-2", "--kind", "task", "--profile", "research", "--forced")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("--forced", proc.stderr)
            self.assertEqual(self.init(d, "--id", "R-2", "--kind", "task", "--profile", "research").returncode, 0)
            props = json.loads(run("state.py", "get", d, "profile", "--json").stdout)
            self.assertEqual(props["profile"], "research")
            self.assertEqual((props["mutates"], props["finalize_artifact"], props["part_runner"]),
                             (False, "research", "scheduler"))
            self.assertEqual(run("state.py", "get", d, "profile").stdout.strip(), "research")

    def test_new_state_persists_default_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.init(tmp, "--id", "F-1", "--kind", "task", "--tier", "M").returncode, 0)
            state = json.loads(run("state.py", "get", tmp).stdout)
            self.assertEqual((state["profile"], state["tier"]), ("full", "M"))

    def test_part_inherits_parent_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.init(tmp, "--id", "AL-9", "--kind", "multitask", "--profile", "research")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            d = str(Path(tmp) / "auth")
            part = ("--id", "AL-9/auth", "--kind", "part", "--multitask-id", "AL-9", "--part", "auth")
            self.assertEqual(self.init(d, *part, "--profile", "full").returncode, 2)
            self.assertFalse((Path(d) / "state.yaml").exists())
            proc = self.init(d, *part)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run("state.py", "get", d, "profile").stdout.strip(), "research")
            self.assertEqual(run("state.py", "get", d, "tier").stdout.strip(), "null")
            self.assertEqual(self.init(d, *part, "--profile", "research", "--force").returncode, 0)

    def test_part_parent_must_be_matching_multitask(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / "auth")
            part = ("--id", "AL-9/auth", "--kind", "part", "--part", "auth")
            # no parent state
            self.assertEqual(self.init(d, *part, "--multitask-id", "AL-9").returncode, 2)
            # parent is not a multitask
            self.assertEqual(self.init(tmp, "--id", "AL-9", "--kind", "task").returncode, 0)
            self.assertEqual(self.init(d, *part, "--multitask-id", "AL-9").returncode, 2)
            # parent multitask with another id
            self.assertEqual(self.init(tmp, "--id", "AL-9", "--kind", "multitask", "--force").returncode, 0)
            self.assertEqual(self.init(d, *part, "--multitask-id", "AL-8").returncode, 2)
            self.assertEqual(self.init(d, *part, "--multitask-id", "AL-9").returncode, 0)

    def test_tier_and_unknown_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = str(Path(tmp) / "R-2")
            self.assertEqual(self.init(d, "--id", "R-2", "--kind", "task",
                                       "--profile", "research", "--tier", "M").returncode, 2)
            self.assertEqual(self.init(d, "--id", "R-2", "--kind", "task", "--profile", "audit").returncode, 2)
            self.assertFalse((Path(d) / "state.yaml").exists())
            self.assertEqual(self.init(d, "--id", "R-2", "--kind", "task", "--profile", "research").returncode, 0)
            state = json.loads(run("state.py", "get", d).stdout)
            self.assertIn("tier", state)
            self.assertIsNone(state["tier"])

    def test_set_profile_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.init(tmp, "--id", "F-2", "--kind", "task").returncode, 0)
            self.assertEqual(run("state.py", "set", tmp, "profile=audit").returncode, 2)
            run("state.py", "complete", tmp, "refine")
            self.assertEqual(run("state.py", "set", tmp, "profile=research").returncode, 0)
            self.assertEqual(run("state.py", "get", tmp, "profile").stdout.strip(), "research")
            run("state.py", "set", tmp, "profile=full", "completed=[\"refine\",\"spec\"]")
            self.assertEqual(run("state.py", "set", tmp, "profile=research").returncode, 2)
            self.assertEqual(run("state.py", "get", tmp, "profile").stdout.strip(), "full")


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


RESEARCH_DESCRIPTION = DESCRIPTION.replace(
    "<!-- omixflow:multitask:start -->", "<!-- omixflow:multitask:start profile=research -->")

HANDWRITTEN = """Текст до блока.

<!--  omixflow:multitask:start  -->
| # | part | title | depends | owner | status | branch | commit |
|---|------|---|---|---|---|---|---|
|1|auth-flow|Экран логина|—|swarga|done|task/AL-9-auth-flow|a1b2c3d|
| 2 | i18n-keys   | Словарь |  -  | - | pending | - | - |
<!-- omixflow:multitask:end -->
Текст после блока.
"""


class MarkerTests(unittest.TestCase):
    def cli(self, text: str, *args: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.md"
            f.write_text(text, encoding="utf-8")
            return run("multitask.py", args[0], "--from", str(f), *args[1:])

    def test_attributed_marker_found_by_has_extract_meta(self):
        self.assertEqual(self.cli(RESEARCH_DESCRIPTION, "has").returncode, 0)
        self.assertEqual(len(mt.extract(RESEARCH_DESCRIPTION)), 4)
        proc = self.cli(RESEARCH_DESCRIPTION, "meta")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        meta = json.loads(proc.stdout)
        self.assertEqual(meta["profile"], "research")
        self.assertEqual(meta["attrs"], {"profile": "research"})
        self.assertEqual(meta["repos"], [])
        self.assertEqual(json.loads(self.cli(DESCRIPTION, "meta").stdout)["profile"], "full")

    def test_set_preserves_attributed_marker_line(self):
        proc = self.cli(RESEARCH_DESCRIPTION, "set", "--part", "i18n-keys", "status=in-work", "owner=swarga")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<!-- omixflow:multitask:start profile=research -->\n", proc.stdout)
        self.assertEqual(mt.block_meta(proc.stdout)["profile"], "research")

    def test_set_rewrites_only_target_row(self):
        proc = self.cli(HANDWRITTEN, "set", "--part", "i18n-keys", "status=in-work", "owner=ivanov")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        before, after = HANDWRITTEN.splitlines(True), proc.stdout.splitlines(True)
        self.assertEqual(len(before), len(after))
        diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(diff, [6])
        self.assertEqual(after[6], "| 2 | i18n-keys | Словарь | - | ivanov | in-work | - | - |\n")

    def test_noop_set_is_byte_identical(self):
        for pairs in (["status=done", "owner=swarga"], ["owner=—", "depends=—"]):
            part = "auth-flow" if pairs[0] == "status=done" else "i18n-keys"
            proc = self.cli(HANDWRITTEN, "set", "--part", part, *pairs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, HANDWRITTEN, pairs)

    def test_canonical_block_round_trips(self):
        text = "Описание.\n\n" + mt.render(mt.extract(DESCRIPTION)) + "\n"
        self.assertEqual(mt.render(mt.extract(text)), text[len("Описание.\n\n"):-1])
        there = mt.set_row(text, "i18n-keys", ["status=in-work", "owner=swarga"])
        self.assertNotEqual(there, text)
        self.assertEqual(mt.set_row(there, "i18n-keys", ["status=pending", "owner=—"]), text)

    def test_set_key_without_column_is_an_error(self):
        text = HANDWRITTEN.replace(" commit |", " |", 1).replace("|---|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|---|")
        text = text.replace("|a1b2c3d|", "|").replace(" | - | - |\n", " | - |\n")
        self.assertEqual(self.cli(text, "set", "--part", "i18n-keys", "status=in-work", "owner=x").returncode, 0)
        proc = self.cli(text, "set", "--part", "i18n-keys", "commit=abc1234")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("колонки 'commit' нет в заголовке", proc.stderr)

    def test_render_emits_profile_attribute_only_for_non_full(self):
        rows = mt.extract(DESCRIPTION)
        self.assertTrue(mt.render(rows).startswith(mt.MARK_START + "\n"))
        self.assertTrue(mt.render(rows, "research").startswith(
            "<!-- omixflow:multitask:start profile=research -->\n"))

    def test_second_start_marker_is_an_error(self):
        text = DESCRIPTION + "\n<!-- omixflow:multitask:start -->\n"
        self.assertEqual(self.cli(text, "has").returncode, 2)
        with self.assertRaises(lib.OmixflowError):
            mt.extract(text)

    def test_inline_marker_in_prose_is_not_a_marker(self):
        prose = "Блок начинается с `<!-- omixflow:multitask:start -->` в описании.\n"
        self.assertEqual(self.cli(prose, "has").returncode, 1)
        text = prose + DESCRIPTION
        self.assertEqual(self.cli(text, "has").returncode, 0)
        self.assertEqual(len(mt.extract(text)), 4)
        out = self.cli(text, "set", "--part", "i18n-keys", "status=skipped")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith(prose))
        self.assertEqual(self.cli("Маркер в конце фразы <!-- omixflow:multitask:start -->\n", "has").returncode, 1)
        self.assertEqual(self.cli("<!-- omixflow:multitask:start --> открывает блок.\n", "has").returncode, 1)

    def test_end_marker_must_be_whole_line(self):
        start_only = "<!-- omixflow:multitask:start -->\n| # | part |\n"
        self.assertEqual(self.cli(start_only, "has").returncode, 2)
        text = DESCRIPTION.replace(
            "| 3 | profile-store",
            "Конец блока это `<!-- omixflow:multitask:end -->`, не раньше.\n| 3 | profile-store")
        self.assertEqual(len(mt.extract(text)), 4)

    def test_marker_errors_rejected_and_tolerated(self):
        bad = {
            "unknown key": "profle=research",
            "duplicate key": "profile=research profile=research",
            "unknown profile": "profile=audit",
            "malformed": "research",
        }
        for label, attrs in bad.items():
            text = DESCRIPTION.replace("<!-- omixflow:multitask:start -->",
                                       f"<!-- omixflow:multitask:start {attrs} -->")
            with self.subTest(label):
                self.assertTrue(mt.marker_errors(text))
                validate = self.cli(text, "validate")
                self.assertEqual(validate.returncode, 1)
                self.assertIn("маркер" if label != "unknown profile" else "неизвестный профиль audit", validate.stdout)
                self.assertEqual(self.cli(text, "meta").returncode, 2)
                self.assertEqual(self.cli(text, "ready").returncode, 2)
                self.assertEqual(self.cli(text, "file", "--id", "AL-9", "--title", "К").returncode, 2)
                self.assertEqual(self.cli(text, "extract").returncode, 0)
                self.assertEqual(self.cli(text, "has").returncode, 0)
                self.assertEqual(self.cli(text, "waves").returncode, 0)
                out = self.cli(text, "set", "--part", "i18n-keys", "status=skipped")
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn(f"<!-- omixflow:multitask:start {attrs} -->\n", out.stdout)
        self.assertEqual(mt.marker_errors(RESEARCH_DESCRIPTION), [])
        self.assertEqual(mt.marker_errors(DESCRIPTION), [])
        self.assertEqual(self.cli(RESEARCH_DESCRIPTION, "validate").returncode, 0)

    def test_crlf_block(self):
        for label, text in (("legacy", HANDWRITTEN.replace("\n", "\r\n")),
                            ("attributed", RESEARCH_DESCRIPTION.replace("\n", "\r\n"))):
            with self.subTest(label):
                self.assertEqual(self.cli(text, "has").returncode, 0)
                self.assertTrue(mt.extract(text))
                self.assertEqual(mt.marker_errors(text), [])
        crlf = HANDWRITTEN.replace("\n", "\r\n")
        self.assertEqual([r["part"] for r in mt.extract(crlf)], ["auth-flow", "i18n-keys"])
        self.assertEqual(mt.block_meta(RESEARCH_DESCRIPTION.replace("\n", "\r\n"))["profile"], "research")
        out = mt.set_row(crlf, "i18n-keys", ["status=in-work", "owner=ivanov"])
        before, after = crlf.split("\r\n"), out.split("\r\n")
        self.assertEqual(len(before), len(after))
        self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b], [6])
        self.assertEqual(after[6], "| 2 | i18n-keys | Словарь | - | ivanov | in-work | - | - |")
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_set_rejects_pipe_and_newline(self):
        for value in ("A | B", "A\nB", "A\rB"):
            with self.subTest(value=value):
                with self.assertRaises(lib.OmixflowError) as ctx:
                    mt.set_row(HANDWRITTEN, "i18n-keys", [f"title={value}"])
                self.assertIn("недопустимы в ячейке", str(ctx.exception))
        proc = self.cli(HANDWRITTEN, "set", "--part", "i18n-keys", "title=A | B")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_declared_profile(self):
        text = DESCRIPTION.replace("<!-- omixflow:multitask:start -->",
                                   "<!-- omixflow:multitask:start profile=research bogus=1 -->")
        self.assertEqual(mt.declared_profile(text), "research")
        self.assertEqual(mt.declared_profile(text.replace("=research", "=audit")), "full")
        self.assertEqual(mt.declared_profile(DESCRIPTION), "full")


REPO_DESCRIPTION = """Исследование.

<!-- omixflow:multitask:start profile=research -->
| # | part | title | repo | depends | owner | status | branch | commit |
|---|---|---|---|---|---|---|---|---|
| 1 | app-usage | Использование | — | — | swarga | in-work | — | — |
| 2 | lib-api | API библиотеки | omix-lib | — | swarga | in-work | — | — |
| 3 | lib-store | Стор библиотеки | omix-lib | — | — | pending | — | — |
| 4 | eal-ui | UI приложения | eal | — | — | pending | — | — |
| 5 | home-docs | Документация | — | — | — | pending | — | — |
| 6 | wrap-up | Итог | — | lib-api | — | pending | — | — |
<!-- omixflow:multitask:end -->
"""


class RepoProfileTests(unittest.TestCase):
    def cli(self, text: str, *args: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "d.md"
            f.write_text(text, encoding="utf-8")
            return run("multitask.py", args[0], "--from", str(f), *args[1:])

    def full(self, text: str) -> str:
        return text.replace("<!-- omixflow:multitask:start profile=research -->", mt.MARK_START)

    def test_repo_parsed_and_rendered_after_title(self):
        rows = mt.extract(REPO_DESCRIPTION)
        self.assertEqual([r["repo"] for r in rows], [None, "omix-lib", "omix-lib", "eal", None, None])
        block = mt.render(rows, "research").splitlines()
        self.assertEqual(block[1], "| # | part | title | repo | depends | owner | status | branch | commit |")
        self.assertEqual(block[3], "| 1 | app-usage | Использование | — | — | swarga | in-work | — | — |")
        self.assertEqual(block[4], "| 2 | lib-api | API библиотеки | omix-lib | — | swarga | in-work | — | — |")
        self.assertEqual(mt.block_meta(REPO_DESCRIPTION)["repos"], ["omix-lib", "eal"])

    def test_render_without_repo_is_unchanged(self):
        rows = mt.extract(DESCRIPTION)[:2]
        self.assertTrue(all(r["repo"] is None for r in rows))
        self.assertEqual(mt.render(rows), "\n".join([
            "<!-- omixflow:multitask:start -->",
            "| # | part | title | depends | owner | status | branch | commit |",
            "|---|---|---|---|---|---|---|---|",
            "| 1 | auth-flow | Экран логина | — | swarga | done | task/AL-9-auth-flow | a1b2c3d |",
            "| 2 | i18n-keys | Словарь | — | — | pending | — | — |",
            "<!-- omixflow:multitask:end -->"]))

    def test_validate_repo_rules(self):
        self.assertEqual(self.cli(REPO_DESCRIPTION, "validate").returncode, 0)
        self.assertEqual(self.cli(REPO_DESCRIPTION, "validate", "--repos", "omix-lib,eal").returncode, 0)
        proc = self.cli(REPO_DESCRIPTION, "validate", "--repos", "omix-lib")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("'eal' нет в workspace.repos", proc.stdout)
        proc = self.cli(self.full(REPO_DESCRIPTION), "validate")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("недопустим в мутирующем профиле full", proc.stdout)
        self.assertTrue(any("должен быть slug" in e for e in
                            mt.validate(mt.extract(REPO_DESCRIPTION.replace("| eal |", "| Eal_X |")), "research")))

    def test_declared_profile_drives_row_validation_in_set_and_waves(self):
        tolerated = REPO_DESCRIPTION.replace("profile=research -->", "profile=research bogus=1 -->")
        unknown = REPO_DESCRIPTION.replace("profile=research -->", "profile=audit -->")
        for text, code in ((REPO_DESCRIPTION, 0), (tolerated, 0), (self.full(REPO_DESCRIPTION), 2), (unknown, 2)):
            with self.subTest(marker=text.splitlines()[2]):
                self.assertEqual(self.cli(text, "set", "--part", "home-docs", "status=skipped").returncode, code)
                self.assertEqual(self.cli(text, "waves").returncode, code)

    def test_set_repo_only_while_pending(self):
        proc = self.cli(REPO_DESCRIPTION, "set", "--part", "lib-store", "repo=eal")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(mt.extract(proc.stdout)[2]["repo"], "eal")
        proc = self.cli(REPO_DESCRIPTION, "set", "--part", "lib-store", "repo=—")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNone(mt.extract(proc.stdout)[2]["repo"])
        proc = self.cli(REPO_DESCRIPTION, "set", "--part", "lib-api", "repo=eal")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("только у pending", proc.stderr)
        self.assertEqual(self.cli(REPO_DESCRIPTION, "set", "--part", "lib-store", "repo=ghost",
                                  "--repos", "omix-lib,eal").returncode, 2)

    def test_add_part_appends_a_pending_row_and_keeps_the_rest(self):
        proc = self.cli(DESCRIPTION, "add-part", "--part", "profile-ui — Экран профиля", "--depends", "profile-store")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        before, after = DESCRIPTION.splitlines(), proc.stdout.splitlines()
        end = next(i for i, ln in enumerate(before) if ln.strip() == mt.MARK_END)
        self.assertEqual(after[:end], before[:end], "rows and text before the new row stay byte-for-byte")
        self.assertEqual(after[end], "| 5 | profile-ui | Экран профиля | profile-store | — | pending | — | — |")
        self.assertEqual(after[end + 1:], before[end:])
        self.assertEqual(self.cli(DESCRIPTION, "add-part", "--part", "auth-flow — Ещё раз", "--depends", "—").returncode, 2)
        proc = self.cli(DESCRIPTION, "add-part", "--part", "x-part — X", "--depends", "ghost")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ghost", proc.stderr)

    def test_first_repo_adds_the_column(self):
        proc = self.cli(RESEARCH_DESCRIPTION, "add-part", "--part", "lib-api — API библиотеки", "--depends", "—",
                        "--repo", "omix-lib", "--repos", "omix-lib")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<!-- omixflow:multitask:start profile=research -->", proc.stdout)
        self.assertEqual(mt.block_header(proc.stdout)[3], "repo")
        rows = {r["part"]: r for r in mt.extract(proc.stdout)}
        self.assertEqual((rows["lib-api"]["repo"], rows["lib-api"]["status"]), ("omix-lib", "pending"))
        self.assertEqual((rows["auth-flow"]["status"], rows["auth-flow"]["owner"]), ("done", "swarga"))
        proc = self.cli(RESEARCH_DESCRIPTION, "set", "--part", "i18n-keys", "repo=omix-lib")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual({r["part"]: r["repo"] for r in mt.extract(proc.stdout)}["i18n-keys"], "omix-lib")
        self.assertEqual(self.cli(RESEARCH_DESCRIPTION, "set", "--part", "auth-flow", "repo=omix-lib").returncode, 2)
        self.assertEqual(self.cli(RESEARCH_DESCRIPTION, "set", "--part", "i18n-keys", "repo=—").stdout,
                         RESEARCH_DESCRIPTION, "«—» without the column changes nothing")

    def test_seed_profile_and_repo(self):
        proc = run("multitask.py", "seed", "--parts", "lib-api — API", "app-usage — Использование",
                   "--repo", "omix-lib", "—", "--profile", "research", "--repos", "omix-lib")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], "<!-- omixflow:multitask:start profile=research -->")
        self.assertEqual(lines[1], "| # | part | title | repo | depends | owner | status | branch | commit |")
        meta = mt.block_meta(proc.stdout)
        self.assertEqual((meta["profile"], meta["repos"]), ("research", ["omix-lib"]))
        self.assertEqual([r["repo"] for r in mt.extract(proc.stdout)], ["omix-lib", None])
        self.assertEqual(run("multitask.py", "seed", "--parts", "lib-api — API", "--repo", "omix-lib").returncode, 2)
        self.assertEqual(run("multitask.py", "seed", "--parts", "lib-api — API", "--repo", "omix-lib",
                             "--profile", "research", "--repos", "eal").returncode, 2)
        self.assertEqual(run("multitask.py", "seed", "--parts", "a — A", "--profile", "audit").returncode, 2)

    def test_ready_parallel_and_repos(self):
        proc = self.cli(REPO_DESCRIPTION, "ready", "--owner", "swarga", "--parallel", "4")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        r = json.loads(proc.stdout)
        self.assertEqual(r["ready"], ["lib-store", "eal-ui", "home-docs"])
        self.assertEqual(r["slots"], 2)
        self.assertEqual(list(r["ready_by_repo"].items()),
                         [("—", ["home-docs"]), ("omix-lib", ["lib-store"]), ("eal", ["eal-ui"])])
        self.assertEqual(r["active_repos"], ["—", "omix-lib"])
        self.assertEqual(json.loads(self.cli(REPO_DESCRIPTION, "ready", "--owner", "swarga",
                                             "--parallel", "1").stdout)["slots"], 0)
        self.assertIsNone(json.loads(self.cli(REPO_DESCRIPTION, "ready").stdout)["slots"])
        # someone else's active part counts neither for slots nor for active_repos
        other = REPO_DESCRIPTION.replace("| eal | — | — | pending |", "| eal | — | ivanov | in-work |")
        r = json.loads(self.cli(other, "ready", "--owner", "swarga", "--parallel", "4").stdout)
        self.assertEqual((r["slots"], r["active_repos"]), (2, ["—", "omix-lib"]))

    def test_file_integration_and_repo_lines(self):
        research = self.cli(REPO_DESCRIPTION, "file", "--id", "AL-7", "--title", "И")
        self.assertEqual(research.returncode, 0, research.stderr)
        self.assertIn("части коммитятся по пути `.tasks/AL-7/{part}/` в `task/AL-7`", research.stdout)
        self.assertIn("`docs(AL-7): research {part} — {title}`", research.stdout)
        self.assertNotIn("workspace.integration", research.stdout)
        self.assertIn("- Репозиторий: omix-lib", research.stdout)
        self.assertIn("- Репозиторий: домашний", research.stdout)
        home_only = self.cli(REPO_DESCRIPTION.replace("| omix-lib |", "| — |").replace("| eal |", "| — |"),
                             "file", "--id", "AL-7", "--title", "И")
        self.assertIn("- Репозиторий: домашний", home_only.stdout)
        full = self.cli(DESCRIPTION, "file", "--id", "AL-9", "--title", "К")
        self.assertIn("по `workspace.integration`", full.stdout)
        self.assertNotIn("коммитятся по пути", full.stdout)
        self.assertNotIn("Репозиторий", full.stdout)

    def test_render_cli_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "rows.json"
            f.write_text(json.dumps(mt.extract(REPO_DESCRIPTION)), encoding="utf-8")
            proc = run("multitask.py", "render", "--rows", str(f), "--profile", "research")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.startswith("<!-- omixflow:multitask:start profile=research -->\n"))
            self.assertTrue(run("multitask.py", "render", "--rows", str(f)).stdout.startswith(mt.MARK_START + "\n"))


if __name__ == "__main__":
    unittest.main()
