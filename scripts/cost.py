#!/usr/bin/env python3
"""Cost of a session's model requests, from the transcripts the harness keeps.

    cost.py session [--session ID] [--projects DIR] [--since TS] [--until TS] [--json] [--line]
                    [--model-factor opus=1,sonnet=0.6,haiku=0.04]
    cost.py phase TASK_DIR PHASE [--session ID] [--projects DIR] [--json] [--model-factor …]

The requests written to the transcripts of the orchestrator and of its subagents are read
from `{projects}/*/{session}.jsonl` and `{projects}/*/{session}/subagents/*.jsonl` (the
transcripts `agent_ctx.py` reads). One request may be split over several records with the
same requestId; the last record carries the final usage (the earlier ones hold partial
output counts), so the last one counts. API-error and synthetic records are skipped. Side
requests the harness does not write to the transcripts (compaction, titles) are not seen:
the harness's own `cost-state` record of the session, when present, is printed next to the
result as a cross-check (`usd`).

Prices are relative: cost_eq is the request in "Opus input tokens" — input 1, cache write
1.25 (2.0 for the 1-hour cache), cache read 0.1, output 5 — times a model factor. The
default factors (opus 1, sonnet 0.6, haiku 0.04) are the ratios of the harness's own
price table, read from the `cost-state` records of the runs of 2026-10 (sonnet $2.0 and
opus $2.5–3.0 per weighted MTok); `session` derives them from the session's own
`cost-state` record when it has one opus model (by full model name; models with web
search left out). cost_eq compares runs and roles; it is not a bill. The rule it exposes:
cost ≈ 0.1 × Σ(context of every request), so the number of requests and the average context
are what to cut.

Per agent (and per role, and in total): requests, average and peak context, tokens by kind,
cost_eq, and the mechanics that cost most in the runs of 0.5–0.7:
- `intro` — the context at the end of the agent's first assignment (170–300k in the runs):
  what a rotation or a fresh agent after an idle pays again. An assignment is a prompt
  from the parent (a user record with text, not a system reminder or an interruption)
  after at least one request;
- `rebuilds` — requests after the agent's first whose cache write is over half the context:
  the prompt cache expired during an idle (5 min TTL for subagents) and was written again
  at 1.25 instead of read at 0.1;
- `refusals` — Bash calls the worktree-isolated session refused ("This session is isolated
  in the worktree"), by command shape, and the `retries` that followed them (the next Bash
  call); a refusal costs one empty request, the retry does the refused work;
- `polls` — `gate.py poll` results still RUNNING: empty requests too.

`session` prints a table (--json: one object; --line: one line for log.md). --since/--until
(ISO timestamps, naive ones as UTC) keep the requests, refusals and polls of a time window:
a phase. A rebuild on the first request of a window still counts: the flag is computed over
the whole transcript.

`phase` is what a phase skill calls before `state.py finish`: it sums the window since the
previous `phase` call of this task (state.yaml `cost.last`, else the session start),
appends `{phase, requests, cost_eq, by_role, …}` to `cost.phases`, moves `cost.last` and
prints the log.md line `- Стоимость: …`. Start calls it first, so later phases start at the
task. A part of a multitask and the multitask share one session when the parts run one
after another, so the window starts at the latest cursor among the task, its multitask and
its sibling parts that this session wrote (`cost.session`; a cursor synced in from another
owner's session is ignored). `phase` keeps the default factors (or --model-factor): the cost-state
record appears only when the session ends, and the phases of one task must share a unit.
Finalize reads `cost.phases` for the task total (protocol/runtime.md, «Стоимость»).

Unknown session (no CLAUDE_CODE_SESSION_ID, no transcript): JSON with `error`, exit 3;
a bad --since/--until: exit 2.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

UNKNOWN = 3
USAGE = 2
SESSION_RE = re.compile(r"^[A-Za-z0-9-]+$")
WEIGHTS = {"input": 1.0, "cache_write": 1.25, "cache_write_1h": 2.0, "cache_read": 0.1, "output": 5.0}
MODEL_FACTORS = {"opus": 1.0, "sonnet": 0.6, "haiku": 0.04}
REBUILD_SHARE = 0.5          # cache write over this share of the context = the cache was rebuilt
ISOLATION = "This session is isolated in the worktree"
RUNNING = re.compile(r"^RUNNING \d+s", re.M)
NOT_A_PROMPT = ("<system-reminder", "[Request interrupted", "Your response above was")
ORCHESTRATOR = "orchestrator"
# Command shapes of a refused Bash call, exclusive, in the order one rule removes them
# (omixflow-lead, 2026-10-12, 604 refusals: variables 70 %, heredoc 12 %, chains 8 %, cd 3 %).
CHAIN = re.compile(r"&&|\|\||;\s*\S|[^|]\|[^|]")
SHAPES: List[Tuple[str, Optional["re.Pattern[str]"]]] = [
    ("variable", re.compile(r"\$\{?[A-Za-z_(]")),
    ("heredoc", re.compile(r"<<-?\s*['\"]?\w")),
    ("loop", re.compile(r"\b(for|while|until)\b[^;]*;\s*do\b")),
    ("cd", re.compile(r"(^|[;&|]\s*)cd\s")),
    ("chain-git", None),
    ("chain", CHAIN),
]


def projects_dir(given: Optional[str]) -> Path:
    if given:
        return Path(given).expanduser()
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"


def parse_ts(value: Any) -> Optional[datetime]:
    """An ISO timestamp (or a datetime YAML already parsed) as an aware UTC datetime; None for
    nothing; ValueError for text that is not a timestamp."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def in_window(ts: Optional[datetime], since: Optional[datetime], until: Optional[datetime]) -> bool:
    if ts is None:
        return True
    return not ((since and ts < since) or (until and ts > until))


