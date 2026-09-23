#!/usr/bin/env python3
"""OMIXFlow doctor: check a project's config, adapters and environment.

    doctor.py [--project DIR] [--json] [--init [--force]]

Exit code: 0 all OK or WARN, 1 at least one FAIL, 2 usage/config error.
--init writes a draft .claude/omixflow/flow.yaml from the template plus
auto-detected values (never overwrites without --force) and then runs checks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Check:
    section: str
    name: str
    status: str
    detail: str = ""


class Doctor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.checks: List[Check] = []
        self.cfg: Optional[Dict[str, Any]] = None

    def add(self, section: str, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(section, name, status, detail))

    # ------------------------------------------------------------------ env
    def check_env(self) -> None:
        v = sys.version_info
        self.add("env", "python", OK if v >= (3, 9) else FAIL, f"{v.major}.{v.minor}.{v.micro}")
        self.add("env", "pyyaml", OK if lib.yaml is not None else FAIL,
                 "" if lib.yaml is not None else "python3 -m pip install pyyaml")
        self.add("env", "git", OK if lib.which("git") else FAIL)
        inside = lib.git(self.root, "rev-parse", "--is-inside-work-tree")
        self.add("env", "git repository", OK if inside == "true" else WARN,
                 str(self.root) if inside == "true" else "проект не в git: проверки веток пропущены")

    # --------------------------------------------------------------- config
    def check_config(self) -> bool:
        path = lib.config_path(self.root)
        if not path.exists():
            self.add("config", "flow.yaml", FAIL, f"нет файла {path}; создать: doctor.py --init")
            return False
        try:
            self.cfg = lib.load_config(self.root)
        except lib.OmixflowError as e:
            self.add("config", "flow.yaml", FAIL, str(e))
            return False
        errors = lib.validate_config(self.cfg)
        if errors:
            for e in errors:
                self.add("config", "schema", FAIL, e)
            return False
        self.add("config", "schema", OK, str(path))
        return True

    # ---------------------------------------------------------------- ports
    def check_ports(self) -> None:
        assert self.cfg is not None
        servers = lib.known_mcp_servers(self.root)
        for port in lib.PORTS:
            names = lib.adapters_for(self.cfg, port)
            if not names:
                self.add(f"port:{port}", "adapter", FAIL, "адаптер не задан в конфиге")
                continue
            try:
                contract = lib.port_contract(port)
            except lib.OmixflowError as e:
                self.add(f"port:{port}", "PORT.md", FAIL, str(e))
                continue
            for name in names:
                sec = f"port:{port}" if len(names) == 1 else f"port:{port}/{name}"
                try:
                    chain = lib.resolve_adapter(port, name, self.root)
                except lib.OmixflowError as e:
                    self.add(sec, "resolve", FAIL, str(e))
                    continue
                layers = " → ".join(f"{a.layer}:{a.name}" for a in chain)
                self.add(sec, "chain", OK, layers)
                leaf = chain[-1]
                if leaf.layer == "project" and not leaf.extends:
                    plugin_twin = lib.adapter_path(port, name, "plugin", self.root)
                    if plugin_twin.exists():
                        self.add(sec, "replacement", WARN,
                                 f"{leaf.path.name} заменяет плагинный адаптер целиком (нет extends); намеренно?")
                caps = lib.chain_capabilities(chain)
                missing = [c for c in contract["required"] if c not in caps]
                unknown = [c for c in caps if c not in contract["required"] + contract["optional"]]
                self.add(sec, "capabilities", FAIL if missing else OK,
                         ("не покрыты обязательные: " + ", ".join(missing)) if missing else ", ".join(caps))
                if unknown:
                    self.add(sec, "capabilities", WARN, "не описаны в PORT.md: " + ", ".join(unknown))
                req = lib.chain_requires(chain)
                for binary in req["bin"]:
                    self.add(sec, f"bin:{binary}", OK if lib.which(binary) else FAIL,
                             "" if lib.which(binary) else "не найден в PATH")
                for tool in req["tools"]:
                    server = lib.tool_server(tool)
                    if server is None:
                        self.add(sec, f"tool:{tool}", WARN, "не MCP-шаблон, проверить вручную")
                    elif server in servers:
                        self.add(sec, f"tool:{tool}", OK, f"сервер {server}")
                    else:
                        self.add(sec, f"tool:{tool}", FAIL,
                                 f"MCP-сервер {server} не найден в ~/.claude.json или .mcp.json")

    # ------------------------------------------------------------ workspace
    def check_workspace(self) -> None:
        assert self.cfg is not None
        inside = lib.git(self.root, "rev-parse", "--is-inside-work-tree") == "true"
        spec = str(lib.config_get(self.cfg, "workspace.base") or "auto")
        if inside:
            try:
                base = lib.resolve_base_branch(self.cfg, self.root)
            except lib.OmixflowError as e:
                self.add("workspace", "base", FAIL, str(e))
                base = None
            if base is None:
                self.add("workspace", "base", FAIL, f"{spec!r} не разрешается ни в одну ветку")
            elif lib.branch_exists(self.root, base):
                self.add("workspace", "base", OK, f"{spec} → {base}")
            else:
                self.add("workspace", "base", FAIL, f"{spec} → {base}, но такой ветки нет")
        else:
            self.add("workspace", "base", WARN, f"{spec}: не проверено, проект не в git")

        branch = str(lib.config_get(self.cfg, "workspace.branch") or "")
        self.add("workspace", "branch template", OK if "{id}" in branch else FAIL, branch)

        for sub in lib.config_get(self.cfg, "workspace.submodules") or []:
            path = sub.get("path") if isinstance(sub, dict) else None
            gm = self.root / ".gitmodules"
            declared = gm.exists() and path is not None and re.search(
                rf"path\s*=\s*{re.escape(path)}\s*$", gm.read_text(encoding="utf-8"), re.M)
            self.add("workspace", f"submodule:{path}", OK if declared else FAIL,
                     "" if declared else "не объявлен в .gitmodules")

        setup = lib.config_get(self.cfg, "workspace.setup")
        if setup:
            first = str(setup).split()[0]
            self.add("workspace", "setup", OK if lib.which(first) else WARN,
                     str(setup) if lib.which(first) else f"{first} не найден в PATH")
        else:
            self.add("workspace", "setup", WARN, "не задан: хук worktree зависимости не поставит")

        wt = lib.config_get(self.cfg, "workspace.worktree") or "optional"
        self.add("workspace", "worktree", OK, str(wt))

    # --------------------------------------------------------------- verify
    def check_verify(self) -> None:
        assert self.cfg is not None
        verify = self.cfg.get("verify") or {}
        for gate in lib.GATES:
            g = verify.get(gate)
            if not g:
                self.add("verify", gate, WARN if gate in ("typecheck", "lint") else OK, "не задан")
                continue
            cmd = str(g.get("cmd", ""))
            first = cmd.split()[0] if cmd.split() else ""
            found = bool(first) and lib.which(first) is not None
            extra = f"[{g.get('criterion')}]" + (" background" if g.get("background") else "")
            self.add("verify", gate, OK if found else WARN,
                     f"{cmd} {extra}" if found else f"{first!r} не найден в PATH: {cmd}")

    # ------------------------------------------------------------ artifacts
    def check_artifacts(self) -> None:
        assert self.cfg is not None
        d = str(lib.config_get(self.cfg, "artifacts.dir") or ".tasks")
        tracked = lib.config_get(self.cfg, "artifacts.tracked")
        tracked = True if tracked is None else bool(tracked)
        inside = lib.git(self.root, "rev-parse", "--is-inside-work-tree") == "true"
        if tracked and inside:
            probe = f"{d.rstrip('/')}/probe/state.yaml"
            ignored = lib.git(self.root, "check-ignore", "-q", probe)
            # git check-ignore exits 0 when ignored → our helper returns "" (not None)
            is_ignored = ignored is not None
            self.add("artifacts", "tracked", FAIL if is_ignored else OK,
                     f"{d} игнорируется .gitignore, а artifacts.tracked: true" if is_ignored else f"{d} версионируется")
        else:
            self.add("artifacts", "tracked", OK if not tracked else WARN,
                     f"{d}, tracked={str(tracked).lower()}")

    # --------------------------------------------------------------- agents
    def check_agents(self) -> None:
        assert self.cfg is not None
        mapping = self.cfg.get("agents") or {}
        plugin_agents = lib.PLUGIN_ROOT / "agents"
        has_plugin_agents = plugin_agents.exists() and any(plugin_agents.glob("*.md"))
        if not has_plugin_agents and not mapping:
            self.add("agents", "plugin", WARN, "в плагине пока нет агентов (скелет)")
        for role, target in mapping.items():
            info = lib.resolve_agent(str(role), self.root, self.cfg)
            self.add("agents", f"{role} → {target}", OK if info["agent"] else FAIL,
                     info["agent"] or f"нет файла .claude/agents/{target}.md")
        rules_dir = self.root / lib.OVERRIDE_REL / "agents"
        if rules_dir.exists():
            for f in sorted(rules_dir.glob("*.md")):
                meta, _ = lib.parse_frontmatter(f)
                ext = meta.get("extends")
                self.add("agents", f"rules:{f.stem}", OK if ext else WARN,
                         str(ext) if ext else "нет extends: правила не привяжутся к агенту плагина")

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        self.check_env()
        if self.check_config():
            self.check_ports()
            self.check_workspace()
            self.check_verify()
            self.check_artifacts()
            self.check_agents()
        return 1 if any(c.status == FAIL for c in self.checks) else 0


# ------------------------------------------------------------------- --init

def detect_defaults(root: Path) -> Dict[str, Any]:
    """Best-effort detection for a draft config; the skill refines it in dialog."""
    cfg: Dict[str, Any] = {
        "version": 1,
        "tracker": {"adapter": "none"},
        "forge": {"adapter": "none"},
        "lang": [],
        "workspace": {"base": "auto", "branch": "task/{id}", "worktree": "optional", "integration": "squash"},
        "verify": {},
        "artifacts": {"dir": ".tasks", "tracked": True},
    }
    servers = lib.known_mcp_servers(root)
    if "youtrack" in servers:
        cfg["tracker"] = {"adapter": "youtrack", "project": "CHANGE-ME"}
    if lib.which("gh") and lib.git(root, "remote", "get-url", "origin") and "github.com" in (lib.git(root, "remote", "get-url", "origin") or ""):
        cfg["forge"] = {"adapter": "github"}

    pkg = root / "package.json"
    if pkg.exists():
        cfg["lang"].append("ts")
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except json.JSONDecodeError:
            scripts = {}
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        run = f"{pm} run" if pm == "npm" else pm
        cfg["workspace"]["setup"] = f"{pm} install"
        for gate, candidates in (
            ("typecheck", ("check-types", "typecheck", "type-check", "tsc")),
            ("test", ("test",)),
            ("lint", ("lint",)),
            ("build", ("build",)),
            ("e2e", ("e2e", "test:e2e")),
        ):
            for s in candidates:
                if s in scripts:
                    cmd = f"{run} {s}"
                    if gate == "lint":
                        cfg["verify"][gate] = {"cmd": cmd, "criterion": "zero-diagnostics"}
                    elif gate in ("build", "e2e"):
                        cfg["verify"][gate] = {"cmd": cmd, "background": True}
                    else:
                        cfg["verify"][gate] = cmd
                    break
    for marker, lang, setup in (
        ("go.mod", "go", "go mod download"),
        ("Cargo.toml", "rust", "cargo fetch"),
        ("composer.json", "php", "composer install"),
    ):
        if (root / marker).exists():
            cfg["lang"].append(lang)
            cfg["workspace"].setdefault("setup", setup)
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        cfg["lang"].append("csharp")
        cfg["workspace"].setdefault("setup", "dotnet restore")
    if not cfg["lang"]:
        cfg["lang"] = ["ts"]
    if "test" not in cfg["verify"]:
        cfg["verify"]["test"] = "echo 'configure verify.test'"

    gm = root / ".gitmodules"
    if gm.exists():
        paths = re.findall(r"^\s*path\s*=\s*(\S+)", gm.read_text(encoding="utf-8"), re.M)
        cfg["workspace"]["submodules"] = [{"path": p, "readonly": True} for p in paths]
    return cfg


def write_init(root: Path, force: bool) -> Path:
    lib.require_yaml()
    path = lib.config_path(root)
    if path.exists() and not force:
        raise lib.OmixflowError(f"{path} уже существует; перезаписать: --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = detect_defaults(root)
    header = (
        "# OMIXFlow: конфиг проекта, черновик от doctor --init.\n"
        "# Значения с CHANGE-ME и закомментированные ключи из templates/flow.yaml плагина\n"
        "# уточняются вручную или скилом /omixflow:doctor. Схема: schema/flow.schema.json.\n\n"
    )
    body = lib.yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, default_flow_style=False)
    path.write_text(header + body, encoding="utf-8")
    return path


# --------------------------------------------------------------------- main

def render(checks: List[Check]) -> str:
    width = max((len(f"{c.section} {c.name}") for c in checks), default=20)
    lines = []
    for c in checks:
        label = f"{c.section} {c.name}".ljust(width)
        lines.append(f"{c.status:<4} {label}  {c.detail}".rstrip())
    fails = sum(1 for c in checks if c.status == FAIL)
    warns = sum(1 for c in checks if c.status == WARN)
    lines.append("")
    lines.append(f"итого: {len(checks)} проверок, {fails} FAIL, {warns} WARN")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--force", action="store_true")
    ns = ap.parse_args(argv)
    root = lib.find_project_root(ns.project)

    if ns.init:
        try:
            path = write_init(root, ns.force)
        except lib.OmixflowError as e:
            print(f"omixflow: {e}", file=sys.stderr)
            return 2
        if not ns.json:
            print(f"создан черновик: {path}\n")

    doc = Doctor(root)
    code = doc.run()
    if ns.json:
        print(json.dumps({"project": str(root), "exit": code,
                          "checks": [asdict(c) for c in doc.checks]}, ensure_ascii=False, indent=2))
    else:
        print(f"OMIXFlow doctor: {root}\n")
        print(render(doc.checks))
    return code


if __name__ == "__main__":
    sys.exit(main())
