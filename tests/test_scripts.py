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


if __name__ == "__main__":
    unittest.main()