def model_factor(model: Optional[str], factors: Dict[str, float]) -> float:
    """The factor of a model: by its full name first (derived factors), then by family."""
    name = (model or "").lower()
    if name in factors:
        return factors[name]
    for key, value in factors.items():
        if key in name:
            return value
    return 1.0


def shape_of(cmd: str) -> str:
    for name, rx in SHAPES:
        if rx is None:
            if CHAIN.search(cmd) and re.search(r"\bgit\b", cmd):
                return name
        elif rx.search(cmd):
            return name
    return "single"


def result_text(block: Dict[str, Any]) -> str:
    out = block.get("content")
    if isinstance(out, list):
        return " ".join(str(x.get("text", "")) for x in out if isinstance(x, dict))
    return "" if out is None else str(out)


def prompt_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(x.get("text", "")) for x in content if isinstance(x, dict) and x.get("type") == "text")
    return ""


def read_transcript(log: Path) -> Dict[str, Any]:
    """One transcript as it is: requests in order (last record per requestId), assignment
    boundaries, refusals, retries, polls and the harness's cost-state record."""
    requests: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    boundaries: List[int] = []        # index of the first request of each assignment after the first
    requests_since_prompt = 0
    bash: Dict[str, str] = {}         # tool_use id → command
    refusals: List[Tuple[Optional[datetime], str]] = []
    retries: List[Optional[datetime]] = []
    polls: List[Optional[datetime]] = []
    refusal_pending = False
    cost_state: Optional[Dict[str, Any]] = None
    with log.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            kind = rec.get("type")
            message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            try:
                ts = parse_ts(rec.get("timestamp"))
            except ValueError:
                ts = None
            if kind == "cost-state":
                cost_state = rec
                continue
            if kind == "user":
                content = message.get("content")
                text = prompt_text(content).strip()
                if text and not text.startswith(NOT_A_PROMPT) and requests_since_prompt:
                    boundaries.append(len(order))
                    requests_since_prompt = 0
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            cmd = bash.get(block.get("tool_use_id"))
                            if cmd is None:
                                continue
                            out = result_text(block)
                            if ISOLATION in out:
                                refusals.append((ts, shape_of(cmd)))
                                refusal_pending = True
                            elif RUNNING.search(out):
                                polls.append(ts)
                continue
            if kind != "assistant" or rec.get("isApiErrorMessage") or message.get("model") == "<synthetic>":
                continue
            rid = rec.get("requestId") or rec.get("uuid")
            usage = message.get("usage")
            if isinstance(usage, dict):
                cache = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
                if rid not in requests:
                    order.append(rid)
                    requests_since_prompt += 1
                requests[rid] = {
                    "input": int(usage.get("input_tokens") or 0),
                    "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
                    "cache_write_1h": int(cache.get("ephemeral_1h_input_tokens") or 0),
                    "cache_read": int(usage.get("cache_read_input_tokens") or 0),
                    "output": int(usage.get("output_tokens") or 0),
                    "ts": ts, "model": message.get("model"),
                }
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
                    bash[block.get("id")] = str((block.get("input") or {}).get("command", ""))
                    if refusal_pending:
                        retries.append(ts)
                        refusal_pending = False
    return {"requests": [requests[r] for r in order], "boundaries": boundaries, "refusals": refusals,
            "retries": retries, "polls": polls, "cost_state": cost_state}


