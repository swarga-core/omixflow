#!/usr/bin/env python3
"""Manage a task's state.yaml (see protocol/artifacts.md).

    state.py init DIR --id ID --kind task|multitask|part [--mode pipeline|manual]
                      [--tier S|M|L] [--forced] [--branch B] [--base B]
                      [--multitask-id X --part P] [--session S] [--force]
    state.py get DIR [KEY]                 # whole state as JSON, or one value
    state.py set DIR KEY=VALUE ...         # dotted keys; JSON for lists/objects
    state.py unset DIR KEY ...
    state.py complete DIR PHASE            # add to completed, advance phase
    state.py next DIR                      # print the next phase to run
    state.py step DIR done N | start N     # implement bookkeeping
    state.py agents DIR --session S        # drop agents from another session

DIR is the task directory (.tasks/{id} or .tasks/{id}/{part}).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

PHASES: List[str] = ["refine", "start", "research", "spec", "plan", "implement", "review", "finalize"]
KINDS = ("task", "multitask", "part")
MODES = ("pipeline", "manual")
TIERS = ("S", "M", "L")
FILE = "state.yaml"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_of(d: Path) -> Path:
    return d / FILE


def load(d: Path) -> Dict[str, Any]:
    lib.require_yaml()
    p = path_of(d)
    if not p.exists():
        raise lib.OmixflowError(f"нет состояния: {p} (state.py init)")
    data = lib.yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise lib.OmixflowError(f"{p}: состояние должно быть объектом")
    return data


def save(d: Path, state: Dict[str, Any]) -> None:
    lib.require_yaml()
    state["updated"] = now()
    d.mkdir(parents=True, exist_ok=True)
    path_of(d).write_text(
        lib.yaml.safe_dump(state, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8")


def parse_value(raw: str) -> Any:
    if raw in ("null", "~", ""):
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw[:1] in "[{":
        return json.loads(raw)
    try:
        return int(raw)
    except ValueError:
        return raw


def set_dotted(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = obj
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def unset_dotted(obj: Dict[str, Any], dotted: str) -> None:
    keys = dotted.split(".")
    cur: Any = obj
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return
        cur = cur[k]
    if isinstance(cur, dict):
        cur.pop(keys[-1], None)


def next_phase(state: Dict[str, Any]) -> str:
    completed = [p for p in state.get("completed") or []]
    for p in PHASES:
        if p not in completed:
            return p
    return "done"


# ---------------------------------------------------------------- commands

def cmd_init(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    if path_of(d).exists() and not ns.force:
        raise lib.OmixflowError(f"{path_of(d)} уже существует; перезаписать: --force")
    if ns.kind not in KINDS:
        raise lib.OmixflowError(f"kind должен быть одним из {KINDS}")
    if ns.mode not in MODES:
        raise lib.OmixflowError(f"mode должен быть одним из {MODES}")
    if ns.tier and ns.tier not in TIERS:
        raise lib.OmixflowError(f"tier должен быть одним из {TIERS}")
    state: Dict[str, Any] = {
        "schema": 1,
        "id": ns.id,
        "kind": ns.kind,
        "mode": ns.mode,
        "tier": ns.tier,
        "tier_forced": bool(ns.forced),
        "phase": PHASES[0],
        "completed": [],
        "step": None,
        "steps_total": None,
        "steps_done": [],
        "iteration": 1,
        "agents": {},
        "session": ns.session,
        "branch": ns.branch,
        "base": ns.base,
    }
    if ns.kind == "part":
        if not (ns.multitask_id and ns.part):
            raise lib.OmixflowError("для kind=part нужны --multitask-id и --part")
        state["multitask"] = {"id": ns.multitask_id, "part": ns.part}
    save(d, state)
    print(path_of(d))
    return 0


def cmd_get(ns: argparse.Namespace) -> int:
    state = load(Path(ns.dir).resolve())
    if ns.key:
        value = lib.config_get(state, ns.key)
        if value is None:
            print("null")
            return 1
        print(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)
        return 0
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_set(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = load(d)
    for pair in ns.pairs:
        if "=" not in pair:
            raise lib.OmixflowError(f"ожидается KEY=VALUE, получено {pair!r}")
        key, raw = pair.split("=", 1)
        value = parse_value(raw)
        if key == "phase" and value not in PHASES + ["done"]:
            raise lib.OmixflowError(f"phase должна быть одной из {PHASES + ['done']}")
        if key == "tier" and value not in TIERS:
            raise lib.OmixflowError(f"tier должен быть одним из {TIERS}")
        if key == "mode" and value not in MODES:
            raise lib.OmixflowError(f"mode должен быть одним из {MODES}")
        set_dotted(state, key, value)
    save(d, state)
    return 0


def cmd_unset(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = load(d)
    for key in ns.keys:
        unset_dotted(state, key)
    save(d, state)
    return 0


def cmd_complete(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = load(d)
    phase = ns.phase
    if phase not in PHASES:
        raise lib.OmixflowError(f"неизвестная фаза {phase!r}")
    completed = list(state.get("completed") or [])
    if phase not in completed:
        completed.append(phase)
    state["completed"] = [p for p in PHASES if p in completed]
    state["phase"] = next_phase(state)
    save(d, state)
    print(state["phase"])
    return 0


def cmd_next(ns: argparse.Namespace) -> int:
    state = load(Path(ns.dir).resolve())
    print(next_phase(state))
    return 0


def cmd_step(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = load(d)
    n = int(ns.n)
    if ns.action == "start":
        state["step"] = n
        if ns.total is not None:
            state["steps_total"] = int(ns.total)
    else:
        done = [int(x) for x in state.get("steps_done") or []]
        if n not in done:
            done.append(n)
        state["steps_done"] = sorted(done)
        total = state.get("steps_total")
        state["step"] = n + 1 if (total is None or n < int(total)) else None
    save(d, state)
    return 0


def cmd_agents(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = load(d)
    if state.get("session") != ns.session:
        state["agents"] = {}
        state["session"] = ns.session
        save(d, state)
        print("cleared")
    else:
        print("kept")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("dir")
    p.add_argument("--id", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--mode", default="manual")
    p.add_argument("--tier", default=None)
    p.add_argument("--forced", action="store_true")
    p.add_argument("--branch", default=None)
    p.add_argument("--base", default=None)
    p.add_argument("--multitask-id", default=None)
    p.add_argument("--part", default=None)
    p.add_argument("--session", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("get")
    p.add_argument("dir")
    p.add_argument("key", nargs="?")
    p.set_defaults(fn=cmd_get)

    p = sub.add_parser("set")
    p.add_argument("dir")
    p.add_argument("pairs", nargs="+")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("unset")
    p.add_argument("dir")
    p.add_argument("keys", nargs="+")
    p.set_defaults(fn=cmd_unset)

    p = sub.add_parser("complete")
    p.add_argument("dir")
    p.add_argument("phase")
    p.set_defaults(fn=cmd_complete)

    p = sub.add_parser("next")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_next)

    p = sub.add_parser("step")
    p.add_argument("dir")
    p.add_argument("action", choices=["start", "done"])
    p.add_argument("n")
    p.add_argument("--total", default=None)
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("agents")
    p.add_argument("dir")
    p.add_argument("--session", required=True)
    p.set_defaults(fn=cmd_agents)

    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
