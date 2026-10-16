#!/usr/bin/env python3
"""Context size of a live agent of this session, read from its transcript.

    agent_ctx.py AGENT [--session ID] [--projects DIR]
    agent_ctx.py --list [--session ID] [--projects DIR]

The rotation threshold (protocol/tiers.md, «Смена агента по ходу задачи») needs the
agent's context size. A named agent in agent-team mode reports the end of its turn with
an idle notice that carries no usage, so the size comes from the transcript the harness
keeps for every subagent: `{projects}/*/{session}/subagents/agent-{id}.jsonl` holds its
messages, the `.meta.json` next to it the spawn's agent type, description and — when the
harness took a `name` at the spawn — the name. The size is the input of the agent's latest
model reply: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`;
API-error records the harness writes with zero usage are skipped.

AGENT is the agent's address (protocol/runtime.md, «Спавн агентов»): its id — the
transcript's file name without `agent-` (`agent-aa1c990a52da5a28a.jsonl` →
`aa1c990a52da5a28a`), the `agentId` of the spawn result — or its name. Since Claude Code
2.1.300 the Agent tool takes no `name` (SwAIS T-10: no `.meta.json` of the session has
one), so an agent spawned there is found by id only; agents spawned with a name are found
by either. After the session restarts (`claude respawn`) SendMessage no longer finds the
agents spawned before it by name, only by id. Several transcripts with the NAME: the
latest one counts.

--session defaults to $CLAUDE_CODE_SESSION_ID, --projects to $CLAUDE_CONFIG_DIR/projects
or ~/.claude/projects.

Prints one JSON line. Known: `{"agent", "name", "id", "others", "context", "at",
"transcript"}`, exit 0; `agent` is AGENT as given, `name` the transcript's name (null for an
agent spawned without one), `others` counts older transcripts with the same name (a tester
respawned per step, a reviewer spawned again; 0 for a lookup by id). Unknown (no session
id, no subagents directory, no transcript of AGENT, no reply yet, unreadable transcript):
`{"agent", "context": null, "reason"}`, exit 3, with `name`, `id` and `others` once the
transcript is found (an agent that failed on its first request still has an id); the
caller falls back as tiers.md says. The id is verified for plain subagents (T-7); a
teammate of agent-team mode is not restored after a restart (protocol/runtime.md).

`--list` prints the session's subagents, latest first, one JSON line in all:
`{"agents": [{"id", "name", "type", "description", "context", "at"}…]}` — the way back to
an agent's id when the orchestrator did not keep it (`description` is the spawn's).
Usage error: exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

UNKNOWN = 3
SESSION_RE = re.compile(r"^[A-Za-z0-9-]+$")


def projects_dir(given: Optional[str]) -> Path:
    if given:
        return Path(given).expanduser()
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"


def agent_id_of(log: Path) -> str:
    stem = log.name[: -len(".jsonl")]
    return stem[len("agent-"):] if stem.startswith("agent-") else stem


def subagents(projects: Path, session: str) -> List[Tuple[Path, Dict[str, Any]]]:
    """Every subagent transcript of SESSION with its meta (empty when missing or unreadable: the
    id needs only the transcript's file name), latest first."""
    found = []
    for log in projects.glob(f"*/{session}/subagents/*.jsonl"):
        meta_path = log.with_name(log.name[: -len(".jsonl")] + ".meta.json")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        found.append((log, meta if isinstance(meta, dict) else {}))
    return sorted(found, key=lambda item: item[0].stat().st_mtime, reverse=True)


def transcripts(projects: Path, session: str, agent: str) -> Tuple[List[Tuple[Path, Dict[str, Any]]], bool]:
    """Transcripts of AGENT in SESSION, latest first, and whether the match was by id."""
    every = subagents(projects, session)
    by_id = [item for item in every if agent_id_of(item[0]) == agent]
    if by_id:
        return by_id[:1], True
    return [item for item in every if item[1].get("name") == agent], False


def reply_context(rec: Any) -> Optional[int]:
    """Input size of one transcript record, None when it is not a real model reply.

    The harness also writes assistant records for API errors (`model: "<synthetic>"`,
    `isApiErrorMessage`) with zero usage: they say nothing about the context.
    """
    if not isinstance(rec, dict) or rec.get("type") != "assistant" or rec.get("isApiErrorMessage"):
        return None
    message = rec.get("message")
    if not isinstance(message, dict) or message.get("model") == "<synthetic>":
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        context = sum(int(usage.get(k) or 0) for k in
                      ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    except (TypeError, ValueError):
        return None
    return context or None


def last_usage(log: Path) -> Optional[Dict[str, Any]]:
    """Context size and timestamp of the latest real model reply."""
    last = None
    with log.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:  # a line the harness is still writing
                continue
            context = reply_context(rec)
            if context is not None:
                last = {"context": context, "at": rec.get("timestamp")}
    return last


def session_problem(session: Optional[str]) -> Optional[str]:
    if not session:
        return "нет id сессии: ни --session, ни CLAUDE_CODE_SESSION_ID"
    if not SESSION_RE.match(session):
        return f"id сессии {session!r}: буквы, цифры, '-'"
    return None


def measure(agent: str, session: Optional[str], projects: Path) -> Dict[str, Any]:
    problem = session_problem(session)
    if problem:
        return {"agent": agent, "context": None, "reason": problem}
    dirs = f"{projects}/*/{session}/subagents"
    if not any(projects.glob(f"*/{session}/subagents")):
        return {"agent": agent, "context": None,
                "reason": f"транскрипт агента не найден: у сессии нет каталога субагентов {dirs}"}
    logs, by_id = transcripts(projects, session, agent)
    if not logs:
        return {"agent": agent, "context": None,
                "reason": f"транскрипт агента не найден: в {dirs} нет ни agent-{agent}.jsonl, ни "
                          f".meta.json с name «{agent}»; агент, заспавненный без name (Claude Code "
                          "2.1.300+), находится только по agentId из результата спавна (--list)"}
    log, meta = logs[0]
    found = {"agent": agent, "name": meta.get("name"), "id": agent_id_of(log),
             "others": 0 if by_id else len(logs) - 1}
    usage = last_usage(log)
    if usage is None:
        return {**found, "context": None, "reason": f"в транскрипте нет ответов: {log}"}
    return {**found, "context": usage["context"], "at": usage["at"], "transcript": str(log)}


def listing(session: Optional[str], projects: Path) -> Dict[str, Any]:
    problem = session_problem(session)
    if problem:
        return {"agents": None, "reason": problem}
    rows = []
    for log, meta in subagents(projects, session):
        try:
            usage = last_usage(log) or {}
        except OSError:
            usage = {}
        rows.append({"id": agent_id_of(log), "name": meta.get("name"),
                     "type": meta.get("agentType"), "description": meta.get("description"),
                     "context": usage.get("context"), "at": usage.get("at")})
    return {"agents": rows}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--session", default=None)
    ap.add_argument("--projects", default=None)
    ns = ap.parse_args(argv)
    if bool(ns.agent) == ns.list:
        ap.error("give AGENT (an id or a name) or --list")
    session = ns.session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if ns.list:
        try:
            result = listing(session, projects_dir(ns.projects))
        except Exception as e:  # the transcript format is the harness's, not ours: never a traceback
            result = {"agents": None, "reason": f"транскрипты не прочитаны: {type(e).__name__}: {e}"}
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["agents"] is not None else UNKNOWN
    try:
        result = measure(ns.agent, session, projects_dir(ns.projects))
    except Exception as e:  # the transcript format is the harness's, not ours: never a traceback
        result = {"agent": ns.agent, "context": None, "reason": f"транскрипт не прочитан: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["context"] is not None else UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
