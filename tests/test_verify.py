"""Gate sets, change areas and orchestrator checks (adapters/lang/PORT.md, «Гейты»,
«Проверки оркестратора»): lib.verify_plan, `resolve.py verify`, doctor."""
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
import omixflow_lib as lib  # noqa: E402

BASE_CFG = ("version: 1\ntracker: none\nforge: none\nlang: [ts]\n"
            "workspace: {base: main, branch: 'task/{id}'}\n")
FULL = """areas:
  sim: [sim/**]
  client: [client/]
  docs: ["**/*.md"]
verify:
  typecheck: tc
  test: tt
  lint: { cmd: ll, criterion: zero-diagnostics }
  build: { cmd: bb, background: true }
  e2e: { cmd: ee, when: [client] }
checks:
  editor: { when: [sim, client], at: [step, review, delivery] }
  device: { when: [sim] }
  merged: { at: [accept] }
"""


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


class GlobTests(unittest.TestCase):
    def test_globs_follow_path_segments(self):
        cases = [("sim/**", "sim/a/b.cs", True), ("sim/**", "simx/a.cs", False), ("client/", "client/x/y", True),
                 ("**/*.md", "README.md", True), ("**/*.md", "a/b/c.md", True), ("*.md", "a/b.md", False),
                 ("src/?.ts", "src/a.ts", True), ("src/?.ts", "src/ab.ts", False), ("a?b", "a/b", False),
                 ("a.b", "axb", False), ("docs/*.md", "docs/заметка.md", True)]
        for pattern, path, hit in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(bool(lib.glob_regex(pattern).match(path)), hit)

    def test_touched_areas_keep_config_order(self):
        areas = {"docs": ["**/*.md"], "sim": ["sim/**"], "client": ["client/**"]}
        self.assertEqual(lib.touched_areas(areas, ["sim/a.cs", "x.md"]), ["docs", "sim"])
        self.assertEqual(lib.touched_areas(areas, ["tools/x.py"]), [])


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        self.write("README.md", "x")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        git(self.root, "checkout", "-q", "-b", "task/T-1")
        (self.root / lib.CONFIG_REL).parent.mkdir(parents=True)
        (self.root / lib.CONFIG_REL).write_text(BASE_CFG + FULL, encoding="utf-8")
        (self.root / ".gitignore").write_text(".claude/\n.tasks/\n", encoding="utf-8")
        git(self.root, "add", ".gitignore")
        git(self.root, "commit", "-q", "-m", "ignore")
        self.cfg = lib.load_config(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, text: str = "x") -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit_all(self, msg: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)

    def plan(self, at: str, base: str | None = None, checked: dict | None = None) -> dict:
        return lib.verify_plan(self.cfg, self.root, at, base, checked)

    @staticmethod
    def names(items: list) -> list:
        return [i["name"] for i in items]

    def test_config_is_valid(self):
        self.assertEqual(lib.validate_config(self.cfg), [])

    def test_step_set_is_the_main_gates_plus_touched_when_gates(self):
        self.write("tools/x.py")  # untracked, no area
        p = self.plan("step")
        self.assertEqual(self.names(p["gates"]), ["typecheck", "test", "lint"])
        self.assertEqual(p["areas"], [])
        self.assertEqual(p["checks"], [])
        self.write("client/ui.cs")
        p = self.plan("step")
        self.assertEqual(self.names(p["gates"]), ["typecheck", "test", "lint", "e2e"])
        self.assertEqual(p["areas"], ["client"])
        self.assertEqual(self.names(p["checks"]), ["editor"])
        self.assertEqual(p["on_demand"], ["device"])
        self.assertEqual(p["gates"][2]["criterion"], "zero-diagnostics")

    def test_structure_is_a_step_gate_when_declared(self):
        """0.9 step 7: structural invariants (dependency direction, forbidden imports) live in a
        gate the step set always runs, not in the prose of project specs."""
        import copy
        cfg = copy.deepcopy(self.cfg)
        cfg["verify"]["structure"] = {"cmd": "dc", "criterion": "exit-code"}
        self.write("tools/x.py")
        self.assertIn("structure", self.names(lib.verify_plan(cfg, self.root, "step")["gates"]))
        self.assertNotIn("structure", self.names(lib.verify_plan(self.cfg, self.root, "step")["gates"]))
        self.assertIn("structure", lib.GATES)

    def test_also_adds_the_gates_a_checkpoint_names(self):
        """T-9: the step 6 checkpoint asked for build, which has no `when` and is outside the step set."""
        self.write("tools/x.py")
        p = lib.verify_plan(self.cfg, self.root, "step", also=["build", "lint", "visual", "visual"])
        self.assertEqual(self.names(p["gates"]), ["typecheck", "test", "lint", "build"])
        self.assertEqual([g.get("also") for g in p["gates"]], [None, None, None, True])
        self.assertEqual((p["gates"][3]["cmd"], p["gates"][3]["background"]), ("bb", True))
        self.assertNotIn("build", [s.get("gate") for s in p["skipped"]])
        self.assertIn({"gate": "e2e", "why": "when ['client']: области не задеты"}, p["skipped"])
        self.assertEqual(p["also_missing"], ["visual"])  # a port gate the project does not declare
        self.assertNotIn("also_missing", self.plan("step"))
        with self.assertRaises(lib.OmixflowError):
            lib.verify_plan(self.cfg, self.root, "step", also=["deploy"])
        res = run("resolve.py", "verify", "--at", "step", "--project", str(self.root), "--also", "build", "e2e")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.names(json.loads(res.stdout)["gates"]), ["typecheck", "test", "lint", "build", "e2e"])
        res = run("resolve.py", "verify", "--at", "step", "--project", str(self.root), "--also", "deploy")
        self.assertEqual(res.returncode, 2)
        self.assertIn("не имя гейта", res.stderr)

    def test_step_looks_only_at_uncommitted_changes(self):
        self.write("sim/core.cs")
        self.commit_all("sim")
        self.assertEqual(self.plan("step")["areas"], [])
        self.write("sim/core.cs", "y")  # tracked and modified
        self.assertEqual(self.plan("step")["areas"], ["sim"])

    def test_full_set_runs_gates_without_when_and_touched_when_gates(self):
        self.write("sim/core.cs")
        self.commit_all("sim")
        p = self.plan("review", base="main")
        self.assertEqual(self.names(p["gates"]), ["typecheck", "test", "lint", "build"])
        self.assertTrue(p["gates"][3]["background"])
        self.assertIn({"gate": "e2e", "why": "when ['client']: области не задеты"}, p["skipped"])
        self.assertEqual(self.names(p["checks"]), ["editor"])
        self.write("client/a.cs")  # uncommitted counts for the branch too
        self.assertEqual(self.names(self.plan("review", base="main")["gates"])[-1], "e2e")

    def test_branch_moments_need_a_base(self):
        with self.assertRaises(lib.OmixflowError):
            self.plan("review")
        with self.assertRaises(lib.OmixflowError):
            self.plan("delivery", base="no-such-branch")
        with self.assertRaises(lib.OmixflowError):
            self.plan("later")

    def test_delivery_skips_a_check_whose_areas_did_not_change_since_its_green_run(self):
        self.write("sim/core.cs")
        self.commit_all("sim")
        green = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.names(self.plan("delivery", "main", {"editor": "0" * 40})["checks"]), ["editor"])
        self.write(".tasks/T-1/log.md")  # artifacts after the green run do not count
        self.write("docs/notes.md")
        self.commit_all("docs after review")
        p = self.plan("delivery", "main", {"editor": green})
        self.assertEqual(p["checks"], [])
        self.assertIn({"check": "editor", "why": f"зелёная на {green[:7]}, после неё области не задеты"},
                      p["skipped"])
        # a green run is no reason to skip at review: only delivery reuses it
        self.assertEqual(self.names(self.plan("review", "main", {"editor": green})["checks"]), ["editor"])
        self.write("client/fix.cs")  # uncommitted change in its area: due again
        self.assertEqual(self.names(self.plan("delivery", "main", {"editor": green})["checks"]), ["editor"])

    def test_delivery_check_without_when_reruns_on_any_change_but_artifacts(self):
        self.cfg["checks"]["whole"] = {"at": ["delivery"]}
        self.write("sim/core.cs")
        self.commit_all("sim")
        green = git(self.root, "rev-parse", "HEAD")
        self.write(".tasks/T-1/state.yaml")
        self.assertNotIn("whole", self.names(self.plan("delivery", "main", {"whole": green})["checks"]))
        self.write("tools/x.py")
        self.assertIn("whole", self.names(self.plan("delivery", "main", {"whole": green})["checks"]))

    def test_renames_deletions_and_non_ascii_paths_touch_their_areas(self):
        self.write("sim/A.cs")
        self.write("client/old.cs")
        self.write("sim/заметка.cs")
        self.commit_all("seed")
        git(self.root, "mv", "sim/A.cs", "A.cs")  # renamed out of the area
        self.assertEqual(self.plan("step")["areas"], ["sim"])
        git(self.root, "reset", "-q", "--hard")
        git(self.root, "rm", "-q", "client/old.cs")
        self.assertEqual(self.plan("step")["areas"], ["client"])
        git(self.root, "reset", "-q", "--hard")
        self.write("sim/заметка.cs", "y")
        self.assertIn("sim/заметка.cs", lib.changed_files(self.root))
        self.assertEqual(self.plan("step")["areas"], ["sim"])

    def test_artifacts_dir_never_touches_an_area(self):
        self.cfg["artifacts"] = {"dir": "sim/tasks"}
        self.write("sim/tasks/T-1/log.md")
        self.assertEqual(self.plan("step")["areas"], [])

    def test_when_on_a_step_gate_makes_it_conditional_in_the_full_set_only(self):
        self.cfg["verify"]["typecheck"]["when"] = ["client"]
        self.write("sim/core.cs")
        self.assertIn("typecheck", self.names(self.plan("step")["gates"]))
        self.assertNotIn("typecheck", self.names(self.plan("accept")["gates"]))

    def test_paths_plan_for_given_files_instead_of_the_tree(self):
        absolute = str(self.root / "client" / "x.cs")  # agents pass absolute paths
        p = lib.verify_plan(self.cfg, self.root, "step", paths=[absolute, "README.md"])
        self.assertEqual(p["areas"], ["client", "docs"])
        # planning lists the checks of every moment, so a review-only check is foreseen too
        self.assertEqual([(c["name"], c["at"]) for c in p["checks"]],
                         [("editor", ["step", "review", "delivery"]), ("merged", ["accept"])])
        self.assertEqual(p["on_demand"], ["device"])

    def test_since_counts_only_changes_after_a_ref(self):
        self.write("sim/core.cs")
        self.commit_all("sim")  # the branch touches sim
        self.write("docs/news.md")  # what a sync merge brings in, uncommitted
        self.assertEqual(self.plan("review", base="main")["areas"], ["sim", "docs"])
        p = lib.verify_plan(self.cfg, self.root, "review", since="HEAD")  # no base needed
        self.assertEqual((p["areas"], p["checks"]), (["docs"], []))

    def test_malformed_config_is_an_error_not_a_guess(self):
        for key, value in (("areas", {"sim": "sim/**"}), ("areas", ["sim"]),
                           ("verify", {"test": {"cmd": "t", "when": "sim"}}), ("checks", {"x": {"at": "step"}})):
            cfg = dict(self.cfg, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(lib.OmixflowError):
                lib.verify_plan(cfg, self.root, "step")

    def test_remote_only_base_works(self):
        origin = Path(self.tmp.name) / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.root), str(origin)], check=True)
        git(self.root, "remote", "add", "origin", str(origin))
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "branch", "-q", "-D", "main")
        self.write("sim/core.cs")
        self.commit_all("sim")
        self.assertEqual(self.plan("review", base="main")["areas"], ["sim"])

    def test_accept_is_the_full_set_over_uncommitted_changes(self):
        self.write("docs/x.md")
        p = self.plan("accept")
        self.assertEqual(self.names(p["gates"]), ["typecheck", "test", "lint", "build"])
        self.assertEqual(self.names(p["checks"]), ["merged"])

    def test_resolve_verify_cli_takes_base_and_checks_from_the_task(self):
        self.write("sim/core.cs")
        self.commit_all("sim")
        head = git(self.root, "rev-parse", "HEAD")
        task = self.root / ".tasks" / "T-1"
        task.mkdir(parents=True)
        (task / "state.yaml").write_text(f"id: T-1\nbase: main\nchecks:\n  editor: '{head}'\n", encoding="utf-8")
        res = run("resolve.py", "verify", "--at", "delivery", "--task", str(task))  # root from the task dir
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual((out["checks"], out["head"]), ([], head))
        res = run("resolve.py", "verify", "--at", "step", "--paths", "sim/x.cs", "--task", str(task))
        self.assertEqual(json.loads(res.stdout)["areas"], ["sim"])
        res = run("resolve.py", "verify", "--at", "review", "--project", str(self.root))
        self.assertEqual(res.returncode, 2)
        self.assertIn("нужна база", res.stderr)
        res = run("resolve.py", "verify", "--project", str(self.root))
        self.assertEqual(res.returncode, 2)


class AgentTeamsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "config"
        self.root = Path(self.tmp.name) / "proj"
        (self.root / ".claude").mkdir(parents=True)
        self.config.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def settings(self, path: Path, value: str | None) -> None:
        path.write_text(json.dumps({"env": {} if value is None else {lib.AGENT_TEAMS_ENV: value}}))

    def effective(self, shell: str | None = None) -> tuple:
        import os
        saved = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", lib.AGENT_TEAMS_ENV)}
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.config)
        if shell is None:
            os.environ.pop(lib.AGENT_TEAMS_ENV, None)
        else:
            os.environ[lib.AGENT_TEAMS_ENV] = shell
        try:
            return lib.agent_teams_setting(self.root)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_later_settings_override_earlier_and_the_shell(self):
        self.assertEqual(self.effective(), (None, "окружение"))
        self.assertEqual(self.effective(shell="1"), ("1", "окружение"))
        self.settings(self.config / "settings.json", "0")
        self.assertEqual(self.effective(shell="1")[0], "0")  # user settings beat a shell export
        project = self.root / ".claude" / "settings.json"
        self.settings(project, "1")
        self.assertEqual(self.effective(), ("1", str(project)))
        local = self.root / ".claude" / "settings.local.json"
        self.settings(local, "0")
        self.assertEqual(self.effective(), ("0", str(local)))
        local.write_text("{broken")
        self.assertEqual(self.effective()[0], "1")  # an unreadable file is skipped


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        (self.root / "sim").mkdir()
        (self.root / "sim" / "a.cs").write_text("x", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "seed")

    def tearDown(self):
        self.tmp.cleanup()

    def doctor(self, extra: str, adapter: str | None = None) -> dict:
        (self.root / lib.CONFIG_REL).parent.mkdir(parents=True, exist_ok=True)
        (self.root / lib.CONFIG_REL).write_text(BASE_CFG + extra, encoding="utf-8")
        if adapter is not None:
            path = self.root / lib.OVERRIDE_REL / "lang" / "ts.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(adapter, encoding="utf-8")
        proc = run("doctor.py", "--project", str(self.root), "--json")
        return {(c["section"], c["name"]): c for c in json.loads(proc.stdout)["checks"]}

    def test_when_must_name_declared_areas_and_stay_off_the_step_gates(self):
        checks = self.doctor("areas:\n  sim: [sim/**]\n  ghost: [nowhere/**]\n"
                             "verify:\n  test: { cmd: 'true', when: [sim] }\n  lint: { cmd: 'true', when: [sim] }\n"
                             "  typecheck: { cmd: 'true', when: [sim] }\n"
                             "  e2e: { cmd: 'true', when: [client] }\n")
        self.assertEqual(checks[("verify", "test.when")]["status"], "FAIL")
        self.assertEqual(checks[("verify", "lint.when")]["status"], "WARN")
        self.assertEqual(checks[("verify", "e2e.areas")]["status"], "FAIL")
        self.assertIn("client", checks[("verify", "e2e.areas")]["detail"])
        self.assertNotIn(("verify", "e2e.when"), checks)
        self.assertEqual(checks[("areas", "sim")]["status"], "OK")
        self.assertEqual(checks[("areas", "ghost")]["status"], "WARN")
        self.assertEqual(checks[("verify", "typecheck.when")]["status"], "WARN")

    def test_checks_need_the_capability_and_a_described_subsection(self):
        cfg = ("areas:\n  sim: [sim/**]\nverify:\n  test: 'true'\n"
               "checks:\n  editor: { when: [sim], at: [step] }\n  device: { when: [moon] }\n")
        checks = self.doctor(cfg)
        self.assertEqual(checks[("checks", "capability")]["status"], "FAIL")
        adapter = ("---\nport: lang\nname: ts\nextends: omixflow:ts\ncapabilities: [orchestrator_checks]\n---\n\n"
                   "## orchestrator_checks\n\n### editor\n\nhow\n\n## other\n\n### device\n")
        checks = self.doctor(cfg, adapter)
        self.assertNotIn(("checks", "capability"), checks)
        self.assertEqual(checks[("checks", "editor")]["status"], "OK")
        self.assertEqual(checks[("checks", "device")]["status"], "WARN")  # described outside the section
        self.assertIn("по требованию", checks[("checks", "device")]["detail"])
        self.assertEqual(checks[("checks", "device.areas")]["status"], "FAIL")

    def test_a_described_check_missing_from_the_config_is_reported(self):
        adapter = ("---\nport: lang\nname: ts\nextends: omixflow:ts\ncapabilities: [orchestrator_checks]\n---\n\n"
                   "## orchestrator_checks\n\n### editor\n\nhow\n")
        checks = self.doctor("verify:\n  test: 'true'\n", adapter)
        self.assertEqual(checks[("checks", "editor")]["status"], "WARN")
        self.assertIn("нет", checks[("checks", "editor")]["detail"])

    def test_doctor_warns_when_agent_teams_are_on_for_the_project(self):
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"env": {lib.AGENT_TEAMS_ENV: "1"}}))
        checks = self.doctor("verify:\n  test: 'true'\n")
        self.assertEqual(checks[("env", "agent teams")]["status"], "WARN")
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"env": {lib.AGENT_TEAMS_ENV: "0"}}))
        checks = self.doctor("verify:\n  test: 'true'\n")
        self.assertEqual(checks[("env", "agent teams")]["status"], "OK")

    def test_doctor_counts_non_ascii_files_in_areas(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "заметка.md").write_text("x", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "ru")
        checks = self.doctor("areas:\n  docs: [docs/*.md]\nverify:\n  test: 'true'\n")
        self.assertEqual(checks[("areas", "docs")]["status"], "OK")


if __name__ == "__main__":
    unittest.main()
