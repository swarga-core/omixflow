#!/usr/bin/env python3
"""Resolve OMIXFlow adapters, agents, scripts and the base branch for a project.

    resolve.py adapter <port> [<name>] [--project DIR] [--json]
    resolve.py adapter-script <port> <key> [--project DIR]   # script declared by the port's adapter
    resolve.py agent <role>            [--project DIR] [--json]
    resolve.py script <name>           [--project DIR]
    resolve.py base                    [--project DIR]
    resolve.py repo NAME               [--project DIR] [--json]   # workspace.repos entry, ref → sha
    resolve.py repo --list             [--project DIR]            # names, comma-separated
    resolve.py route POINT             [--project DIR]            # lead route: JSON {point, kind, mode, timeout}
    resolve.py lead                    [--project DIR]            # lead settings: JSON {default, timeout, stall, actions, notify}
    resolve.py verify --at MOMENT      [--project DIR] [--task DIR | --base B] [--since REF] [--paths P...]
                                       [--also GATE...]
        gates and orchestrator checks due at MOMENT (step | review | delivery | accept):
        JSON {at, head, since, files, areas, gates, checks, on_demand, skipped}
        (adapters/lang/PORT.md, «Гейты», «Проверки оркестратора»). review and delivery
        need the branch base: --base, or --task with `base` in its state.yaml; --task also
        gives `checks` (the commit of each check's last green full run) for delivery and,
        without --project, the project root. --since REF counts the changes from REF (a sync
        merge: HEAD, what the base brings in). --paths plans for these paths instead of the
        tree's changes (the files of plan steps): checks of every moment, each with its `at`.
        --also GATE puts a declared gate into `gates` whatever the set says, with `"also": true`
        (the gates a plan step's test checkpoint names); an undeclared port gate is listed in
        `also_missing`, a name outside the port's gates is an error (exit 2).

Without --json prints one path per line, base → leaf.

--fallback-project HOME (with --project FOREIGN) resolves for a foreign repository
from workspace.repos. FOREIGN is the root itself; only FOREIGN/.claude/omixflow/flow.yaml
counts as its config (no ancestor walk). Without that config: adapter names come
from HOME, each resolving to the FOREIGN project-layer file when present, else as
HOME would; `base` is `auto` in the FOREIGN repository. `agent` always resolves the
agent against HOME (only home agents are spawnable) with rules from FOREIGN.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402


def print_agent(info: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(info["subagent_type"])
        if info["agent"]:
            print(info["agent"])
        for r in info["rules"]:
            print(r)
    return 0 if info["agent"] else 1


def cmd_repo(ns: argparse.Namespace, root: Path) -> int:
    """workspace.repos of the home config: the list of names, or one entry resolved."""
    repos = lib.config_get(lib.load_config(root), "workspace.repos") or {}
    if ns.list:
        print(",".join(repos))
        return 0
    if len(ns.args) != 1:
        raise lib.OmixflowError("укажи имя репозитория: repo NAME или repo --list")
    name = ns.args[0]
    if name not in repos:
        raise lib.OmixflowError(f"workspace.repos.{name} нет в конфиге; есть: {', '.join(repos) or 'ничего'}")
    entry = repos[name] or {}
    path = (root / str(entry.get("path", ""))).resolve()
    ref = str(entry.get("ref") or "auto")
    is_repo = path.is_dir() and lib.git(path, "rev-parse", "--git-dir") is not None
    sha = lib.resolve_repo_ref(path, ref) if is_repo else None
    state = lib.repo_checkout_state(path) if is_repo else {"head": None, "dirty": False}
    info = {"name": name, "path": str(path), "remote": entry.get("remote"), "ref": ref, "sha": sha,
            "head": state["head"], "dirty": state["dirty"], "has_config": lib.config_path(path).exists()}
    if ns.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(sha or "null")
    return 0 if sha else 1


def cmd_verify(ns: argparse.Namespace, root: Path) -> int:
    base, checked = ns.base, None
    if ns.task is not None:
        lib.require_yaml()
        path = Path(ns.task).resolve() / "state.yaml"
        if not path.exists():
            raise lib.OmixflowError(f"нет {path}")
        state = lib.yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        base = base or state.get("base")
        checked = state.get("checks") or {}
    plan = lib.verify_plan(lib.load_config(root), root, ns.at, base, checked, ns.paths, ns.since, ns.also)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["adapter", "adapter-script", "agent", "script", "base", "repo", "route", "lead",
                                     "verify"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--fallback-project", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--at", choices=lib.MOMENTS, default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--task", type=Path, default=None)
    ap.add_argument("--paths", nargs="+", default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--also", nargs="+", action="extend", default=None)
    ns = ap.parse_args(argv)

    foreign_bare = False  # foreign repository without its own flow.yaml
    home: Optional[Path] = None
    if ns.fallback_project is not None:
        root = (ns.project or Path.cwd()).resolve()
        home = lib.find_project_root(ns.fallback_project)
        foreign_bare = not lib.config_path(root).exists()
    else:
        root = lib.find_project_root(ns.project if ns.project is not None or ns.task is None else ns.task)
    try:
        if ns.kind == "repo":
            return cmd_repo(ns, root)

        if ns.kind == "verify":
            if ns.at is None:
                raise lib.OmixflowError("укажи момент: verify --at " + "|".join(lib.MOMENTS))
            return cmd_verify(ns, root)

        if ns.kind == "lead":
            print(json.dumps(lib.lead_settings(lib.load_config(root)), ensure_ascii=False))
            return 0

        if ns.kind == "route":
            if len(ns.args) != 1:
                raise lib.OmixflowError("укажи точку решения: route POINT")
            print(json.dumps(lib.lead_route(lib.load_config(root), ns.args[0]), ensure_ascii=False))
            return 0

        if ns.kind == "base":
            cfg = {} if foreign_bare else lib.load_config(root)
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

        if ns.kind == "agent" and home is not None:
            if not ns.args:
                raise lib.OmixflowError("укажи роль агента")
            info = lib.resolve_agent(ns.args[0], home, lib.load_config(home))
            rules = root / lib.OVERRIDE_REL / "agents" / f"{ns.args[0]}.md"
            info["rules"] = [str(rules)] if rules.exists() else []
            return print_agent(info, ns.json)

        if foreign_bare:
            assert home is not None
            cfg = lib.load_config(home)
            print(f"omixflow: в {root} нет flow.yaml; адаптеры по конфигу {home}", file=sys.stderr)
        else:
            cfg = lib.load_config(root)

        def adapter_root(port: str, name: str) -> Path:
            """Where the adapter chain resolves: the FOREIGN project layer when it has the
            file, else HOME for a foreign repo without config, else the project itself."""
            if foreign_bare and not lib.adapter_path(port, name, "project", root).exists():
                assert home is not None
                return home
            return root

        if ns.kind == "adapter-script":
            if len(ns.args) < 2:
                raise lib.OmixflowError("укажи порт и ключ скрипта: adapter-script forge pr")
            port, key = ns.args[0], ns.args[1]
            names = lib.adapters_for(cfg, port)
            if not names:
                raise lib.OmixflowError(f"в конфиге нет адаптера для порта {port}")
            path = lib.resolve_adapter_script(port, names[0], key, adapter_root(port, names[0]))
            if path is None:
                raise lib.OmixflowError(f"адаптер {port}/{names[0]} не объявляет скрипт {key!r}")
            print(path)
            return 0

        if ns.kind == "agent":
            if not ns.args:
                raise lib.OmixflowError("укажи роль агента")
            info = lib.resolve_agent(ns.args[0], root, cfg)
            return print_agent(info, ns.json)

        # adapter
        if not ns.args:
            raise lib.OmixflowError("укажи порт: " + ", ".join(lib.PORTS))
        port = ns.args[0]
        names = ns.args[1:] or lib.adapters_for(cfg, port)
        if not names:
            raise lib.OmixflowError(f"в конфиге нет адаптера для порта {port}")
        result = []
        for name in names:
            chain = lib.resolve_adapter(port, name, adapter_root(port, name))
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
