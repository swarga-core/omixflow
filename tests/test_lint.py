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


class AgentReportLint(unittest.TestCase):
    """A long agent reply is truncated in the message channel (protocol/runtime.md, «Отчёт
    агента»): coder and tester write the full report to REPORT_PATH, and every skill that
    hands them work passes the path."""

    def test_agents_write_reports_to_a_file(self):
        for agent, markers in {"coder": ("REPORT_PATH", "TREE STATE", "MUTATIONS", "BYTES CHECK",
                                         "SUPPRESSIONS CHECK", "gate.py"),
                               "tester": ("REPORT_PATH", "TREE STATE", "MUTATIONS", "BYTES CHECK",
                                          "SUPPRESSIONS CHECK", "gate.py", "agents/coder.md")}.items():
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertEqual([m for m in markers if m not in body], [])

    def test_skills_pass_report_path_to_coder_and_tester(self):
        hits = []
        for path in iter_files("skills"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"name: (coder|tester)-\{id\}", text) and "REPORT_PATH" not in text:
                hits.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(hits, [], "скил даёт работу coder/tester без REPORT_PATH:\n" + "\n".join(hits))

    def test_report_labels_come_from_the_runtime_table(self):
        text = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        section = text[text.index("## Отчёт агента"):text.index("## Модели")]
        known = set(re.findall(r"^\| `([a-z-]+\{[A-Z]\})` \|", section, re.M))
        self.assertTrue(known, "таблица меток в runtime.md не найдена")
        used = set()
        for path in iter_files("skills"):
            used |= set(re.findall(r"reports/(?:\{phase\}|implement|review|finalize)-([a-z-]+\{[A-Z]\})\.md",
                                   path.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertEqual(sorted(used - known), [], "метки отчётов вне таблицы runtime.md")

    def test_parent_line_asks_for_one_report_per_turn(self):
        """MEW-2: agents sent the summary with SendMessage and then a second, longer one as
        their final text, which reached the orchestrator too (idle notice)."""
        text = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        start = text.index("    PARENT: the orchestrator")
        parent = text[start:text.index("PLUGIN_ROOT:", start)]
        for marker in ("once per turn", "`sent`", "never a second summary"):
            self.assertIn(marker, parent)

    def test_parent_line_keeps_the_report_in_the_file(self):
        """T-1: a subagent without SendMessage answered with the full text and wrote no file at
        REPORT_PATH; the PARENT line then called its final reply the report."""
        text = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        start = text.index("    PARENT: the orchestrator")
        parent = " ".join(text[start:text.index("PLUGIN_ROOT:", start)].split())
        self.assertNotIn("final reply is the report", parent)
        for marker in ("the short summary when the full report goes to a file", "written before the summary"):
            self.assertIn(marker, parent)
        for agent in ("coder", "tester"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertIn("a reply without the file is not a report", " ".join(body.split()).lower())

    def test_background_gate_names_come_from_the_report_label(self):
        """T-3: the coder named a sync gate itself (`step-sync-build`) and the orchestrator's
        `poll build` found no log: an agent's gate name is `{label}-{gate}`, the label being
        its report file's name."""
        runtime = " ".join((ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8").split())
        gates = runtime[runtime.index("## Гейты"):runtime.index("## Проверки оркестратора")]
        for marker in ("`{метка}-{gate}`", "`{moment}-{gate}`", "`delivery-build`"):
            self.assertIn(marker, gates)
        self.assertNotIn("{phase}-{gate}", gates)  # `delivery` is a moment, not a phase
        self.assertIn("{moment}-{gate}", (ROOT / "scripts" / "gate.py").read_text(encoding="utf-8"))
        for agent in ("coder", "tester", "reviewer"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            calls = re.findall(r"gate\.py\s+(?:start|poll)\s+(\S+)", body)
            with self.subTest(agent=agent):
                self.assertTrue(calls)
                self.assertEqual(sorted(set(calls)), ["{label}-{gate}"])
        _, tester = lib.parse_frontmatter(ROOT / "agents" / "tester.md")
        self.assertIn("gate.py {label}-{gate}, EXIT {code}", tester)
        implement = " ".join((ROOT / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("`gate.py poll {имя}`", implement)

    def test_mutations_have_a_line_per_new_test(self):
        """T-4: the coder listed 47 probes by function, implement 2.2 checks every new test
        against MUTATIONS, and the step went back."""
        for agent in ("coder", "tester"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            flat = " ".join(body.split()).lower()
            with self.subTest(agent=agent):
                self.assertIn("mutations has a line for every new test", flat)
                self.assertNotIn("one line per probe", flat)
        implement = " ".join((ROOT / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("Каждый новый тест шага", implement)

    def test_review_fixes_are_routed_by_the_files_they_touch(self):
        """T-2: a `code` finding in a test file would have gone to the coder by category while
        the tester fixed the same file in the same pass."""
        cycle = " ".join((ROOT / "protocol" / "review-cycle.md").read_text(encoding="utf-8").split())
        self.assertIn("исполнитель по файлам правки", cycle)
        self.assertNotIn("исполнитель по категории", cycle)
        review = " ".join((ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("по файлам правки", review)
        self.assertNotIn("По исполнителю категории", review)
        _, body = lib.parse_frontmatter(ROOT / "agents" / "reviewer.md")
        flat = " ".join(body.split())
        self.assertIn("by the files the fix touches", flat)
        for stale in ("tells the orchestrator who fixes it", "agent for the category"):
            self.assertNotIn(stale, flat)

    def test_agents_report_through_the_parent_channel(self):
        """An agent's own «reply with a summary» wording beside the PARENT line gave MEW-2 a
        second, longer report every turn: every agent's output section points to PARENT."""
        for agent in ("architect", "coder", "researcher", "reviewer", "tester"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertIn("channel as the PARENT line says", " ".join(body.split()))

    def test_rotation_measures_context_by_the_transcript_script(self):
        """Named agents' idle notices carry no usage: tiers.md names agent_ctx.py, which exists."""
        text = (ROOT / "protocol" / "tiers.md").read_text(encoding="utf-8")
        start = text.index("## Смена агента по ходу задачи")
        end = text.find("\n## ", start + 1)
        section = text[start:end if end != -1 else len(text)]
        self.assertIn("scripts/agent_ctx.py", section)
        self.assertIn("неизвестен", section)
        self.assertTrue((ROOT / "scripts" / "agent_ctx.py").is_file())
        self.assertIn("не потолок", section)  # T-5: one step took the coder from 237k to 439k

    def test_report_file_names_avoid_the_word_report(self):
        """T-5: the harness refused every subagent Write to a file with `report` in its name
        (`report2-head.md`), while writes to `reports/{phase}-{label}.md` passed."""
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        section = runtime[runtime.index("## Отчёт агента"):runtime.index("## Модели")]
        rows = re.findall(r"^\| `([^`]+)` \|", section, re.M)
        self.assertEqual(len(rows), len(re.findall(r"^\| `", section, re.M)))
        self.assertGreaterEqual(len(rows), 9)
        self.assertEqual([label for label in rows if "report" in label.lower()], [])
        paths = []
        for path in iter_files(*CORE_DIRS):
            paths += re.findall(r"(?:reports|review)/[^\s`)\]]+\.(?:md|json)", path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(set(paths)), 10)
        self.assertEqual(sorted({p for p in paths if "report" in p.rsplit("/", 1)[-1].lower()}), [])
        flat_section = " ".join(section.split())
        self.assertIn("`REPORT_PATH refused by the harness: {сообщение харнесса}`", flat_section)
        self.assertIn("кроме ответа `REPORT_PATH refused by the harness`", flat_section)
        self.assertIn("у coder'а `NOTES`, у tester'а `SUMMARY`", flat_section)
        self.assertIn("агент, которому харнесс отказал в записи `REPORT_PATH`", flat_section)
        for agent in ("coder", "tester"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            flat = " ".join(body.split())
            with self.subTest(agent=agent):
                self.assertIn("a piece of the report a name containing `report`", flat)
                self.assertIn("REPORT_PATH refused by the harness", flat)
                self.assertIn("do not retry under another name or through the shell", flat)
        # T-6: the tester followed the harness's system-prompt note against report files and
        # wrote no file; every agent that writes a report file is told the note does not cover it.
        for agent in ("coder", "tester", "researcher", "reviewer"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            flat = " ".join(body.split())
            with self.subTest(agent=agent):
                self.assertIn("is a task artifact, not a summary file", flat)
                self.assertIn("for any other report or summary file the note stands", flat.lower())
        implement = " ".join((ROOT / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8").split())
        tester = implement.index("**2.3 Tester.**")
        for part in (implement[implement.index("**2.2 Отчёт coder.**"):tester],
                     implement[tester:implement.index("**2.4")]):
            self.assertIn("REPORT_PATH refused by the harness", part)


class AgentRulesLint(unittest.TestCase):
    """Field rules of 0.7.1 (Swarga AI Studio T-9, T-18)."""

    def body(self, agent: str) -> str:
        _, text = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
        return " ".join(text.split())

    def flat(self, rel: str) -> str:
        return " ".join((ROOT / rel).read_text(encoding="utf-8").split())

    def test_checkpoint_gates_come_with_also(self):
        """T-9: the step 6 checkpoint named build, outside the step set; the coder ran only `gates`."""
        coder = self.body("coder")
        self.assertIn("Add `--also {gate}` for every gate the step's test checkpoint names", coder)
        self.assertIn("`also_missing`", coder)
        self.assertIn("«Test checkpoint» шага (plan.md; у тира S", self.flat("skills/implement/SKILL.md"))
        self.assertIn("only those the project declares", self.body("architect"))
        tester = self.body("tester")
        self.assertIn("- **CHECKPOINT_GATES** (implement steps only; absent means none):", tester)
        self.assertIn("Run the gates of CHECKPOINT_GATES too, and only those", tester)
        self.assertIn("`CHECKPOINT_GATES` (гейты «Test checkpoint» шага кроме `test`", self.flat("skills/implement/SKILL.md"))
        self.assertIn("`resolve.py verify --at step --also {gate}`", self.flat("adapters/lang/PORT.md"))

    def test_probes_cover_existing_behaviour_and_unnamed_probes(self):
        """T-18: «the schema is unchanged and it checks existing behaviour», «none was requested»."""
        for agent in ("coder", "tester"):
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("pins behaviour that already existed", body)
                self.assertIn('"no probe was requested" are not reasons', body)
                self.assertIn("{new test} — no probe possible: {why}", body)
        implement = self.flat("skills/implement/SKILL.md")
        self.assertIn("почему пробу не построить", implement)
        self.assertIn("«пробу не просили» — не причины", implement)
        for agent in ("coder", "tester"):
            self.assertIn("a test that stays green is strengthened, not excused", self.body(agent))

    def test_agents_run_commands_without_cd(self):
        """T-18: the coder ran `cd` twice; no agent definition had the rule."""
        shell = [p.stem for p in sorted((ROOT / "agents").glob("*.md"))
                 if "Bash" in (lib.parse_frontmatter(p)[0].get("tools") or "")]
        self.assertEqual(shell, ["coder", "researcher", "reviewer", "tester"])
        for agent in shell:
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("ommands without `cd`", body)
                self.assertIn("`git -C {dir}`", body)
                self.assertNotIn("persists between your shell calls", body)  # a subagent's cwd is reset

    def test_reply_paths_are_copied_not_rebuilt(self):
        """T-9: the architect edited spec.md in the worktree and named the main tree's path."""
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        start = runtime.index("    PARENT: the orchestrator")
        parent = " ".join(runtime[start:runtime.index("PLUGIN_ROOT:", start)].split())
        self.assertIn("A path in your reply starts with a path given in this prompt", parent)
        self.assertIn("Путь в ответе агента — не источник", " ".join(runtime.split()))

    def test_scratch_goes_to_the_scratchpad_and_leftovers_are_reported(self):
        """MEW-17: agents' probes stayed in bare /tmp (118 MB) and could not be removed."""
        shell = [p.stem for p in sorted((ROOT / "agents").glob("*.md"))
                 if "Bash" in (lib.parse_frontmatter(p)[0].get("tools") or "")]
        for agent in shell:
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("never bare `/tmp`", body)
                self.assertIn("do not try another form of removal", " ".join(body.split()))
                self.assertIn("SCRATCH_DIR", body)
                self.assertIn("SCRATCH: ", body)
        for agent in ("coder", "tester"):
            self.assertIn("SCRATCH: clean | {path} {size}", self.body(agent))
        self.assertIn("**Временные файлы агента**", self.flat("protocol/runtime.md"))
        runtime = self.flat("protocol/runtime.md")
        self.assertIn("SCRATCH_DIR: {scratchpad оркестратора}/{имя агента}", runtime)
        self.assertIn("`- SCRATCH {метка}: {путь} {размер}`", runtime)
        self.assertIn("`SCRATCH` не `clean` — в log.md строкой `- SCRATCH {метка}: {путь} {размер}`",
                      self.flat("skills/implement/SKILL.md"))
        self.assertIn("`CHECKPOINT GATES`, `SCRATCH`; пропуск", self.flat("skills/implement/SKILL.md"))
        finalize = self.flat("skills/finalize/SKILL.md")
        self.assertIn("Временные файлы агентов вне дерева", finalize)
        self.assertIn("собрать до удаления `TASK_DIR`", finalize)
        self.assertIn("`scratch` — остаток временных файлов агентов", self.flat("protocol/lead.md"))
        self.assertIn("(поле `scratch` из `done`", self.flat("skills/lead/SKILL.md"))

    def test_a_subitem_the_lead_splits_off_is_added_to_the_question(self):
        """T-8#6: the lead split F6-pass off F6; `state.py ack` refused it and `close F6` closed the question."""
        lead_md = self.flat("protocol/lead.md")
        self.assertIn("`state.py ack … F6-pass=E-29 --add`", lead_md)
        self.assertIn("(подпункт, выделенный лидом, — с `--add`; метку со статусом из `open`", lead_md)
        self.assertIn("до `decision`, закрывающего пункт", lead_md)
        self.assertIn("с `open: F6-pass E-29`", lead_md)
        self.assertIn("SCRATCH_DIR: {как в основном шаблоне}", self.flat("protocol/runtime.md"))
        self.assertEqual(self.flat("skills/finalize/SKILL.md").count("остатком `SCRATCH`"), 2)
        self.assertIn("заводит только лид, свои метки сессия без дефиса", lead_md)
        self.assertIn("выделить подпункт `{метка}-{суффикс}` в `ack` до `decision`", self.flat("skills/lead/SKILL.md"))

    def test_agents_are_resumed_by_id_after_a_session_restart(self):
        """T-7, MEW-25: after `respawn` the session's earlier agents were unreachable by name;
        by id T-7 kept the reviewer's context, MEW-25 respawned them and lost it."""
        runtime = self.flat("protocol/runtime.md")
        self.assertIn("по `id` из `python3 {корень плагина}/scripts/agent_ctx.py {имя}`", runtime)
        self.assertIn("Нет id или и по id не дошло — новый спавн", runtime)
        self.assertIn("После `/resume` с новым id сессии прежних агентов нет", runtime)
        for skill in ("implement", "spec", "plan", "review", "research", "finalize"):
            with self.subTest(skill=skill):
                self.assertIn("после перезапуска сессии — по id", self.flat(f"skills/{skill}/SKILL.md"))
        for path in iter_files("skills"):  # every skill that continues agents points to the rule
            text = " ".join(path.read_text(encoding="utf-8").split())
            if re.search(r"SendMessage[^.]{0,80}(живому|agents\.|`(architect|reviewer|researcher|coder)-\{id\})"
                         r"|из `agents\.[a-z_]+`", text):
                with self.subTest(skill=path.parent.name):
                    self.assertIn("после перезапуска сессии — по id", text)
        self.assertIn("после перезапуска сессии — по id", self.flat("protocol/review-cycle.md"))
        for rel in ("protocol/lead.md", "skills/lead/SKILL.md"):
            with self.subTest(rel=rel):
                self.assertIn("прежних агентов — по id (`agent_ctx.py`)", self.flat(rel))

    def test_a_failed_agent_gets_the_same_assignment_again(self):
        """T-7: the reviewer broke off on ENOTFOUND before writing FINDINGS_PATH."""
        runtime = self.flat("protocol/runtime.md")
        self.assertIn("**Обрыв сбоем.** Уведомление `failed` (сбой API, сеть) без файла отчёта", runtime)
        self.assertIn("Второй `failed` на то же задание — СТОП", runtime)
        self.assertIn("задание, оборванное остановкой сессии", runtime)
        implement = self.flat("skills/implement/SKILL.md")
        self.assertIn("Уведомление `failed` без файла — повтор того же задания", implement)
        self.assertIn("`failed` — не stall", implement)
        self.assertIn("**Повтор после `failed`**", self.flat("protocol/review-cycle.md"))

    def test_commit_templates_leave_room_for_the_adapter_scope(self):
        """MEW-25: the literal review-fix template gave a commit without the zone scope mewria requires."""
        self.assertIn("{feat|fix|refactor|test|docs}[({область})]: {описание шага}", self.flat("skills/implement/SKILL.md"))
        review = self.flat("skills/review/SKILL.md")
        self.assertIn("fix[({область})]: address review findings for {id} (pass {N})", review)
        self.assertIn("fix[({область})]: repair red gate for {id} (gate fix {K})", review)
        port = self.flat("adapters/workspace/PORT.md")
        self.assertIn("| commit_message | нет |", port)
        self.assertIn("## commit_message", (ROOT / "adapters" / "workspace" / "PORT.md").read_text(encoding="utf-8"))
        self.assertIn("в адаптере без раздела — его правило о сообщении в прозе", port)
        # every commit template in the skills either leaves room for the scope or uses the task id
        templates = []
        for path in iter_files("skills"):
            text = path.read_text(encoding="utf-8")
            templates += [(path.parent.name, m.group(0)) for m in re.finditer(
                r"(?m)(?:^|`|\")(?:\{feat\|fix[^}]*\}|feat|fix|docs|test|refactor|chore)(\S*?): (?=\S)", text)]
        self.assertGreaterEqual(len(templates), 6)
        bad = [t for t in templates if not ("[({область})]" in t[1] or "({id})" in t[1])]
        self.assertEqual(bad, [])
        self.assertIn("repair sync breakage for {id} (sync {K})", self.flat("skills/implement/SKILL.md"))

    def test_capability_tables_match_the_port_frontmatter(self):
        """0.7.3 review: `commit_message` was in the workspace table but not in `optional:`,
        so doctor would warn about an adapter that declares it."""
        for path in sorted((ROOT / "adapters").glob("*/PORT.md")):
            meta, body = lib.parse_frontmatter(path)
            declared = set(meta.get("required") or []) | set(meta.get("optional") or [])
            section = body[body.index("## Возможности"):] if "## Возможности" in body else body
            rows = set(re.findall(r"^\| ([a-z_]+) \| (?:да|нет) \|", section, re.M))
            with self.subTest(port=path.parent.name):
                self.assertTrue(rows)
                self.assertEqual(sorted(rows ^ declared), [])


class LeadLaunchLint(unittest.TestCase):
    """The lead launches task sessions by the developer's word, in the background or in a
    window (protocol/lead.md, «Запуск сессий»); the second SwAIS wave ran T-18, T-8 and T-9
    in the background."""

    def section(self, text: str, start: str) -> str:
        begin = text.index(start)
        end = text.find("\n## ", begin + 1)
        return " ".join(text[begin:end if end != -1 else len(text)].split())

    def test_protocol_describes_the_launch(self):
        lead_md = (ROOT / "protocol" / "lead.md").read_text(encoding="utf-8")
        self.assertNotIn("сессии не запускает", " ".join(lead_md.split()))
        launch = self.section(lead_md, "## Запуск сессий")
        for marker in ("`scripts/sessions.py launch`", "санкция `A-{n}`", "в реестре есть сессия без `done`",
                       "остановленную предлагает поднять", "через Bash или скриптом",
                       "`launch` в `lead.yaml`", "`background` или `terminal`", "`part_runner: sequential`",
                       "в режиме разрешений лида", "`permissionMode`", '{"bgIsolation": "none"}', "статус `waiting`",
                       "`sessions.py watch`", "`sessions.py respawn {имя}`", "постоянной санкции",
                       "во временном worktree", "`claude rm`", "Workspace not trusted"):
            with self.subTest(marker=marker):
                self.assertIn(marker, launch)

    def test_skill_asks_the_mode_once_and_watches_background_sessions(self):
        skill = (ROOT / "skills" / "lead" / "SKILL.md").read_text(encoding="utf-8")
        flat = " ".join(skill.split())
        launch = self.section(skill, "## 1a. Запуск задачи")
        for marker in ("lead.py list --type session --task {id}", "--task {id}/{part}", "SESSIONS probe --root",
                       "Где запускать {id} и все следующие задачи?", "в фоне", "в отдельных окнах Terminal",
                       "(рекомендую)", "`launch: background | terminal`", 'lead.py approve --action "запуск {имя}',
                       "SESSIONS launch {имя} --root {корень} --mode {launch}",
                       "/omixflow:develop {id} --lead={имя лида} --worktree", "`part_runner: sequential`",
                       "--owner {имя лида} --notify", "`bg_isolation`"):
            with self.subTest(marker=marker):
                self.assertIn(marker, launch)
        self.assertIn("SESSIONS respawn {имя} --root {корень}", flat)
        self.assertIn("постоянной санкции «поднимай остановленные сам»", flat)
        self.assertIn("Исключение — режим запуска на первой задаче", flat)

    def test_named_subcommands_exist(self):
        parsers = set(re.findall(r'add_parser\(\s*"([a-z-]+)"', (ROOT / "scripts" / "sessions.py").read_text(encoding="utf-8")))
        used = set()
        for rel in ("protocol/lead.md", "skills/lead/SKILL.md", "README.md", "CHANGELOG.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            used |= set(re.findall(r"(?:sessions\.py|SESSIONS)`? ([a-z]+)\b", text))
        self.assertTrue(used)
        self.assertEqual(sorted(used - parsers), [])


class VerifyLint(unittest.TestCase):
    """Gate sets and orchestrator checks are computed by `resolve.py verify` at fixed places
    (adapters/lang/PORT.md, «Гейты»): before 0.6.0 the orchestrator ran a check only when it
    remembered the adapter section, and four files read `when` differently."""

    PLACES = {"skills/implement/SKILL.md": ("step", "review"), "skills/review/SKILL.md": ("review", "step"),
              "skills/finalize/SKILL.md": ("delivery",), "skills/lead/SKILL.md": ("accept",),
              "protocol/lead.md": ("accept",), "agents/coder.md": ("step", "review")}
    CALL_RE = re.compile(r"resolve\.py verify --at (\w+)([^`]*)")

    def test_places_call_the_plan_for_their_moments(self):
        for rel, moments in self.PLACES.items():
            text = " ".join((ROOT / rel).read_text(encoding="utf-8").split())
            calls = self.CALL_RE.findall(text)
            for moment in moments:
                with self.subTest(file=rel, moment=moment):
                    self.assertIn(moment, [m for m, _ in calls])
            for moment, args in calls:
                with self.subTest(file=rel, call=moment + args):
                    self.assertIn(moment, lib.MOMENTS)
                    if moment in ("review", "delivery"):  # the branch view needs its base
                        self.assertRegex(args, r"--task|--base")

    def test_moments_and_step_gates_match_the_port(self):
        text = (ROOT / "adapters" / "lang" / "PORT.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| шага |"))
        for gate in lib.STEP_GATES:
            self.assertIn(gate, row)
        schema = lib.load_schema()["properties"]["checks"]["additionalProperties"]["properties"]["at"]
        self.assertEqual(tuple(schema["items"]["enum"]), lib.MOMENTS)
        for moment in lib.MOMENTS:
            self.assertIn(f"`{moment}`", text)


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
        self.assertEqual(lead["delivery"]["default"], lib.LEAD_DEFAULT_DELIVERY)
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
