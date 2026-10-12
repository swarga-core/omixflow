#!/usr/bin/env python3
"""Mutation probe of a test in one call: baseline, mutate, run, restore, verify
(agents/coder.md, «Mutation-check your tests»).

    probe.py run --root DIR --test NAME --file PATH --cmd 'COMMAND'
                 (--replace OLD --with NEW | --patch FILE)
                 [--check 'COMMAND'] [--rebuild 'COMMAND'] [--timeout SEC] [--no-baseline]
                 [--tail N] [--json]
    probe.py batch --root DIR --spec FILE [--rebuild 'COMMAND'] [--timeout SEC] [--tail N] [--json]
    probe.py restore --root DIR --file PATH

A new test is verified by mutation: break the behaviour it guards, see the test go red,
restore the code. By hand that is four or five tool calls per test, each a model request
at the agent's full context; `run` does it in one call and prints the report's own
MUTATIONS line. The recipe is the one of the runs of 0.4–0.7:

1. baseline: `--cmd` runs once on the unmutated tree; a test that is not green there
   proves nothing (a typo in the command, a filter that matches nothing, exit 127) — the
   probe is not run (`--no-baseline` skips this when the same command was just green);
2. copy PATH to PATH.orig next to it — never `git checkout` or `git restore`, the
   uncommitted step would go with the probe;
3. mutate: `--replace OLD --with NEW` replaces one literal occurrence of OLD in PATH (it
   must occur exactly once; `\\n`, `\\t` stand for a newline and a tab, `\\\\` for one
   backslash; line endings are kept as they are), or `--patch FILE` applies a unified
   diff with `git apply` — the diff may touch only PATH;
4. `--check` (typecheck or build of the mutant, optional) runs first: a mutant that does
   not compile is no probe — `no probe possible`, exit 3;
5. `--cmd` runs the test under `--timeout` (default 240 s per command: the baseline,
   `--check`, the test and `--rebuild` each get it, so one call may take longer than the
   Bash tool's 600 s); RED is a non-zero exit code or a timeout (an endless mutant is
   caught, the line says `timed out`). Call the script with the Bash timeout at 600000 ms;
   a call expected to run past nine minutes — a slow suite, several builds, `run` or
   `batch` alike — goes through `gate.py start {label}-probes --root DIR -- 'python3 …
   probe.py …'` and `gate.py poll … --timeout 540`, the lines are read from its log;
6. restore with `cp PATH.orig PATH` and remove the copy: `cp` writes a new modification
   time, `mv` would bring back the old one and a build that decides by it would keep
   the mutant (MEW-6). The mutant is dated 1 s ahead of the original and the restored file
   1 s ahead of the mutant: a build that rebuilds when the input is newer than its
   output (make, MSBuild, tsc -b) sees both changes, and a cache keyed by the mtime's
   second and the size (`__pycache__`) does not serve the original for a mutant of the
   same length. The restored bytes are compared with the copy, and `git diff -- PATH`
   with what it was before the probe. SIGTERM and SIGINT (a Bash timeout) kill the
   running command with its process group and restore too, exit 128+signal; a copy left
   by a killed run blocks the next probe — `probe.py restore` puts the file back;
7. `--rebuild` (the lang adapter's full rebuild, optional) runs after the restore: an
   incremental cache may still hold a mutant. With `run` it belongs on the last probe of
   a series; `batch` runs it once after all probes.

Outcomes and exit codes:
- RED (the test caught the mutant) — exit 0;
- GREEN (false-green: strengthen the test and probe again) — exit 1;
- `no probe possible` — exit 3: the mutant fails `--check` (does not compile); this is
  the only reason the script writes into a MUTATIONS line;
- the probe was not run — exit 2, a `PROBE NOT RUN` line that is not a MUTATIONS line:
  the baseline is red, OLD is missing or ambiguous, the patch does not apply or touches
  another file, a copy is left from an unfinished probe, the restore does not match
  (the diff is kept for the agent to look at), `--rebuild` failed. Fix the call and run
  again; nothing of the probe stays in the tree (except the kept diff of a failed restore).

The report lines (the last lines of the output; in `batch` the tails of RED probes are
left out, the summary goes to stderr):

    - {NAME} ← {what was mutated} → RED
    - {NAME} ← {what was mutated} → GREEN (false-green: strengthen the test and probe again)
    - {NAME} — no probe possible: {why}
    PROBE NOT RUN: {NAME} — {why}

`batch` runs a list of probes from a JSON file — `[{"test", "file", "cmd", "replace",
"with" | "patch", "check"}]` — after checking the whole list: one after another, the
baseline of a command once, the rebuild once after the last mutant; exit 1 when any
probe is GREEN (never hidden), else 2 when any was not run, else 3 when any is `no probe
possible`, else 0. Paths are absolute or relative to DIR; `--json` prints one object per
probe.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RED, GREEN, NOT_RUN, NO_PROBE = 0, 1, 2, 3
ORIG = ".orig"
DEFAULT_TIMEOUT = 240.0        # per command (baseline, --check, test, --rebuild); a long call goes through gate.py
MTIME_STEP = 1                 # seconds the mutant and the restore are dated ahead (see date_ahead)
_pending: List[Tuple[Path, Path]] = []   # (file, backup) of the probe in progress, for the signal handler
_child: Optional[subprocess.Popen] = None   # the command running now, killed with its group on a signal

# The reasons of a probe that was not run, as they appear in `PROBE NOT RUN` lines; report.py
# bounces a `no probe possible` line that carries one of them (the agent pasted an input error
# as a reason). Every NotRun message below contains one of these phrases.
NOT_RUN_PHRASES = ("OLD occurs ", "needs exactly 1", "patch does not apply", "the patch touches",
                   "left unfinished", "is not green without the mutant", "differs from before the probe",
                   "--rebuild after the restore failed", "file not found: ", "no mutation: give",
                   "nothing to restore")


def unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in "nt\\":
            out.append({"n": "\n", "t": "\t", "\\": "\\"}[text[i + 1]])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def git(root: Path, *args: str) -> Optional[bytes]:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            return
        try:
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            continue


def run_cmd(cmd: str, root: Path, tail: int, timeout: float) -> Dict[str, Any]:
    """A shell command in ROOT in its own process group; a timeout, SIGTERM or SIGINT kills
    the group (the harness killing the Bash call must not leave an endless mutant running)."""
    global _child
    proc = subprocess.Popen(cmd, shell=True, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    _child = proc
    try:
        out, _ = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        kill_group(proc)
        out, _ = proc.communicate()
        timed_out = True
    finally:
        _child = None
    text = (out or b"").decode("utf-8", errors="replace")
    lines = text.splitlines()
    return {"exit": proc.returncode, "timed_out": timed_out,
            "tail": "\n".join(lines[-tail:]) if tail > 0 else ""}


def resolve(root: Path, given: str) -> Path:
    p = Path(given)
    return p if p.is_absolute() else root / p


def patch_paths(root: Path, patch: Path) -> List[str]:
    out = git(root, "apply", "--numstat", "-z", str(patch))
    if out is None:
        return []
    return [rec.split("\t")[-1] for rec in out.decode("utf-8", errors="replace").split("\0") if rec.strip()]


class NotRun(Exception):
    """The probe could not be run: an input error, nothing to do with the test."""


def mutate(root: Path, path: Path, replace: Optional[str], with_: Optional[str], patch: Optional[str]) -> str:
    """Apply the mutation; returns its description; NotRun when the call is wrong."""
    if patch:
        patch_path = resolve(root, patch)
        if not patch_path.is_file():
            raise NotRun(f"patch not found: {patch_path}")
        touched = patch_paths(root, patch_path)
        rel = os.path.relpath(path, root)
        if touched != [rel]:
            raise NotRun(f"the patch touches {touched or 'nothing readable'}, a probe mutates only --file {rel}")
        proc = subprocess.run(["git", "-C", str(root), "apply", str(patch_path)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise NotRun(f"patch does not apply: {(proc.stderr or proc.stdout).strip()[-300:]}")
        return f"patch {patch_path.name}"
    if replace is None or with_ is None:
        raise NotRun("no mutation: give --replace OLD --with NEW or --patch FILE")
    old, new = unescape(replace).encode("utf-8"), unescape(with_).encode("utf-8")
    data = path.read_bytes()   # bytes: line endings and encoding stay as they are
    n = data.count(old)
    if n != 1:
        raise NotRun(f"OLD occurs {n} times in {path.name}, needs exactly 1: {old[:80]!r}")
    path.write_bytes(data.replace(old, new, 1))
    return f"{path.name}: {old.decode('utf-8', 'replace').strip()[:60]!r} → {new.decode('utf-8', 'replace').strip()[:60]!r}"


def date_ahead(path: Path, after: float) -> float:
    """Give PATH a modification time later than AFTER and than now, in a different second.
    Builds that rebuild when an input is newer than its output (make, MSBuild, tsc -b, cargo)
    must see the mutant and then the restored file as newer than what the previous run built;
    caches keyed by (mtime in seconds, size) — Python's __pycache__ — must see a different
    second. Dating backwards (an earlier draft) made every such build keep the original: a
    false GREEN on each probe. The drift is two seconds per probe of the same file (a
    series of thirty leaves it a minute ahead): builds rebuild that file until the clock
    catches up, and GNU make may warn about clock skew — harmless, and a one-second step
    keeps it small."""
    stamp = max(time.time(), after) + MTIME_STEP
    os.utime(path, (stamp, stamp))
    return stamp


def restore_file(path: Path, backup: Path) -> None:
    """cp, not mv: a fresh modification time, later than the mutant's (MEW-6)."""
    try:
        mutant_mtime = os.stat(path).st_mtime
    except OSError:
        mutant_mtime = 0.0
    path.write_bytes(backup.read_bytes())
    date_ahead(path, mutant_mtime)
    backup.unlink()


