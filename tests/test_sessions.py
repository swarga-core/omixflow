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
                               "model": "opus", "model_source": "config", "id": "1a2b3c4d"})
        [bg] = self.bg_calls()
        self.assertEqual(bg["argv"], ["--bg", "--name", "T-18", "--permission-mode", "acceptEdits",
                                      "--model", "opus", PROMPT])
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
        code, out = self.launch("--model", "sonnet")      # the flag needs no config
        self.assertEqual((code, out["model"]), (0, "sonnet"))

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
                                             "model": "opus", "model_source": "config", "id": "late1"}))

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
                                                       prompt])
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
        self.assertEqual(sorted(out[0]), ["cwd", "id", "kind", "name", "state", "status"])
        self.assertEqual([x["name"] for x in self.run_script("status", "T-8", "--root", str(self.root))[1]],
                         ["T-8"])

    def test_watch_wakes_on_waiting(self):
        self.polls([[self.entry("T-18", "busy")], [self.entry("T-18", "waiting", state="blocked")]])
        code, out = self.watch("T-18", polls=5)
        self.assertEqual(code, 0)
        self.assertEqual(out["events"], [{"name": "T-18", "state": "waiting", "id": "aaaa1111"}])
        self.assertEqual(out["known"], {"T-18": "waiting"})

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
