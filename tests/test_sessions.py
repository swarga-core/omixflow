"""Tests for sessions.py: task sessions the lead launches in the background or in a window."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sessions.py"

# `claude` stub: logs argv and cwd; `agents` answers the next poll of agents.json
# ("fail" exits 1); `--bg` prints bg_out, or the backgrounded line with bg_name (default:
# the requested name), or exits bg_code with bg_err.
CLAUDE_STUB = r'''#!/usr/bin/env python3
import json, os, sys
d = os.environ["STUB_DIR"]
args = sys.argv[1:]
with open(os.path.join(d, "log.jsonl"), "a") as f:
    f.write(json.dumps({"tool": "claude", "argv": args, "cwd": os.getcwd()}) + "\n")
def read(name, default=None):
    try:
        with open(os.path.join(d, name)) as f:
            return f.read()
    except OSError:
        return default
if args[:1] == ["--help"]:
    print(read("help.txt", "  --bg, --background   Start the session in the background"))
elif args[:1] == ["--version"]:
    print("2.1.296 (Claude Code)")
elif args[:1] == ["agents"]:
    polls = json.loads(read("agents.json", "[[]]"))
    n = int(read("agents.count", "0") or 0)
    with open(os.path.join(d, "agents.count"), "w") as f:
        f.write(str(n + 1))
    poll = polls[min(n, len(polls) - 1)]
    if poll == "fail":
        sys.exit(1)
    print(json.dumps(poll))
elif "--bg" in args:
    code = int(read("bg_code", "0") or 0)
    if code:
        print(read("bg_err", ""), file=sys.stderr)
        sys.exit(code)
    out = read("bg_out")
    name = read("bg_name") or args[args.index("--name") + 1]
    print(out if out is not None else "backgrounded · 1a2b3c4d · " + name)
elif args[:1] == ["respawn"]:
    sys.exit(int(read("respawn_code", "0") or 0))
'''

OSASCRIPT_STUB = r'''#!/usr/bin/env python3
import json, os, sys
d = os.environ["STUB_DIR"]
with open(os.path.join(d, "log.jsonl"), "a") as f:
    f.write(json.dumps({"tool": "osascript", "argv": sys.argv[1:]}) + "\n")
code = os.path.join(d, "osa_code")
sys.exit(int(open(code).read()) if os.path.exists(code) else 0)
'''

SESSION = "b06639d4-4f62-4ecc-90b5-283e3798c1a5"
PROMPT = "/omixflow:develop T-18 --lead=swais-lead --worktree"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.stub = base / "stub"
        self.stub.mkdir()
        self.root = base / "my project"
        (self.root / ".claude" / "omixflow").mkdir(parents=True)
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text("version: 1\n")
        self.other = base / "other"
        self.config = base / "config"
        self.config.mkdir()
        self.claude = self.stub / "claude"
        self.claude.write_text(CLAUDE_STUB)
        self.claude.chmod(0o755)
        self.osa = self.stub / "osascript"
        self.osa.write_text(OSASCRIPT_STUB)
        self.osa.chmod(0o755)
        self.polls([[]])

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, name, status, state="working", sid="aaaa1111", started=1000, cwd=None):
        return {"name": name, "id": sid, "kind": "background", "status": status, "state": state,
                "cwd": str(cwd or self.root / ".claude" / "worktrees" / name), "startedAt": started,
                "sessionId": sid + "-x", "pid": 1}

    def polls(self, polls):
        (self.stub / "agents.json").write_text(json.dumps(polls))
        (self.stub / "agents.count").write_text("0")

    def env(self, osascript=True, session=None, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_BG_ISOLATION")}
        env.update(STUB_DIR=str(self.stub), OMIXFLOW_CLAUDE=str(self.claude),
                   OMIXFLOW_OSASCRIPT=str(self.osa if osascript else self.stub / "missing"),
                   CLAUDE_CONFIG_DIR=str(self.config), **extra)
        if session:
            env["CLAUDE_CODE_SESSION_ID"] = session
        return env

    def run_script(self, *args, osascript=True, session=None, **extra):
        res = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                             env=self.env(osascript, session, **extra))
        out = json.loads(res.stdout) if res.stdout.strip() else None
        return res.returncode, out

    def log(self, tool=None):
        path = self.stub / "log.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if tool is None or r["tool"] == tool]

    def bg_calls(self):
        return [r for r in self.log("claude") if "--bg" in r["argv"]]

    def transcript(self, *modes):
        d = self.config / "projects" / "-lead"
        d.mkdir(parents=True, exist_ok=True)
        rows = [{"type": "permission-mode", "permissionMode": m} for m in modes]
        (d / f"{SESSION}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + '{"type": "user"')

    def launch(self, *extra, mode="background", prompt=PROMPT, root=None, **kw):
        return self.run_script("launch", "T-18", "--root", str(root or self.root), "--mode", mode, *extra,
                               "--", prompt, **kw)

    def watch(self, *names, known=(), polls=3, **kw):
        args = ["watch", *names, "--root", str(self.root), "--owner", "swais-lead", "--interval", "0",
                "--max-polls", str(polls)]
        if known:
            args += ["--known", *known]
        return self.run_script(*args, **kw)

    # probe

    def test_probe_reports_background_terminal_and_isolation(self):
        (self.root / ".claude" / "settings.json").write_text('{"worktree": {"bgIsolation": "worktree"}}')
        (self.config / "settings.json").write_text('{"worktree": {"bgIsolation": "none"}}')
        code, out = self.run_script("probe", "--root", str(self.root))
        self.assertEqual((code, out), (0, {"background": True, "terminal": True, "version": "2.1.296",
                                           "bg_isolation": "worktree"}))
        (self.root / ".claude" / "settings.local.json").write_text('{"worktree": {"bgIsolation": "none"}}')
        self.assertEqual(self.run_script("probe", "--root", str(self.root))[1]["bg_isolation"], "none")
        out = self.run_script("probe", "--root", str(self.root), CLAUDE_BG_ISOLATION="worktree")[1]
        self.assertEqual(out["bg_isolation"], "worktree")  # the harness reads the env first

    def test_probe_without_bg_or_osascript(self):
        (self.stub / "help.txt").write_text("  -n, --name <name>  Set a display name")
        code, out = self.run_script("probe", osascript=False)
        self.assertEqual((code, out["background"], out["terminal"]), (0, False, False))
        self.assertNotIn("bg_isolation", out)

    # launch

    def test_background_launch_runs_in_the_root_in_the_lead_mode(self):
        self.transcript("default", "acceptEdits")
        code, out = self.launch(session=SESSION)
        self.assertEqual(code, 0)
        self.assertEqual(out, {"name": "T-18", "mode": "background", "permission_mode": "acceptEdits",
                               "model": "opus", "model_source": "config", "effort": "xhigh",
                               "effort_source": "config", "id": "1a2b3c4d"})
        [bg] = self.bg_calls()
        self.assertEqual(bg["argv"], ["--bg", "--name", "T-18", "--permission-mode", "acceptEdits",
                                      "--model", "opus", "--effort", "xhigh", PROMPT])
        self.assertEqual(os.path.realpath(bg["cwd"]), str(self.root))

    def test_explicit_mode_wins_and_unknown_mode_passes_no_flag(self):
        self.transcript("acceptEdits")
        self.launch("--permission-mode", "plan", session=SESSION)
        argv = self.bg_calls()[-1]["argv"]
        self.assertEqual(argv[argv.index("--permission-mode"):argv.index("--permission-mode") + 2],
                         ["--permission-mode", "plan"])
        self.assertNotIn("acceptEdits", argv)
        code, out = self.launch(session="no-such-session")
        self.assertEqual((code, out["permission_mode"]), (0, None))
        self.assertNotIn("--permission-mode", self.bg_calls()[-1]["argv"])

    def test_the_model_is_always_passed_flag_then_orchestrator_then_strong(self):
        """SwAIS T-10, T-12…T-14: without --model a background session ran on Fable under the user's
        `"model": "opus"`; the session's model is the project's, set at launch."""
        flow = self.root / ".claude" / "omixflow" / "flow.yaml"
        cases = [("version: 1\nmodels: {strong: fable}\n", (), ("fable", "config")),
                 ("version: 1\nmodels: {strong: fable, orchestrator: claude-opus-5-5}\n", (), ("claude-opus-5-5", "config")),
                 ("version: 1\nmodels: {orchestrator: opus}\n", ("--model", "sonnet"), ("sonnet", "flag"))]
        for text, extra, (model, source) in cases:
            with self.subTest(config=text, extra=extra):
                flow.write_text(text)
                code, out = self.launch(*extra)
                self.assertEqual((code, out["model"], out["model_source"]), (0, model, source), out)
                argv = self.bg_calls()[-1]["argv"]
                self.assertEqual(argv[argv.index("--model") + 1], model)
                self.assertEqual(argv.count("--model"), 1)
        flow.write_text("version: 1\nmodels: {orchestrator: sonnet}\n")
        code, out = self.launch(mode="terminal", osascript=False)
        self.assertIn("--model sonnet", out["command"])

    def test_the_prompt_learns_the_model_and_a_broken_config_is_refused(self):
        """Review F3: the session must know what it was launched on (`develop --model={model}`);
        F1, F5: a malformed flow.yaml or an empty model is exit 3 with a reason, not a traceback."""
        flow = self.root / ".claude" / "omixflow" / "flow.yaml"
        flow.write_text("version: 1\nmodels: {orchestrator: claude-opus-5-5}\n")
        code, out = self.launch(prompt="/omixflow:develop T-18 --lead=swais-lead --worktree --model={model}")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.bg_calls()[-1]["argv"][-1],
                         "/omixflow:develop T-18 --lead=swais-lead --worktree --model=claude-opus-5-5")
        for text in ("version: 1\nmodels: {orchestrator: [unclosed\n", "version: 1\nmodels: {strong: '  '}\n",
                     "version: 1\nmodels: {orchestrator: {a: 1}}\n"):
            with self.subTest(config=text):
                flow.write_text(text)
                code, out = self.launch()
                self.assertEqual(code, 3, out)
                self.assertIn("передай --model", out["error"])
        flow.write_text("version: 1\nmodels: {orchestrator: [unclosed\n")
        code, out = self.launch("--model", "sonnet")      # 0.9.3: the effort still comes from the config
        self.assertEqual(code, 3, out)
        self.assertIn("передай --effort", out["error"])
        code, out = self.launch("--model", "sonnet", "--effort", "high")      # both flags need no config
        self.assertEqual((code, out["model"], out["effort"]), (0, "sonnet", "high"))

    def test_the_effort_is_always_passed_flag_then_config_then_xhigh(self):
        """Without --effort a session takes the level the user settings keep for its model, else the
        model's default — medium on Opus 5.5, which ignores a top-level `effortLevel`."""
        flow = self.root / ".claude" / "omixflow" / "flow.yaml"
        cases = [("version: 1\n", (), ("xhigh", "config")),
                 ("version: 1\neffort: {orchestrator: high}\n", (), ("high", "config")),
                 ("version: 1\neffort: {orchestrator: ' '}\n", (), ("xhigh", "config")),
                 ("version: 1\neffort: {orchestrator: high}\n", ("--effort", "max"), ("max", "flag"))]
        for text, extra, (effort, source) in cases:
            with self.subTest(config=text, extra=extra):
                flow.write_text(text)
                code, out = self.launch(*extra)
                self.assertEqual((code, out["effort"], out["effort_source"]), (0, effort, source), out)
                argv = self.bg_calls()[-1]["argv"]
                self.assertEqual(argv[argv.index("--effort") + 1], effort)
                self.assertEqual(argv.count("--effort"), 1)
        flow.write_text("version: 1\neffort: {orchestrator: medium}\n")
        code, out = self.launch(mode="terminal", osascript=False)
        self.assertIn("--effort medium", out["command"])

    def test_an_unknown_effort_is_refused(self):
        """Review 0.9.3: `effort: low` (not an object) silently became xhigh; `High` passed here
        but not the schema's enum."""
        flow = self.root / ".claude" / "omixflow" / "flow.yaml"
        for text in ("version: 1\neffort: {orchestrator: ultra}\n", "version: 1\neffort: {orchestrator: 3}\n",
                     "version: 1\neffort: low\n", "version: 1\neffort: {orchestrator: High}\n"):
            with self.subTest(config=text):
                flow.write_text(text)
                code, out = self.launch()
                self.assertEqual(code, 3, out)
                self.assertIn("передай --effort", out["error"])
        code, out = self.launch("--effort", "ultra")
        self.assertEqual(code, 2, out)
        self.assertFalse(self.bg_calls())
        code, out = self.launch("--effort", "low")      # the flag wins over a bad config value
        self.assertEqual((code, out["effort"]), (0, "low"))

    def test_launch_refuses_a_name_active_anywhere_but_not_a_stopped_one(self):
        self.polls([[self.entry("T-18", "idle", sid="mew1", cwd=self.other)]])
        code, out = self.launch()
        self.assertEqual(code, 3)
        self.assertIn("занято", out["error"])
        self.assertFalse(self.bg_calls())
        self.polls([[self.entry("T-18", None, state="stopped", sid="old1")]])
        self.assertEqual(self.launch()[0], 0)

    def test_suffixed_name_is_reported_with_its_id(self):
        (self.stub / "bg_name").write_text("T-18 (2)")
        code, out = self.launch()
        self.assertEqual(code, 3)
        self.assertEqual((out["id"], out["actual_name"]), ("1a2b3c4d", "T-18 (2)"))

    def test_bg_without_an_id_is_a_failure_unless_agents_lists_it(self):
        (self.stub / "bg_out").write_text("started")
        code, out = self.launch()
        self.assertEqual(code, 3)
        self.assertIn("не назвал id", out["error"])
        self.polls([[], [self.entry("T-18", "busy", sid="late1")]])
        self.assertEqual(self.launch(), (0, {"name": "T-18", "mode": "background", "permission_mode": None,
                                             "model": "opus", "model_source": "config", "effort": "xhigh",
                                             "effort_source": "config", "id": "late1"}))

    def test_background_failure_is_reported_with_the_harness_message(self):
        (self.stub / "bg_code").write_text("1")
        (self.stub / "bg_err").write_text("Workspace not trusted. Run `claude` in /x once")
        code, out = self.launch()
        self.assertEqual(code, 3)
        self.assertIn("Workspace not trusted", out["error"])

    def test_root_must_be_the_main_checkout_of_an_omixflow_project(self):
        self.other.mkdir()
        code, out = self.launch(root=self.other)
        self.assertEqual(code, 3)
        self.assertIn("flow.yaml", out["error"])
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "init")
        linked = Path(self.tmp.name).resolve() / "linked"
        git(self.root, "worktree", "add", "-q", str(linked))
        code, out = self.launch(root=linked)
        self.assertEqual(code, 3)
        self.assertIn("связанный worktree", out["error"])
        self.assertEqual(self.launch()[0], 0)
        self.assertFalse([c for c in self.bg_calls() if os.path.realpath(c["cwd"]) != str(self.root)])

    def test_terminal_launch_opens_a_window_with_the_quoted_command(self):
        self.transcript("acceptEdits")
        prompt = '/omixflow:develop "fix the \'x\' \\ bug" --lead=swais-lead'
        code, out = self.launch(mode="terminal", prompt=prompt, session=SESSION)
        self.assertEqual((code, out["opened"]), (0, True))
        [osa] = self.log("osascript")
        self.assertEqual(osa["argv"][0], "-e")
        script = osa["argv"][1]
        head = 'tell application "Terminal" to do script "'
        self.assertTrue(script.startswith(head), script)
        shell, i = [], len(head)
        while script[i] != '"':  # an AppleScript literal: backslash escapes, a bare quote ends it
            if script[i] == "\\":
                i += 1
            shell.append(script[i])
            i += 1
        self.assertEqual(i, len(script) - 1, "текст после конца строки AppleScript")
        self.assertEqual("".join(shell), out["command"])
        self.assertEqual(shlex.split(out["command"]), ["cd", str(self.root), "&&", str(self.claude), "-n",
                                                       "T-18", "--permission-mode", "acceptEdits", "--model", "opus",
                                                       "--effort", "xhigh", prompt])
        self.assertFalse(self.bg_calls())

    def test_terminal_without_osascript_hands_the_command_to_the_developer(self):
        code, out = self.launch(mode="terminal", osascript=False)
        self.assertEqual((code, out["opened"]), (4, False))
        self.assertIn("-n T-18", out["command"])
        (self.stub / "osa_code").write_text("1")
        code, out = self.launch(mode="terminal")
        self.assertEqual((code, out["opened"]), (4, False))
        self.assertIn("osascript", out["reason"])

    def test_status_watch_and_respawn_check_the_root(self):
        for args in (["status"], ["watch", "T-18", "--owner", "l", "--max-polls", "1"], ["respawn", "T-18"]):
            with self.subTest(cmd=args[0]):
                code, out = self.run_script(*args, "--root", str(self.other))
                self.assertEqual(code, 3)
                self.assertIn("корень", out["error"])

    def test_names_and_usage_errors_are_json_exit_2(self):
        self.assertEqual(self.run_script("launch", "T 18;", "--root", str(self.root), "--mode",
                                         "background", "--", "x")[0], 2)
        code, out = self.run_script("watch", "T-18", "--root", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("--owner", out["error"])

    # status, watch, respawn

    def test_status_lists_the_project_sessions_only(self):
        self.polls([[self.entry("T-8", "idle", sid="b", started=2), self.entry("T-18", "busy", started=1),
                     self.entry("T-18", "busy", sid="mew", cwd=self.other)]])
        code, out = self.run_script("status", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual([(x["name"], x["id"]) for x in out], [("T-18", "aaaa1111"), ("T-8", "b")])
        self.assertEqual(sorted(out[0]), ["cwd", "id", "kind", "limited", "limited_until", "name", "state", "status"])
        self.assertEqual([x["name"] for x in self.run_script("status", "T-8", "--root", str(self.root))[1]],
                         ["T-8"])

    def test_watch_wakes_on_waiting(self):
        self.polls([[self.entry("T-18", "busy")], [self.entry("T-18", "waiting", state="blocked")]])
        code, out = self.watch("T-18", polls=5)
        self.assertEqual(code, 0)
        self.assertEqual(out["events"], [{"name": "T-18", "state": "waiting", "id": "aaaa1111"}])
        self.assertEqual(out["known"], {"T-18": "waiting"})

    def limited_transcript(self, sid: str, resets, where: str = "quotaLimits") -> None:
        """The record the harness writes when the account's usage limit rejects a request
        (SwAIS T-13, 2026-10-17: `error: rate_limit`, `apiError: usage_limit_reached`)."""
        d = self.config / "projects" / "-wt"
        d.mkdir(parents=True, exist_ok=True)
        rows = [{"type": "assistant", "message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "ok"}]}},
                {"type": "user", "message": {"content": "notice"}},
                {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "apiError": "usage_limit_reached",
                 "timestamp": "2026-10-17T11:41:56Z",
                 "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your weekly limit"}]}}]
        info = {"status": "rejected", "rateLimitType": "seven_day", **({"resetsAt": resets} if resets is not None else {})}
        if where == "quotaLimits":
            rows[-1]["quotaLimits"] = info
        else:
            rows[-1]["apiErrorParams"] = {"rate_limit_info": info}
        (d / f"{sid}-x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_a_limited_session_is_an_event_only_after_the_reset(self):
        """G-75: the weekly limit stopped the lead and T-13, T-14 at once; after the reset nobody
        woke them for ~16 h. A lead woken before the reset would hit the same limit."""
        self.polls([[self.entry("T-13", "idle", sid="t13")]])
        self.limited_transcript("t13", int(time.time()) + 3600)
        self.assertEqual(self.watch("T-13", polls=2), (1, {"events": [], "known": {}}))
        rows = self.run_script("status", "--root", str(self.root))[1]
        self.assertTrue(rows[0]["limited_until"].endswith("Z"))
        reset = int(time.time()) - 120
        self.limited_transcript("t13", reset)
        code, out = self.watch("T-13", polls=2)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["events"], [{"name": "T-13", "state": "limited", "id": "t13",
                                          "resets_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(reset))}])
        self.assertEqual(out["known"], {"T-13": f"limited@{reset}"})
        self.assertEqual(self.watch("T-13", known=(f"T-13=limited@{reset}",), polls=2)[0], 1)   # no repeat
        # review F3: limited again right after the advisory — a new reset is a new event
        later = int(time.time()) - 61
        self.limited_transcript("t13", later)
        code, out = self.watch("T-13", known=(f"T-13=limited@{reset}",), polls=1)
        self.assertEqual((code, out["events"][0]["state"]), (0, "limited"))
        self.polls([[self.entry("T-13", "busy", sid="t13")]])        # working again: not limited
        self.assertEqual(self.watch("T-13", polls=1)[1]["known"], {"T-13": "busy"})

    def test_while_the_account_is_limited_no_event_wakes_the_lead(self):
        """Review F4: another session's `stopped` during the window would wake a lead that is limited
        too (its turns failed at 11:41:58 and 11:42:22), and the watch would not be restarted."""
        self.polls([[self.entry("T-13", "idle", sid="t13"), self.entry("T-14", None, state="stopped", sid="t14")]])
        self.limited_transcript("t13", int(time.time()) + 3600)
        self.assertEqual(self.watch("T-13", "T-14", polls=2), (1, {"events": [], "known": {}}))
        self.limited_transcript("t13", int(time.time()) - 120)
        code, out = self.watch("T-13", "T-14", polls=1)
        self.assertEqual((code, sorted(e["state"] for e in out["events"])), (0, ["limited", "stopped"]))

    def replied(self, sid: str, at: str) -> None:
        d = self.config / "projects" / "-wt"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{sid}-x.jsonl").write_text(json.dumps({"type": "assistant", "timestamp": at,
                                                       "message": {"model": "claude-opus-5-5", "content": []}}) + "\n")

    def test_one_limited_session_does_not_silence_the_others_once_the_account_works(self):
        """Re-review N1: a per-model limit or extra usage — another session replied after the limit
        record, so the lead is not limited and T-14's dialog must reach the developer now."""
        self.polls([[self.entry("T-13", "idle", sid="t13"), self.entry("T-14", "waiting", sid="t14")]])
        self.limited_transcript("t13", int(time.time()) + 86400)
        self.replied("t14", "2026-10-17T12:30:00Z")
        code, out = self.watch("T-13", "T-14", polls=1)
        self.assertEqual((code, [e["state"] for e in out["events"]]), (0, ["waiting"]))
        self.assertNotIn("T-13", out["known"])               # its event waits for its own reset

    def test_a_synthetic_record_is_no_reply(self):
        """Re-review S1: «No response requested.» after an interruption is written as a synthetic
        assistant record; it neither lifts the hold nor hides the session's own limit."""
        self.limited_transcript("t13", int(time.time()) - 120)
        log = self.config / "projects" / "-wt" / "t13-x.jsonl"
        with log.open("a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-17T12:00:00Z",
                                "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "No response requested."}]}}) + "\n")
        self.polls([[self.entry("T-13", "idle", sid="t13")]])
        code, out = self.watch("T-13", polls=1)
        self.assertEqual((code, out["events"][0]["state"]), (0, "limited"))

    def test_the_leads_own_reply_after_the_limit_lifts_the_hold(self):
        """Re-review S2: a per-model limit — the watched sessions are limited, the lead replied since."""
        lead_dir = self.config / "projects" / "-lead"
        lead_dir.mkdir(parents=True, exist_ok=True)
        (lead_dir / f"{SESSION}.jsonl").write_text(json.dumps(
            {"type": "assistant", "timestamp": "2026-10-17T12:30:00Z", "message": {"model": "claude-fable-5-1", "content": []}}) + "\n")
        self.polls([[self.entry("T-13", "idle", sid="t13"), self.entry("T-14", "waiting", sid="t14")]])
        self.limited_transcript("t13", int(time.time()) + 3600)
        code, out = self.watch("T-13", "T-14", polls=1, session=SESSION)
        self.assertEqual((code, [e["state"] for e in out["events"]]), (0, ["waiting"]))

    def lead_context(self, size: int, at: str = "2026-10-20T10:00:00Z") -> None:
        """The lead's own transcript ending with a reply whose request held SIZE tokens."""
        lead_dir = self.config / "projects" / "-lead"
        lead_dir.mkdir(parents=True, exist_ok=True)
        usage = {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": size - 1003,
                 "output_tokens": 500}
        (lead_dir / f"{SESSION}.jsonl").write_text(json.dumps(
            {"type": "assistant", "timestamp": at, "message": {"model": "claude-opus-5-5", "content": [], "usage": usage}}) + "\n")

    def test_the_leads_context_over_the_threshold_is_one_rotate_event(self):
        """Lead rotation (0.9.7): 13 leads ran at 365–550k on average up to the 1M auto-compact;
        changing the lead at 300k by /clear cuts its cost by 42–57 % in a replay of the transcripts."""
        self.polls([[self.entry("T-14", "busy", sid="t14")]])
        self.lead_context(350_000)
        code, out = self.watch("T-14", "--rotate-context", "300000", polls=2, session=SESSION)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["events"], [{"name": "swais-lead", "state": "rotate", "context": 350_000}])
        self.assertEqual(out["known"], {"T-14": "busy", "swais-lead": f"rotate@{SESSION}"})
        # once per lead session: the known state from the output stops a repeat
        self.assertEqual(self.watch("T-14", "--rotate-context", "300000", known=(f"swais-lead=rotate@{SESSION}",),
                                    polls=2, session=SESSION)[0], 1)
        # review 0.9.7: the known state is per lead session — the lead after /clear is signalled again
        code, out = self.watch("T-14", "--rotate-context", "300000", known=("swais-lead=rotate@old-session",),
                               polls=1, session=SESSION)
        self.assertEqual((code, out["known"]["swais-lead"]), (0, f"rotate@{SESSION}"))
        self.assertEqual(self.watch("T-14", "--rotate-context", "350000", polls=1, session=SESSION)[0], 1)  # above, not at
        # under the threshold, without the option, without the lead's session id: no event
        self.lead_context(250_000)
        self.assertEqual(self.watch("T-14", "--rotate-context", "300000", polls=1, session=SESSION)[0], 1)
        self.lead_context(350_000)
        self.assertEqual(self.watch("T-14", polls=1, session=SESSION)[0], 1)
        self.assertEqual(self.watch("T-14", "--rotate-context", "300000", polls=1)[0], 1)
        self.assertEqual(self.watch("T-14", "--rotate-context", "-1", polls=1, session=SESSION)[0], 2)

    def test_the_rotate_event_notifies_with_the_steps(self):
        self.polls([[self.entry("T-14", "busy", sid="t14")]])
        self.lead_context(420_000)
        code, _ = self.watch("T-14", "--rotate-context", "300000", "--notify", polls=1, session=SESSION)
        self.assertEqual(code, 0)
        script = " ".join(" ".join(r["argv"]) for r in self.log("osascript"))
        self.assertIn("контекст 420k — смена лида: /clear, затем /omixflow:lead (фоновый лид — claude attach swais-lead)",
                      script)

    def test_a_lead_without_background_sessions_watches_for_rotate_alone(self):
        """Review 0.9.7, finding 9: a lead in terminal mode, or with all its sessions done, held no
        watch and got no signal; without names watch keeps the rotate event and polls no sessions."""
        self.lead_context(350_000)
        code, out = self.watch("--rotate-context", "300000", polls=2, session=SESSION)
        self.assertEqual((code, out), (0, {"events": [{"name": "swais-lead", "state": "rotate", "context": 350_000}],
                                           "known": {"swais-lead": f"rotate@{SESSION}"}}))
        self.assertEqual(self.watch("--rotate-context", "300000", known=(f"swais-lead=rotate@{SESSION}",),
                                    polls=2, session=SESSION)[0], 1)
        self.assertEqual(self.log("claude"), [])                   # no `claude agents` polls
        code, out = self.watch(polls=1, session=SESSION)          # nothing else to watch for
        self.assertEqual(code, 2)
        self.assertIn("--rotate-context", out["error"])

    def test_no_rotate_event_while_the_lead_is_limited(self):
        """A lead woken under the account's limit could not act on it either."""
        self.polls([[self.entry("T-13", "idle", sid="t13")]])
        self.limited_transcript("t13", int(time.time()) + 3600)
        self.lead_context(350_000, at="2026-10-17T11:00:00Z")      # its reply is older than the limit
        self.assertEqual(self.watch("T-13", "--rotate-context", "300000", polls=1, session=SESSION)[0], 1)

    def test_the_leads_own_limit_holds_every_event(self):
        lead_dir = self.config / "projects" / "-lead"
        lead_dir.mkdir(parents=True, exist_ok=True)
        (lead_dir / f"{SESSION}.jsonl").write_text(json.dumps(
            {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "apiError": "usage_limit_reached",
             "timestamp": "2026-10-17T11:41:58Z", "quotaLimits": {"status": "rejected", "resetsAt": int(time.time()) + 3600},
             "message": {"content": []}}) + "\n")
        self.polls([[self.entry("T-14", "waiting", sid="t14")]])
        self.replied("t14", "2026-10-17T12:30:00Z")
        self.assertEqual(self.watch("T-14", polls=1, session=SESSION), (1, {"events": [], "known": {}}))

    def test_the_reset_may_come_in_rate_limit_info_or_not_at_all(self):
        self.polls([[self.entry("T-13", "idle", sid="t13")]])
        reset = int(time.time()) - 300
        self.limited_transcript("t13", reset, where="apiErrorParams")
        out = self.watch("T-13", polls=1)[1]
        self.assertEqual(out["events"][0]["resets_at"], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(reset)))
        self.limited_transcript("t13", None)                  # review F9: no reset time — at once, `null`
        code, out = self.watch("T-13", polls=1)
        self.assertEqual((code, out["events"][0]["resets_at"]), (0, None))
        rows = self.run_script("status", "--root", str(self.root))[1]
        self.assertEqual((rows[0]["limited"], rows[0]["limited_until"]), (True, None))

    def test_a_waiting_session_stays_waiting_under_a_limit_record(self):
        """Review F7: a dialog needs the developer, an advisory cannot dismiss it."""
        self.polls([[self.entry("T-13", "waiting", sid="t13")]])
        self.limited_transcript("t13", int(time.time()) - 120)
        code, out = self.watch("T-13", polls=1)
        self.assertEqual((code, out["events"][0]["state"]), (0, "waiting"))

    def test_an_ordinary_api_error_is_not_the_limit(self):
        d = self.config / "projects" / "-wt"
        d.mkdir(parents=True, exist_ok=True)
        (d / "t13-x.jsonl").write_text(json.dumps({"type": "assistant", "isApiErrorMessage": True,
                                                   "error": "server_error", "message": {"content": []}}) + "\n")
        self.polls([[self.entry("T-13", "idle", sid="t13")]])
        self.assertEqual(self.watch("T-13", polls=1)[1]["known"], {"T-13": "idle"})
        self.assertIsNone(self.run_script("status", "--root", str(self.root))[1][0]["limited_until"])

    def test_session_waiting_for_the_lead_is_not_an_event(self):
        """T-18 ended its turn with «Жду decision»: status idle, state blocked."""
        self.polls([[self.entry("T-18", "idle", state="blocked")]])
        self.assertEqual(self.watch("T-18"), (1, {"events": [], "known": {"T-18": "idle"}}))

    def test_another_project_session_with_the_same_name_is_not_watched(self):
        self.polls([[self.entry("T-18", "waiting", cwd=self.other), self.entry("T-18", "busy", sid="mine")]])
        self.assertEqual(self.watch("T-18")[1]["known"], {"T-18": "busy"})

    def test_live_session_wins_over_a_newer_stopped_one(self):
        self.polls([[self.entry("T-18", "busy", sid="live", started=100),
                     self.entry("T-18", None, state="stopped", sid="dead", started=200)]])
        self.assertEqual(self.watch("T-18"), (1, {"events": [], "known": {"T-18": "busy"}}))

    def test_known_takes_several_values_and_suppresses_repeats(self):
        self.polls([[self.entry("T-18", "waiting"), self.entry("T-8", "waiting", sid="b")]])
        code, _ = self.watch("T-18", "T-8", known=("T-18=waiting", "T-8=waiting"))
        self.assertEqual(code, 1)
        self.polls([[self.entry("T-18", "waiting")], [self.entry("T-18", "busy")], [self.entry("T-18", "waiting")]])
        code, out = self.watch("T-18", known=("T-18=waiting",), polls=5)
        self.assertEqual((code, [e["state"] for e in out["events"]]), (0, ["waiting"]))

    def test_malformed_known_and_interval_are_usage_errors(self):
        self.assertEqual(self.watch("T-18", known=("T-18",))[0], 2)
        code, _ = self.run_script("watch", "T-18", "--root", str(self.root), "--owner", "l", "--interval", "-1")
        self.assertEqual(code, 2)

    def test_watch_reports_stopped_and_absent_sessions(self):
        self.polls([[self.entry("T-18", None, state="stopped", sid="s1"), self.entry("T-8", "busy", sid="b")]])
        code, out = self.watch("T-18", "T-8", "T-9", polls=2)
        self.assertEqual(code, 0)
        self.assertEqual({e["name"]: e["state"] for e in out["events"]}, {"T-18": "stopped", "T-9": "absent"})
        self.assertEqual(out["known"], {"T-18": "stopped", "T-8": "busy", "T-9": "absent"})

    def test_watch_survives_a_failed_poll_but_not_three(self):
        self.polls(["fail", [self.entry("T-18", "waiting")]])
        self.assertEqual(self.watch("T-18", polls=5)[0], 0)
        self.polls(["fail", "fail", "fail", [self.entry("T-18", "waiting")]])
        code, out = self.watch("T-18", polls=5)
        self.assertEqual(code, 3)
        self.assertIn("claude agents", out["error"])

    def test_notify_sends_a_notification_per_event(self):
        self.polls([[self.entry("T-18", "waiting")]])
        self.run_script("watch", "T-18", "--root", str(self.root), "--owner", "l", "--notify",
                        "--interval", "0", "--max-polls", "1")
        [osa] = self.log("osascript")
        self.assertIn("display notification", osa["argv"][1])
        self.assertIn("claude attach T-18", osa["argv"][1])

    def test_a_new_watch_supersedes_the_previous_one(self):
        git(self.root, "init", "-q")
        self.polls([[self.entry("T-18", "busy")]])
        first = subprocess.Popen([sys.executable, str(SCRIPT), "watch", "T-18", "--root", str(self.root),
                                  "--owner", "swais-lead", "--interval", "0.2"],
                                 stdout=subprocess.PIPE, text=True, env=self.env())
        lock = self.root / ".git" / "omixflow-sessions" / "watch-swais-lead.pid"
        for _ in range(100):
            if lock.exists() and lock.read_text().strip() == str(first.pid):
                break
            time.sleep(0.05)
        self.assertEqual(lock.read_text().strip(), str(first.pid))
        self.assertEqual(self.watch("T-18", polls=1)[0], 1)
        out, _ = first.communicate(timeout=10)
        self.assertEqual(first.returncode, 5)
        self.assertEqual(json.loads(out), {"events": [], "superseded": True})
        self.assertFalse(lock.exists())

    def test_respawn_takes_the_latest_stopped_project_session(self):
        self.polls([[self.entry("T-18", None, state="done", sid="old", started=100),
                     self.entry("T-18", None, state="stopped", sid="new", started=200),
                     self.entry("T-18", None, state="stopped", sid="mew", started=300, cwd=self.other)]])
        code, out = self.run_script("respawn", "T-18", "--root", str(self.root))
        self.assertEqual((code, out), (0, {"name": "T-18", "id": "new", "respawned": True}))
        self.assertIn(["respawn", "new"], [r["argv"] for r in self.log("claude")])

    def test_respawn_refuses_active_missing_other_project_and_failed(self):
        self.polls([[self.entry("T-18", "busy")]])
        code, out = self.run_script("respawn", "T-18", "--root", str(self.root))
        self.assertEqual(code, 3)
        self.assertIn("занято", out["error"])
        self.polls([[self.entry("T-18", None, state="stopped", sid="mine"),
                     self.entry("T-18", "busy", sid="mew", cwd=self.other)]])
        code, out = self.run_script("respawn", "T-18", "--root", str(self.root))
        self.assertEqual(code, 3)  # another project's live T-18 holds the address
        self.assertNotIn("respawn", [r["argv"][0] for r in self.log("claude")])
        self.polls([[self.entry("T-18", None, state="stopped", cwd=self.other)]])
        self.assertEqual(self.run_script("respawn", "T-18", "--root", str(self.root))[0], 3)
        self.polls([[self.entry("T-18", None, state="stopped")]])
        (self.stub / "respawn_code").write_text("1")
        self.assertEqual(self.run_script("respawn", "T-18", "--root", str(self.root))[0], 3)


if __name__ == "__main__":
    unittest.main()
