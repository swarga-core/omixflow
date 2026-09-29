"""Tests for OMIXFlow scripts: config validation, adapter resolution, doctor.

Run: python3 -m unittest discover tests
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "ts-youtrack"
sys.path.insert(0, str(SCRIPTS))
import omixflow_lib as lib  # noqa: E402


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True)


class ConfigTests(unittest.TestCase):
    def test_fixture_config_is_valid(self):
        cfg = lib.load_config(FIXTURE)
        self.assertEqual(lib.validate_config(cfg), [])

    def test_template_is_valid(self):
        data = lib.yaml.safe_load(lib.TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(lib.validate_config(lib.normalize_config(data)), [])

    def test_shorthands_normalize(self):
        cfg = lib.normalize_config({
            "version": 1, "tracker": "none", "forge": "none", "lang": "ts",
            "workspace": {"base": "main", "branch": "task/{id}"},
            "verify": {"test": "make test", "lint": {"cmd": "make lint", "criterion": "zero-diagnostics"}},
        })
        self.assertEqual(cfg["tracker"], {"adapter": "none"})
        self.assertEqual(cfg["lang"], ["ts"])
        self.assertEqual(cfg["workspace"]["adapter"], "git")
        self.assertEqual(cfg["verify"]["test"], {"cmd": "make test", "criterion": "exit-code"})
        self.assertEqual(lib.validate_config(cfg), [])

    def test_unknown_keys_and_bad_enums_are_rejected(self):
        cfg = lib.load_config(FIXTURE)
        cfg["workspace"]["worktree"] = "sometimes"
        cfg["verify"]["test"]["criterion"] = "vibes"
        cfg["bogus"] = 1
        cfg["workspace"]["branch"] = "task/no-id"
        errors = lib.validate_config(cfg)
        joined = "\n".join(errors)
        self.assertIn("workspace.worktree", joined)
        self.assertIn("verify.test.criterion", joined)
        self.assertIn("'bogus'", joined)
        self.assertIn("workspace.branch", joined)

    def test_config_get(self):
        cfg = lib.load_config(FIXTURE)
        self.assertEqual(lib.config_get(cfg, "tracker.project"), "AL")
        self.assertEqual(lib.config_get(cfg, "workspace.submodules.0.path"), "omix")
        self.assertIsNone(lib.config_get(cfg, "nope.nope"))


class AdapterTests(unittest.TestCase):
    def test_project_extension_chains_onto_plugin_adapter(self):
        chain = lib.resolve_adapter("tracker", "youtrack", FIXTURE)
        self.assertEqual([a.layer for a in chain], ["plugin", "project"])
        self.assertEqual(chain[-1].extends, "omixflow:youtrack")
        caps = lib.chain_capabilities(chain)
        self.assertIn("get", caps)
        self.assertIn("update_description", caps)

    def test_plugin_adapters_cover_required_capabilities(self):
        for port in lib.PORTS:
            contract = lib.port_contract(port)
            for path in sorted((lib.PLUGIN_ROOT / "adapters" / port).glob("*.md")):
                if path.name == "PORT.md":
                    continue
                with self.subTest(port=port, adapter=path.stem):
                    chain = lib.resolve_adapter(port, path.stem, FIXTURE, layer="plugin")
                    caps = lib.chain_capabilities(chain)
                    missing = [c for c in contract["required"] if c not in caps]
                    self.assertEqual(missing, [], f"{port}/{path.stem} не покрывает {missing}")
                    unknown = [c for c in caps if c not in contract["required"] + contract["optional"]]
                    self.assertEqual(unknown, [], f"{port}/{path.stem} объявляет неизвестные {unknown}")

    def test_missing_adapter_raises(self):
        with self.assertRaises(lib.OmixflowError):
            lib.resolve_adapter("forge", "gitlab", FIXTURE)

    def test_extends_cycle_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / lib.OVERRIDE_REL / "forge"
            d.mkdir(parents=True)
            (root / lib.CONFIG_REL).write_text("version: 1\n", encoding="utf-8")
            (d / "a.md").write_text("---\nport: forge\nname: a\nextends: project:b\n---\n", encoding="utf-8")
            (d / "b.md").write_text("---\nport: forge\nname: b\nextends: project:a\n---\n", encoding="utf-8")
            with self.assertRaises(lib.OmixflowError) as ctx:
                lib.resolve_adapter("forge", "a", root)
            self.assertIn("цикл", str(ctx.exception))

    def test_port_declared_in_frontmatter_must_match_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / lib.OVERRIDE_REL / "lang"
            d.mkdir(parents=True)
            (d / "go.md").write_text("---\nport: tracker\nname: go\n---\n", encoding="utf-8")
            with self.assertRaises(lib.OmixflowError):
                lib.resolve_adapter("lang", "go", root)

    def test_agent_mapping_and_rules(self):
        cfg = lib.load_config(FIXTURE)
        info = lib.resolve_agent("coder", FIXTURE, cfg)
        self.assertEqual(info["layer"], "plugin")
        self.assertEqual(info["subagent_type"], "omixflow:coder")
        self.assertFalse(info["replaced"])
        self.assertTrue(info["agent"].endswith("agents/coder.md"))
        cfg["agents"] = {"coder": "my-coder"}
        info = lib.resolve_agent("coder", FIXTURE, cfg)
        self.assertEqual(info["subagent_type"], "omixflow:my-coder")
        self.assertIsNone(info["agent"])  # fixture has no .claude/agents/my-coder.md

    def test_same_name_project_agent_overrides_plugin_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / lib.CONFIG_REL).parent.mkdir(parents=True)
            (root / lib.CONFIG_REL).write_text("version: 1\n", encoding="utf-8")
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / ".claude" / "agents" / "coder.md").write_text("---\nname: coder\n---\n", encoding="utf-8")
            info = lib.resolve_agent("coder", root, {})
            self.assertTrue(info["replaced"])
            self.assertEqual(info["subagent_type"], "coder")
            self.assertEqual(info["layer"], "project")

    def test_plugin_agents_exist_for_all_roles(self):
        for role in lib.ROLES:
            self.assertTrue((lib.PLUGIN_ROOT / "agents" / f"{role}.md").exists(), role)


class ScriptTests(unittest.TestCase):
    def test_doctor_json(self):
        proc = run("doctor.py", "--project", str(FIXTURE), "--json")
        report = json.loads(proc.stdout)
        self.assertEqual(Path(report["project"]), FIXTURE)
        by_key = {(c["section"], c["name"]): c for c in report["checks"]}
        self.assertEqual(by_key[("config", "schema")]["status"], "OK")
        for port in lib.PORTS:
            self.assertEqual(by_key[(f"port:{port}", "chain")]["status"], "OK", port)
            self.assertEqual(by_key[(f"port:{port}", "capabilities")]["status"], "OK", port)
        self.assertEqual(by_key[("port:tracker", "chain")]["detail"], "plugin:youtrack → project:youtrack")
        self.assertEqual(by_key[("workspace", "submodule:omix")]["status"], "OK")
        self.assertEqual(by_key[("workspace", "branch template")]["status"], "OK")

    def test_doctor_fails_without_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run("doctor.py", "--project", tmp, "--json")
            self.assertEqual(proc.returncode, 1)
            report = json.loads(proc.stdout)
            statuses = {c["name"]: c["status"] for c in report["checks"]}
            self.assertEqual(statuses["flow.yaml"], "FAIL")

    def test_doctor_init_writes_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run", "lint": "biome check ."}}), encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("", encoding="utf-8")
            proc = run("doctor.py", "--project", tmp, "--init", "--json")
            cfg = lib.load_config(root)
            self.assertEqual(cfg["lang"], ["ts"])
            self.assertEqual(cfg["verify"]["test"]["cmd"], "pnpm test")
            self.assertEqual(cfg["verify"]["lint"]["criterion"], "zero-diagnostics")
            self.assertEqual(cfg["workspace"]["setup"], "pnpm install")
            self.assertEqual(lib.validate_config(cfg), [])
            # second init without --force refuses
            proc = run("doctor.py", "--project", tmp, "--init")
            self.assertEqual(proc.returncode, 2)

    def test_doctor_warns_about_accumulated_review_worktrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                            "--allow-empty", "-m", "init"], check=True)
            (root / lib.CONFIG_REL).parent.mkdir(parents=True)
            (root / lib.CONFIG_REL).write_text(
                "version: 1\ntracker: none\nforge: none\nlang: [ts]\n"
                "workspace: {base: main, branch: 'task/{id}'}\nverify: {test: 'true'}\n", encoding="utf-8")
            for i in range(1, 5):
                subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", "--detach",
                                str(root / ".claude" / "worktrees" / f"pr-{i}")], check=True)
            proc = run("doctor.py", "--project", str(root), "--json")
            report = json.loads(proc.stdout)
            check = next(c for c in report["checks"] if c["name"] == "review worktrees")
            self.assertEqual(check["status"], "WARN")
            self.assertIn("pr-4", check["detail"])

    def test_resolve_adapter_prints_chain(self):
        proc = run("resolve.py", "adapter", "tracker", "--project", str(FIXTURE))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("adapters/tracker/youtrack.md"))
        self.assertTrue(lines[1].endswith(".claude/omixflow/tracker/youtrack.md"))

    def test_cfg_prints_values(self):
        proc = run("cfg.py", "workspace.setup", "--project", str(FIXTURE))
        self.assertEqual(proc.stdout.strip(), "pnpm install")
        proc = run("cfg.py", "workspace.submodules", "--project", str(FIXTURE))
        self.assertEqual(json.loads(proc.stdout), [{"path": "omix", "readonly": True}])
        proc = run("cfg.py", "missing.key", "--project", str(FIXTURE))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.strip(), "null")


HOME_CFG = ("version: 1\ntracker: none\nforge: github\nlang: [ts]\n"
            "workspace: {base: main, branch: 'task/{id}'}\nverify: {test: 'true'}\n")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(root: Path, name: str, text: str = "x") -> str:
    (root / name).write_text(text, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", name)
    return git(root, "rev-parse", "HEAD")


def write_cfg(root: Path, text: str = HOME_CFG) -> None:
    (root / lib.CONFIG_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / lib.CONFIG_REL).write_text(text, encoding="utf-8")


def foreign_clone(tmp: Path) -> dict:
    """A bare origin (default branch `trunk`, branches `feature`, `other`) cloned into
    tmp/outer/foreign; tmp/outer carries its own flow.yaml (an ancestor config that
    must never apply). Local `feature` gets a commit origin does not have."""
    seed = tmp / "seed"
    subprocess.run(["git", "init", "-q", "-b", "trunk", str(seed)], check=True)
    trunk = commit(seed, "a.txt")
    git(seed, "tag", "v1")
    git(seed, "checkout", "-q", "-b", "feature")
    feature = commit(seed, "f.txt")
    git(seed, "checkout", "-q", "-b", "other", "trunk")
    other = commit(seed, "o.txt")
    git(seed, "checkout", "-q", "trunk")
    origin = tmp / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)
    outer = tmp / "outer"
    outer.mkdir()
    write_cfg(outer, HOME_CFG.replace("tracker: none", "tracker: local").replace("forge: github", "forge: none")
              .replace("base: main", "base: other"))
    foreign = outer / "foreign"
    subprocess.run(["git", "clone", "-q", str(origin), str(foreign)], check=True)
    git(foreign, "checkout", "-q", "feature")
    local_feature = commit(foreign, "local.txt")
    git(foreign, "checkout", "-q", "-b", "local-only")
    local_only = commit(foreign, "lo.txt")
    git(foreign, "checkout", "-q", "trunk")
    home = tmp / "home"
    home.mkdir()
    write_cfg(home)
    return {"foreign": foreign, "home": home, "outer": outer, "trunk": trunk, "feature": feature,
            "other": other, "local_feature": local_feature, "local_only": local_only}


class WorkspaceReposSchemaTests(unittest.TestCase):
    def cfg(self, **ws):
        cfg = lib.normalize_config(lib.yaml.safe_load(HOME_CFG))
        cfg["workspace"].update(ws)
        return cfg

    def test_valid_repos_and_parallel_parts(self):
        cfg = self.cfg(repos={"omix-lib": {"path": "../lib", "remote": "git@github.com:o/lib.git",
                                           "ref": "auto", "setup": True},
                              "eal": {"path": "../eal", "remote": "https://github.com/o/eal"}})
        cfg["multitask"] = {"parallel_parts": 4, "parallel_per_owner": 1}
        self.assertEqual(lib.validate_config(cfg), [])

    def test_bad_repo_entries_rejected(self):
        cases = {
            "missing remote": ({"path": "../lib"}, "обязательный ключ 'remote'"),
            "unknown key": ({"path": "../lib", "remote": "r", "branch": "x"}, "неизвестный ключ 'branch'"),
            "non-boolean setup": ({"path": "../lib", "remote": "r", "setup": "yes"}, "setup: ожидается boolean"),
        }
        for label, (entry, message) in cases.items():
            with self.subTest(label):
                errors = lib.validate_config(self.cfg(repos={"lib": entry}))
                self.assertTrue(any("workspace.repos.lib" in e and message in e for e in errors), errors)

    def test_parallel_parts_minimum(self):
        cfg = self.cfg()
        cfg["multitask"] = {"parallel_parts": 0}
        self.assertTrue(any("multitask.parallel_parts" in e for e in lib.validate_config(cfg)))

    def test_template_declares_parallel_parts(self):
        data = lib.yaml.safe_load(lib.TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["multitask"]["parallel_parts"], 4)
        self.assertIn("# repos:", lib.TEMPLATE_PATH.read_text(encoding="utf-8"))


class ForeignRepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.r = foreign_clone(self.tmp)
        self.foreign, self.home = self.r["foreign"], self.r["home"]

    def tearDown(self):
        self._tmp.cleanup()

    def resolve(self, *args: str) -> subprocess.CompletedProcess:
        return run("resolve.py", *args, "--project", str(self.foreign), "--fallback-project", str(self.home))

    def test_normalize_remote(self):
        same = ["git@github.com:Org/Repo.git", "https://github.com/Org/Repo", "https://user@GitHub.com/Org/Repo.git/",
                "ssh://git@github.com:22/Org/Repo.git", "ssh://git@github.com/Org/Repo"]
        self.assertEqual({lib.normalize_remote(u) for u in same}, {"github.com/Org/Repo"})
        self.assertNotEqual(lib.normalize_remote("git@github.com:org/other.git"), "github.com/Org/Repo")

    def test_resolve_repo_ref(self):
        f = self.foreign
        self.assertEqual(lib.resolve_repo_ref(f, "feature"), self.r["feature"])  # origin/feature, not local
        self.assertEqual(lib.resolve_repo_ref(f, "local-only"), self.r["local_only"])
        self.assertEqual(lib.resolve_repo_ref(f, "v1"), self.r["trunk"])
        self.assertEqual(lib.resolve_repo_ref(f, self.r["other"][:10]), self.r["other"])
        self.assertIsNone(lib.resolve_repo_ref(f, "ghost"))
        # auto / absent: remote default branch without a foreign config, not the ancestor's base
        self.assertEqual(lib.resolve_repo_ref(f, "auto"), self.r["trunk"])
        self.assertEqual(lib.resolve_repo_ref(f, None), self.r["trunk"])
        write_cfg(f, HOME_CFG.replace("base: main", "base: other"))
        self.assertEqual(lib.resolve_repo_ref(f, "auto"), self.r["other"])

    def test_auto_ref_falls_back_to_main_master(self):
        repo = self.tmp / "plain"
        subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
        sha = commit(repo, "m.txt")
        self.assertEqual(lib.resolve_repo_ref(repo, "auto"), sha)

    def test_repo_checkout_state(self):
        f = self.foreign
        state = lib.repo_checkout_state(f)
        self.assertEqual(state, {"head": self.r["trunk"], "dirty": False})
        (f / "untracked.txt").write_text("u", encoding="utf-8")
        git(f, "worktree", "add", "-q", "--detach", str(f / ".claude" / "worktrees" / "research-AL-1"), "trunk")
        self.assertFalse(lib.repo_checkout_state(f)["dirty"])
        (f / "a.txt").write_text("changed", encoding="utf-8")
        self.assertTrue(lib.repo_checkout_state(f)["dirty"])

    def test_fallback_adapter_chain_from_home(self):
        # without the flag the foreign repo resolves to the ancestor config (tracker local)
        plain = run("resolve.py", "adapter", "tracker", "--project", str(self.foreign))
        self.assertTrue(plain.stdout.strip().endswith("adapters/tracker/local.md"), plain.stdout)
        proc = self.resolve("adapter", "tracker")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip().endswith("adapters/tracker/none.md"), proc.stdout)
        self.assertIn("нет flow.yaml", proc.stderr)
        # the foreign project layer wins when present
        d = self.foreign / lib.OVERRIDE_REL / "lang"
        d.mkdir(parents=True)
        (d / "ts.md").write_text("---\nport: lang\nname: ts\nextends: omixflow:ts\n---\n", encoding="utf-8")
        lines = self.resolve("adapter", "lang").stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(Path(lines[1]), d / "ts.md")
        # a home project-layer file is used when the foreign one is absent
        h = self.home / lib.OVERRIDE_REL / "tracker"
        h.mkdir(parents=True)
        (h / "none.md").write_text("---\nport: tracker\nname: none\nextends: omixflow:none\n---\n", encoding="utf-8")
        self.assertEqual(Path(self.resolve("adapter", "tracker").stdout.strip().splitlines()[-1]), h / "none.md")

    def test_fallback_adapter_script_uses_home_names(self):
        # without the flag the ancestor config (forge none, no scripts) applies
        self.assertEqual(run("resolve.py", "adapter-script", "forge", "pr", "--project", str(self.foreign)).returncode, 2)
        proc = self.resolve("adapter-script", "forge", "pr")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip().endswith("adapters/forge/github/pr.py"), proc.stdout)
        # a home project-layer adapter shadowing the script applies to a foreign repo without config
        d = self.home / lib.OVERRIDE_REL / "forge"
        d.mkdir(parents=True)
        (d / "github.md").write_text("---\nport: forge\nname: github\nextends: omixflow:github\n"
                                     "scripts: {pr: pr_home.py}\n---\n", encoding="utf-8")
        (d / "pr_home.py").write_text("", encoding="utf-8")
        self.assertEqual(Path(self.resolve("adapter-script", "forge", "pr").stdout.strip()), d / "pr_home.py")

    def test_fallback_base_resolves_in_foreign_repo(self):
        proc = self.resolve("base")
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "trunk"), proc.stderr)
        write_cfg(self.foreign, HOME_CFG.replace("base: main", "base: other"))
        self.assertEqual(self.resolve("base").stdout.strip(), "other")

    def test_fallback_agent_from_home_rules_from_foreign(self):
        for root in (self.home, self.foreign):
            (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
            (root / lib.OVERRIDE_REL / "agents").mkdir(parents=True, exist_ok=True)
            (root / lib.OVERRIDE_REL / "agents" / "researcher.md").write_text("rules", encoding="utf-8")
        (self.foreign / ".claude" / "agents" / "researcher.md").write_text("---\nname: researcher\n---\n", encoding="utf-8")
        for with_cfg in (False, True):
            if with_cfg:
                write_cfg(self.foreign)
            with self.subTest(foreign_config=with_cfg):
                info = json.loads(self.resolve("agent", "researcher", "--json").stdout)
                self.assertEqual(info["subagent_type"], "omixflow:researcher")
                self.assertEqual(info["layer"], "plugin")
                self.assertEqual([Path(p) for p in info["rules"]],
                                 [self.foreign / lib.OVERRIDE_REL / "agents" / "researcher.md"])
        (self.foreign / lib.OVERRIDE_REL / "agents" / "researcher.md").unlink()
        self.assertEqual(json.loads(self.resolve("agent", "researcher", "--json").stdout)["rules"], [])

    def test_repo_command(self):
        write_cfg(self.home, HOME_CFG.replace(
            "branch: 'task/{id}'}",
            "branch: 'task/{id}', repos: {lib: {path: ../outer/foreign, remote: 'git@x:o/f.git', ref: feature},"
            " auto: {path: ../outer/foreign, remote: r}, ghost: {path: ../outer/foreign, remote: r, ref: nope}}}"))
        home = str(self.home)
        proc = run("resolve.py", "repo", "lib", "--json", "--project", home)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        info = json.loads(proc.stdout)
        self.assertEqual(info, {"name": "lib", "path": str(self.foreign), "remote": "git@x:o/f.git", "ref": "feature",
                                "sha": self.r["feature"], "head": self.r["trunk"], "dirty": False,
                                "has_config": False})
        self.assertEqual(run("resolve.py", "repo", "lib", "--project", home).stdout.strip(), self.r["feature"])
        auto = json.loads(run("resolve.py", "repo", "auto", "--json", "--project", home).stdout)
        self.assertEqual((auto["ref"], auto["sha"]), ("auto", self.r["trunk"]))
        ghost = run("resolve.py", "repo", "ghost", "--json", "--project", home)
        self.assertEqual(ghost.returncode, 1)
        self.assertIsNone(json.loads(ghost.stdout)["sha"])
        self.assertEqual(run("resolve.py", "repo", "nope", "--project", home).returncode, 2)
        listing = run("resolve.py", "repo", "--list", "--project", home)
        self.assertEqual((listing.returncode, listing.stdout.strip()), (0, "lib,auto,ghost"))
        empty = run("resolve.py", "repo", "--list", "--project", str(self.tmp / "outer"))
        self.assertEqual((empty.returncode, empty.stdout), (0, "\n"))


class DoctorRepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.r = foreign_clone(self.tmp)
        self.foreign, self.home = self.r["foreign"], self.r["home"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.home)], check=True)
        commit(self.home, "README")

    def tearDown(self):
        self._tmp.cleanup()

    def doctor(self, repos: str) -> dict:
        write_cfg(self.home, HOME_CFG.replace("branch: 'task/{id}'}", "branch: 'task/{id}', repos: {" + repos + "}}"))
        proc = run("doctor.py", "--project", str(self.home), "--json")
        report = json.loads(proc.stdout)
        report["exit"] = proc.returncode
        return report

    @staticmethod
    def checks(report: dict, repo: str) -> dict:
        return {c["name"]: c for c in report["checks"] if c["section"] == f"repo:{repo}"}

    def test_slug_path_and_git_failures(self):
        (self.home / "inner").mkdir()
        (self.tmp / "plain").mkdir()
        (self.foreign / "sub").mkdir()
        report = self.doctor("Bad_Name: {path: ../outer/foreign, remote: r}, missing: {path: ../nope, remote: r},"
                             " inner: {path: inner, remote: r}, self: {path: ., remote: r},"
                             " plain: {path: ../plain, remote: r}, sub: {path: ../outer/foreign/sub, remote: r}")
        self.assertEqual(report["exit"], 1)
        self.assertEqual(self.checks(report, "Bad_Name")["slug"]["status"], "FAIL")
        self.assertEqual(self.checks(report, "missing")["slug"]["status"], "OK")
        for name, needle in (("missing", "нет каталога"), ("inner", "внутри домашнего проекта"),
                             ("self", "внутри домашнего проекта")):
            with self.subTest(name):
                c = self.checks(report, name)
                self.assertEqual(c["path"]["status"], "FAIL")
                self.assertIn(needle, c["path"]["detail"])
                self.assertNotIn("git", c)
        for name in ("plain", "sub"):
            with self.subTest(name):
                c = self.checks(report, name)
                self.assertEqual((c["path"]["status"], c["git"]["status"]), ("OK", "FAIL"))
                self.assertNotIn("remote", c)

    def test_remote_ref_and_flow_yaml(self):
        git(self.foreign, "remote", "set-url", "origin", "git@GitHub.com:org/foreign.git")
        report = self.doctor("ok: {path: ../outer/foreign, remote: 'https://github.com/org/foreign', ref: feature},"
                             " bad: {path: ../outer/foreign, remote: 'https://github.com/org/other', ref: nope}")
        ok, bad = self.checks(report, "ok"), self.checks(report, "bad")
        self.assertEqual(ok["remote"]["status"], "OK")
        self.assertIn("git@GitHub.com:org/foreign.git", ok["remote"]["detail"])
        self.assertEqual(bad["remote"]["status"], "FAIL")
        self.assertEqual(ok["ref"], {"section": "repo:ok", "name": "ref", "status": "OK",
                                     "detail": f"feature → {self.r['feature'][:12]}"})
        self.assertEqual(bad["ref"]["status"], "FAIL")
        self.assertEqual((ok["flow.yaml"]["status"], ok["flow.yaml"]["detail"]),
                         ("OK", "flow.yaml нет, фолбэк на цепочку домашнего проекта"))
        self.assertNotIn("research worktrees", ok)
        git(self.foreign, "remote", "remove", "origin")
        write_cfg(self.foreign)
        c = self.checks(self.doctor("ok: {path: ../outer/foreign, remote: r}"), "ok")
        self.assertEqual(c["remote"]["status"], "FAIL")
        self.assertIn("нет origin", c["remote"]["detail"])
        self.assertEqual((c["flow.yaml"]["status"], c["flow.yaml"]["detail"]), ("OK", "flow.yaml есть"))

    def add_research_worktree(self, task_id: str) -> None:
        git(self.foreign, "worktree", "add", "-q", "--detach",
            str(self.foreign / ".claude" / "worktrees" / f"research-{task_id}"), "trunk")

    def test_research_worktrees(self):
        repos = "lib: {path: ../outer/foreign, remote: r}"
        self.add_research_worktree("AL-3")
        c = self.checks(self.doctor(repos), "lib")["research worktrees"]
        self.assertEqual(c["status"], "OK")
        self.assertIn("состояние неизвестно: research-AL-3", c["detail"])
        # done in the working tree
        state = self.home / ".tasks" / "AL-1"
        state.mkdir(parents=True)
        (state / "state.yaml").write_text("id: AL-1\nphase: done\n", encoding="utf-8")
        self.add_research_worktree("AL-1")
        c = self.checks(self.doctor(repos), "lib")["research worktrees"]
        self.assertEqual(c["status"], "WARN")
        self.assertIn("задачи завершены: research-AL-1", c["detail"])
        # in progress in the working tree is OK; done only on the task branch warns
        (state / "state.yaml").write_text("id: AL-1\nphase: research\n", encoding="utf-8")
        self.assertEqual(self.checks(self.doctor(repos), "lib")["research worktrees"]["status"], "OK")
        git(self.home, "checkout", "-q", "-b", "task/AL-3")
        (self.home / ".tasks" / "AL-3").mkdir(parents=True)
        (self.home / ".tasks" / "AL-3" / "state.yaml").write_text("id: AL-3\nphase: done\n", encoding="utf-8")
        git(self.home, "add", ".tasks/AL-3/state.yaml")
        git(self.home, "commit", "-q", "-m", "state")
        git(self.home, "checkout", "-q", "main")
        self.assertFalse((self.home / ".tasks" / "AL-3").exists())
        c = self.checks(self.doctor(repos), "lib")["research worktrees"]
        self.assertEqual(c["status"], "WARN")
        self.assertIn("задачи завершены: research-AL-3", c["detail"])
        self.assertNotIn("состояние неизвестно", c["detail"])

    def test_too_many_research_worktrees_warn(self):
        repos = "lib: {path: ../outer/foreign, remote: r}"
        for i in range(1, 4):
            self.add_research_worktree(f"X-{i}")
        self.assertEqual(self.checks(self.doctor(repos), "lib")["research worktrees"]["status"], "OK")
        self.add_research_worktree("X-4")
        c = self.checks(self.doctor(repos), "lib")["research worktrees"]
        self.assertEqual(c["status"], "WARN")
        self.assertIn("4 (", c["detail"])

    def test_no_repo_sections_without_repos(self):
        report = json.loads(run("doctor.py", "--project", str(FIXTURE), "--json").stdout)
        self.assertFalse([c for c in report["checks"] if c["section"].startswith("repo:")])


if __name__ == "__main__":
    unittest.main()
