"""Tests for agent_ctx.py: an agent's context size read from its harness transcript."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SESSION = "cc4aff56-1ee5-4672-b4ea-26b12d35ad84"


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CONFIG_DIR")}
    full.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPTS / "agent_ctx.py"), *args],
                          capture_output=True, text=True, env=full)


def reply(ts: str, inp: int, read: int, create: int) -> dict:
    return {"type": "assistant", "timestamp": ts,
            "message": {"usage": {"input_tokens": inp, "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": create, "output_tokens": 50}}}


class AgentCtxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = Path(self.tmp.name) / "projects"

    def tearDown(self):
        self.tmp.cleanup()

    def agent(self, name: str, records: list, slug: str = "-proj", session: str = SESSION,
              suffix: str = "abc", raw_tail: str = "") -> Path:
        d = self.projects / slug / session / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        stem = f"agent-a{name}-{suffix}"
        (d / f"{stem}.meta.json").write_text(json.dumps({"name": name, "taskKind": "in_process_teammate"}))
        log = d / f"{stem}.jsonl"
        log.write_text("".join(json.dumps(r) + "\n" for r in records) + raw_tail)
        return log

    def measure(self, name: str, *extra: str) -> tuple:
        res = run(name, "--session", SESSION, "--projects", str(self.projects), *extra)
        return res.returncode, json.loads(res.stdout) if res.stdout.strip() else None

    def test_context_of_the_latest_reply_sums_all_input_kinds(self):
        log = self.agent("coder-MEW-2", [
            {"type": "user", "message": {"content": "STEP: 1"}},
            reply("2026-10-09T17:30:00Z", 2, 100_000, 1_000),
            reply("2026-10-09T18:06:52Z", 3, 430_000, 7_305),
            {"type": "user", "message": {"content": "STEP: 5"}},
        ])
        code, out = self.measure("coder-MEW-2")
        self.assertEqual(code, 0)
        self.assertEqual(out["context"], 437_308)
        self.assertEqual(out["at"], "2026-10-09T18:06:52Z")
        self.assertEqual(out["transcript"], str(log))

    def test_api_error_and_malformed_records_do_not_hide_the_last_real_reply(self):
        synthetic = reply("t2", 0, 9, 0)  # usage non-zero: the model marker alone must skip it
        synthetic["message"]["model"] = "<synthetic>"
        flagged = reply("t3", 0, 9, 0)  # the error flag alone must skip it
        flagged["isApiErrorMessage"] = True
        self.agent("coder-MEW-2", [
            reply("t1", 2, 400_000, 0), synthetic, flagged, reply("t4", 0, 0, 0),
            {"type": "assistant", "message": "oops"},
            {"type": "assistant", "message": {"usage": {"input_tokens": "many"}}},
            {"type": "assistant", "message": {"usage": None}},
            ["not", "a", "record"],
        ])
        code, out = self.measure("coder-MEW-2")
        self.assertEqual((code, out["context"], out["at"]), (0, 400_002, "t1"))

    def test_broken_or_orphan_meta_files_are_skipped(self):
        d = self.projects / "-proj" / SESSION / "subagents"
        d.mkdir(parents=True)
        (d / "agent-abroken.meta.json").write_text("{not json")
        (d / "agent-alist.meta.json").write_text('["coder-X"]')
        (d / "agent-aorphan.meta.json").write_text('{"name": "coder-X"}')  # no .jsonl next to it
        code, out = self.measure("coder-X")
        self.assertEqual((code, out["context"]), (3, None))
        self.assertIn("не найден", out["reason"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_unreadable_transcript_is_unknown_not_a_traceback(self):
        log = self.agent("coder-X", [reply("t", 1, 1, 1)])
        log.chmod(0)
        try:
            res = run("coder-X", "--session", SESSION, "--projects", str(self.projects))
        finally:
            log.chmod(0o644)
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertIn("не прочитан", json.loads(res.stdout)["reason"])

    def test_line_still_being_written_is_skipped(self):
        self.agent("coder-MEW-2", [reply("t1", 1, 10, 0)], raw_tail='{"type": "assistant", "mess')
        code, out = self.measure("coder-MEW-2")
        self.assertEqual((code, out["context"], out["at"]), (0, 11, "t1"))

    def test_other_names_and_other_sessions_do_not_count(self):
        self.agent("coder-MEW-2-2", [reply("t", 1, 900, 0)])
        self.agent("coder-MEW-2", [reply("t", 1, 900, 0)], session="other-session")
        code, out = self.measure("coder-MEW-2")
        self.assertEqual(code, 3)
        self.assertIsNone(out["context"])
        self.assertIn("не найден", out["reason"])

    def test_latest_transcript_wins_when_a_name_repeats(self):
        old = self.agent("reviewer-X", [reply("t", 1, 500_000, 0)], suffix="old")
        os.utime(old, (time.time() - 100, time.time() - 100))
        self.agent("reviewer-X", [reply("t", 1, 40_000, 0)], suffix="new", slug="-wt")
        self.assertEqual(self.measure("reviewer-X")[1]["context"], 40_001)

    def test_agent_without_a_reply_yet_is_unknown(self):
        self.agent("tester-X", [{"type": "user", "message": {"content": "go"}}])
        code, out = self.measure("tester-X")
        self.assertEqual(code, 3)
        self.assertIn("нет ответов", out["reason"])

    def test_session_and_projects_come_from_the_environment(self):
        config = Path(self.tmp.name) / "config"
        self.projects = config / "projects"
        self.agent("architect-X", [reply("t", 0, 7, 0)])
        res = run("architect-X", env={"CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_CONFIG_DIR": str(config)})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(json.loads(res.stdout)["context"], 7)

    def test_missing_or_malformed_session_id_is_unknown(self):
        res = run("coder-X", "--projects", str(self.projects))
        self.assertEqual(res.returncode, 3)
        self.assertIn("нет id сессии", json.loads(res.stdout)["reason"])
        self.agent("coder-X", [reply("t", 1, 1, 1)])
        res = run("coder-X", "--session", "*", "--projects", str(self.projects))
        self.assertEqual(res.returncode, 3)
        self.assertIsNone(json.loads(res.stdout)["context"])


if __name__ == "__main__":
    unittest.main()
