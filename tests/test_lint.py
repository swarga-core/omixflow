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
import json
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
                self.assertIn(meta.get("effort"), lib.EFFORT_LEVELS)     # not the developer's settings (0.9.3)


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

    def test_test_support_the_prose_names_is_machine_readable(self):
        """G-67, SwAIS T-10: the ts adapter's prose named `test/` test support, its globs did
        not, and `plan.py files` counted the helpers as code."""
        for path in sorted((ROOT / "adapters" / "lang").glob("*.md")):
            if path.name == "PORT.md":
                continue
            meta, body = lib.parse_frontmatter(path)
            if "Тестовая поддержка" in body:
                with self.subTest(file=path.name):
                    support = (meta.get("tests") or {}).get("support")
                    self.assertIsInstance(support, list)
                    for d in re.findall(r"`([\w.-]+)/`", body.split("Тестовая поддержка", 1)[1].split("\n- ", 1)[0]):
                        self.assertIn(f"**/{d}/**", support)
        self.assertIn("support: [glob…]", (ROOT / "adapters" / "lang" / "PORT.md").read_text(encoding="utf-8"))

    def test_port_contracts_declare_required(self):
        for port in lib.PORTS:
            contract = lib.port_contract(port)
            self.assertTrue(contract["required"], port)


class SkillLint(unittest.TestCase):
    SEND_RE = re.compile(r"SendMessage[^\n]*?\b(to:\s*)?[\"'`]?([a-z]+)-\{", re.I)
    SPAWN_RE = re.compile(r"name:\s*[\"'`]?([a-z]+)-\{", re.I)

    def test_spec_is_intent_scenarios_contracts_and_decisions_and_design_lives_in_the_plan(self):
        """0.9 step 2: specs of 0.5–0.8 averaged 34k characters of per-file design; the
        reviewer's catches were in scenarios, boundary contracts and the claims behind
        decisions. The plan carries the design and says which scenarios each step covers."""
        _, architect = lib.parse_frontmatter(ROOT / "agents" / "architect.md")
        flat_arch = " ".join(architect.split())
        for marker in ("## Intent", "## Scenarios", "## Contracts", "## Decisions", "## Out of Scope",
                       "**Covers:**", "**Design:**", "rests on:"):
            self.assertIn(marker, architect, marker)
        self.assertNotIn("#### Modified contracts", architect)      # the per-slice design format is gone
        # the tests an architect can apply: what is a Contract, what is a Decision (finding 3, 4 of the step review)
        self.assertIn("**What is a Contract.** Any statement a caller outside the files that implement it relies on", flat_arch)
        self.assertIn("another package of the same task included", flat_arch)
        self.assertIn("**What is a Decision.** A choice with a rejected alternative the developer could prefer", flat_arch)
        self.assertIn("also when it is about internals", flat_arch)
        self.assertIn("**Decisions live in the spec, not the plan.**", flat_arch)
        self.assertIn("Every scenario and every contract is covered by a step", flat_arch)
        self.assertIn("a step with `Covers: none` changes no observable behaviour", flat_arch)
        self.assertIn("ids that are append-only within the task", flat_arch)
        self.assertIn("process criteria (gates, test style, review) go to the plan's Verification", flat_arch)
        self.assertEqual(flat_arch.count("Marshal.SizeOf"), 1)        # the evidence once, not three times
        _, reviewer = lib.parse_frontmatter(ROOT / "agents" / "reviewer.md")
        flat = " ".join(reviewer.split())
        self.assertIn("every claim a decision rests on probed", flat)
        self.assertIn("Design that no caller and no project spec states is a `spec` finding", flat)
        self.assertIn("Not an aspect: wording, section order, style", flat)
        self.assertIn("every behavioural acceptance criterion of task.md has one", flat)
        self.assertIn("every scenario and contract in some step's `Covers`", flat)
        self.assertIn("project specs listed; `plan.py files`: the file and step thresholds) — do not repeat it", flat)
        self.assertIn("a step with `Covers: none` whose Design or Files change observable behaviour is a finding", flat)
        self.assertIn("a Design choice that meets the Decision test (architect.md «What is a Decision») without a D-n is a `spec` finding", flat)
        self.assertIn("**Plan review** (plan, architecture, spec)", flat)
        for agent in ("coder", "tester"):            # a test proves a scenario: the MUTATIONS line names it
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertIn("- {new test} [S{n}] ← {probe}", body)
        _, tester = lib.parse_frontmatter(ROOT / "agents" / "tester.md")
        self.assertIn("`## Scenarios` (S1, S2, …) are the tests to write", " ".join(tester.split()))
        _, coder = lib.parse_frontmatter(ROOT / "agents" / "coder.md")
        self.assertIn("covered scenarios and contracts, design, files, test checkpoint", " ".join(coder.split()))
        spec = (ROOT / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        flat_spec = " ".join(spec.split())
        self.assertIn("Intent, Scenarios (S1…), Contracts, Dependencies, Decisions", flat_spec)
        self.assertIn("ASPECTS спеки из `agents/reviewer.md`, «Aspects by phase»", flat_spec)   # L points, not restates
        self.assertIn("`## Scenarios` (1–3 сценария S1…", flat_spec)                   # S tier too
        self.assertIn("`## Out of Scope` (одной строкой", flat_spec)
        self.assertIn("ярлыки буквально", flat_spec)                                  # the S skeleton check reads
        for label in ("**Covers:** S1", "**Files:**", "**Test checkpoint:**"):
            self.assertIn(label, flat_spec)
        self.assertNotIn("Changes по слайсам", spec)
        self.assertNotIn("## Delta", spec)
        plan_skill = " ".join((ROOT / "skills" / "plan" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("Covers — сценарии, контракты и D-n шага; Design", plan_skill)       # L plan phase, finding 1
        for skill in ("spec", "plan"):                                 # the mechanical check runs before the reviewer
            text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertGreaterEqual(text.count("scripts/plan.py check --task TASK_DIR"), 2 if skill == "spec" else 1)
        self.assertIn("The mechanical part ran before you (`plan.py check`", flat)
        self.assertIn("do not repeat it", flat)
        self.assertNotIn("file paths exact, new files marked CREATE", flat)        # mechanical, the script's
        for judgement in ("an external resource", "seams with branches in flight", "`Transitional notes`"):
            self.assertIn(judgement, flat)                                      # the backlog's plan defects have an owner
        _, architect_body = lib.parse_frontmatter(ROOT / "agents" / "architect.md")
        self.assertIn("Lines of `plan.py check` come without ids", " ".join(architect_body.split()))
        for skill in ("spec", "plan"):
            text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertIn("Затем снова `plan.py check`", text)                   # after fixes too
        self.assertIn("Категории plan, architecture, spec", plan_skill)
        self.assertIn("выбор уровня решения без D-n — finding категории `spec`", plan_skill)
        for path in ("agents/architect.md", "skills/spec/SKILL.md", "skills/plan/SKILL.md"):
            m = re.search(r"^description:\s*(.*)$", (ROOT / path).read_text(encoding="utf-8"), re.M)
            desc = m.group(1) if m else ""                 # a colon in the description breaks the YAML parser
            with self.subTest(path=path):
                self.assertNotIn("the delta (what changes and why)", desc)
                self.assertNotIn("the task delta", desc)
        self.assertIn("`Design` consistent with the spec's contracts and decisions", flat)
        self.assertIn("the claim under that choice", flat)            # probed in the same pass (one-pass rule)
        self.assertIn("appears in a `[S{n}]` tag of the reports' MUTATIONS lines", flat)
        for path in iter_files("protocol", "skills", "agents"):       # the old form nowhere, not only in named files
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                for old in ("Research, Delta, Steps", "Changes по слайсам", "#### Modified contracts", "## Delta"):
                    self.assertNotIn(old, text)
        artifacts = (ROOT / "protocol" / "artifacts.md").read_text(encoding="utf-8")
        self.assertIn("Summary, Intent, Scenarios (S1…), Contracts, Dependencies, Decisions, Out of Scope", artifacts)
        phases = (ROOT / "protocol" / "phases.md").read_text(encoding="utf-8")
        self.assertIn("сценарии приёмки, контракты на границе, решения с основанием", phases)

    def test_artifact_review_searches_once_and_research_is_the_input_of_the_spec(self):
        """0.9 steps 3 and 5: passes 2–3 of spec reviews were a cascade of document edits
        (mewria: 20 of 31 outcome-changing findings in pass 1); research.md was cited once
        in 37 coder reports and averaged 31k chars of narrative."""
        cycle = (ROOT / "protocol" / "review-cycle.md").read_text(encoding="utf-8")
        limit = " ".join("\n".join(lib.section_lines(cycle, "Лимит проходов")[1]).split())
        self.assertIn("Ревью артефактов (Spec, Plan): один содержательный проход", limit)
        self.assertIn("новые findings в них — только `critical` и `warning [architecture]`", limit)
        self.assertIn("ревью кода это правило не касается", limit)
        _, reviewer = lib.parse_frontmatter(ROOT / "agents" / "reviewer.md")
        self.assertIn("On an artifact re-review (spec, plan) you add a new finding only when it is `critical` or `warning [architecture]`",
                      " ".join(reviewer.split()))
        for skill in ("spec", "plan"):
            text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertIn("только сверка фиксов", text)
        _, researcher = lib.parse_frontmatter(ROOT / "agents" / "researcher.md")
        flat = " ".join(researcher.split())
        self.assertIn("research.md is the input of the spec, not a document of its own", flat)
        for gone in ("## Current State", "## Existing Patterns", "## External Research"):
            self.assertNotIn(gone, researcher)
        self.assertIn("R1: {one fact the spec rests on", researcher)
        artifacts = (ROOT / "protocol" / "artifacts.md").read_text(encoding="utf-8")
        self.assertIn("Findings (факты `R{n}` с доказательством", artifacts)
        self.assertNotIn("Current State", artifacts)
        self.assertNotIn("## External Research", (ROOT / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8"))

    def test_the_sdd_invariant_takes_the_form_the_project_chooses(self):
        """0.9 step 7: project specs passed through in SwAIS and were 41 % bookkeeping in
        mewria; `specs.mode` picks descriptions, decision records or nothing, and the
        `structure` gate holds the invariants mechanically."""
        phases = " ".join((ROOT / "protocol" / "phases.md").read_text(encoding="utf-8").split())
        self.assertIn("по `specs.mode` конфига", phases)
        self.assertIn("**одна на решение D-n, которое меняет контракт**", phases)          # the unit of a record
        self.assertIn("Колонки статусов, прогресса и имён тестов, пометки «→ {id}» — конвенция проекта", phases)
        self.assertIn("`git diff --diff-filter=MDR {base}...HEAD -- {adr_dir}` пуст", phases)
        self.assertIn("`none` — ничего сверх spec.md задачи", phases)
        self.assertIn("без строки — `descriptions`", phases)
        cycle = " ".join((ROOT / "protocol" / "review-cycle.md").read_text(encoding="utf-8").split())
        self.assertIn("только при `specs.mode: descriptions` и правиле проекта о таких строках", cycle)
        review = " ".join((ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("второе задание прохода (только `specs.mode: descriptions`", review)
        pr = " ".join((ROOT / "skills" / "pr-review" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("По `specs.mode` конфига (`cfg.py get specs.mode`", pr)
        self.assertIn("`none`: группа G не проверяется", pr)
        for agent in ("architect", "coder", "reviewer"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertIn("absent means `descriptions`", " ".join(body.split()))
        glossary = (ROOT / "protocol" / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("| запись решения | decision record (ADR) |", glossary)
        self.assertIn("structure, build, e2e, visual |", glossary)
        self.assertIn("verify.structure", (ROOT / "adapters" / "lang" / "PORT.md").read_text(encoding="utf-8").split("---")[1])
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        self.assertIn("    SPECS: {descriptions | adr {specs.adr_dir} | none}", runtime)
        for agent in ("architect", "coder", "reviewer"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            with self.subTest(agent=agent):
                self.assertIn("- **SPECS**:", body)
        _, coder = lib.parse_frontmatter(ROOT / "agents" / "coder.md")
        flat = " ".join(coder.split())
        self.assertIn("`adr {dir}` — one decision record per D-n the step implements that changes a contract", flat)
        self.assertIn("a record that existed at the base of the branch is never edited", flat)
        _, reviewer = lib.parse_frontmatter(ROOT / "agents" / "reviewer.md")
        self.assertIn("every D-n of the branch that changes a contract has its record there", " ".join(reviewer.split()))
        for skill in ("spec", "plan", "implement", "review"):          # every spawn passes SPECS
            text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill):
                self.assertIn("`SPECS`", text)
        self.assertIn("structure", lib.GATES)
        self.assertIn("structure", lib.STEP_GATES)
        self.assertIn("`structure` (структурные инварианты кода", (ROOT / "adapters" / "lang" / "PORT.md").read_text(encoding="utf-8"))
        self.assertIn("| structure |", (ROOT / "adapters" / "lang" / "ts.md").read_text(encoding="utf-8"))
        template = (ROOT / "templates" / "flow.yaml").read_text(encoding="utf-8")
        self.assertIn("specs:\n  mode: descriptions\n  adr_dir: docs/decisions", template)
        self.assertIn("# structure:", template)
        self.assertIn("def check_specs", (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8"))

    def test_coder_amends_the_spec_and_stops_on_scope_decisions_and_contracts(self):
        """0.9 step 6: coders reported 13 departures from the spec's letter and stopped twice;
        amendments go into the spec with a report line, three kinds are a stop."""
        _, coder = lib.parse_frontmatter(ROOT / "agents" / "coder.md")
        flat = " ".join(coder.split())
        self.assertIn("**The spec learns from the implementation.**", flat)
        self.assertIn("SPEC AMENDMENTS:", coder)
        for kind in ("the **scope**", "the **choice of a decision**", "a **contract** in `## Contracts`"):
            self.assertIn(kind, flat)
        sys.path.insert(0, str(ROOT / "scripts"))
        import report as rp  # noqa: E402
        self.assertIn("SPEC AMENDMENTS", rp.SECTIONS["coder"])
        self.assertEqual(rp.STOP_SECTIONS, ("Contracts", "Out of Scope", "Intent"))
        self.assertTrue(callable(rp.decision_choices))              # a decision's choice, however it wraps
        implement = " ".join((ROOT / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("`SPEC AMENDMENTS` — в log.md", implement)
        self.assertIn("coder остановился на спеке: смена объёма (Intent, Out of Scope), выбора решения D-n или контракта", implement)
        self.assertIn("coder сообщает конфликт spec и plan (план противоречит спеке", implement)   # still a stop reason
        for skill in ("implement", "review"):                       # every baseline snapshots the spec
            text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertEqual(len(re.findall(r"report\.py baseline --out[^`]*?--task \{TASK_DIR\}", text)),
                                 text.count("report.py baseline --out"))
        review = " ".join((ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("правки спеки по ходу (`SPEC AMENDMENTS` отчётов", review)
        self.assertIn("от коммита артефактов фазы Plan до HEAD", review)
        cycle = " ".join("\n".join(lib.section_lines((ROOT / "protocol" / "review-cycle.md").read_text(encoding="utf-8"), "Лимит проходов")[1]).split())
        self.assertIn("оркестратор, получив их, отклоняет строкой в log.md", cycle)   # the rule binds the orchestrator too
        self.assertIn("Первый проход нового объёма", cycle)
        _, reviewer = lib.parse_frontmatter(ROOT / "agents" / "reviewer.md")
        self.assertIn("the spec's own diff since the plan", " ".join(reviewer.split()))

    def test_tier_rules_reach_every_place_the_tier_is_set_or_the_plan_is_final(self):
        """SwAIS T-1, T-6, T-7, T-11: M-tier plans touched 28–63 files against m_max_files 15
        and nothing in the flow said so (0.9 step 1); G-22: a tier from the brief was treated
        as forced by judgement; tiers.max: a project could not cap its tier."""
        tiers = (ROOT / "protocol" / "tiers.md").read_text(encoding="utf-8")
        titles = {s["title"] for s in lib.sections_of(tiers)}
        for title in ("Тир из постановки или брифа", "Потолок тира проекта", "Порог файлов после плана"):
            self.assertIn(title, titles)
        section = lib.section_lines(tiers, "Порог файлов после плана")
        self.assertEqual(section[0]["level"], 2)                        # its own heading: printed whole, read on demand
        threshold = " ".join("\n".join(section[1]).split())
        self.assertIn("scripts/plan.py files --task TASK_DIR", threshold)
        self.assertIn("Молчаливого «остаётся M» нет", threshold)
        self.assertIn("режет вертикально", threshold)                   # a slice by scenarios, not a prefix of steps
        self.assertIn("без прецедента", threshold)                      # lead.md: limit exceptions are not precedents
        self.assertNotIn("становится прецедентом", threshold)
        self.assertIn("до ревью", threshold)
        criteria = " ".join("\n".join(lib.section_lines(tiers, "Критерии")[1]).split())
        self.assertIn("нетестовых файлов", criteria)
        self.assertNotIn("Research, Delta, Steps", criteria)
        self.assertIn("Не выше потолка `tiers.max`; форсированный тир не повышается молча", criteria)
        for skill in ("spec", "plan"):          # every place a plan becomes final runs the threshold, with the full path
            text = " ".join((ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertGreaterEqual(text.count("scripts/plan.py files --task"), 3 if skill == "spec" else 2)
                self.assertNotIn("Порог файлов: `plan.py files", text)
                self.assertIn("«Порог файлов после плана»", text)
        develop = (ROOT / "skills" / "develop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("«Тир из постановки или брифа»", develop)
        self.assertIn("tiers.max", develop)
        self.assertIn("--forced --tier-source={flag|statement|brief}", develop)
        self.assertIn("как у задачи (потолок", develop)                 # a part's triage is capped too
        start = (ROOT / "skills" / "start" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("tiers.max", start)
        self.assertIn("--forced --tier-source {flag|statement|brief}", start)
        self.assertIn("тиром и его источником при `--forced`", start)
        research = " ".join((ROOT / "skills" / "research" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("выше потолка `tiers.max` скрипт откажет", research)
        state_py = (ROOT / "scripts" / "state.py").read_text(encoding="utf-8")
        self.assertIn("def check_tier_ceiling", state_py)
        lead_md = " ".join((ROOT / "protocol" / "lead.md").read_text(encoding="utf-8").split())
        self.assertIn("и из порога файлов тира («продолжить как есть»", lead_md)      # option c) is no precedent
        self.assertIn("`lead.py decide … --exception`", lead_md)
        self.assertIn("или из порога файлов тира — с `--exception`", lead_md)          # the session's own journal write too
        self.assertIn("запись идёт с `lead.py decide … --exception`", threshold)
        self.assertIn("--exception", (ROOT / "scripts" / "lead.py").read_text(encoding="utf-8"))
        lead_skill = " ".join((ROOT / "skills" / "lead" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("и из порога файлов тира", lead_skill)
        self.assertIn("`lead.py decide … --exception`", lead_skill)
        for path in ("protocol/lead.md", "skills/lead/SKILL.md"):
            self.assertIn("«Тир из постановки или брифа»", (ROOT / path).read_text(encoding="utf-8"), path)
        self.assertIn("план больше порога файлов тира", (ROOT / "protocol" / "dialog.md").read_text(encoding="utf-8"))
        self.assertIn("max: L", (ROOT / "templates" / "flow.yaml").read_text(encoding="utf-8"))

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


class CostLint(unittest.TestCase):
    """Every phase that leaves a trace records its cost (protocol/runtime.md, «Стоимость»):
    the phase skill calls `cost.py phase` before `state.py finish`, Finalize reports the total."""
    PHASES = ("start", "research", "spec", "plan", "implement", "review", "finalize")

    def test_phase_skills_record_the_phase_cost(self):
        missing = []
        for phase in self.PHASES:
            text = (ROOT / "skills" / phase / "SKILL.md").read_text(encoding="utf-8")
            calls = (f"cost.py phase TASK_DIR {phase}", f'cost.py" phase "{{TASK_DIR}}" {phase}')
            if not any(c in text for c in calls) or "«Стоимость»" not in text:
                missing.append(phase)
        self.assertEqual(missing, [], "скил фазы не вызывает cost.py phase со ссылкой на runtime.md «Стоимость»")
        finalize = (ROOT / "skills" / "finalize" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cost.total_eq", finalize)
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        self.assertIn("## Стоимость", runtime)
        self.assertIn("cost:", (ROOT / "protocol" / "artifacts.md").read_text(encoding="utf-8"))


class ProtocolDietLint(unittest.TestCase):
    """A skill names the protocol sections to read first and the conditions for the rest
    (protocol/runtime.md, «Чтение протокола»): the session does not read 110–175k characters
    of protocol before its first action. Section references must resolve to real headings."""
    PROTOCOL = sorted(p.stem for p in (ROOT / "protocol").glob("*.md"))
    WHOLE_OK = {"dialog", "phases"}                       # short files a prologue may read whole
    WHOLE_OK_CONDITIONAL = {"multitask"}                   # whole only under a condition («По условию»)
    WHOLE_OK_BY_SKILL = {"lead": {"lead"}}                 # the lead is lead.md's only full reader
    FILE_RE = re.compile(r"`?(?:protocol/)?(" + "|".join(PROTOCOL) + r")\.md`?")
    QUOTE_RE = re.compile(r"«([^»]+)»")

    ANY_MD_RE = re.compile(r"`?([A-Za-z0-9_.-]+)\.md`?")
    KNOWN_MD = {"SKILL", "CLAUDE", "README", "CHANGELOG", "PORT", "task", "log", "research", "spec", "plan",
                "multitask", "state", "comments", "review"}

    @classmethod
    def headings(cls, name: str) -> set:
        """Section titles as `resolve.py section` sees them: `##`/`###` headings and the bold
        labels that open a paragraph, fence-aware (a heading inside a template is not one)."""
        text = (ROOT / "protocol" / f"{name}.md").read_text(encoding="utf-8")
        return {s["title"] for s in lib.sections_of(text)}

    @classmethod
    def all_headings(cls) -> dict:
        return {name: cls.headings(name) for name in cls.PROTOCOL}

    @staticmethod
    def prologue(path: Path) -> str:
        """The skill text between its frontmatter (not YAML-parsed: descriptions hold colons)
        and its first `## ` heading; a `---` rule later in the body is not a frontmatter end."""
        text = path.read_text(encoding="utf-8")
        m = re.match(r"\A---[ \t]*\n.*?\n---[ \t]*\n", text, re.S)
        body = text[m.end():] if m else text
        return body.split("\n## ", maxsplit=1)[0]

    def test_prologues_name_sections_first_and_conditions_for_the_rest(self):
        problems = []
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            skill = path.parent.name
            if skill == "doctor":
                continue
            text = self.prologue(path)
            if "resolve.py\" section" not in text or "Сначала:" not in text:
                problems.append(f"{skill}: в прологе нет команды `resolve.py section` и «Сначала:»")
                continue
            for stem in self.ANY_MD_RE.findall(text):
                if stem not in self.PROTOCOL and stem not in self.KNOWN_MD and stem != "{файл}":
                    problems.append(f"{skill}: пролог называет неизвестный файл {stem}.md")
            first, _, rest = text.split("Сначала:", maxsplit=1)[1].partition("По условию:")
            for part_name, part, conditional in (("Сначала", first, False), ("По условию", rest, True)):
                tokens = [(m.start(), m.group(1)) for m in self.FILE_RE.finditer(part)]
                for i, (pos, name) in enumerate(tokens):
                    end = tokens[i + 1][0] if i + 1 < len(tokens) else len(part)
                    tail = part[pos:end]
                    whole_ok = (name in self.WHOLE_OK or name in self.WHOLE_OK_BY_SKILL.get(skill, set())
                                or (conditional and name in self.WHOLE_OK_CONDITIONAL))
                    if "целиком" in tail and not whole_ok:
                        problems.append(f"{skill}: «{part_name}» читает {name}.md целиком")
                    elif "целиком" not in tail and not self.QUOTE_RE.search(tail) and "из пролога" not in tail:
                        problems.append(f"{skill}: «{part_name}» называет {name}.md без секции")
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        prologue = lib.section_lines(runtime, "Пролог скила")
        self.assertIsNotNone(prologue)
        self.assertIn("После сжатия контекста", "\n".join(prologue[1]),
                      "«Пролог скила» должен велеть перечитать «Сначала» после сжатия контекста")
        self.assertEqual(problems, [], "пролог скила:\n" + "\n".join(problems))

    def test_section_references_resolve_to_headings(self):
        headings = self.all_headings()
        everywhere = set().union(*headings.values())
        problems = []
        for path in iter_files("skills", "protocol", "agents", "adapters"):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            tokens = [(m.end(), m.group(1)) for m in self.FILE_RE.finditer(text)]
            for i, (pos, name) in enumerate(tokens):
                # the quotes that belong to this file mention: up to the next mention, within
                # one clause («A», «B», «C» after `file.md`), not a quote of a later sentence
                end = min(tokens[i + 1][0] if i + 1 < len(tokens) else len(text), pos + 160)
                clause = re.split(r"[.;]\s|\n\n", text[pos:end], maxsplit=1)[0]
                # a clause that opens with a quote — after punctuation or a parenthesised word —
                # is a list of sections of this file: `file.md` «A», «B»; (`file.md`, раздел «A»);
                # elsewhere only a known heading counts as a reference
                reference_list = re.match(r"^[` ,:()—]*(?:\([^)]*\)\s*|раздел[ыа]?\s+|секци[яи]\s+)?«", clause) is not None
                for q in self.QUOTE_RE.findall(clause):
                    title = " ".join(q.split())
                    if title in headings[name]:
                        continue
                    # a quoted message («дождись гейтов и отчитайся») is lower-case and no file name;
                    # a section title is upper-case or a file name (artifacts.md «log.md»)
                    looks_like_title = title[:1].isupper() or re.fullmatch(r"[\w.-]+\.(md|yaml|json)", title)
                    if title in everywhere or (reference_list and looks_like_title):
                        owner = [n for n, hs in headings.items() if title in hs]
                        problems.append(f"{rel}: «{title}» после {name}.md — "
                                        + (f"секция файла {', '.join(owner)}" if owner else "такой секции нет"))
            # the quote-before-file form: «Коммит артефактов» (`artifacts.md`)
            for m in re.finditer(r"«([^»]+)»\s*\(\s*`?(?:protocol/)?(" + "|".join(self.PROTOCOL) + r")\.md`?", text):
                title, name = " ".join(m.group(1).split()), m.group(2)
                if title not in headings[name] and (title in everywhere or title[:1].isupper()):
                    problems.append(f"{rel}: «{title}» перед {name}.md — такой секции нет (склонение?)")
        self.assertEqual(problems, [], "ссылка на секцию протокола не резолвится:\n" + "\n".join(problems))


class RequestEconomyLint(unittest.TestCase):
    """Every tool call is a model request at the agent's full context (CHANGELOG 0.8.0): the
    rules that cut calls stay in the agents and the skills."""

    def body(self, agent: str) -> str:
        return " ".join(lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")[1].split())

    def skill(self, name: str) -> str:
        return " ".join((ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8").split())

    def test_architect_writes_each_artifact_once(self):
        architect = self.body("architect")
        self.assertIn("## How you write", architect)
        self.assertIn("single Write per file", architect)
        self.assertIn("Edit is for MODE: fix", architect)

    def test_mutation_probes_go_through_the_script(self):
        for agent in ("coder", "tester"):
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("probe.py", body)
                self.assertIn("batch", body)
        self.assertIn("One call per probe: `probe.py`", self.body("coder"))
        self.assertIn("restore from a copy, never from git", self.body("coder").lower())

    def test_long_gates_are_polled_once_with_a_long_timeout(self):
        for agent in ("coder", "tester", "reviewer"):
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("--timeout 540", body)
                self.assertIn("600000", body)
        self.assertIn("G-56", self.body("coder"))

    def test_agents_batch_independent_reads(self):
        for agent in ("coder", "tester", "reviewer", "researcher"):
            with self.subTest(agent=agent):
                body = self.body(agent)
                self.assertIn("together", body)
                self.assertIn("in one message", body)
                self.assertRegex(body, r"never `cat` a whole file|never `cat`\s+a whole file")

    def test_reports_are_checked_by_the_script(self):
        implement = self.skill("implement")
        self.assertIn("report.py check --role coder", implement)
        self.assertIn("--role tester", implement)
        self.assertIn("report.py check --role coder|tester", self.skill("review"))
        runtime = " ".join((ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8").split())
        self.assertIn("scripts/report.py check", runtime)
        self.assertIn("report.py baseline", implement)
        self.assertIn("report.py baseline", self.skill("review"))

    def test_report_sections_match_the_agents_output_formats(self):
        """The parser's section lists are the agents' Output format blocks: a renamed section
        in an agent would silently stop being checked."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import report as rp  # noqa: E402
        for agent in ("coder", "tester"):
            _, body = lib.parse_frontmatter(ROOT / "agents" / f"{agent}.md")
            block = body.split("Full report", 1)[1].split("```", 2)[1]
            headers = []
            for line in block.splitlines():
                m = re.match(r"^([A-Z][A-Z ]*[A-Z])(?: \(if any\))?:", line)
                if m:
                    name = "FILES" if m.group(1).startswith("FILES ") else m.group(1)
                    if name not in headers and name not in rp.OPTIONAL:
                        headers.append(name)
            with self.subTest(agent=agent):
                self.assertEqual(headers, rp.SECTIONS[agent])
                self.assertEqual(headers[-1], rp.LAST[agent])


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
                # `{label}-probes`: a long probe.py batch run through gate.py (coder, tester)
                self.assertEqual(sorted(set(calls) - {"{label}-probes"}), ["{label}-{gate}"])
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
        self.assertIn("ответ целиком, с первой строкой", flat_section)   # report.py check reads that line
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
                # isolation refusals of 0.3–0.7 are shell variables / `$(…)`, heredocs and `git -C`
                # elsewhere; the agent item is a pointer to the ISOLATION line and the refusal text,
                # and it must not send ordinary chains into separate calls (each one a request).
                self.assertIn("`ISOLATION` line", body)
                self.assertIn("This session is isolated in the worktree", body)
                for phrase in ("literal absolute paths", "heredoc", "`git -C` only on this worktree",
                               "script in SCRATCH_DIR run as the whole command", "do not split them"):
                    self.assertIn(phrase, body)
                self.assertNotIn("one plain command per call", body)

    def test_isolation_recipe_is_in_the_spawn_template_and_the_protocol(self):
        """T-1: the orchestrator wrote the isolation recipe into the spawn prompt by hand; MEW-15
        and T-11: heredocs and `commit -F -` refused, a commit message file left in TASK_DIR.
        The transcripts show chains and pipes without a variable or heredoc passing (`git add
        … && git commit …` 199/0), so the recipe must not split them."""
        runtime = (ROOT / "protocol" / "runtime.md").read_text(encoding="utf-8")
        template = runtime[runtime.index("Agent tool:"):runtime.index("{параметры режима агента")]
        self.assertIn("    ISOLATION: this session is isolated in its worktree", template)
        self.assertIn("other than `gate.py start`", template)
        self.assertNotIn("separately", template)
        section = lib.section_lines(runtime, "Формы команд в изоляции")
        self.assertIsNotNone(section)
        self.assertEqual(section[0]["level"], 2)                        # a heading: the whole text prints
        recipe = " ".join("\n".join(section[1]).split())                # what resolve.py section prints
        for phrase in ("без `$VAR`, `$(…)`", "без heredoc", "`git -C` — только свой worktree",
                       "commit -F", "не в `TASK_DIR`", "`zsh {путь}`", "кроме `gate.py start`",
                       "Обычные цепочки и конвейеры без этого проходят", "алиас `complete`",
                       "пути основного дерева (shared checkout)", "This session is isolated in the worktree"):
            self.assertIn(phrase, recipe)
        self.assertNotIn("отдельно", recipe)
        prologue = " ".join("\n".join(lib.section_lines(runtime, "Пролог скила")[1]).split())
        self.assertIn("«Формы команд в изоляции» (`runtime.md`)", prologue)   # read on the worktree condition
        self.assertNotIn("Формы команд в изоляции.**", prologue)              # not inside the prologue itself
        for path in ("protocol/worktree.md", "skills/start/SKILL.md"):
            text = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn('[ "$(git rev-parse', text)      # the in-worktree check itself was refusable
                self.assertIn("git rev-parse --path-format=absolute --git-dir --git-common-dir", text)
        implement = (ROOT / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("commit-msg-step{N}.txt", implement)
        commit_call = "`git -C {дерево} add {файлы} && git -C {дерево} commit -F {файл}`"
        self.assertIn(commit_call, implement)                           # one call, both halves on the tree
        self.assertIn(commit_call, recipe)
        self.assertIn("журнал лида пишет только скрипт `lead.py`", recipe.lower())   # never a file tool
        worktree_md = (ROOT / "protocol" / "worktree.md").read_text(encoding="utf-8")
        traps = " ".join("\n".join(lib.section_lines(worktree_md, "Изолированная сессия")[1]).split())
        self.assertIn("журнал лида — только скриптом `lead.py`", traps)
        lead_md = (ROOT / "protocol" / "lead.md").read_text(encoding="utf-8")
        journal = " ".join("\n".join(lib.section_lines(lead_md, "Журнал")[1]).split())
        self.assertIn("только скриптом `lead.py`, никогда файловыми инструментами", journal)
        self.assertIn("под блокировкой файла", journal)
        self.assertNotIn("отклоняет их для путей вне её дерева", journal)   # the old, wrong reason
        artifacts = (ROOT / "protocol" / "artifacts.md").read_text(encoding="utf-8")
        self.assertIn("`commit -F`, не heredoc", artifacts)
        pr_review = (ROOT / "skills" / "pr-review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("строку `ISOLATION`", pr_review)                   # its Explore agents are spawned by hand
        self.assertEqual(re.findall(r"\$PR\b(?! `)", pr_review.replace("отклоняет `$PR`", "")), [])   # prose too
        kanban = (ROOT / "adapters" / "tracker" / "kanban.md").read_text(encoding="utf-8")
        self.assertNotIn("BOARD=$(", kanban)

    def test_no_label_section_ends_with_a_colon(self):
        """A bold-label section ends at the first blank line: a label whose text ends with `:`
        prints as a list header without its list (step 7, finding 1)."""
        bad = []
        for path in iter_files("protocol"):
            text = path.read_text(encoding="utf-8")
            for sec, lines in ((s, text.splitlines()[s["start"] - 1:s["end"] - 1]) for s in lib.sections_of(text)):
                body = [l for l in lines if l.strip()]
                if sec["level"] >= 4 and body and body[-1].rstrip().endswith(":"):
                    bad.append(f"{path.relative_to(ROOT)}:{sec['start']} «{sec['title']}»")
        self.assertEqual(bad, [])

    def test_shell_recipes_run_inside_a_worktree_use_no_variables_or_heredocs(self):
        """kanban.md's `BOARD=$(…)`, pr-review's `PR=$(…)` and refine's `repos=$(…)` showed the
        form the recipe forbids (step 7, finding 3). Blocks that run only in the main tree —
        git.md's research-worktree and submodule teardown (`$wt`) — are allowed."""
        fence = re.compile(r"```(?:bash|sh|zsh)\n(.*?)```", re.S)
        refusable = re.compile(r"\$\(|<<|\$(?!\{CLAUDE_PLUGIN_ROOT\})[A-Za-z_{]")
        bad = []
        for path in iter_files("skills", "protocol", "adapters"):
            text = path.read_text(encoding="utf-8")
            for m in fence.finditer(text):
                block = m.group(1)
                if path.name == "git.md" and "$wt" in block:
                    continue
                for l in block.splitlines():
                    code = l.split("#", 1)[0]          # a trailing comment may name the refused form
                    if refusable.search(code):
                        bad.append(f"{path.relative_to(ROOT)}: {l.strip()[:80]}")
        self.assertEqual(bad, [], "переменные shell, `$(…)` или heredoc в рецепте:\n" + "\n".join(bad))

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
        self.assertIn("`CHECKPOINT GATES`, `SCRATCH`; код 1", self.flat("skills/implement/SKILL.md"))
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
        self.assertIn("по `id` из `python3 {корень плагина}/scripts/agent_ctx.py {адрес}`", runtime)
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

    def test_an_agent_is_addressed_by_its_name_or_its_spawn_id(self):
        """T-10: since Claude Code 2.1.300 the Agent tool takes no `name`; the session kept the
        agentIds in state.yaml, agent_ctx.py found none of them by name."""
        runtime = self.flat("protocol/runtime.md")
        self.assertIn("**Адрес агента.**", runtime)
        self.assertIn("иначе `agentId` из результата спавна", runtime)
        self.assertIn("`state.py set TASK_DIR agents.{ключ}={адрес}`", runtime)
        self.assertIn("`agent_ctx.py --list`", runtime)
        self.assertNotIn("обязан иметь `name`", runtime)
        self.assertIn('description: "{role}-{id}: {задание}"', runtime)
        tiers = self.flat("protocol/tiers.md")
        self.assertIn("agent_ctx.py {адрес агента}", tiers)
        self.assertIn("<usage><subagent_tokens>N</subagent_tokens>", tiers)
        stale = ("обязан иметь `name`", "FIX-цикл идёт по имени", "SendMessage to `", "спавн агента с именем",
                 "имя может быть с суффиксом", "Имя — в `agents.", "с параметром `name`", "один спавн с `name`")
        for path in [*iter_files("skills"), *iter_files("protocol"), *iter_files("agents")]:  # review F4, F10
            with self.subTest(path=f"{path.parent.name}/{path.name}"):
                text = " ".join(path.read_text(encoding="utf-8").split())
                self.assertNotRegex(text, r"agents\.[a-z_{}]+=\{имя\}")      # state keeps the address, not a name
                self.assertNotRegex(text, r"SendMessage `[a-z]+-\{id\}")
                for phrase in stale:
                    self.assertNotIn(phrase, text)
        research = self.flat("skills/research/SKILL.md")
        self.assertIn("agents.researcher={адрес}", research)
        self.assertIn("по адресу из `agents.researcher`", research)
        self.assertIn("agentId — служебный", runtime)      # review F8: not in log.md or the tracker
        self.assertIn("оркестратор записывает сразу после его спавна", self.flat("skills/spec/SKILL.md"))   # N3
        self.assertNotIn("Спавн без имени там, где агента продолжают", self.flat("protocol/review-cycle.md"))   # N4
        self.assertNotIn("{новый адрес}", tiers)

    def test_lead_retires_a_rule_and_briefs_carry_open_rules_only(self):
        """G-61, SwAIS R-1: `replace` refused the rule, `list --type rule` kept handing it on."""
        lead_md = self.flat("protocol/lead.md")
        self.assertIn("lead.py rule-retire R-{n} --decision D-{m}", lead_md)
        skill = self.flat("skills/lead/SKILL.md")
        self.assertIn("действующие правила (`lead.py list --type rule --open`: снятые `rule-retire` не идут", skill)
        self.assertIn("действующие правила (`lead.py list --type rule --open`) и решения", skill)
        self.assertNotRegex(skill, r"lead\.py list --type rule`")     # every rule listing for a brief or a decision is --open

    def test_bytes_check_has_a_per_file_form_and_n_a_means_an_ascii_diff(self):
        """G-71, SwAIS T-12: `n/a` written for «checked, nothing invisible» over Cyrillic lines."""
        for rel in ("agents/coder.md", "agents/tester.md"):
            with self.subTest(rel=rel):
                text = self.flat(rel)
                self.assertIn("invisible and escapes: none — verified by bytes", text)
        self.assertIn("never for «checked, nothing invisible»", self.flat("agents/coder.md"))

    def test_a_probe_copy_never_goes_next_to_the_file(self):
        """G-69, SwAIS T-12: node-pg-migrate loaded the `.orig` copy as a second migration."""
        for rel in ("agents/coder.md", "agents/tester.md"):
            with self.subTest(rel=rel):
                text = self.flat(rel)
                self.assertNotIn("{file}.orig", text)
                self.assertNotIn("`.orig` copy next to the file is the exception", text)
        self.assertIn("{SCRATCH_DIR}/{label}/{name}.orig", self.flat("agents/coder.md"))

    def test_release_0_9_4_rules_are_written_where_the_agents_and_skills_read_them(self):
        """0.9.4, SwAIS T-13…T-16: the account limit, the worktree hook, the sync report, the
        lead's file map, `it.each`, `git -C` in kanban, a probe with no test run."""
        lead_md, lead_skill = self.flat("protocol/lead.md"), self.flat("skills/lead/SKILL.md")
        self.assertIn("**Лимит аккаунта.**", lead_md)
        self.assertIn("`limited` (лимит аккаунта сброшен, `resets_at`)", lead_skill)
        self.assertIn("Обрыв лимитом аккаунта", self.flat("protocol/runtime.md"))
        self.assertIn("omixflow-wt-setup.status", self.flat("skills/start/SKILL.md"))
        self.assertIn("omixflow-wt-setup.status", self.flat("protocol/worktree.md"))
        self.assertIn("--conflicts {CONFLICTS}", self.flat("skills/implement/SKILL.md"))
        self.assertIn("`RESOLUTIONS:` section", self.flat("agents/coder.md"))
        self.assertIn("`--add-file …` (дополняет", lead_skill)
        self.assertNotIn("или `git -C .tasks/board` только для чтения", self.flat("adapters/tracker/kanban.md"))
        meta, _ = lib.parse_frontmatter(ROOT / "adapters" / "lang" / "ts.md")
        rx = re.compile(meta["tests"]["declaration"])
        for line in ("it.each([1])('n', () => {})", "test.each`a`('t', () => {})", "it.only('o')", "test.concurrent('c')"):
            self.assertTrue(rx.match(line), line)
        for line in ("test.describe('d', () => {})", "test.beforeEach(() => {})", "test.step('s')", "test.use({})"):
            self.assertFalse(rx.match(line), line)                 # review F13: Playwright's hooks are not tests
        self.assertTrue(meta["tests"]["ran"])
        for path in sorted((ROOT / "adapters" / "tracker").glob("*.md")):   # G-80: no `git -C` advice for a worktree session
            for line in path.read_text(encoding="utf-8").splitlines():
                if "git -C" in line:
                    with self.subTest(file=path.name, line=line):
                        self.assertIn("основного дерева", line)
        self.assertIn("ran: regex", self.flat("adapters/lang/PORT.md"))

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

    def test_the_orchestrators_model_is_the_projects_and_always_passed(self):
        """0.9.2: SwAIS T-10, T-12…T-14 ran on Fable under `"model": "opus"` — launch passed no model."""
        flat = lambda rel: " ".join((ROOT / rel).read_text(encoding="utf-8").split())
        tiers = flat("protocol/tiers.md")
        self.assertIn("**Модель оркестратора.**", tiers)
        self.assertIn("`models.orchestrator`, без значения — `models.strong`", tiers)
        self.assertIn("**Модель.** `sessions.py launch` всегда передаёт `--model`", flat("protocol/lead.md"))
        lead_skill = flat("skills/lead/SKILL.md")
        self.assertIn("[--model {модель}]", lead_skill)
        self.assertIn("--worktree --model={model}`", lead_skill)          # the session learns its launch model
        self.assertIn("--worktree --model={model}`", flat("protocol/lead.md"))
        develop = flat("skills/develop/SKILL.md")
        self.assertIn("`--model=M`", develop)
        self.assertIn("`state.py set TASK_DIR model_requested=M`", develop)        # a relaunch by the lead
        self.assertIn("`model_requested` — как в резюме задачи", develop)          # a part's relaunch
        self.assertIn("`state.py set TASK_DIR model_requested=null`", develop)      # review N4: a developer's session
        self.assertEqual(develop.count("[--model=M]"), 4)      # task start, multitask M1 and MS, part M3
        self.assertIn("--part {part} --lead=… --model={model}`", lead_skill)          # review N1: parts too
        self.assertIn("с `--model={model}`", lead_skill)                              # the research multitask
        start = flat("skills/start/SKILL.md")
        self.assertIn("`--model-requested M`", start)
        self.assertEqual(start.count("[--model-requested {M}]"), 3)    # task, multitask, part init
        self.assertIn("model_requested:", flat("protocol/artifacts.md"))
        self.assertNotIn("(в конфиге", tiers)
        self.assertIn("модель оркестратора по транскрипту (`model`)", flat("skills/start/SKILL.md"))
        self.assertIn("Строка называет модель и effort оркестратора", flat("protocol/runtime.md"))
        schema = json.loads((ROOT / "schema" / "flow.schema.json").read_text(encoding="utf-8"))
        self.assertIn("orchestrator", schema["properties"]["models"]["properties"])
        self.assertIn("# orchestrator:", (ROOT / "templates" / "flow.yaml").read_text(encoding="utf-8"))

    def test_effort_is_the_plugins_and_the_orchestrators_is_always_passed(self):
        """0.9.3: a subagent took the level the developer's settings keep for its model (Opus 5.5:
        medium by default) — the plugin set none; launch passed no effort either."""
        flat = lambda rel: " ".join((ROOT / rel).read_text(encoding="utf-8").split())
        tiers = flat("protocol/tiers.md")
        section = self.section((ROOT / "protocol" / "tiers.md").read_text(encoding="utf-8"), "## Effort агентов")
        for path in sorted((ROOT / "agents").glob("*.md")):
            meta, _ = lib.parse_frontmatter(path)
            with self.subTest(agent=path.stem):
                self.assertIn(f"| {path.stem} | {meta['effort']} |", section)   # the table names the frontmatter's level
        self.assertIn("**Effort оркестратора.**", tiers)
        self.assertIn("`effort.orchestrator` проекта, без значения — xhigh", tiers)
        self.assertIn("Оркестратор не передаёт `effort` при спавне", tiers)
        self.assertIn("`CLAUDE_CODE_EFFORT_LEVEL`", section)
        self.assertIn("**Effort.** `sessions.py launch` всегда передаёт и `--effort`", flat("protocol/lead.md"))
        self.assertIn("[--effort {уровень}]", flat("skills/lead/SKILL.md"))
        self.assertIn("параметр `effort` при спавне оркестратор не передаёт", flat("protocol/runtime.md"))
        self.assertIn("effort: {orchestrator: xhigh", flat("protocol/artifacts.md"))
        schema = json.loads((ROOT / "schema" / "flow.schema.json").read_text(encoding="utf-8"))
        orchestrator = schema["properties"]["effort"]["properties"]["orchestrator"]
        self.assertEqual((orchestrator["default"], tuple(orchestrator["enum"])), ("xhigh", lib.EFFORT_LEVELS))
        self.assertIn("effort:\n  orchestrator: xhigh", (ROOT / "templates" / "flow.yaml").read_text(encoding="utf-8"))

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
