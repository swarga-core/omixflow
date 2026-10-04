#!/usr/bin/env python3
"""The lead journal (protocol/lead.md, «Журнал»): an append-only JSON Lines event log.

    lead.py [--journal PATH] decide --task T --q N --item I --point P --choice C --basis B [--by S]
    lead.py [--journal PATH] escalate --task T --q N --item I --point P --summary S
    lead.py [--journal PATH] resolve E-n --answer TEXT [--decision D-n]
    lead.py [--journal PATH] replace D-n --with D-m
    lead.py [--journal PATH] rule --text TEXT [--task T ...] [--decision D-n ...]
    lead.py [--journal PATH] rule-use R-n --task T [--decision D-n]
    lead.py [--journal PATH] oblige --trigger TEXT --action TEXT [--task T]
    lead.py [--journal PATH] fulfil O-n [--note TEXT]
    lead.py [--journal PATH] approve --action TEXT --answer TEXT [--task T]
    lead.py [--journal PATH] accept --task T --branch B --into I --commit SHA --approval A-n
    lead.py [--journal PATH] gotcha --text TEXT --task T [--route R] [--by S]
    lead.py [--journal PATH] gotcha-link G-n --task T
    lead.py [--journal PATH] gotcha-route G-n --route plugin|project|memory|reject --where TEXT
    lead.py [--journal PATH] register NAME [--task T] [--dir D] [--phase P] [--branch B]
                                           [--base B] [--worktree W] [--asked N] [--file F ...]
    lead.py [--journal PATH] list [--type decision|escalation|rule|obligation|approval|merge|gotcha|session]
                                  [--task T] [--open] [--trigger TEXT]
    lead.py [--journal PATH] show [--task T]
    lead.py [--journal PATH] board --from DESC [--task T ...] [--before HEADING]  # omixflow:lead block
    lead.py [--journal PATH] precedents --point P     # developer decisions at P and rules (mode precedent)
    lead.py [--journal PATH] overlaps [--task T]      # file-map intersections of active sessions
    lead.py veto-cost --state STATE_YAML              # rollback class of a vetoed decision

The journal defaults to {artifacts.dir}/_lead/journal.jsonl of the project around
the current directory; a task session passes the absolute path from the lead's
brief. Every write appends one event under an exclusive file lock, so ids
(D-n, E-n, R-n, O-n, A-n, M-n, G-n) stay unique when several sessions write at once. Current
records are a fold of the events; nothing is ever rewritten. Writing commands
print the id they created or touched; `list` prints JSON, `show` text.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

JOURNAL_REL = Path("_lead") / "journal.jsonl"
PREFIX = {"decision": "D", "escalation": "E", "rule": "R", "obligation": "O", "approval": "A", "merge": "M",
          "gotcha": "G"}
RECORD_TYPES = ("decision", "escalation", "rule", "obligation", "approval", "merge", "gotcha", "session")
ROUTES = ("plugin", "project", "memory", "reject")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_journal() -> Path:
    root = lib.find_project_root()
    try:
        artifacts = lib.config_get(lib.load_config(root), "artifacts.dir") or ".tasks"
    except lib.OmixflowError:
        artifacts = ".tasks"
    return root / str(artifacts) / JOURNAL_REL


def read_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise lib.OmixflowError(f"{path}:{n}: строка журнала не JSON: {e}")
    return events


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def append(path: Path, event: Dict[str, Any]) -> None:
    event = {"ts": now(), **event}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        fh.flush()


def next_id(events: List[Dict[str, Any]], kind: str) -> str:
    prefix = PREFIX[kind]
    taken = [int(e["id"].split("-", 1)[1]) for e in events
             if e.get("type") == kind and str(e.get("id", "")).startswith(prefix + "-")]
    return f"{prefix}-{max(taken, default=0) + 1}"


def fold(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Current records by type and id (sessions by name)."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = {t: {} for t in RECORD_TYPES}
    for e in events:
        t = e.get("type")
        if t == "decision":
            out[t][e["id"]] = {**e, "replaced_by": None}
        elif t == "escalation":
            out[t][e["id"]] = {**e, "resolved": None}
        elif t == "rule":
            out[t][e["id"]] = {**e, "uses": []}
        elif t == "obligation":
            out[t][e["id"]] = {**e, "fulfilled": None}
        elif t in ("approval", "merge"):
            out[t][e["id"]] = dict(e)
        elif t == "gotcha":
            out[t][e["id"]] = {**e, "tasks": [e["task"]], "routed": None}
        elif t == "gotcha-link":
            tasks = out["gotcha"][e["ref"]]["tasks"]
            if e["task"] not in tasks:
                tasks.append(e["task"])
        elif t == "gotcha-route":
            out["gotcha"][e["ref"]]["routed"] = {"route": e["route"], "where": e["where"], "ts": e["ts"]}
        elif t == "session":
            cur = out[t].setdefault(e["name"], {"type": "session", "name": e["name"]})
            cur.update({k: v for k, v in e.items() if v is not None and k != "type"})
        elif t == "resolve":
            out["escalation"][e["ref"]]["resolved"] = {"ts": e["ts"], "answer": e["answer"],
                                                       "decision": e.get("decision")}
        elif t == "replace":
            out["decision"][e["ref"]]["replaced_by"] = e["with"]
        elif t == "rule-use":
            out["rule"][e["ref"]]["uses"].append({"task": e["task"], "decision": e.get("decision")})
        elif t == "fulfil":
            out["obligation"][e["ref"]]["fulfilled"] = {"ts": e["ts"], "note": e.get("note")}
    return out


def require(records: Dict[str, Dict[str, Any]], ref: str, kind: str) -> Dict[str, Any]:
    if ref not in records:
        raise lib.OmixflowError(f"нет записи {ref} ({kind}) в журнале")
    return records[ref]


def is_open(record: Dict[str, Any]) -> bool:
    t = record["type"]
    if t == "escalation":
        return record["resolved"] is None
    if t == "obligation":
        return record["fulfilled"] is None
    if t == "decision":
        return record["replaced_by"] is None
    if t == "gotcha":
        return record["routed"] is None
    return True


# ---------------------------------------------------------------- commands

def write(ns: argparse.Namespace, build) -> int:
    """Run build(events, records) under the lock; it returns (event, printed id)."""
    with locked(ns.journal):
        events = read_events(ns.journal)
        event, printed = build(events, fold(events))
        append(ns.journal, event)
    print(printed)
    return 0


def cmd_decide(ns: argparse.Namespace) -> int:
    def build(events, records):
        rid = next_id(events, "decision")
        return ({"type": "decision", "id": rid, "task": ns.task, "q": ns.q, "item": ns.item,
                 "point": ns.point, "choice": ns.choice, "basis": ns.basis, "by": ns.by}, rid)
    return write(ns, build)


def cmd_escalate(ns: argparse.Namespace) -> int:
    def build(events, records):
        rid = next_id(events, "escalation")
        return ({"type": "escalation", "id": rid, "task": ns.task, "q": ns.q, "item": ns.item,
                 "point": ns.point, "summary": ns.summary}, rid)
    return write(ns, build)


def cmd_resolve(ns: argparse.Namespace) -> int:
    def build(events, records):
        esc = require(records["escalation"], ns.ref, "escalation")
        if esc["resolved"] is not None:
            raise lib.OmixflowError(f"{ns.ref} уже закрыта")
        if ns.decision:
            require(records["decision"], ns.decision, "decision")
        return ({"type": "resolve", "ref": ns.ref, "answer": ns.answer, "decision": ns.decision}, ns.ref)
    return write(ns, build)


def cmd_replace(ns: argparse.Namespace) -> int:
    def build(events, records):
        old = require(records["decision"], ns.ref, "decision")
        require(records["decision"], ns.with_, "decision")
        if old["replaced_by"] is not None:
            raise lib.OmixflowError(f"{ns.ref} уже заменено на {old['replaced_by']}")
        return ({"type": "replace", "ref": ns.ref, "with": ns.with_}, ns.ref)
    return write(ns, build)


def cmd_rule(ns: argparse.Namespace) -> int:
    def build(events, records):
        for d in ns.decision:
            require(records["decision"], d, "decision")
        rid = next_id(events, "rule")
        return ({"type": "rule", "id": rid, "text": ns.text, "tasks": ns.task,
                 "decisions": ns.decision}, rid)
    return write(ns, build)


def cmd_rule_use(ns: argparse.Namespace) -> int:
    def build(events, records):
        require(records["rule"], ns.ref, "rule")
        if ns.decision:
            require(records["decision"], ns.decision, "decision")
        return ({"type": "rule-use", "ref": ns.ref, "task": ns.task, "decision": ns.decision}, ns.ref)
    return write(ns, build)


def cmd_oblige(ns: argparse.Namespace) -> int:
    def build(events, records):
        rid = next_id(events, "obligation")
        return ({"type": "obligation", "id": rid, "trigger": ns.trigger, "action": ns.action,
                 "task": ns.task}, rid)
    return write(ns, build)


def cmd_fulfil(ns: argparse.Namespace) -> int:
    def build(events, records):
        ob = require(records["obligation"], ns.ref, "obligation")
        if ob["fulfilled"] is not None:
            raise lib.OmixflowError(f"{ns.ref} уже исполнено")
        return ({"type": "fulfil", "ref": ns.ref, "note": ns.note}, ns.ref)
    return write(ns, build)


def cmd_approve(ns: argparse.Namespace) -> int:
    def build(events, records):
        rid = next_id(events, "approval")
        return ({"type": "approval", "id": rid, "action": ns.action, "answer": ns.answer, "task": ns.task}, rid)
    return write(ns, build)


def cmd_accept(ns: argparse.Namespace) -> int:
    def build(events, records):
        require(records["approval"], ns.approval, "approval")
        rid = next_id(events, "merge")
        return ({"type": "merge", "id": rid, "task": ns.task, "branch": ns.branch, "into": ns.into,
                 "commit": ns.commit, "approval": ns.approval}, rid)
    return write(ns, build)


def cmd_gotcha(ns: argparse.Namespace) -> int:
    def build(events, records):
        rid = next_id(events, "gotcha")
        return ({"type": "gotcha", "id": rid, "text": ns.text, "task": ns.task, "route": ns.route,
                 "by": ns.by}, rid)
    return write(ns, build)


def cmd_gotcha_link(ns: argparse.Namespace) -> int:
    def build(events, records):
        require(records["gotcha"], ns.ref, "gotcha")
        return ({"type": "gotcha-link", "ref": ns.ref, "task": ns.task}, ns.ref)
    return write(ns, build)


def cmd_gotcha_route(ns: argparse.Namespace) -> int:
    def build(events, records):
        g = require(records["gotcha"], ns.ref, "gotcha")
        if g["routed"] is not None:
            raise lib.OmixflowError(f"{ns.ref} уже разложена: {g['routed']['route']}")
        return ({"type": "gotcha-route", "ref": ns.ref, "route": ns.route, "where": ns.where}, ns.ref)
    return write(ns, build)


def cmd_register(ns: argparse.Namespace) -> int:
    def build(events, records):
        return ({"type": "session", "name": ns.name, "task": ns.task, "dir": ns.dir,
                 "phase": ns.phase, "branch": ns.branch, "base": ns.base,
                 "worktree": ns.worktree, "asked": ns.asked, "files": ns.file or None}, ns.name)
    return write(ns, build)


def select(ns: argparse.Namespace) -> List[Dict[str, Any]]:
    records = fold(read_events(ns.journal))
    types = [ns.type] if ns.type else list(RECORD_TYPES)
    out = []
    for t in types:
        for rec in records[t].values():
            if ns.task and ns.task != rec.get("task") and ns.task not in (rec.get("tasks") or []):
                continue
            if ns.open and not is_open(rec):
                continue
            if ns.trigger and ns.trigger.lower() not in str(rec.get("trigger", "")).lower():
                continue
            out.append(rec)
    return out


def cmd_list(ns: argparse.Namespace) -> int:
    print(json.dumps(select(ns), ensure_ascii=False, indent=2))
    return 0


def describe(rec: Dict[str, Any]) -> str:
    t = rec["type"]
    if t == "decision":
        tail = f" (заменено {rec['replaced_by']})" if rec["replaced_by"] else ""
        return (f"{rec['id']} {rec['task']}#{rec['q']} {rec['item']} [{rec['point']}]: "
                f"{rec['choice']} — {rec['basis']}{tail}")
    if t == "escalation":
        state = f"закрыта: «{rec['resolved']['answer']}»" if rec["resolved"] else "ждёт разработчика"
        return f"{rec['id']} {rec['task']}#{rec['q']} {rec['item']} [{rec['point']}]: {rec['summary']} — {state}"
    if t == "rule":
        uses = ", ".join(u["task"] for u in rec["uses"])
        return f"{rec['id']} {rec['text']} (задачи: {', '.join(rec['tasks'] or []) or '—'}; применено: {uses or '—'})"
    if t == "obligation":
        state = "исполнено" if rec["fulfilled"] else "открыто"
        return f"{rec['id']} при «{rec['trigger']}»: {rec['action']} — {state}"
    if t == "approval":
        return f"{rec['id']} {rec['action']}: «{rec['answer']}»"
    if t == "gotcha":
        state = (f"{rec['routed']['route']}: {rec['routed']['where']}" if rec["routed"]
                 else f"не разложена{', предложено ' + rec['route'] if rec.get('route') else ''}")
        return f"{rec['id']} [{', '.join(rec['tasks'])}] {rec['text']} — {state}"
    if t == "merge":
        return f"{rec['id']} {rec['task']}: {rec['branch']} → {rec['into']} @ {rec['commit']} ({rec['approval']})"
    fields = ", ".join(f"{k}={rec[k]}" for k in ("task", "phase", "branch", "worktree") if rec.get(k))
    return f"{rec['name']}: {fields}"


def cmd_show(ns: argparse.Namespace) -> int:
    titles = {"session": "Сессии", "escalation": "Эскалации", "decision": "Решения",
              "rule": "Правила-прецеденты", "obligation": "Обязательства",
              "approval": "Санкции", "merge": "Приёмки", "gotcha": "Гочи"}
    records = select(ns)
    for t in ("session", "escalation", "decision", "approval", "merge", "gotcha", "rule", "obligation"):
        rows = [r for r in records if r["type"] == t]
        if rows:
            print(f"## {titles[t]}")
            for r in rows:
                print(f"- {describe(r)}")
            print()
    return 0


BOARD_KIND = "lead"
INACTIVE_PHASES = ("done", "retired")


def developer_made(decision: Dict[str, Any]) -> bool:
    """A decision the developer made: through the lead (`developer E-n …`) or in a session."""
    basis = str(decision.get("basis", ""))
    return basis.startswith("developer") or basis.startswith("разработчик")


def cmd_precedents(ns: argparse.Namespace) -> int:
    records = fold(read_events(ns.journal))
    decisions = [d for d in records["decision"].values()
                 if d["point"] == ns.point and d["replaced_by"] is None and developer_made(d)]
    print(json.dumps({"decisions": decisions, "rules": list(records["rule"].values())},
                     ensure_ascii=False, indent=2))
    return 0


def veto_cost(state: Dict[str, Any]) -> Dict[str, Any]:
    """Rollback class for a vetoed lead decision by the session's progress (protocol/lead.md, «Вето»):
    1 — spec not written yet: re-read the decision; 2 — spec or plan written, no implement
    step committed: restart from spec (uncommitted step work is redone); 3 — a step is
    committed or implement is over: a new iteration on top, not a rollback."""
    completed = list(state.get("completed") or [])
    phase = state.get("phase")
    committed = "implement" in completed or phase in ("review", "finalize", "done") \
        or bool(state.get("steps_done"))
    if committed:
        return {"class": 3, "phase": phase, "action": "iteration",
                "detail": "код закоммичен: доработка новой итерацией поверх сделанного"}
    if "spec" in completed or "plan" in completed:
        return {"class": 2, "phase": phase, "action": "restart", "from": "spec",
                "detail": "spec или plan готовы: перезапуск с фазы spec"}
    return {"class": 1, "phase": phase, "action": "reread",
            "detail": "spec ещё не написан: сессия перечитывает решение"}


def cmd_veto_cost(ns: argparse.Namespace) -> int:
    lib.require_yaml()
    state = lib.yaml.safe_load(Path(ns.state).read_text(encoding="utf-8")) or {}
    print(json.dumps(veto_cost(state), ensure_ascii=False))
    return 0


def cmd_overlaps(ns: argparse.Namespace) -> int:
    sessions = [s for s in fold(read_events(ns.journal))["session"].values()
                if s.get("phase") not in INACTIVE_PHASES and s.get("files")]
    pairs = []
    for i, a in enumerate(sessions):
        for b in sessions[i + 1:]:
            if ns.task and ns.task not in (a.get("task"), b.get("task")):
                continue
            common = sorted(set(a["files"]) & set(b["files"]))
            if common:
                pairs.append({"a": a.get("task"), "b": b.get("task"), "files": common})
    print(json.dumps(pairs, ensure_ascii=False, indent=2))
    return 0


def board_body(records: Dict[str, Dict[str, Dict[str, Any]]], tasks: Optional[List[str]] = None) -> str:
    merges: Dict[str, Dict[str, Any]] = {}
    for m in records["merge"].values():
        merges[m["task"]] = m
    open_esc: Dict[str, int] = {}
    for e in records["escalation"].values():
        if e["resolved"] is None:
            open_esc[e["task"]] = open_esc.get(e["task"], 0) + 1
    rows = ["Сводка лида: строится из журнала лида, руками не правится.", "",
            "| задача | сессия | фаза | ветка | приёмка | эскалации |", "|---|---|---|---|---|---|"]
    for s in sorted(records["session"].values(), key=lambda r: (str(r.get("task")), r["name"])):
        if tasks and s.get("task") not in tasks:
            continue
        task = s.get("task") or "—"
        m = merges.get(task)
        merged = f"{m['id']} {m['commit']} → {m['into']}" if m else "—"
        rows.append(f"| {task} | {s['name']} | {s.get('phase') or '—'} | {s.get('branch') or '—'} "
                    f"| {merged} | {open_esc.get(task, 0) or '—'} |")
    return "\n".join(rows)


def cmd_board(ns: argparse.Namespace) -> int:
    text = Path(ns.source).read_text(encoding="utf-8")
    body = board_body(fold(read_events(ns.journal)), ns.task)
    sys.stdout.write(lib.replace_managed_block(text, BOARD_KIND, body, ns.before))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("decide")
    for flag in ("--task", "--item", "--point", "--choice", "--basis"):
        p.add_argument(flag, required=True)
    p.add_argument("--q", type=int, required=True)
    p.add_argument("--by", default="lead")
    p.set_defaults(fn=cmd_decide)

    p = sub.add_parser("escalate")
    for flag in ("--task", "--item", "--point", "--summary"):
        p.add_argument(flag, required=True)
    p.add_argument("--q", type=int, required=True)
    p.set_defaults(fn=cmd_escalate)

    p = sub.add_parser("resolve")
    p.add_argument("ref")
    p.add_argument("--answer", required=True)
    p.add_argument("--decision", default=None)
    p.set_defaults(fn=cmd_resolve)

    p = sub.add_parser("replace")
    p.add_argument("ref")
    p.add_argument("--with", dest="with_", required=True)
    p.set_defaults(fn=cmd_replace)

    p = sub.add_parser("rule")
    p.add_argument("--text", required=True)
    p.add_argument("--task", action="append", default=[])
    p.add_argument("--decision", action="append", default=[])
    p.set_defaults(fn=cmd_rule)

    p = sub.add_parser("rule-use")
    p.add_argument("ref")
    p.add_argument("--task", required=True)
    p.add_argument("--decision", default=None)
    p.set_defaults(fn=cmd_rule_use)

    p = sub.add_parser("oblige")
    p.add_argument("--trigger", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--task", default=None)
    p.set_defaults(fn=cmd_oblige)

    p = sub.add_parser("fulfil")
    p.add_argument("ref")
    p.add_argument("--note", default=None)
    p.set_defaults(fn=cmd_fulfil)

    p = sub.add_parser("approve")
    p.add_argument("--action", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--task", default=None)
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("accept")
    for flag in ("--task", "--branch", "--into", "--commit", "--approval"):
        p.add_argument(flag, required=True)
    p.set_defaults(fn=cmd_accept)

    p = sub.add_parser("gotcha")
    p.add_argument("--text", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--route", choices=ROUTES[:-1], default=None)
    p.add_argument("--by", default="lead")
    p.set_defaults(fn=cmd_gotcha)

    p = sub.add_parser("gotcha-link")
    p.add_argument("ref")
    p.add_argument("--task", required=True)
    p.set_defaults(fn=cmd_gotcha_link)

    p = sub.add_parser("gotcha-route")
    p.add_argument("ref")
    p.add_argument("--route", choices=ROUTES, required=True)
    p.add_argument("--where", required=True)
    p.set_defaults(fn=cmd_gotcha_route)

    p = sub.add_parser("register")
    p.add_argument("name")
    for flag in ("--task", "--dir", "--phase", "--branch", "--base", "--worktree"):
        p.add_argument(flag, default=None)
    p.add_argument("--asked", type=int, default=None)
    p.add_argument("--file", action="append", default=[])
    p.set_defaults(fn=cmd_register)

    p = sub.add_parser("precedents")
    p.add_argument("--point", required=True)
    p.set_defaults(fn=cmd_precedents)

    p = sub.add_parser("overlaps")
    p.add_argument("--task", default=None)
    p.set_defaults(fn=cmd_overlaps)

    p = sub.add_parser("veto-cost")
    p.add_argument("--state", required=True)
    p.set_defaults(fn=cmd_veto_cost)

    p = sub.add_parser("board")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--task", action="append", default=[])
    p.add_argument("--before", default=None)
    p.set_defaults(fn=cmd_board)

    for name, fn in (("list", cmd_list), ("show", cmd_show)):
        p = sub.add_parser(name)
        p.add_argument("--type", choices=RECORD_TYPES, default=None)
        p.add_argument("--task", default=None)
        p.add_argument("--open", action="store_true")
        p.add_argument("--trigger", default=None)
        p.set_defaults(fn=fn)

    ns = ap.parse_args(argv)
    try:
        if ns.cmd != "veto-cost":
            ns.journal = (ns.journal or default_journal()).resolve()
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
