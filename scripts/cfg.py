#!/usr/bin/env python3
"""Print a value from the project's flow.yaml by dotted key.

    cfg.py workspace.setup [--project DIR] [--raw]
    cfg.py get workspace.setup             # `get` before the key is tolerated

A key missing from flow.yaml yields its default from schema/flow.schema.json
(protocol/phases.md: «дефолты в схеме»); an object gets its default children under the
configured ones. `--raw` reads flow.yaml only. Scalars print as-is, lists and objects as
JSON; a key with neither a value nor a default prints "null" and exits 1. Used by hooks
and skills that need a single value.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", nargs="+", help="dotted key; a leading `get` is ignored")
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--raw", action="store_true", help="flow.yaml only, without schema defaults")
    ns = ap.parse_args(argv)
    words = ns.key[1:] if ns.key[0] == "get" and len(ns.key) == 2 else ns.key
    if len(words) != 1:
        ap.error("ожидается один ключ: cfg.py KEY")
    root = lib.find_project_root(ns.project)
    try:
        cfg = lib.load_config(root)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2
    value = lib.config_value(cfg, words[0], defaults=not ns.raw)
    if value is None:
        print("null")
        return 1
    if isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