def _on_signal(signum, _frame):
    """A Bash timeout or Ctrl-C: kill the running command with its group, put the file back,
    leave with 128+signal — never through the `finally` of a probe in progress (its restore
    would find the backup gone) and never with the GREEN code."""
    if _child is not None:
        kill_group(_child)
    for path, backup in list(_pending):
        try:
            if backup.exists():
                restore_file(path, backup)
        except OSError:
            pass
    _pending.clear()
    for stream in (sys.stdout, sys.stderr):    # the lines of probes already finished stay printed
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(128 + signum)


def probe(root: Path, name: str, file: str, cmd: str, replace: Optional[str] = None, with_: Optional[str] = None,
          patch: Optional[str] = None, check: Optional[str] = None, rebuild: Optional[str] = None,
          tail: int = 20, timeout: float = DEFAULT_TIMEOUT, baseline: bool = True,
          baseline_cache: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    path = resolve(root, file)
    result: Dict[str, Any] = {"test": name, "file": str(path), "outcome": None, "mutation": None,
                              "test_exit": None, "tail": "", "reason": None, "restored": None, "ran": False}

    def not_run(why: str, tail_text: str = "") -> Dict[str, Any]:
        result.update(outcome="not run", reason=why, tail=tail_text)
        return result

    if not path.is_file():
        return not_run(f"file not found: {path}")
    backup = path.with_name(path.name + ORIG)
    if backup.exists():
        return not_run(f"{backup.name} exists: a probe was left unfinished — `probe.py restore --root {root} "
                       f"--file {path}` puts the file back, then run again")
    if baseline:
        cache = baseline_cache if baseline_cache is not None else {}
        base = cache.get(cmd) or run_cmd(cmd, root, tail, timeout)
        cache[cmd] = base
        if base["timed_out"] or base["exit"] != 0:
            return not_run("the test is not green without the mutant (wrong command, filter or a failing test)",
                           base["tail"])
    before_diff = git(root, "diff", "--", str(path))
    original = path.read_bytes()
    original_mtime = os.stat(path).st_mtime    # may already be ahead of now after an earlier restore
    path.with_name(path.name + ORIG).write_bytes(original)
    _pending.append((path, backup))
    try:
        try:
            result["mutation"] = mutate(root, path, replace, with_, patch)
        except NotRun as e:
            return not_run(str(e))
        date_ahead(path, original_mtime)    # newer than the original and everything the baseline built
        result["ran"] = True
        if check:
            chk = run_cmd(check, root, tail, timeout)
            if chk["timed_out"] or chk["exit"] != 0:
                result.update(outcome="no probe possible", reason="the mutant does not pass --check (does not compile)",
                              tail=chk["tail"])
                return result
        test = run_cmd(cmd, root, tail, timeout)
        result.update(test_exit=test["exit"], tail=test["tail"],
                      outcome="RED" if (test["exit"] != 0 or test["timed_out"]) else "GREEN")
        if test["timed_out"]:
            result["mutation"] += f" (timed out after {timeout:.0f} s)"
        return result
    finally:
        if backup.exists():        # gone only when the signal handler restored first
            restore_file(path, backup)
        _pending[:] = [p for p in _pending if p[0] != path]
        restored_bytes = path.read_bytes() == original
        after_diff = git(root, "diff", "--", str(path))
        result["restored"] = restored_bytes and before_diff == after_diff
        if not result["restored"]:
            result.update(outcome="not run",
                          reason=f"after the restore {path.name} differs from before the probe (bytes or `git diff`); "
                                 "look at it before anything else")
        elif rebuild and result["ran"]:
            rb = run_cmd(rebuild, root, tail, timeout)
            if rb["timed_out"] or rb["exit"] != 0:
                result.update(outcome="not run", reason="--rebuild after the restore failed", tail=rb["tail"])


def line_of(r: Dict[str, Any]) -> str:
    if r["outcome"] == "RED":
        return f"- {r['test']} ← {r['mutation']} → RED"
    if r["outcome"] == "GREEN":
        return f"- {r['test']} ← {r['mutation']} → GREEN (false-green: strengthen the test and probe again)"
    if r["outcome"] == "no probe possible":
        return f"- {r['test']} — no probe possible: {r['reason']}"
    return f"PROBE NOT RUN: {r['test']} — {r['reason']}"


def code_of(r: Dict[str, Any]) -> int:
    return {"RED": RED, "GREEN": GREEN, "no probe possible": NO_PROBE}.get(str(r["outcome"]), NOT_RUN)


def emit(r: Dict[str, Any], as_json: bool, show_tail: bool) -> None:
    """Each probe's lines are flushed at once: a batch killed later keeps what was printed."""
    if as_json:
        print(json.dumps(r, ensure_ascii=False), flush=True)
        return
    if r["tail"] and show_tail:
        print(r["tail"])
    print(line_of(r), flush=True)


def cmd_run(ns: argparse.Namespace) -> int:
    root = Path(ns.root).resolve()
    r = probe(root, ns.test, ns.file, ns.cmd, ns.replace, ns.with_, ns.patch, ns.check, ns.rebuild, ns.tail,
              ns.timeout, baseline=not ns.no_baseline)
    emit(r, ns.json, show_tail=True)
    return code_of(r)


def cmd_restore(ns: argparse.Namespace) -> int:
    root = Path(ns.root).resolve()
    path = resolve(root, ns.file)
    backup = path.with_name(path.name + ORIG)
    if not backup.exists():
        print(f"probe.py: nothing to restore, {backup.name} is not there")
        return NOT_RUN
    restore_file(path, backup)
    print(f"restored {path} from {backup.name}; check `git diff -- {path.name}` shows your step's change")
    return 0


def cmd_batch(ns: argparse.Namespace) -> int:
    root = Path(ns.root).resolve()
    spec_path = resolve(root, ns.spec)
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"probe.py: spec {spec_path}: {e}", file=sys.stderr)
        return NOT_RUN
    if not isinstance(spec, list) or not all(isinstance(p, dict) for p in spec):
        print("probe.py: spec must be a JSON list of probes", file=sys.stderr)
        return NOT_RUN
    for i, p in enumerate(spec, 1):   # the whole list is checked before any probe runs
        missing = [k for k in ("test", "file", "cmd") if not p.get(k)]
        if missing:
            print(f"probe.py: probe {i}: missing {', '.join(missing)}", file=sys.stderr)
            return NOT_RUN
        if not p.get("patch") and (p.get("replace") is None or p.get("with") is None):
            print(f"probe.py: probe {i} ({p['test']}): give replace+with or patch", file=sys.stderr)
            return NOT_RUN
    results: List[Dict[str, Any]] = []
    cache: Dict[str, Dict[str, Any]] = {}
    for p in spec:
        r = probe(root, str(p["test"]), str(p["file"]), str(p["cmd"]), p.get("replace"), p.get("with"),
                  p.get("patch"), p.get("check"), None, ns.tail, ns.timeout, baseline=not ns.no_baseline,
                  baseline_cache=cache)
        results.append(r)
        emit(r, ns.json, show_tail=r["outcome"] != "RED")
    rebuild_failed = False
    if ns.rebuild and any(r["ran"] for r in results):
        rb = run_cmd(ns.rebuild, root, ns.tail, ns.timeout)
        rebuild_failed = rb["timed_out"] or rb["exit"] != 0
        if rebuild_failed:
            print(rb["tail"])
            print("REBUILD FAILED after the probes: run the gates as a full rebuild before anything else",
                  file=sys.stderr)
    counts = {k: sum(1 for r in results if r["outcome"] == k) for k in ("RED", "GREEN", "no probe possible", "not run")}
    print(f"probes: {len(results)}, RED {counts['RED']}, GREEN {counts['GREEN']}, "
          f"no probe {counts['no probe possible']}, not run {counts['not run']}"
          + (", rebuild FAILED" if rebuild_failed else ""), file=sys.stderr)
    if counts["GREEN"]:
        return GREEN
    if counts["not run"] or rebuild_failed:
        return NOT_RUN
    if counts["no probe possible"]:
        return NO_PROBE
    return RED


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--root", required=True)
    p.add_argument("--test", required=True, help="the test's name as it goes into MUTATIONS")
    p.add_argument("--file", required=True, help="the source file to mutate")
    p.add_argument("--cmd", required=True, help="the command that runs the test (shell, in --root)")
    p.add_argument("--replace", default=None)
    p.add_argument("--with", dest="with_", default=None)
    p.add_argument("--patch", default=None)
    p.add_argument("--check", default=None, help="typecheck or build of the mutant before the test")
    p.add_argument("--rebuild", default=None, help="full rebuild after the restore (last probe of a series)")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--no-baseline", action="store_true", help="skip the green run without the mutant")
    p.add_argument("--tail", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("batch")
    p.add_argument("--root", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--rebuild", default=None, help="full rebuild once, after the last probe")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--no-baseline", action="store_true")
    p.add_argument("--tail", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_batch)
    p = sub.add_parser("restore")
    p.add_argument("--root", required=True)
    p.add_argument("--file", required=True)
    p.set_defaults(fn=cmd_restore)
    ns = ap.parse_args(argv)
    if ns.cmd == "run" and not ns.patch and (ns.replace is None or ns.with_ is None):
        ap.error("give --replace OLD --with NEW or --patch FILE")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _on_signal)
    return ns.fn(ns)


if __name__ == "__main__":
    sys.exit(main())