def context_of(req: Dict[str, Any]) -> int:
    return req["input"] + req["cache_write"] + req["cache_read"]


def cost_of(req: Dict[str, Any], factors: Dict[str, float]) -> float:
    five_min = req["cache_write"] - req["cache_write_1h"]
    weighted = (req["input"] * WEIGHTS["input"] + five_min * WEIGHTS["cache_write"]
                + req["cache_write_1h"] * WEIGHTS["cache_write_1h"] + req["cache_read"] * WEIGHTS["cache_read"]
                + req["output"] * WEIGHTS["output"])
    return weighted * model_factor(req["model"], factors)


def summarize(name: str, role: str, data: Dict[str, Any], since: Optional[datetime], until: Optional[datetime],
              factors: Dict[str, float]) -> Dict[str, Any]:
    reqs_all = data["requests"]
    contexts_all = [context_of(r) for r in reqs_all]
    rebuild_all = [i > 0 and contexts_all[i] > 0 and r["cache_write"] > REBUILD_SHARE * contexts_all[i]
                   for i, r in enumerate(reqs_all)]
    first_end = data["boundaries"][0] if data["boundaries"] else len(reqs_all)
    # the orchestrator's prompts are the developer's and the harness's notices, not assignments
    intro = contexts_all[first_end - 1] if first_end and role != ORCHESTRATOR else None
    keep = [i for i, r in enumerate(reqs_all) if in_window(r["ts"], since, until)]
    reqs = [reqs_all[i] for i in keep]
    contexts = [contexts_all[i] for i in keep]
    rebuilds = [reqs_all[i] for i in keep if rebuild_all[i]]
    refusals = [shape for ts, shape in data["refusals"] if in_window(ts, since, until)]
    retries = sum(1 for ts in data["retries"] if in_window(ts, since, until))
    polls = sum(1 for ts in data["polls"] if in_window(ts, since, until))
    models = collections.Counter(r["model"] for r in reqs if r["model"])
    return {
        "agent": name, "role": role, "model": models.most_common(1)[0][0] if models else None,
        "requests": len(reqs), "assignments": len(data["boundaries"]) + 1 if reqs_all else 0,
        "avg_context": int(sum(contexts) / len(contexts)) if contexts else 0,
        "max_context": max(contexts) if contexts else 0,
        "input": sum(r["input"] for r in reqs), "cache_write": sum(r["cache_write"] for r in reqs),
        "cache_read": sum(r["cache_read"] for r in reqs), "output": sum(r["output"] for r in reqs),
        "cost_eq": int(sum(cost_of(r, factors) for r in reqs)),
        "intro": intro,
        "rebuilds": len(rebuilds), "rebuild_tokens": sum(r["cache_write"] for r in rebuilds),
        "refusals": len(refusals), "refusal_shapes": dict(collections.Counter(refusals)),
        "retries": retries, "polls": polls,
        "first": reqs[0]["ts"].isoformat() if reqs and reqs[0]["ts"] else None,
        "last": reqs[-1]["ts"].isoformat() if reqs and reqs[-1]["ts"] else None,
    }


def role_of(meta: Dict[str, Any], name: str) -> str:
    """The role of a subagent: the agent type of a plain subagent (`agentType`), of a teammate
    (`spawnedAgentType`, `customAgentType`; its `agentType` is the name), else the name's prefix."""
    for key in ("spawnedAgentType", "customAgentType", "agentType"):
        value = str(meta.get(key) or "")
        if value and ":" in value:
            return value.split(":")[-1]
        if value and value != name and key == "agentType":
            return value
    return name.split("-", 1)[0] if name else "agent"


