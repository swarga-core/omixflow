#!/usr/bin/env python3
"""Print a value from the project's flow.yaml by dotted key.

    cfg.py workspace.setup [--project DIR]

Scalars print as-is, lists and objects as JSON, a missing key prints "null"
and exits 1. Used by hooks and skills that need a single value.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("key")
    ap.add_argument("--project", type=Path, default=None)
    ns = ap.parse_args(argv)
    root = lib.find_project_root(ns.project)
    try:
        cfg = lib.load_config(root)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2
    value = lib.config_get(cfg, ns.key)
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
