"""Tests for cost.py: the cost of a session's requests from the harness transcripts.

Fixtures follow the record shapes of real transcripts (Claude Code 2.1.296): a request split
over several assistant records with partial output counts, the last one final; a teammate
meta with the role in `spawnedAgentType`; an isMeta system reminder before the first
request; a `gate.py poll` result with the "Exit code 3" line; the session's `cost-state`."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cost  # noqa: E402

SESSION = "0f1003da-f117-4bd9-a849-1b15cf7e3558"
ISOLATION = cost.ISOLATION
REMINDER = "<system-reminder>\nOther agents active in this session, addressable via SendMessage\n</system-reminder>"


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CONFIG_DIR")}
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
        code = cost.main(list(args))
    return code, out.getvalue()


def reply(ts: str, read: int, create: int, out: int = 100, model: str = "claude-opus-5-5",
          rid: str | None = None, tools: list | None = None, inp: int = 1, create_1h: int = 0) -> dict:
    content = [{"type": "text", "text": "ok"}]
    for i, (name, arg) in enumerate(tools or []):
        content.append({"type": "tool_use", "id": f"{rid}-t{i}", "name": name, "input": arg})
    return {"type": "assistant", "timestamp": ts, "requestId": rid or f"req-{ts}",
            "message": {"model": model, "content": content,
                        "usage": {"input_tokens": inp, "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": create, "output_tokens": out,
                                  "cache_creation": {"ephemeral_5m_input_tokens": create - create_1h,
                                                     "ephemeral_1h_input_tokens": create_1h}}}}


def split(ts: str, read: int, create: int, outs: list[int], rid: str) -> list[dict]:
    """One request as the harness writes it: a record per content block, output partial until the last."""
    return [reply(ts, read, create, out=o, rid=rid) for o in outs]


def prompt(ts: str, text: str, meta: bool = False) -> dict:
    rec = {"type": "user", "timestamp": ts, "message": {"content": text}}
    if meta:
        rec["isMeta"] = True
    return rec


def result(ts: str, tool_use_id: str, text: str) -> dict:
    return {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": text}]}}


def cost_state(models: dict) -> dict:
    return {"type": "cost-state", "sessionId": SESSION, "totalCostUSD": sum(u["costUSD"] for u in models.values()),
            "modelUsage": models}


class CostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = Path(self.tmp.name) / "projects"
        self.project = self.projects / "-proj"
        (self.project / SESSION / "subagents").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path: Path, records: list, raw_tail: str = "") -> None:
        path.write_text("".join(json.dumps(r) + "\n" for r in records) + raw_tail)

    def main_log(self, records: list, raw_tail: str = "") -> None:
        self.write(self.project / f"{SESSION}.jsonl", records, raw_tail)

    def agent(self, name: str, records: list, meta: dict | None = None) -> None:
        d = self.project / SESSION / "subagents"
        (d / f"agent-{name}.meta.json").write_text(json.dumps({"name": name, **(meta or {"agentType": f"omixflow:{name.split('-')[0]}"})}))
        self.write(d / f"agent-{name}.jsonl", records)

    def session(self, *extra: str) -> dict:
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--json", *extra)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    # ----------------------------------------------------------------- usage

    def test_a_split_request_counts_once_with_the_last_records_usage(self):
        self.main_log([
            prompt("2026-10-10T20:00:00Z", "/omixflow:develop T-1"),
            *split("2026-10-10T20:00:01Z", read=10_000, create=40_000, outs=[8, 8, 448], rid="r1"),
            reply("2026-10-10T20:00:02Z", read=50_000, create=2_000, out=100, rid="r2"),
            {"type": "assistant", "timestamp": "2026-10-10T20:00:03Z", "requestId": "r3", "isApiErrorMessage": True,
             "message": {"model": "<synthetic>", "usage": {"input_tokens": 0}}},
        ])
        out = self.session()
        self.assertEqual(out["requests"], 2)
        self.assertEqual(out["output"], 548)
        expected = (1 + 40_000 * 1.25 + 10_000 * 0.1 + 448 * 5) + (1 + 2_000 * 1.25 + 50_000 * 0.1 + 100 * 5)
        self.assertEqual(out["cost_eq"], int(expected))
        self.assertEqual(out["avg_context"], (50_001 + 52_001) // 2)

    def test_one_hour_cache_writes_weigh_two(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1", create_1h=100_000),
                       reply("2026-10-10T20:00:02Z", read=0, create=100_000, out=0, inp=0, rid="o2")])
        out = self.session()
        self.assertEqual([a["cost_eq"] for a in out["agents"]], [int(100_000 * 2.0 + 100_000 * 1.25)])

    def test_malformed_lines_and_a_session_without_subagents_are_tolerated(self):
        (self.project / SESSION / "subagents").rmdir()
        (self.project / SESSION).rmdir()
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1")], raw_tail='{"type": "assistant", "mess\n[]\n')
        out = self.session()
        self.assertEqual(out["requests"], 1)
        self.assertEqual([a["agent"] for a in out["agents"]], ["orchestrator"])

    # ----------------------------------------------------------------- roles and models

    def test_roles_come_from_the_spawned_type_of_teammates_and_the_agent_type_of_subagents(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, out=0, rid="o1")])
        self.agent("coder-T-1-2", [prompt("2026-10-10T20:01:00Z", "STEP: 1"),
                                   reply("2026-10-10T20:01:01Z", read=0, create=100_000, out=0, rid="c1")],
                   meta={"agentType": "coder-T-1-2", "taskKind": "in_process_teammate",
                         "customAgentType": "omixflow:coder", "spawnedAgentType": "omixflow:coder"})
        self.agent("coder-T-1", [prompt("2026-10-10T20:02:00Z", "STEP: 2"),
                                 reply("2026-10-10T20:02:01Z", read=0, create=100_000, out=0, rid="c2")])
        self.agent("tester-T-1", [prompt("2026-10-10T20:03:00Z", "SPEC_PATH: x"),
                                  reply("2026-10-10T20:03:01Z", read=0, create=100_000, out=0, rid="t1",
                                        model="claude-sonnet-5-5")])
        self.agent("helper-x", [reply("2026-10-10T20:04:01Z", read=0, create=10, out=0, rid="h1")], meta={})
        out = self.session()
        self.assertEqual(set(out["by_role"]), {"orchestrator", "coder", "tester", "helper"})
        self.assertEqual(out["by_role"]["coder"]["agents"], 2)
        self.assertEqual(out["by_role"]["coder"]["cost_eq"], 2 * int(1 + 100_000 * 1.25))
        self.assertEqual(out["by_role"]["tester"]["cost_eq"], int((1 + 100_000 * 1.25) * 0.6))  # default sonnet factor

    def test_model_factors_come_from_the_cost_state_unless_given(self):
        opus = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 1_000_000, "cacheCreationInputTokens": 0,
                "costUSD": 0.3}       # $3 per weighted MTok
        sonnet = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 1_000_000, "cacheCreationInputTokens": 0,
                  "costUSD": 0.15}    # $1.5 per weighted MTok → 0.5 of opus
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, out=0, rid="o1"),
                       cost_state({"claude-opus-5-5": opus, "claude-sonnet-5-5": sonnet})])
        self.agent("tester-T-1", [reply("2026-10-10T20:03:01Z", read=0, create=100_000, out=0, inp=0, rid="t1",
                                        model="claude-sonnet-5-5")])
        out = self.session()
        self.assertEqual(out["model_factors"]["claude-sonnet-5-5"], 0.5)
        self.assertEqual(out["usd"], {"total": 0.45, "by_model": {"claude-opus-5-5": 0.3, "claude-sonnet-5-5": 0.15}})
        self.assertEqual(out["by_role"]["tester"]["cost_eq"], int(100_000 * 1.25 * 0.5))
        out = self.session("--model-factor", "sonnet=0.1")
        self.assertEqual(out["by_role"]["tester"]["cost_eq"], int(100_000 * 1.25 * 0.1))

    def test_derived_factors_are_per_model_name_and_need_one_opus_model_without_web_search(self):
        usage = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 1_000_000, "cacheCreationInputTokens": 0}
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, out=0, rid="o1"),
                       cost_state({"claude-opus-5-5": {**usage, "costUSD": 0.3},
                                   "claude-opus-4-1": {**usage, "costUSD": 0.5},           # a second opus: no derivation
                                   "claude-haiku-5-5": {**usage, "costUSD": 0.06, "webSearchRequests": 2}})])
        factors = self.session()["model_factors"]
        self.assertEqual((factors["sonnet"], factors["haiku"]), (0.6, 0.04))
        self.assertNotIn("claude-opus-4-1", factors)
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, out=0, rid="o1"),
                       cost_state({"claude-opus-5-5": {**usage, "costUSD": 0.3},
                                   "claude-sonnet-5-5": {**usage, "costUSD": 0.15},
                                   "claude-sonnet-4-5": {**usage, "costUSD": 0.3},
                                   "claude-haiku-5-5": {**usage, "costUSD": 0.06, "webSearchRequests": 2}})])
        factors = self.session()["model_factors"]
        self.assertEqual((factors["claude-sonnet-5-5"], factors["claude-sonnet-4-5"]), (0.5, 1.0))
        self.assertEqual(factors["haiku"], 0.04)          # web search: left out
        self.assertEqual(cost.model_factor("claude-sonnet-4-5", factors), 1.0)  # the full name wins over the family
        self.assertEqual(cost.model_factor("claude-sonnet-5-5-x", factors), 0.6)

    # ----------------------------------------------------------------- intro, rebuilds, empty requests

    def test_intro_is_the_context_at_the_end_of_the_first_assignment_and_reminders_are_not_assignments(self):
        self.main_log([prompt("2026-10-10T19:59:00Z", "/omixflow:develop T-1"),
                       reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1"),
                       prompt("2026-10-10T20:00:02Z", "<task-notification>agent done</task-notification>"),
                       reply("2026-10-10T20:00:03Z", read=1000, create=10, rid="o2")])
        self.agent("coder-T-1", [
            prompt("2026-10-10T20:01:00Z", "STEP: 1"),
            reply("2026-10-10T20:01:01Z", read=0, create=50_000, rid="c1"),
            prompt("2026-10-10T20:01:01Z", REMINDER, meta=True),                      # between requests: not an assignment
            prompt("2026-10-10T20:01:01Z", "[Request interrupted by user]"),
            prompt("2026-10-10T20:01:01Z", "Your response above was stopped by a safety classifier"),
            reply("2026-10-10T20:01:02Z", read=50_000, create=150_000, rid="c2"),
            prompt("2026-10-10T20:10:00Z", "The coordinator sent a message while you were working:\nSTEP: 2"),
            reply("2026-10-10T20:10:01Z", read=200_000, create=5_000, rid="c3"),
        ])
        out = self.session()
        orchestrator, coder = out["agents"]
        self.assertIsNone(orchestrator["intro"])            # its prompts are notices, not assignments
        self.assertEqual(coder["assignments"], 2)
        self.assertEqual(coder["intro"], 200_001)           # 50_001 if the reminder or the interruption counted
        self.assertEqual(coder["max_context"], 205_001)

    def test_a_rebuild_is_a_cache_write_over_half_the_context_after_the_first_request(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1")])
        self.agent("architect-T-1", [
            prompt("2026-10-10T20:01:00Z", "MODE: spec"),
            reply("2026-10-10T20:01:01Z", read=0, create=200_000, rid="a1"),            # first request: never a rebuild
            reply("2026-10-10T20:01:02Z", read=200_000, create=3_000, rid="a2"),
            reply("2026-10-10T20:40:00Z", read=102_000, create=98_000, inp=0, rid="a3"),  # 0.49 of the context: no
            reply("2026-10-10T21:30:01Z", read=98_000, create=102_000, inp=0, rid="a4"),  # 0.51: a rebuild
        ])
        out = self.session()
        self.assertEqual((out["agents"][1]["rebuilds"], out["agents"][1]["rebuild_tokens"]), (1, 102_000))
        self.assertEqual(out["rebuild_tokens"], 102_000)

    def test_refusals_by_shape_retries_and_polls_behind_an_exit_code_line(self):
        self.main_log([
            prompt("2026-10-10T20:00:00Z", "/omixflow:develop T-1"),
            reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1",
                  tools=[("Bash", {"command": "R=/x/log.md; sed -n 1p $R"})]),
            result("2026-10-10T20:00:02Z", "o1-t0", f"{ISOLATION}: too complex to verify"),
            reply("2026-10-10T20:00:03Z", read=1000, create=10, rid="o2",
                  tools=[("Bash", {"command": "sed -n 1p /x/log.md"})]),
            result("2026-10-10T20:00:04Z", "o2-t0", "line"),
            reply("2026-10-10T20:00:05Z", read=1100, create=10, rid="o3",
                  tools=[("Bash", {"command": "cat >> /x/log.md <<'EOF'\nx\nEOF"})]),
            result("2026-10-10T20:00:06Z", "o3-t0", f"{ISOLATION}: computed at runtime"),
            reply("2026-10-10T20:00:07Z", read=1200, create=10, rid="o4",
                  tools=[("Bash", {"command": "python3 gate.py poll build --root /x"})]),
            result("2026-10-10T20:00:08Z", "o4-t0", "Exit code 3\nRUNNING 100s, вывод 12 байт: /x/.git/omixflow-gates/build.log"),
        ])
        orch = self.session()["agents"][0]
        self.assertEqual((orch["refusals"], orch["refusal_shapes"]), (2, {"variable": 1, "heredoc": 1}))
        self.assertEqual((orch["retries"], orch["polls"]), (2, 1))

    # ----------------------------------------------------------------- window

    def test_the_window_filters_requests_refusals_and_polls_and_keeps_a_rebuild_on_its_first_request(self):
        self.main_log([
            prompt("2026-10-10T20:00:00Z", "/omixflow:develop T-1"),
            reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1", tools=[("Bash", {"command": "echo $X"})]),
            result("2026-10-10T20:00:02Z", "o1-t0", f"{ISOLATION}: too complex"),
            reply("2026-10-10T20:00:03Z", read=1000, create=10, rid="o2"),
            reply("2026-10-10T22:00:01Z", read=0, create=200_000, rid="o3", tools=[("Bash", {"command": "gate.py poll x"})]),
            result("2026-10-10T22:00:02Z", "o3-t0", "Exit code 3\nRUNNING 10s"),
            reply("2026-10-10T23:00:01Z", read=200_000, create=4000, rid="o4"),
        ])
        whole = self.session()
        self.assertEqual((whole["requests"], whole["refusals"], whole["polls"], whole["rebuilds"]), (4, 1, 1, 1))
        window = self.session("--since", "2026-10-10T21:30:00", "--until", "2026-10-10T22:30:00Z")  # naive = UTC
        self.assertEqual((window["requests"], window["refusals"], window["polls"], window["rebuilds"]), (1, 0, 1, 1))
        self.assertEqual(window["cache_write"], 200_000)

    def test_a_bad_window_is_a_usage_error(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1")])
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--since", "yesterday")
        self.assertEqual(code, 2)
        self.assertIn("ISO", json.loads(out)["error"])

    # ----------------------------------------------------------------- output forms and errors

    def test_line_names_cost_requests_context_and_role_shares(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1")])
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--line")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("- Стоимость: 0.1M cost_eq, запросов 1, средний контекст 100k; orchestrator 100 %"), out)

    def test_fable_costs_about_1_8_opus_by_default(self):
        """SwAIS T-10: `phase` without derived factors counted Fable as Opus (33.3M)."""
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1",
                             model="claude-fable-5-1")])
        whole = self.session("--model-factor", "fable=1")     # a given factor overrides the default
        self.assertEqual(whole["cost_eq"], 125_000)
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--json")
        self.assertEqual(json.loads(out)["model_factors"]["fable"], 1.8)
        self.assertEqual(json.loads(out)["cost_eq"], 225_000)
        self.assertEqual(json.loads(out)["unpriced"], [])

    def test_a_derived_factor_splits_the_one_hour_cache_writes(self):
        """Review F2: cost-state does not split 5-minute from 1-hour writes; Fable writes 1-hour,
        and weighing them at 1.25 put the 1-hour premium into its factor a second time."""
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1"),
                       reply("2026-10-10T20:00:02Z", read=0, create=100_000, out=0, inp=0, rid="f1",
                             model="claude-fable-5-1", create_1h=100_000),
                       {"type": "cost-state", "totalCostUSD": 3.0, "modelUsage": {
                           "claude-opus-5-5": {"inputTokens": 0, "cacheCreationInputTokens": 100_000,
                                               "cacheReadInputTokens": 0, "outputTokens": 0, "costUSD": 1.0},
                           "claude-fable-5-1": {"inputTokens": 0, "cacheCreationInputTokens": 100_000,
                                                "cacheReadInputTokens": 0, "outputTokens": 0, "costUSD": 2.0}}}])
        factors = self.session()["model_factors"]
        self.assertEqual(factors["claude-fable-5-1"], round(2.0 / (100_000 * 2.0) / (1.0 / (100_000 * 1.25)), 3))   # 1.25

    def test_a_model_without_a_factor_is_named(self):
        """Review F7: an unknown family is counted as Opus — the way Fable was before 0.9.2."""
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1", model="claude-mythos-5-1")])
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--line")
        self.assertIn("без коэффициента (как Opus): claude-mythos-5-1", out)

    def test_the_line_names_the_orchestrators_model_and_a_switch_in_time_order(self):
        """T-13, T-14: started on Fable, the developer switched them to Opus with /model; by
        count the later model may lead (T-13: 37 Fable, 50 Opus) — the line keeps time order."""
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1", model="claude-fable-5-1"),
                       reply("2026-10-10T20:00:02Z", read=1000, create=10, rid="o2", model="claude-opus-5-5"),
                       reply("2026-10-10T20:00:03Z", read=1000, create=10, rid="o3", model="claude-opus-5-5")])
        code, out = run("session", "--session", SESSION, "--projects", str(self.projects), "--line")
        self.assertTrue(out.rstrip().endswith("; оркестратор claude-fable-5-1 1 → claude-opus-5-5 2"), out)

    def test_unknown_session_is_json_with_exit_3(self):
        code, out = run("session", "--session", "nope", "--projects", str(self.projects))
        self.assertEqual(code, 3)
        self.assertIn("error", json.loads(out))
        code, out = run("session", "--projects", str(self.projects))
        self.assertEqual(code, 3)

    # ----------------------------------------------------------------- phase

    def test_phase_records_the_model_the_session_runs_on_and_flags_another_than_launched(self):
        """0.9.2: the model in state.yaml is the transcript's, not the launch flag's; a session that
        runs on another model than it was launched on (`model_requested`) is flagged in the line."""
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=1000, rid="o1", model="claude-fable-5-1")])
        task = Path(self.tmp.name) / ".tasks" / "T-1"
        task.mkdir(parents=True)
        base = f"schema: 1\nid: T-1\nkind: task\nsession: {SESSION}\n"
        (task / "state.yaml").write_text(base + "model_requested: opus\n")
        code, out = run("phase", str(task), "start", "--projects", str(self.projects))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.rstrip().endswith("; оркестратор claude-fable-5-1 (запущена на opus)"), out)
        state = yaml.safe_load((task / "state.yaml").read_text())
        self.assertEqual((state["model"], state["cost"]["phases"][0]["model"]), ("claude-fable-5-1", "claude-fable-5-1"))
        for requested in ("fable", "claude-fable-5-1", "fable[1m]", "default", None):   # same model, or none asked
            with self.subTest(requested=requested):
                (task / "state.yaml").write_text(base + (f"model_requested: '{requested}'\n" if requested else ""))
                code, out = run("phase", str(task), "spec", "--projects", str(self.projects))
                self.assertEqual(code, 0, out)
                self.assertTrue(out.rstrip().endswith("; оркестратор claude-fable-5-1"), out)

    def test_phase_sums_since_the_cursor_moves_it_and_accumulates_the_total(self):
        self.main_log([
            reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, rid="o1"),
            reply("2026-10-10T20:30:01Z", read=100_000, create=10_000, out=0, rid="o2"),
        ])
        task = Path(self.tmp.name) / ".tasks" / "T-1"
        task.mkdir(parents=True)
        # the cursor as YAML loads an unquoted timestamp: a datetime, not a string
        (task / "state.yaml").write_text("schema: 1\nid: T-1\nkind: task\nsession: " + SESSION
                                         + "\ncost:\n  last: 2026-10-10T20:15:00Z\n  phases: []\n")
        code, out = run("phase", str(task), "research", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        entry = json.loads(out)
        self.assertEqual((entry["phase"], entry["requests"], entry["since"]), ("research", 1, "2026-10-10T20:15:00Z"))
        first = int(1 + 10_000 * 1.25 + 100_000 * 0.1)
        self.assertEqual(entry["cost_eq"], first)
        state = yaml.safe_load((task / "state.yaml").read_text())
        self.assertEqual(state["cost"]["total_eq"], first)
        self.assertNotEqual(str(state["cost"]["last"]), "2026-10-10T20:15:00Z")
        # the next phase starts at the moved cursor (nothing new): zero, total unchanged; session id from state.yaml
        code, out = run("phase", str(task), "spec", "--projects", str(self.projects))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("- Стоимость: 0.0M cost_eq, запросов 0"), out)
        state = yaml.safe_load((task / "state.yaml").read_text())
        self.assertEqual([(p["phase"], p["cost_eq"]) for p in state["cost"]["phases"]], [("research", first), ("spec", 0)])
        self.assertEqual(state["cost"]["total_eq"], first)

    def test_phase_keeps_one_unit_across_the_task(self):
        """cost-state appears only when the session ends: `phase` never derives factors from it."""
        opus = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 1_000_000, "cacheCreationInputTokens": 0,
                "costUSD": 0.3}
        sonnet = {**opus, "costUSD": 0.15}
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1",
                             model="claude-sonnet-5-5"),
                       cost_state({"claude-opus-5-5": opus, "claude-sonnet-5-5": sonnet})])
        task = Path(self.tmp.name) / ".tasks" / "T-1"
        task.mkdir(parents=True)
        (task / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "T-1", "kind": "task", "session": SESSION}))
        code, out = run("phase", str(task), "start", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["cost_eq"], int(100_000 * 1.25 * 0.6))   # the default, not 0.5

    def test_a_sequential_part_starts_its_window_at_the_latest_cursor_of_the_multitask_and_its_siblings(self):
        self.main_log([
            reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o1"),   # multitask start
            reply("2026-10-10T21:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o2"),   # part one
            reply("2026-10-10T22:00:01Z", read=0, create=100_000, out=0, inp=0, rid="o3"),   # part two
        ])
        root = Path(self.tmp.name) / ".tasks" / "M-1"
        (root / "one").mkdir(parents=True)
        (root / "two").mkdir(parents=True)
        (root / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "multitask", "session": SESSION,
                                                         "cost": {"last": "2026-10-10T20:30:00Z", "session": SESSION, "phases": []}}))
        (root / "one" / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "part", "session": SESSION,
                                                                 "cost": {"last": "2026-10-10T21:30:00Z", "session": SESSION, "phases": []}}))
        (root / "two" / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "part", "session": SESSION}))
        code, out = run("phase", str(root / "two"), "start", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        entry = json.loads(out)
        self.assertEqual((entry["since"], entry["requests"]), ("2026-10-10T21:30:00Z", 1))   # part one's cursor, not the session start
        self.assertEqual((entry["cost_eq"], entry["session"]), (int(100_000 * 1.25), SESSION))
        self.assertEqual(yaml.safe_load((root / "two" / "state.yaml").read_text())["cost"]["session"], SESSION)
        # the multitask's own next window starts after its parts
        code, out = run("phase", str(root), "finalize", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["requests"], 0)

    def test_a_cursor_another_session_wrote_is_ignored(self):
        self.main_log([
            reply("2026-10-10T21:10:01Z", read=0, create=100_000, out=0, inp=0, rid="o1"),
            reply("2026-10-10T21:20:01Z", read=0, create=100_000, out=0, inp=0, rid="o2"),
            reply("2026-10-10T21:40:01Z", read=0, create=100_000, out=0, inp=0, rid="o3"),
        ])
        root = Path(self.tmp.name) / ".tasks" / "M-1"
        (root / "a").mkdir(parents=True)
        (root / "b").mkdir(parents=True)
        (root / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "multitask"}))
        # owner A's part, integrated and synced into B's tree: its cursor comes from A's session
        (root / "a" / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "part",
                                                               "cost": {"last": "2026-10-10T21:30:00Z", "session": "other-session",
                                                                        "phases": []}}))
        (root / "b" / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "M-1", "kind": "part", "session": SESSION,
                                                               "cost": {"last": "2026-10-10T21:00:00Z", "session": SESSION,
                                                                        "phases": []}}))
        code, out = run("phase", str(root / "b"), "research", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        entry = json.loads(out)
        self.assertEqual((entry["since"], entry["requests"]), ("2026-10-10T21:00:00Z", 3))   # 1 if A's cursor counted
        # an unreadable sibling state is skipped, not fatal
        (root / "a" / "state.yaml").write_text("cost: [unclosed")
        code, out = run("phase", str(root / "b"), "spec", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)

    def test_phase_without_a_cursor_counts_from_the_session_start(self):
        self.main_log([reply("2026-10-10T20:00:01Z", read=0, create=100_000, out=0, rid="o1")])
        task = Path(self.tmp.name) / ".tasks" / "T-1"
        task.mkdir(parents=True)
        (task / "state.yaml").write_text(yaml.safe_dump({"schema": 1, "id": "T-1", "kind": "task", "session": SESSION}))
        code, out = run("phase", str(task), "start", "--projects", str(self.projects), "--json")
        self.assertEqual(code, 0, out)
        entry = json.loads(out)
        self.assertEqual((entry["requests"], entry["since"]), (1, None))


if __name__ == "__main__":
    unittest.main()
