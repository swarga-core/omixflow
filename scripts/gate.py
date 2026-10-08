#!/usr/bin/env python3
"""Long gates in the background, waited for in short foreground polls.

    gate.py start NAME --root DIR -- CMD [ARG...]
    gate.py poll NAME --root DIR [--timeout SEC] [--tail N]

NAME labels one gate run (`step3-test`); its output, exit code and runner live in the
git directory of DIR (`{git-dir}/omixflow-gates/NAME.log`, `.exit`, `.pid`): per
worktree, never tracked, never published with the task artifacts.

`start` returns at once: CMD runs in DIR in its own session, detached from the caller,
so it survives the command that started it. A single CMD argument is a shell command
line (`a && b` works); several are an argv. A run of NAME still going is killed first,
and only the latest run may record an exit code.

`poll` waits up to --timeout seconds (default 100, under the caller's own command
timeout) for the exit code. Finished: prints `EXIT {code}` and the last --tail lines of
the output (default 40), exit 0. Still running: prints `RUNNING {seconds}s`, exit 3;
poll again. The runner died without an exit code: prints `LOST`, exit 4; start again.
Never started: exit 2.

An agent never ends its reply while a gate it started runs: its turn would end, and
nothing wakes it when the gate finishes (protocol/runtime.md, «Гейты»). One script call
with literal paths passes a worktree-isolated session, a shell loop with `$?` does not.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

RUNNING = 3
LOST = 4
POLL_INTERVAL = 2.0
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class Files(NamedTuple):
    log: Path
    exit: Path
    pid: Path


def gate_files(root: Path, name: str) -> Files:
    if not NAME_RE.match(name):
        raise lib.OmixflowError(f"имя гейта {name!r}: буквы, цифры, '.', '_', '-'")
    git_dir = lib.git(root, "rev-parse", "--absolute-git-dir")
    if not git_dir:
        raise lib.OmixflowError(f"{root}: не git-дерево, вывод гейта положить некуда")
    base = Path(git_dir) / "omixflow-gates"
    return Files(base / f"{name}.log", base / f"{name}.exit", base / f"{name}.pid")


def command_of(ns: argparse.Namespace) -> List[str]:
    if not ns.command:
        raise lib.OmixflowError("не задана команда после --")
    return ns.command


def read_runner(files: Files) -> Optional[Tuple[int, str]]:
    """(pid, run id) of the latest runner, None before the runner wrote it."""
    try:
        pid, run_id = files.pid.read_text(encoding="utf-8").split()
        return int(pid), run_id
    except (OSError, ValueError):
        return None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_previous(files: Files) -> None:
    """Kill a run of the same name that is still going: the runner leads its own process
    group (start_new_session), so the group takes the gate command down with it."""
    runner = read_runner(files)
    if not runner or files.exit.exists() or not alive(runner[0]):
        return
    pid = runner[0]
    for sig, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if not alive(pid):
                return
            time.sleep(0.1)


def cmd_start(ns: argparse.Namespace) -> int:
    root = Path(ns.root).resolve()
    command = command_of(ns)
    files = gate_files(root, ns.name)
    files.log.parent.mkdir(parents=True, exist_ok=True)
    stop_previous(files)
    files.exit.unlink(missing_ok=True)
    files.log.write_bytes(b"")  # a poll right after start sees a started gate, not a missing one
    files.pid.unlink(missing_ok=True)  # the new runner must not read the previous run's id
    run_id = uuid.uuid4().hex[:12]
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_run", ns.name, "--root", str(root),
                             "--run-id", run_id, "--", *command],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, cwd=root)
    files.pid.write_text(f"{proc.pid} {run_id}\n", encoding="utf-8")
    print(f"STARTED {ns.name}: {files.log}")
    return 0


def cmd_run(ns: argparse.Namespace) -> int:
    """Detached runner: CMD in DIR with output to NAME.log, then NAME.exit written
    atomically, unless a newer run of NAME has replaced this one."""
    root = Path(ns.root)
    command = command_of(ns)
    files = gate_files(root, ns.name)
    shell = len(command) == 1
    with files.log.open("wb") as fh:
        try:
            code = subprocess.run(command[0] if shell else command, shell=shell, cwd=root,
                                  stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT).returncode
        except OSError as e:
            fh.write(f"gate.py: {e}\n".encode("utf-8"))
            code = 127
    deadline = time.monotonic() + 5.0
    while read_runner(files) is None and time.monotonic() < deadline:
        time.sleep(0.05)  # `start` writes the runner record right after spawning us
    runner = read_runner(files)
    if runner is not None and runner[1] != ns.run_id:
        return code
    tmp = files.exit.with_name(files.exit.name + ".tmp")
    tmp.write_text(f"{code}\n", encoding="utf-8")
    tmp.replace(files.exit)
    return code


def tail(path: Path, lines: int) -> str:
    if lines <= 0 or not path.exists():
        return ""
    return "\n".join(path.read_bytes().decode("utf-8", errors="replace").splitlines()[-lines:])


def cmd_poll(ns: argparse.Namespace) -> int:
    files = gate_files(Path(ns.root).resolve(), ns.name)
    if not files.log.exists() and not files.exit.exists():
        raise lib.OmixflowError(f"гейт {ns.name} не запускался: нет {files.log}")
    started = time.monotonic()
    while not files.exit.exists():
        runner = read_runner(files)
        if runner is not None and not alive(runner[0]):
            time.sleep(0.2)  # the runner writes the exit code just before it ends
            if not files.exit.exists():
                print(f"LOST: процесс гейта {ns.name} завершился без кода выхода, запустить заново; "
                      f"вывод: {files.log}")
                return LOST
            break
        elapsed = time.monotonic() - started
        if elapsed >= ns.timeout:
            size = files.log.stat().st_size if files.log.exists() else 0
            print(f"RUNNING {int(elapsed)}s, вывод {size} байт: {files.log}")
            return RUNNING
        time.sleep(min(POLL_INTERVAL, ns.timeout - elapsed))
    print(f"EXIT {files.exit.read_text(encoding='utf-8').strip()}  (полный вывод: {files.log})")
    text = tail(files.log, ns.tail)
    if text:
        print(text)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start")
    p.add_argument("name")
    p.add_argument("--root", required=True)
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("_run")
    p.add_argument("name")
    p.add_argument("--root", required=True)
    p.add_argument("--run-id", required=True)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("poll")
    p.add_argument("name")
    p.add_argument("--root", required=True)
    p.add_argument("--timeout", type=float, default=100)
    p.add_argument("--tail", type=int, default=40)
    p.set_defaults(fn=cmd_poll)

    argv = list(sys.argv[1:] if argv is None else argv)
    command: List[str] = []
    if "--" in argv:  # everything after the first `--` is the gate command, verbatim
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    ns = ap.parse_args(argv)
    ns.command = command
    try:
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