def transcripts(projects: Path, session: str) -> Tuple[Optional[Path], List[Tuple[str, str, Path]]]:
    main = next(iter(projects.glob(f"*/{session}.jsonl")), None)
    agents: List[Tuple[str, str, Path]] = []
    for meta_path in sorted(projects.glob(f"*/{session}/subagents/*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        log = meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".jsonl")
        if log.is_file():
            name = str(meta.get("name") or log.stem)
            agents.append((name, role_of(meta, name), log))
    return main, agents


def weighted_tokens(usage: Dict[str, Any]) -> float:
    return (float(usage.get("inputTokens") or 0) * WEIGHTS["input"]
            + float(usage.get("cacheCreationInputTokens") or 0) * WEIGHTS["cache_write"]
            + float(usage.get("cacheReadInputTokens") or 0) * WEIGHTS["cache_read"]
            + float(usage.get("outputTokens") or 0) * WEIGHTS["output"])


def harness_cost(cost_state: Optional[Dict[str, Any]], factors: Dict[str, float]) -> Tuple[Optional[Dict[str, Any]], Dict[str, float]]:
    """The harness's own figures for the whole session and the model factors they imply: the
    price per weighted token of each model (by full name), relative to the opus model of the
    session. Without an opus model the unit of cost_eq would drift: the factors stay as given.
    A model with web-search requests is left out: the fees inflate its price."""
    if not isinstance(cost_state, dict) or not isinstance(cost_state.get("modelUsage"), dict):
        return None, factors
    prices: Dict[str, float] = {}
    for model, usage in cost_state["modelUsage"].items():
        if (isinstance(usage, dict) and weighted_tokens(usage) > 0 and usage.get("costUSD")
                and not usage.get("webSearchRequests")):
            prices[str(model).lower()] = float(usage["costUSD"]) / weighted_tokens(usage)
    derived = dict(factors)
    opus = [p for m, p in prices.items() if "opus" in m]
    if len(opus) == 1:
        for model, price in prices.items():
            derived[model] = round(price / opus[0], 3)
    usd = {"total": round(float(cost_state.get("totalCostUSD") or 0), 2),
           "by_model": {m: round(float((u or {}).get("costUSD") or 0), 2) for m, u in cost_state["modelUsage"].items()
                        if isinstance(u, dict)}}
    return usd, derived


def measure(session: str, projects: Path, since: Optional[datetime], until: Optional[datetime],
            factors: Dict[str, float], derive_factors: bool = True) -> Dict[str, Any]:
    main, agents = transcripts(projects, session)
    if main is None and not agents:
        return {"session": session, "error": f"транскрипт сессии не найден: {projects}/*/{session}.jsonl"}
    main_data = read_transcript(main) if main is not None else None
    usd, derived = harness_cost(main_data["cost_state"] if main_data else None, factors)
    if derive_factors:
        factors = derived
    rows: List[Dict[str, Any]] = []
    if main_data is not None:
        rows.append(summarize(ORCHESTRATOR, ORCHESTRATOR, main_data, since, until, factors))
    for name, role, log in agents:
        rows.append(summarize(name, role, read_transcript(log), since, until, factors))
    rows = [r for r in rows if r["requests"]] or rows[:1]
    by_role: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        acc = by_role.setdefault(r["role"], {"requests": 0, "cost_eq": 0, "cache_read": 0, "cache_write": 0,
                                             "output": 0, "rebuild_tokens": 0, "refusals": 0, "agents": 0})
        for key in ("requests", "cost_eq", "cache_read", "cache_write", "output", "rebuild_tokens", "refusals"):
            acc[key] += r[key]
        acc["agents"] += 1
    total_cost = sum(r["cost_eq"] for r in rows) or 1
    for acc in by_role.values():
        acc["share"] = round(100 * acc["cost_eq"] / total_cost, 1)
    total_requests = sum(r["requests"] for r in rows)
    weighted = sum(r["avg_context"] * r["requests"] for r in rows)
    return {
        "session": session, "since": since.isoformat() if since else None, "until": until.isoformat() if until else None,
        "requests": total_requests, "cost_eq": sum(r["cost_eq"] for r in rows),
        "avg_context": int(weighted / total_requests) if total_requests else 0,
        "cache_read": sum(r["cache_read"] for r in rows), "cache_write": sum(r["cache_write"] for r in rows),
        "output": sum(r["output"] for r in rows),
        "rebuilds": sum(r["rebuilds"] for r in rows), "rebuild_tokens": sum(r["rebuild_tokens"] for r in rows),
        "refusals": sum(r["refusals"] for r in rows), "retries": sum(r["retries"] for r in rows),
        "polls": sum(r["polls"] for r in rows),
        "model_factors": factors, "usd": usd,
        "by_role": dict(sorted(by_role.items(), key=lambda kv: -kv[1]["cost_eq"])),
        "agents": rows,
    }


def k(n: Optional[int]) -> str:
    return "—" if n is None else f"{n / 1000:.0f}k"


def m(n: float) -> str:
    return f"{n / 1e6:.1f}M"


def line_of(result: Dict[str, Any]) -> str:
    roles = ", ".join(f"{role} {acc['share']:.0f} %" for role, acc in result["by_role"].items())
    extras = []
    if result["rebuilds"]:
        extras.append(f"перестроек кэша {result['rebuilds']} ({k(result['rebuild_tokens'])})")
    if result["refusals"]:
        extras.append(f"отказов изоляции {result['refusals']}")
    if result["polls"]:
        extras.append(f"опросов гейтов {result['polls']}")
    tail = f"; {'; '.join(extras)}" if extras else ""
    return (f"- Стоимость: {m(result['cost_eq'])} cost_eq, запросов {result['requests']}, "
            f"средний контекст {k(result['avg_context'])}; {roles}{tail}")


def render(result: Dict[str, Any]) -> str:
    out = [f"{'agent':30} {'role':13} {'model':16} {'req':>4} {'avg':>6} {'max':>6} {'intro':>6} "
           f"{'cache_r':>8} {'cache_w':>8} {'out':>6} {'cost_eq':>8} {'rebuild':>8} {'refus':>5}"]
    for r in result["agents"]:
        out.append(f"{r['agent'][:30]:30} {r['role'][:13]:13} {str(r['model'] or '')[:16]:16} {r['requests']:4d} "
                   f"{k(r['avg_context']):>6} {k(r['max_context']):>6} {k(r['intro']):>6} "
                   f"{k(r['cache_read']):>8} {k(r['cache_write']):>8} {k(r['output']):>6} {m(r['cost_eq']):>8} "
                   f"{(str(r['rebuilds']) + '/' + k(r['rebuild_tokens'])) if r['rebuilds'] else '—':>8} "
                   f"{r['refusals'] or '—':>5}")
    out.append(f"{'TOTAL':30} {'':13} {'':16} {result['requests']:4d} {k(result['avg_context']):>6} {'':>6} {'':>6} "
               f"{k(result['cache_read']):>8} {k(result['cache_write']):>8} {k(result['output']):>6} "
               f"{m(result['cost_eq']):>8} {(str(result['rebuilds']) + '/' + k(result['rebuild_tokens'])) if result['rebuilds'] else '—':>8} "
               f"{result['refusals'] or '—':>5}")
    out.append("")
    out.append("by role:")
    for role, acc in result["by_role"].items():
        out.append(f"  {role:13} {acc['share']:5.1f} %  cost_eq {m(acc['cost_eq']):>7}  req {acc['requests']:4d}  "
                   f"agents {acc['agents']}  cache_w {k(acc['cache_write']):>6}  rebuilds {k(acc['rebuild_tokens']):>6}  "
                   f"refusals {acc['refusals']}")
    empty = result["refusals"] + result["polls"]
    out.append(f"empty requests: refusals {result['refusals']} + RUNNING polls {result['polls']} = {empty} "
               f"of {result['requests']}; retries after refusals {result['retries']}")
    shapes: collections.Counter = collections.Counter()
    for r in result["agents"]:
        shapes.update(r["refusal_shapes"])
    if shapes:
        out.append("refusal shapes: " + ", ".join(f"{s} {n}" for s, n in shapes.most_common()))
    out.append("model factors: " + ", ".join(f"{name} {value}" for name, value in result["model_factors"].items()))
    if result["usd"]:
        out.append(f"harness cost-state (whole session, not the window): ${result['usd']['total']} = "
                   + ", ".join(f"{model} ${usd}" for model, usd in result["usd"]["by_model"].items()))
    return "\n".join(out)


def parse_factors(text: Optional[str]) -> Dict[str, float]:
    factors = dict(MODEL_FACTORS)
    for item in (text or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            factors[key.strip().lower()] = float(value)
    return factors


def session_id(given: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    session = given or os.environ.get("CLAUDE_CODE_SESSION_ID") or fallback
    return session if session and SESSION_RE.match(session) else None


def cmd_session(ns: argparse.Namespace) -> int:
    session = session_id(ns.session)
    if not session:
        print(json.dumps({"error": "нет id сессии: ни --session, ни CLAUDE_CODE_SESSION_ID"}, ensure_ascii=False))
        return UNKNOWN
    try:
        since, until = parse_ts(ns.since), parse_ts(ns.until)
    except ValueError as e:
        print(json.dumps({"error": f"--since/--until: ожидается ISO-время, {e}"}, ensure_ascii=False))
        return USAGE
    result = measure(session, projects_dir(ns.projects), since, until, parse_factors(ns.model_factor),
                     derive_factors=ns.model_factor is None)
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False))
        return UNKNOWN
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif ns.line:
        print(line_of(result))
    else:
        print(render(result))
    return 0


def cursor_of(path: Path, session: Optional[str] = None) -> Optional[datetime]:
    """`cost.last` of a state.yaml; with SESSION, only a cursor that session wrote
    (`cost.session`): a cursor from another owner's session says nothing about this one.
    None when there is no state, no cursor or it is unreadable."""
    import omixflow_lib as lib
    import state as st

    try:
        cost = st.load(path).get("cost")
        if not isinstance(cost, dict):
            return None
        if session is not None and cost.get("session") != session:
            return None
        return parse_ts(cost.get("last"))
    except (lib.OmixflowError, OSError, ValueError, lib.yaml.YAMLError if lib.yaml else ValueError):
        return None


def phase_since(task_dir: Path, state: Dict[str, Any], session: str) -> Optional[datetime]:
    """Where this task's window starts: the latest of its own cursor and, for a part, the
    cursors of its multitask and sibling parts; for a multitask, of its parts — only cursors
    this session wrote. Sequential parts and their multitask share one session, so a part's
    first window would otherwise start at the session start and count the earlier parts
    again; a cursor another session wrote (another owner's part, synced in) is ignored."""
    cursors = [cursor_of(task_dir)]
    kind = state.get("kind")
    siblings = task_dir.parent if kind == "part" else task_dir if kind == "multitask" else None
    if siblings is not None:
        if kind == "part":
            cursors.append(cursor_of(task_dir.parent, session))
        for other in sorted(siblings.glob("*/state.yaml")):
            if other.parent != task_dir:
                cursors.append(cursor_of(other.parent, session))
    known = [c for c in cursors if c is not None]
    return max(known) if known else None


def cmd_phase(ns: argparse.Namespace) -> int:
    import state as st  # PyYAML is needed only here

    task_dir = Path(ns.task_dir).resolve()
    state = st.load(task_dir)
    session = session_id(ns.session, str(state.get("session") or ""))
    if not session:
        print(json.dumps({"error": "нет id сессии: ни --session, ни CLAUDE_CODE_SESSION_ID, ни session в state.yaml"},
                         ensure_ascii=False))
        return UNKNOWN
    cost = state.get("cost") if isinstance(state.get("cost"), dict) else {}
    since = phase_since(task_dir, state, session)
    # the phases of one task stay in one unit: cost-state appears only when the session's
    # process exits, so `phase` never derives the factors from it
    result = measure(session, projects_dir(ns.projects), since, None, parse_factors(ns.model_factor),
                     derive_factors=False)
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False))
        return UNKNOWN
    entry = {"phase": ns.phase, "requests": result["requests"], "cost_eq": result["cost_eq"],
             "avg_context": result["avg_context"], "rebuild_tokens": result["rebuild_tokens"],
             "refusals": result["refusals"], "polls": result["polls"],
             "by_role": {role: acc["cost_eq"] for role, acc in result["by_role"].items()},
             "since": since.isoformat().replace("+00:00", "Z") if since else None, "until": now_iso(),
             "session": session}
    phases = list(cost.get("phases") or [])
    phases.append(entry)
    state["cost"] = {"last": entry["until"], "session": session, "phases": phases,
                     "total_eq": sum(int(p.get("cost_eq") or 0) for p in phases)}
    st.save(task_dir, state)
    if ns.json:
        print(json.dumps(entry, ensure_ascii=False))
    else:
        print(line_of(result))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("session", cmd_session), ("phase", cmd_phase)):
        p = sub.add_parser(name)
        if name == "phase":
            p.add_argument("task_dir")
            p.add_argument("phase")
        p.add_argument("--session", default=None)
        p.add_argument("--projects", default=None)
        p.add_argument("--model-factor", default=None,
                       help="opus=1,sonnet=0.6,haiku=0.04; given, it replaces the factors derived from cost-state")
        p.add_argument("--json", action="store_true")
        if name == "session":
            p.add_argument("--since", default=None)
            p.add_argument("--until", default=None)
            p.add_argument("--line", action="store_true")
        p.set_defaults(fn=fn)
    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except Exception as e:  # the transcript format is the harness's: a reason, never a traceback
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
