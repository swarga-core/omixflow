"""Lint the plugin sources for terminology and layering rules.

- Forbidden terms (see protocol/glossary.md) must not appear anywhere except the
  files that explain the ban.
- Core (protocol/, skills/, agents/) must not name adapter tools: package managers,
  test runners, forge CLIs, MCP tool ids. Adapter names are fine.
- Every plugin adapter declares port/name matching its location.
- Every SendMessage target mentioned in a skill has a named spawn in the same skill
  (activates once skills are transferred; passes vacuously until then).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omixflow_lib as lib  # noqa: E402

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
        hits = []
        for path in iter_files(*CORE_DIRS):
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if TOOL_NAMES.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "инструменты адаптеров в ядре:\n" + "\n".join(hits))


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


if __name__ == "__main__":
    unittest.main()
