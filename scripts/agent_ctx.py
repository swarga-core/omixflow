#!/usr/bin/env python3
"""Context size of a live agent of this session, read from its transcript.

    agent_ctx.py NAME [--session ID] [--projects DIR]

The rotation threshold (protocol/tiers.md, «Смена агента по ходу задачи») needs the
agent's context size. A named agent in agent-team mode reports the end of its turn with
an idle notice that carries no usage, so the size comes from the transcript the harness
keeps for every subagent: `{projects}/*/{session}/subagents/*.meta.json` names the agent,
the `.jsonl` next to it holds its messages. The size is the input of the agent's latest
model reply: `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`;
API-error records the harness writes with zero usage are skipped.

--session defaults to $CLAUDE_CODE_SESSION_ID, --projects to $CLAUDE_CONFIG_DIR/projects
or ~/.claude/projects. Several transcripts with NAME: the latest one counts.

Prints one JSON line. Known: `{"name", "context", "at", "transcript"}`, exit 0.
Unknown (no session id, no transcript, no reply yet, unreadable transcript):
`{"name", "context": null, "reason"}`, exit 3; the caller falls back as tiers.md says.
Usage error: exit 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

UNKNOWN = 3
SESSION_RE = re.compile(r"^[A-Za-z0-9-]+$")


def projects_dir(given: Optional[str]) -> Path:
    if given:
        return Path(given).expanduser()
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "projects"


def transcripts(projects: Path, session: str, name: str) -> List[Path]:
    """Transcripts of the agents called NAME in SESSION, latest first."""
    found = []
    for meta in projects.glob(f"*/{session}/subagents/*.meta.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        log = meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl")
        if isinstance(data, dict) and data.get("name") == name and log.is_file():
            found.append(log)
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


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


def measure(name: str, session: Optional[str], projects: Path) -> Dict[str, Any]:
    if not session:
        return {"name": name, "context": None,
                "reason": "нет id сессии: ни --session, ни CLAUDE_CODE_SESSION_ID"}
    if not SESSION_RE.match(session):
        return {"name": name, "context": None, "reason": f"id сессии {session!r}: буквы, цифры, '-'"}
    logs = transcripts(projects, session, name)
    if not logs:
        return {"name": name, "context": None,
                "reason": f"транскрипт агента не найден: {projects}/*/{session}/subagents"}
    usage = last_usage(logs[0])
    if usage is None:
        return {"name": name, "context": None, "reason": f"в транскрипте нет ответов: {logs[0]}"}
    return {"name": name, "context": usage["context"], "at": usage["at"], "transcript": str(logs[0])}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--session", default=None)
    ap.add_argument("--projects", default=None)
    ns = ap.parse_args(argv)
    session = ns.session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    try:
        result = measure(ns.name, session, projects_dir(ns.projects))
    except Exception as e:  # the transcript format is the harness's, not ours: never a traceback
        result = {"name": ns.name, "context": None, "reason": f"транскрипт не прочитан: {type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["context"] is not None else UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
