#!/usr/bin/env python3
"""Resolve OMIXFlow adapters, agents, scripts and the base branch for a project.

    resolve.py adapter <port> [<name>] [--project DIR] [--json]
    resolve.py agent <role>            [--project DIR] [--json]
    resolve.py script <name>           [--project DIR]
    resolve.py base                    [--project DIR]

Without --json prints one path per line, base → leaf.
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
    ap.add_argument("kind", choices=["adapter", "agent", "script", "base"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)

    root = lib.find_project_root(ns.project)
    try:
        if ns.kind == "base":
            cfg = lib.load_config(root)
            base = lib.resolve_base_branch(cfg, root)
            if base is None:
                raise lib.OmixflowError("base branch не разрешается: проверь workspace.base")
            print(base)
            return 0

        if ns.kind == "script":
            if not ns.args:
                raise lib.OmixflowError("укажи имя скрипта")
            path = lib.resolve_script(ns.args[0], root)
            if path is None:
                raise lib.OmixflowError(f"скрипт {ns.args[0]} не найден ни в проекте, ни в плагине")
            print(path)
            return 0

        cfg = lib.load_config(root)

        if ns.kind == "agent":
            if not ns.args:
                raise lib.OmixflowError("укажи роль агента")
            info = lib.resolve_agent(ns.args[0], root, cfg)
            if ns.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                if info["agent"]:
                    print(info["agent"])
                for r in info["rules"]:
                    print(r)
            return 0 if info["agent"] else 1

        # adapter
        if not ns.args:
            raise lib.OmixflowError("укажи порт: " + ", ".join(lib.PORTS))
        port = ns.args[0]
        names = ns.args[1:] or lib.adapters_for(cfg, port)
        if not names:
            raise lib.OmixflowError(f"в конфиге нет адаптера для порта {port}")
        result = []
        for name in names:
            chain = lib.resolve_adapter(port, name, root)
            result.append({
                "port": port,
                "name": name,
                "chain": [{"layer": a.layer, "path": str(a.path), "extends": a.extends} for a in chain],
                "capabilities": lib.chain_capabilities(chain),
                "requires": lib.chain_requires(chain),
            })
        if ns.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for r in result:
                for a in r["chain"]:
                    print(a["path"])
        return 0
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
