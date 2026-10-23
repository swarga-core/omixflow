#!/usr/bin/env python3
"""Task sessions the lead launches: in the background (`claude --bg`) or in a Terminal window.

    sessions.py probe [--root DIR]
    sessions.py launch NAME --root DIR --mode background|terminal [--permission-mode MODE] [--model M]
                       [--effort E] -- PROMPT
    sessions.py status --root DIR [NAME ...]
    sessions.py watch [NAME ...] --root DIR --owner LEAD [--known NAME=STATE ...] [--notify]
                      [--interval SEC] [--max-polls N] [--rotate-context N]
    sessions.py respawn NAME --root DIR

protocol/lead.md, «Запуск сессий». DIR is the project root, the main checkout with
`.claude/omixflow/flow.yaml`: the harness takes CLAUDE.md, `.mcp.json`, flow.yaml and the
project settings from the working directory, and the script sets it for the child process,
so the lead runs one plain command without `cd`. `claude agents` lists the sessions of the
whole machine; status, watch and respawn see only those whose cwd is DIR or under it
(a task session moves to `.claude/worktrees/{id}` after Start). Names are SendMessage
addresses for the whole machine, so launch refuses a name any active session holds.

`probe`: `background` (`--bg` in `claude --help`), `terminal` (osascript present), the
Claude Code version; with --root also `bg_isolation`: $CLAUDE_BG_ISOLATION, else
`worktree.bgIsolation` of `.claude/settings.local.json`, `.claude/settings.json`, the user
settings. A background session that has not entered a worktree writes the main tree with
its file tools only under `bgIsolation: none`. Exit 0; no `claude`: exit 3.

`launch`: the permission mode is MODE, else the lead's own one, the last `permissionMode`
of its transcript (`{projects}/*/{session}.jsonl`, session from $CLAUDE_CODE_SESSION_ID),
else no flag and the session inherits `defaultMode` (`permission_mode: null`). A session in
another permission mode than the lead's prompts where the lead's would not, and one in
another class holds cross-session messages for its user's approval. The model is M, else
the project's `models.orchestrator`, else `models.strong` (`model_source`: flag, config):
always passed — without `--model` a background session ran on its parent's model or the
harness default, not on `model` of the user settings (SwAIS T-10, T-12…T-14: Fable under
`"model": "opus"`, Fable at about 1.8 times Opus's price); `claude respawn` keeps the model of
the launch (checked on Claude Code 2.1.302). `{model}` in PROMPT becomes the model, so the
session learns what it was launched on (`/omixflow:develop … --model={model}`: state.yaml
`model_requested`, the cost line flags a session that runs on another). The effort is E, else
the project's `effort.orchestrator`, else xhigh (`effort_source`: flag, config): always passed
too — without `--effort` the session takes the level the user settings keep for its model,
else the model's default (medium on Opus 5.5, which ignores a top-level `effortLevel`);
`claude --bg --effort` and `claude respawn` keep it (checked on Claude Code 2.1.303). The
agents' effort is their frontmatter's (protocol/tiers.md, «Effort агентов»). Background:
prints `{"name", "mode", "id", "permission_mode", "model", "model_source", "effort",
"effort_source"}`, exit 0. The harness may add a suffix to a
taken name (`T-18 (2)`): exit 3 with the `id` and `actual_name` it got. Terminal: opens a
Terminal window with `cd DIR && claude -n NAME … PROMPT`, exit 0; no osascript, or it
failed or timed out: the command for the developer, exit 4 (check whether a window opened).

`status`: `{name, id, kind, status, state, cwd, limited, limited_until}` of the project's sessions,
oldest first; `limited` — the session's last model reply is the account's usage limit,
`limited_until` — its reset (UTC; null without one or without a limit). A reset in the past with
`limited: true` — the session has not answered since: it waits for an `advisory`.

`watch`: polls until a named session needs attention, then prints `{"events": [{"name",
"state", "id"}], "known": {NAME: STATE}}`, exit 0. A permission dialog or a question to the
developer gives no idle notice, only the session status `waiting`. Not `state: blocked`:
the harness sets it on a session that ended its turn waiting for a message too (T-18:
«Жду decision» — `idle`, `blocked`). A session that left the active list is `stopped`
(`status: null`) or `absent` (not listed). A session whose last model reply is the account's
usage limit is `limited` (with `resets_at`; `known` keeps it as `limited@{resetsAt}`, so a new
limit after the advisory is a new event), an event only after its reset plus a minute; while the
lead itself is limited — its own transcript ends with a limit not yet reset, or a watched session
is in one and none has replied since — no event comes out at all: the lead an event wakes then is
limited too. An event is a change into one of these, against
--known and the previous poll; pass `known` of the output to the next watch. One watch per
LEAD and project: a new one ends the previous (its pid in the git directory of DIR,
`omixflow-sessions/watch-{LEAD}.pid`), which prints `{"superseded": true}` and exits 5.
--notify: a macOS notification per event when osascript is present. --max-polls reached
without an event: exit 1. `claude agents` failing three polls in a row: exit 3.
--rotate-context N: the lead's own context — its last model request (input, cache write and
cache read) in its transcript ($CLAUDE_CODE_SESSION_ID) — above N is the event `{"name": LEAD,
"state": "rotate", "context"}`, once per lead session (`known` keeps `LEAD=rotate@{session}`;
`/clear` gives the lead a new one) and not while the lead is limited: every request of the lead
re-reads that context, a lead after `/clear` starts at ~100k (protocol/lead.md, «Смена лида»).
0, the default: no such event; without $CLAUDE_CODE_SESSION_ID or the lead's transcript there is
none either, silently. Without NAME (a lead with no background sessions: terminal mode, or all
of them done) the watch is for this event alone: --rotate-context above 0 is required, and
`claude agents` is not polled.

`respawn`: `claude respawn` of the latest stopped project session named NAME: the
conversation is kept, the name stays, the socket is new. A name any active session holds is
refused (exit 3): respawn would restart it in the middle of its work, or give a second
session the same address. status, watch and respawn check DIR as launch does.

$OMIXFLOW_CLAUDE and $OMIXFLOW_OSASCRIPT replace the `claude` and `osascript` binaries
(tests). Errors: JSON with `error`, exit 3; usage errors: exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

NO_EVENT = 1
USAGE = 2
REFUSED = 3
DEVELOPER = 4
SUPERSEDED = 5
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SESSION_RE = re.compile(r"^[A-Za-z0-9-]+$")
BACKGROUNDED_RE = re.compile(r"backgrounded\s*·\s*(\S+)\s*·\s*(.+?)\s*$", re.M)
ATTENTION = ("waiting", "stopped", "absent", "limited")
LIMIT_GRACE = 60      # seconds after `resetsAt` before a limited session counts as an event
TAIL_BYTES = 262144   # the end of a transcript read for its last model reply
FAILED_POLLS = 3
MIN_INTERVAL = 1.0


class SessionsError(Exception):
    def __init__(self, message: str, **extra: Any):
        super().__init__(message)
        self.extra = extra


class UsageError(Exception):
    pass


def claude() -> str:
    return os.environ.get("OMIXFLOW_CLAUDE", "claude")


def osascript() -> Optional[str]:
    return shutil.which(os.environ.get("OMIXFLOW_OSASCRIPT", "osascript"))


def run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SessionsError(f"{cmd[0]}: {type(e).__name__}: {e}") from e


def agents() -> List[Dict[str, Any]]:
    res = run([claude(), "agents", "--json", "--all"])
    if res.returncode != 0:
        raise SessionsError(f"claude agents: код {res.returncode}: {res.stderr.strip()[-300:]}")
    try:
        data = json.loads(res.stdout)
    except ValueError as e:
        raise SessionsError(f"claude agents: не JSON: {e}") from e
    if not isinstance(data, list):
        raise SessionsError("claude agents: не список")
    return [x for x in data if isinstance(x, dict)]


def started(entry: Dict[str, Any]) -> int:
    try:
        return int(entry.get("startedAt") or 0)
    except (TypeError, ValueError):
        return 0


def active(entry: Dict[str, Any]) -> bool:
    return entry.get("status") is not None


def under(entry: Dict[str, Any], root: Path) -> bool:
    cwd = entry.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return False
    path = os.path.realpath(cwd)
    base = os.path.realpath(root)
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def project(entries: List[Dict[str, Any]], root: Path) -> List[Dict[str, Any]]:
    return [e for e in entries if under(e, root)]


def last_reply(log: Path) -> Optional[Dict[str, Any]]:
    """The last assistant record of a transcript (its end only: transcripts run to megabytes)."""
    try:
        with log.open("rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("type") == "assistant":
            message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            if message.get("model") == "<synthetic>" and not rec.get("isApiErrorMessage"):
                continue    # «No response requested.» after an interruption: no reply of the model
            return rec
    return None


NO_RESET = -1         # a limit record without `resetsAt`: the event comes at once, `resets_at: null`


def reply_state(session: Any) -> Optional[Dict[str, Any]]:
    """The last model reply of SESSION's transcript: `{"kind": "limit", "resets", "at"}` for the
    account's usage limit — the harness writes it as an API-error record with `error:
    rate_limit`, `apiError: usage_limit_reached` and `quotaLimits` (`status: rejected`,
    `resetsAt`; NO_RESET when it names none; a plain 429 without them is no account limit) —
    `{"kind": "error", "at"}` for another API error, `{"kind": "ok", "at"}` for a real reply;
    None without a transcript. SwAIS 2026-10-17: the weekly limit stopped the lead and every task
    session at once, and after the reset nobody woke them for ~16 h."""
    if not isinstance(session, str) or not SESSION_RE.match(session):
        return None
    for log in config_dir().joinpath("projects").glob(f"*/{session}.jsonl"):
        rec = last_reply(log)
        if not rec:
            return None
        at = str(rec.get("timestamp") or "")
        if not rec.get("isApiErrorMessage"):
            return {"kind": "ok", "at": at}
        quota = rec.get("quotaLimits") if isinstance(rec.get("quotaLimits"), dict) else {}
        if rec.get("apiError") != "usage_limit_reached" and quota.get("status") != "rejected":
            return {"kind": "error", "at": at}
        for holder in (quota, (rec.get("apiErrorParams") or {}).get("rate_limit_info")):
            if isinstance(holder, dict) and isinstance(holder.get("resetsAt"), (int, float)):
                return {"kind": "limit", "resets": int(holder["resetsAt"]), "at": at}
        return {"kind": "limit", "resets": NO_RESET, "at": at}
    return None


def session_context(session: Any) -> Optional[int]:
    """The context of SESSION's last model request (input, cache write and cache read): what each
    of its next requests re-reads. None without a transcript or without usage (an API error)."""
    if not isinstance(session, str) or not SESSION_RE.match(session):
        return None
    for log in config_dir().joinpath("projects").glob(f"*/{session}.jsonl"):
        rec = last_reply(log) or {}
        message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        size = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                      "cache_read_input_tokens"))
        return size or None
    return None


def limit_of(entry: Dict[str, Any]) -> Optional[int]:
    """`resetsAt` (or NO_RESET) when the session's last model reply is the account's usage limit."""
    state = reply_state(entry.get("sessionId"))
    return state["resets"] if state and state["kind"] == "limit" else None


def pending(resets: Optional[int]) -> bool:
    """A limit not yet reset (plus the grace minute)."""
    return resets is not None and resets != NO_RESET and time.time() < resets + LIMIT_GRACE


def account_limited(entries: List[Dict[str, Any]], names: List[str]) -> bool:
    """Is the lead limited now? Its own transcript (the owner's session, $CLAUDE_CODE_SESSION_ID)
    ends with a limit not yet reset; or, without that, a watched session is in such a limit and
    none of the watched sessions has replied since — the limit is the account's, and the lead an
    event wakes would hit it too. A session that replied after the limit record (a per-model limit,
    extra usage, a session the developer continues by hand) lifts the hold: one limited session
    must not silence the others' events for days. `busy` is no evidence: a session runs a long
    command under the limit too."""
    own = reply_state(os.environ.get("CLAUDE_CODE_SESSION_ID"))
    if own and own["kind"] == "limit":
        return pending(own["resets"])
    states = [reply_state(e.get("sessionId")) for e in entries if e.get("name") in names and active(e)]
    states.append(own)          # the lead's own reply after the limit records: it can act (a per-model limit)
    limits = [s for s in states if s and s["kind"] == "limit" and pending(s["resets"])]
    if not limits:
        return False
    newest = max(s["at"] for s in limits)
    return not any(s and s["kind"] == "ok" and s["at"] > newest for s in states)


def iso(epoch: Optional[int]) -> Optional[str]:
    if epoch is None or epoch == NO_RESET:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def condition(entries: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    """The state the lead acts on for NAME, with the entry it comes from."""
    named = sorted((e for e in entries if e.get("name") == name), key=started, reverse=True)
    live = [e for e in named if active(e)]
    if live:
        status = str(live[0].get("status"))
        # a working session is past the limit; a waiting one (a dialog, a question) needs the developer
        resets = limit_of(live[0]) if status not in ("busy", "waiting") else None
        if resets is not None:
            return {"name": name, "state": "limited", "id": live[0].get("id"), "resets_at": iso(resets),
                    "resets": resets}
        return {"name": name, "state": status, "id": live[0].get("id")}
    if named:
        return {"name": name, "state": "stopped", "id": named[0].get("id")}
    return {"name": name, "state": "absent", "id": None}


def config_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(config).expanduser() if config else Path.home() / ".claude"


def lead_mode() -> Optional[str]:
    """The permission mode of this session, from its transcript; None when unknown."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session or not SESSION_RE.match(session):
        return None
    mode = None
    for log in config_dir().joinpath("projects").glob(f"*/{session}.jsonl"):
        try:
            with log.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"permissionMode"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(rec, dict) and isinstance(rec.get("permissionMode"), str):
                        mode = rec["permissionMode"]
        except OSError:
            continue
    return mode


def bg_isolation(root: Path) -> Optional[str]:
    """$CLAUDE_BG_ISOLATION, else `worktree.bgIsolation`: local, project, user settings."""
    env = os.environ.get("CLAUDE_BG_ISOLATION")
    if env:
        return env
    for path in (root / ".claude" / "settings.local.json", root / ".claude" / "settings.json",
                 config_dir() / "settings.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        worktree = data.get("worktree") if isinstance(data, dict) else None
        value = worktree.get("bgIsolation") if isinstance(worktree, dict) else None
        if isinstance(value, str):
            return value
    return None


def git(root: Path, *args: str) -> Optional[str]:
    try:
        res = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def project_root(given: str) -> Path:
    root = Path(given).expanduser()
    if not root.is_dir():
        raise SessionsError(f"корень {root}: не каталог")
    if not (root / ".claude" / "omixflow" / "flow.yaml").is_file():
        raise SessionsError(f"корень {root}: нет .claude/omixflow/flow.yaml — не корень проекта OMIXFlow")
    git_dir = git(root, "rev-parse", "--absolute-git-dir")
    common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir and common and os.path.realpath(git_dir) != os.path.realpath(common):
        raise SessionsError(f"корень {root}: связанный worktree, сессии запускаются из основного дерева")
    return root


def applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmd_probe(ns: argparse.Namespace) -> Dict[str, Any]:
    help_out = run([claude(), "--help"])
    version = run([claude(), "--version"]).stdout.strip().split(" ")[0] or None
    out: Dict[str, Any] = {"background": "--bg" in help_out.stdout, "terminal": osascript() is not None,
                           "version": version}
    if ns.root:
        out["bg_isolation"] = bg_isolation(Path(ns.root).expanduser())
    return out


def cmd_launch(ns: argparse.Namespace) -> Dict[str, Any]:
    root = project_root(ns.root)
    taken = [e for e in agents() if e.get("name") == ns.name and active(e)]
    if taken:
        raise SessionsError(f"имя {ns.name} занято активной сессией "
                            f"(id {taken[0].get('id')}, {taken[0].get('cwd')})")
    mode = ns.permission_mode or lead_mode()
    loaded: List[Dict[str, Any]] = []

    def config() -> Dict[str, Any]:     # read once, and only when a flag leaves a value to it
        if not loaded:
            loaded.append(lib.load_config(root))
        return loaded[0]

    if ns.model:
        model, source = ns.model, "flag"
    else:
        try:
            model, source = lib.orchestrator_model(config()), "config"
        except lib.OmixflowError as e:
            raise SessionsError(f"модель сессии: {e}; передай --model") from e
    if ns.effort:
        effort, effort_source = ns.effort, "flag"
    else:
        try:
            effort, effort_source = lib.orchestrator_effort(config()), "config"
        except lib.OmixflowError as e:
            raise SessionsError(f"effort сессии: {e}; передай --effort") from e
    flags = (["--permission-mode", mode] if mode else []) + ["--model", model, "--effort", effort]
    ns.prompt = ns.prompt.replace("{model}", model)
    out: Dict[str, Any] = {"name": ns.name, "mode": ns.mode, "permission_mode": mode,
                           "model": model, "model_source": source, "effort": effort, "effort_source": effort_source}
    if ns.mode == "background":
        res = run([claude(), "--bg", "--name", ns.name, *flags, ns.prompt], cwd=root)
        if res.returncode != 0:
            raise SessionsError(f"claude --bg: код {res.returncode}: {(res.stderr or res.stdout).strip()[-300:]}")
        m = BACKGROUNDED_RE.search(res.stdout)
        if m and m.group(2) != ns.name:
            raise SessionsError(f"харнесс запустил сессию под именем {m.group(2)!r}: имя {ns.name} занято",
                                id=m.group(1), actual_name=m.group(2))
        sid = m.group(1) if m else condition(project(agents(), root), ns.name)["id"]
        if not sid:
            raise SessionsError(f"claude --bg не назвал id, и {ns.name} нет в claude agents: "
                                f"{res.stdout.strip()[-200:]}")
        out["id"] = sid
        return out
    shell = f"cd {shlex.quote(str(root))} && " + " ".join(
        shlex.quote(a) for a in [claude(), "-n", ns.name, *flags, ns.prompt])
    out["command"] = shell
    tool = osascript()
    out["opened"] = False
    if not tool:
        out["reason"] = "osascript нет: окно открывает разработчик"
        return out
    try:
        script = f'tell application "Terminal" to do script {applescript_string(shell)}'
        res = run([tool, "-e", script], timeout=30)
    except SessionsError as e:
        out["reason"] = f"{e}: проверь, открылось ли окно, прежде чем запускать снова"
        return out
    if res.returncode != 0:
        out["reason"] = f"osascript: код {res.returncode}: {res.stderr.strip()[-200:]}"
        return out
    out["opened"] = True
    return out


def known_state(c: Dict[str, Any]) -> str:
    """The state as `known` keeps it: a limit with its reset (`limited@{resetsAt}`), so a new limit
    after the advisory is a new event, not a repeat of the old one."""
    return f"limited@{c['resets']}" if c["state"] == "limited" else c["state"]


def cmd_status(ns: argparse.Namespace) -> List[Dict[str, Any]]:
    keys = ("name", "id", "kind", "status", "state", "cwd")
    rows = []
    for e in sorted(project(agents(), project_root(ns.root)), key=started):
        if ns.names and e.get("name") not in ns.names:
            continue
        row = {k: e.get(k) for k in keys}
        resets = limit_of(e) if active(e) and e.get("status") not in ("busy", "waiting") else None
        row["limited"] = resets is not None
        row["limited_until"] = iso(resets)
        rows.append(row)
    return rows


def lock_path(root: Path, owner: str) -> Optional[Path]:
    common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common) / "omixflow-sessions" / f"watch-{owner}.pid" if common else None


def supersede(lock: Path) -> None:
    """End the previous watch of this lock, if it is still a sessions.py watch."""
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        return
    if pid == os.getpid():
        return
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    except OSError:
        return
    if "sessions.py" in cmd and " watch" in cmd:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def notify(events: List[Dict[str, Any]]) -> None:
    tool = osascript()
    if not tool:
        return
    for e in events:
        text = (f"{e['name']} ждёт тебя: claude attach {e['name']}" if e["state"] == "waiting"
                else f"{e['name']}: лимит сброшен, продолжить" if e["state"] == "limited"
                else f"{e['name']}: контекст {e['context'] // 1000}k — смена лида: /clear, затем "
                     f"/omixflow:lead (фоновый лид — claude attach {e['name']})" if e["state"] == "rotate"
                else f"{e['name']}: сессия {e['state']}")
        try:
            subprocess.run([tool, "-e", f"display notification {applescript_string(text)} "
                                        f"with title {applescript_string('OMIXFlow')}"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


def cmd_watch(ns: argparse.Namespace) -> Dict[str, Any]:
    seen: Dict[str, str] = {}
    for item in ns.known or []:
        name, sep, state = item.partition("=")
        if not sep or not NAME_RE.match(name) or not state:
            raise UsageError(f"--known {item!r}: нужно ИМЯ=СОСТОЯНИЕ")
        seen[name] = state
    if ns.interval < 0 or ns.rotate_context < 0 or not NAME_RE.match(ns.owner):
        raise UsageError("--interval и --rotate-context не меньше 0, --owner — имя лида")
    if not ns.names and not ns.rotate_context:
        raise UsageError("watch без имён — только сигнал смены лида: нужен --rotate-context больше 0")
    interval = ns.interval if ns.max_polls else max(ns.interval, MIN_INTERVAL)
    root = project_root(ns.root)

    def superseded(_signum, _frame):
        print(json.dumps({"events": [], "superseded": True}, ensure_ascii=False))
        sys.exit(SUPERSEDED)

    signal.signal(signal.SIGTERM, superseded)  # before the pid is visible to the next watch
    lock = lock_path(root, ns.owner)
    if lock:
        supersede(lock)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()))
    try:
        polls = failures = 0
        while True:
            try:
                entries = project(agents(), root) if ns.names else []
                failures = 0
            except SessionsError:
                failures += 1
                if failures >= FAILED_POLLS:
                    raise
                entries = None
            if entries is not None:
                now = [condition(entries, name) for name in ns.names]
                # a limited session is an event only after its reset: a lead woken before it hits the
                # same limit and the event is lost; while the lead itself is limited, no event at all
                hold = account_limited(entries, ns.names)
                now = [c for c in now if not (c["state"] == "limited" and pending(c["resets"]))]
                events = [] if hold else [{k: v for k, v in c.items() if k != "resets"} for c in now
                                          if c["state"] in ATTENTION and seen.get(c["name"]) != known_state(c)]
                if not hold:
                    seen.update({c["name"]: known_state(c) for c in now})
                own = os.environ.get("CLAUDE_CODE_SESSION_ID")
                if not hold and ns.rotate_context and seen.get(ns.owner) != f"rotate@{own}":
                    size = session_context(own)
                    if size and size > ns.rotate_context:
                        events.append({"name": ns.owner, "state": "rotate", "context": size})
                        seen[ns.owner] = f"rotate@{own}"
                if events:
                    if ns.notify:
                        notify(events)
                    return {"events": events, "known": seen}
            polls += 1
            if ns.max_polls and polls >= ns.max_polls:
                return {"events": [], "known": seen}
            time.sleep(interval)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            if lock and lock.read_text().strip() == str(os.getpid()):
                lock.unlink()
        except OSError:
            pass


def cmd_respawn(ns: argparse.Namespace) -> Dict[str, Any]:
    root = project_root(ns.root)
    entries = agents()
    live = [e for e in entries if e.get("name") == ns.name and active(e)]
    if live:  # names are machine-wide addresses, like in launch
        raise SessionsError(f"имя {ns.name} занято активной сессией (id {live[0].get('id')}, "
                            f"{live[0].get('cwd')}): respawn перезапустил бы её посреди работы "
                            f"или дал бы второй адрес")
    named = sorted((e for e in project(entries, root) if e.get("name") == ns.name), key=started, reverse=True)
    if not named:
        raise SessionsError(f"сессии {ns.name} проекта {root} нет в claude agents --all")
    sid = named[0].get("id")
    res = run([claude(), "respawn", str(sid)])
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip()[-300:]
        raise SessionsError(f"claude respawn {sid}: код {res.returncode}: {tail}")
    return {"name": ns.name, "id": sid, "respawned": True}


class Parser(argparse.ArgumentParser):
    def error(self, message: str):  # usage errors as JSON, exit 2, like the rest
        print(json.dumps({"error": message}, ensure_ascii=False))
        sys.exit(USAGE)


def parser() -> argparse.ArgumentParser:
    ap = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    p = sub.add_parser("probe")
    p.add_argument("--root", default=None)
    p = sub.add_parser("launch")
    p.add_argument("name")
    p.add_argument("--root", required=True)
    p.add_argument("--mode", required=True, choices=("background", "terminal"))
    p.add_argument("--permission-mode", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None, choices=lib.EFFORT_LEVELS)
    p.add_argument("prompt")
    p = sub.add_parser("status")
    p.add_argument("names", nargs="*")
    p.add_argument("--root", required=True)
    p = sub.add_parser("watch")
    p.add_argument("names", nargs="*")
    p.add_argument("--root", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--known", nargs="+", action="extend")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--interval", type=float, default=20.0)
    p.add_argument("--max-polls", type=int, default=0)
    p.add_argument("--rotate-context", type=int, default=0)
    p = sub.add_parser("respawn")
    p.add_argument("name")
    p.add_argument("--root", required=True)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ns = parser().parse_args(argv)
    for name in [getattr(ns, "name", None), *(getattr(ns, "names", None) or [])]:
        if name is not None and not NAME_RE.match(name):
            print(json.dumps({"error": f"имя сессии {name!r}: буквы, цифры, '.', '_', '-'"}, ensure_ascii=False))
            return USAGE
    try:
        result = {"probe": cmd_probe, "launch": cmd_launch, "status": cmd_status,
                  "watch": cmd_watch, "respawn": cmd_respawn}[ns.cmd](ns)
    except UsageError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return USAGE
    except SessionsError as e:
        print(json.dumps({"error": str(e), **e.extra}, ensure_ascii=False))
        return REFUSED
    print(json.dumps(result, ensure_ascii=False))
    if ns.cmd == "launch" and ns.mode == "terminal" and not result.get("opened"):
        return DEVELOPER
    if ns.cmd == "watch" and not result["events"]:
        return NO_EVENT
    return 0


if __name__ == "__main__":
    sys.exit(main())
