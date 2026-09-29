"""Lint the plugin sources for terminology and layering rules.

- Forbidden terms (see protocol/glossary.md) must not appear anywhere except the
  files that explain the ban.
- Core (protocol/, skills/, agents/) must not name adapter tools: package managers,
  test runners, forge CLIs, MCP tool ids. Adapter names are fine.
- Every plugin adapter declares port/name matching its location.
- Every SendMessage target mentioned in a skill has a named spawn in the same skill
  (activates once skills are transferred; passes vacuously until then).
- The profiles table in protocol/profiles.md equals state.PROFILES.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omixflow_lib as lib  # noqa: E402
import state  # noqa: E402

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".sh"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "tests"}

FORBIDDEN_TERMS = re.compile(r"эпик|\bepic\b|подзадач|\bsubtask", re.I)
FORBIDDEN_TERMS_EXEMPT = {"protocol/glossary.md", "CHANGELOG.md", "README.md",
                          "adapters/tracker/youtrack.md"}  # explains that Type=Epic is meaningless

TOOL_NAMES = re.compile(
    r"\b(pnpm|npm|yarn|vitest|jest|biome|eslint|tsc|turbo|cargo|dotnet|composer|phpunit|go test)\b"
    r"|\bgh (api|pr|repo)\b|mcp__[a-z0-9_-]+__")
CORE_DIRS = ("protocol", "skills", "agents")


def iter_files(*dirs: str):
    bases = [ROOT / d for d in dirs] if dirs else [ROOT]
    for base in bases:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                yield path


class TerminologyLint(unittest.TestCase):
    def test_no_forbidden_terms(self):
        hits = []
        for path in iter_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel in FORBIDDEN_TERMS_EXEMPT:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN_TERMS.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "запрещённые термины:\n" + "\n".join(hits))

    def test_core_does_not_name_tools(self):
        """Agent frontmatter is exempt: its `tools:` allowlist must name real tool ids."""
        hits = []
        for path in iter_files(*CORE_DIRS):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            offset = 0
            if rel.startswith("agents/"):
                _, body = lib.parse_frontmatter(path)
                offset = text.count("\n") - body.count("\n")
                text = body
            for n, line in enumerate(text.splitlines(), 1 + offset):
                if TOOL_NAMES.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "инструменты адаптеров в ядре:\n" + "\n".join(hits))

    def test_agents_declare_frontmatter(self):
        for path in sorted((ROOT / "agents").glob("*.md")):
            meta, _ = lib.parse_frontmatter(path)
            with self.subTest(agent=path.stem):
                self.assertEqual(meta.get("name"), path.stem)
                self.assertTrue(meta.get("description"))
                self.assertIn("tools", meta)
                self.assertIn("model", meta)


class AdapterLint(unittest.TestCase):
    def test_adapter_frontmatter_matches_location(self):
        for port in lib.PORTS:
            for path in sorted((ROOT / "adapters" / port).glob("*.md")):
                meta, _ = lib.parse_frontmatter(path)
                with self.subTest(file=path.name):
                    self.assertEqual(meta.get("port"), port)
                    if path.name != "PORT.md":
                        self.assertEqual(meta.get("name"), path.stem)
                        self.assertIsInstance(meta.get("capabilities"), list)
                        self.assertIn("requires", meta)

    def test_port_contracts_declare_required(self):
        for port in lib.PORTS:
            contract = lib.port_contract(port)
            self.assertTrue(contract["required"], port)


class SkillLint(unittest.TestCase):
    SEND_RE = re.compile(r"SendMessage[^\n]*?\b(to:\s*)?[\"'`]?([a-z]+)-\{", re.I)
    SPAWN_RE = re.compile(r"name:\s*[\"'`]?([a-z]+)-\{", re.I)

    def test_sendmessage_targets_have_named_spawns(self):
        skills = ROOT / "skills"
        if not skills.exists():
            return
        for path in sorted(skills.rglob("SKILL.md")):
            text = path.read_text(encoding="utf-8")
            targets = {m.group(2).lower() for m in self.SEND_RE.finditer(text)}
            spawns = {m.group(1).lower() for m in self.SPAWN_RE.finditer(text)}
            missing = targets - spawns
            with self.subTest(skill=path.parent.name):
                self.assertEqual(missing, set(),
                                 f"{path.parent.name}: SendMessage адресатам {sorted(missing)} без именованного спавна")


class ProfilesLint(unittest.TestCase):
    HEADER = ("| profile | phases | mutates | part_isolation | part_integration "
              "| finalize_artifact | triage | part_runner |")

    @staticmethod
    def cells(line: str):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    @staticmethod
    def typed(key: str, cell: str):
        if key == "phases":
            return [p.strip() for p in cell.split(",")]
        return {"true": True, "false": False}.get(cell, cell)

    def parse_table(self, text: str):
        lines = text.splitlines()
        starts = [i for i, line in enumerate(lines) if line.strip() == self.HEADER]
        self.assertEqual(len(starts), 1, f"protocol/profiles.md: таблица с заголовком {self.HEADER!r}")
        keys = self.cells(self.HEADER)[1:]
        table = {}
        for line in lines[starts[0] + 2:]:
            if not line.strip().startswith("|"):
                break
            cells = self.cells(line)
            self.assertEqual(len(cells), len(keys) + 1, line)
            self.assertNotIn(cells[0], table, f"профиль {cells[0]} повторяется")
            table[cells[0]] = {k: self.typed(k, c) for k, c in zip(keys, cells[1:])}
        return table

    def test_profiles_table_matches_canon(self):
        table = self.parse_table((ROOT / "protocol" / "profiles.md").read_text(encoding="utf-8"))
        self.assertEqual(list(table), list(state.PROFILES))
        for name, props in state.PROFILES.items():
            with self.subTest(profile=name):
                self.assertEqual(table[name], props)


if __name__ == "__main__":
    unittest.main()
