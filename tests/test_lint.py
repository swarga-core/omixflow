"""Lint the plugin sources for terminology and layering rules.

Files ignored by git (local drafts, scratch notes) are not plugin sources and are
skipped; outside a git checkout every file is linted.

- Forbidden terms (see protocol/glossary.md) must not appear anywhere except the
  files that explain the ban.
- Core (protocol/, skills/, agents/) must not name adapter tools: package managers,
  test runners, forge CLIs, MCP tool ids. Adapter names are fine.
- Every plugin adapter declares port/name matching its location.
- Every SendMessage target mentioned in a skill has a named spawn in the same skill
  (activates once skills are transferred; passes vacuously until then).
- The profiles table in protocol/profiles.md equals state.PROFILES.
- Script subcommands avoid shell builtins that a worktree-isolated session refuses;
  the core calls `state.py finish`, never the `complete` alias.
- Decision point ids in protocol/dialog.md are unique and well-formed (kebab-case,
  external actions as `{port}.{action}`); protocol and skills reference known points only.
"""
from __future__ import annotations

import functools
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Optional, Set

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omixflow_lib as lib  # noqa: E402
import state  # noqa: E402

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".sh"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "tests"}

FORBIDDEN_TERMS = re.compile(r"подзадач|\bsubtask", re.I)
FORBIDDEN_TERMS_EXEMPT = {"protocol/glossary.md", "CHANGELOG.md", "README.md",
                          "adapters/tracker/youtrack.md"}  # explains that Type=Epic is meaningless

TOOL_NAMES = re.compile(
    r"\b(pnpm|npm|yarn|vitest|jest|biome|eslint|tsc|turbo|cargo|dotnet|composer|phpunit|go test)\b"
    r"|\bgh (api|pr|repo)\b|mcp__[a-z0-9_-]+__")
CORE_DIRS = ("protocol", "skills", "agents")


@functools.lru_cache(maxsize=None)
def git_visible_files() -> Optional[Set[Path]]:
    """Tracked plus untracked-but-not-ignored files; None outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {ROOT / rel for rel in out.decode("utf-8").split("\0") if rel}


def iter_files(*dirs: str):
    bases = [ROOT / d for d in dirs] if dirs else [ROOT]
    visible = git_visible_files()
    for base in bases:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if visible is not None and path not in visible:
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


class ScriptCallLint(unittest.TestCase):
    """A worktree-isolated session rejects commands it reads as shell builtins that run
    strings (`state.py complete` was refused in five live runs)."""
    RISKY = {"complete", "compgen", "eval", "exec", "source", "trap", "command", "builtin", "alias", "bind"}
    PARSER_RE = re.compile(r'add_parser\(\s*"([a-z-]+)"')
    COMPLETE_CALL_RE = re.compile(
        r"""state\.py["']?\s+complete\b|`complete\s+(refine|start|research|spec|plan|implement|review|finalize)\b""")

    def test_script_subcommands_avoid_risky_builtins(self):
        hits = []
        for path in sorted((ROOT / "scripts").glob("*.py")):
            hits += [f"scripts/{path.name}: {m.group(1)}" for m in self.PARSER_RE.finditer(
                path.read_text(encoding="utf-8")) if m.group(1) in self.RISKY]
        self.assertEqual(hits, [], "подкоманды совпадают со встроенными командами shell:\n" + "\n".join(hits))

    def test_core_calls_finish_not_complete(self):
        hits = []
        for path in iter_files(*CORE_DIRS):
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.COMPLETE_CALL_RE.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "state.py complete вместо finish:\n" + "\n".join(hits))


class ArtifactsCommitLint(unittest.TestCase):
    """Whether task artifacts are committed depends on artifacts.tracked (protocol/artifacts.md,
    «Коммит артефактов»): skills name the commit only together with that rule."""
    COMMIT_RE = re.compile(r"[Кк]оммит (артефактов|состояния)")

    def test_skills_reference_the_artifacts_commit_rule(self):
        hits = []
        for path in iter_files("skills"):
            rel = path.relative_to(ROOT).as_posix()
            lines = path.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines, 1):
                window = line + " " + (lines[n] if n < len(lines) else "")
                if self.COMMIT_RE.search(line) and "artifacts.md" not in window:
                    hits.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "коммит артефактов без ссылки на artifacts.md:\n" + "\n".join(hits))


class CardFieldsLint(unittest.TestCase):
    """omixflow_lib.CARD_FIELDS (used by state.py and the kanban board) is the formal record
    that protocol/artifacts.md lists in «Хранение в задаче трекера»."""

    def test_card_fields_are_the_protocol_list(self):
        text = (ROOT / "protocol" / "artifacts.md").read_text(encoding="utf-8")
        start = text.index("- **`state.yaml`** при создании задачи")
        end = text.index("\n- **", start + 1)
        named = set(re.findall(r"`([a-z_]+)`", text[start:end]))
        self.assertEqual(sorted(set(lib.CARD_FIELDS) - {"schema"} - named), [],
                         "поля CARD_FIELDS, которых нет в перечне artifacts.md")


class DecisionPointsLint(unittest.TestCase):
    ID_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")
    REF_RE = re.compile(r"точк[аеиу] `([^`]+)`")
    PIPELINE_SKILLS = ("develop", "refine", "start", "research", "spec", "plan",
                       "implement", "review", "finalize")
    DIRECT_MODE_RE = re.compile(r"AskUserQuestion|\bAUQ\b|гибрид", re.I)

    def points(self):
        try:
            return lib.decision_points()
        except lib.OmixflowError as e:
            self.fail(str(e))

    def test_lead_defaults_match_schema(self):
        lead = lib.load_schema()["properties"]["lead"]["properties"]
        self.assertEqual(lead["default"]["default"], lib.LEAD_DEFAULT_MODE)
        self.assertEqual(lead["timeout"]["default"], lib.LEAD_DEFAULT_TIMEOUT)
        self.assertEqual(lead["stall"]["default"], lib.LEAD_DEFAULT_STALL)
        self.assertEqual({k: v["default"] for k, v in lead["actions"]["properties"].items()},
                         lib.LEAD_DEFAULT_ACTIONS)

    def test_schema_policy_keys_equal_points(self):
        schema = lib.load_schema()
        names = schema["properties"]["lead"]["properties"]["policy"]["propertyNames"]["enum"]
        self.assertEqual(names, [point for point, _ in self.points()],
                         "ключи lead.policy в схеме расходятся с таблицей protocol/dialog.md")

    def test_ids_are_well_formed_and_unique(self):
        points = self.points()
        ids = [point for point, _ in points]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)), "идентификаторы точек повторяются")
        for point, kind in points:
            with self.subTest(point=point):
                self.assertIn(kind, lib.POINT_KINDS)
                port, dot, action = point.rpartition(".")
                self.assertEqual(bool(dot), kind == "внешнее",
                                 f"{point}: вид `внешнее` ⇔ идентификатор вида {{порт}}.{{действие}}")
                if dot:
                    self.assertIn(port, lib.PORTS, f"{point}: неизвестный порт")
                self.assertRegex(action, self.ID_RE)

    def test_pipeline_skills_do_not_pick_dialog_mode(self):
        """Pipeline skills name decision points; the mode lives in protocol/dialog.md."""
        hits = []
        for name in self.PIPELINE_SKILLS:
            path = ROOT / "skills" / name / "SKILL.md"
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.DIRECT_MODE_RE.search(line):
                    hits.append(f"skills/{name}/SKILL.md:{n}: {line.strip()}")
        self.assertEqual(hits, [], "режим диалога в скиле пайплайна вместо точки решения:\n"
                         + "\n".join(hits))

    def test_references_name_known_points(self):
        ids = {point for point, _ in self.points()}
        hits = []
        for path in iter_files("protocol", "skills"):
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                hits += [f"{rel}:{n}: {m.group(1)}" for m in self.REF_RE.finditer(line)
                         if m.group(1) not in ids]
        self.assertEqual(hits, [], "ссылки на неизвестные точки решения:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
