#!/usr/bin/env python3
"""OMIXFlow shared helpers: project config, light schema validation, adapter
chain resolution, base-branch resolution.

Python 3.9+. The only third-party dependency is PyYAML.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PORTS = ("tracker", "forge", "lang", "workspace")
OVERRIDE_REL = Path(".claude") / "omixflow"
CONFIG_REL = OVERRIDE_REL / "flow.yaml"
SCHEMA_PATH = PLUGIN_ROOT / "schema" / "flow.schema.json"
TEMPLATE_PATH = PLUGIN_ROOT / "templates" / "flow.yaml"
GATES = ("typecheck", "test", "lint", "build", "e2e", "visual")
ROLES = ("researcher", "architect", "coder", "tester", "reviewer", "web-fetcher")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # part slugs, workspace.repos names


class OmixflowError(Exception):
    """Any error the scripts report to the user."""


# --------------------------------------------------------------------------- io

def require_yaml() -> None:
    if yaml is None:
        raise OmixflowError("PyYAML не установлен: python3 -m pip install pyyaml")


def git(root: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.stdout.strip()


def find_project_root(start: Optional[Path] = None) -> Path:
    """The project root is the nearest directory holding .claude/omixflow/flow.yaml,
    starting from `start` (explicit --project wins over the git toplevel, so a
    fixture nested inside another repository still resolves to itself). Without
    a config anywhere, fall back to the git toplevel, then to `start`."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / CONFIG_REL).exists():
            return candidate
    top = git(start, "rev-parse", "--show-toplevel")
    return Path(top) if top else start


def config_path(root: Path) -> Path:
    return root / CONFIG_REL


# ----------------------------------------------------------------------- config

def normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Expand shorthands so that schema validation and consumers see one shape."""
    cfg = dict(cfg)
    for port in ("tracker", "forge"):
        if isinstance(cfg.get(port), str):
            cfg[port] = {"adapter": cfg[port]}
    lang = cfg.get("lang")
    if isinstance(lang, str):
        cfg["lang"] = [lang]
    ws = cfg.get("workspace")
    if isinstance(ws, dict):
        ws = dict(ws)
        ws.setdefault("adapter", "git")
        cfg["workspace"] = ws
    verify = cfg.get("verify")
    if isinstance(verify, dict):
        norm: Dict[str, Any] = {}
        for name, gate in verify.items():
            if isinstance(gate, str):
                norm[name] = {"cmd": gate, "criterion": "exit-code"}
            elif isinstance(gate, dict):
                g = dict(gate)
                g.setdefault("criterion", "exit-code")
                norm[name] = g
            else:
                norm[name] = gate
        cfg["verify"] = norm
    return cfg


def load_config(root: Path) -> Dict[str, Any]:
    require_yaml()
    path = config_path(root)
    if not path.exists():
        raise OmixflowError(f"конфиг не найден: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise OmixflowError(f"конфиг должен быть YAML-объектом: {path}")
    return normalize_config(data)


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def config_get(cfg: Dict[str, Any], dotted: str) -> Any:
    """Keys may contain dots themselves (`lead.policy.tracker.comment`): at each object
    level the longest matching key wins."""
    parts = dotted.split(".")
    cur: Any = cfg
    i = 0
    while i < len(parts):
        if isinstance(cur, dict):
            for j in range(len(parts), i, -1):
                key = ".".join(parts[i:j])
                if key in cur:
                    cur, i = cur[key], j
                    break
            else:
                return None
        elif isinstance(cur, list) and parts[i].isdigit() and int(parts[i]) < len(cur):
            cur, i = cur[int(parts[i])], i + 1
        else:
            return None
    return cur


# ------------------------------------------------------------- light validator

_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _resolve_ref(schema: Dict[str, Any], ref: str) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise OmixflowError(f"неподдерживаемый $ref: {ref}")
    node: Any = schema
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(instance: Any, schema: Dict[str, Any], node: Optional[Dict[str, Any]] = None,
             path: str = "$") -> List[str]:
    """Validate against the subset of JSON Schema draft-07 used by flow.schema.json:
    type, required, properties, additionalProperties, propertyNames, enum, items,
    pattern, minimum, minItems, $ref, definitions."""
    node = schema if node is None else node
    errors: List[str] = []
    if "$ref" in node:
        node = _resolve_ref(schema, node["$ref"])

    typ = node.get("type")
    if typ is not None:
        expected = _TYPES[typ]
        ok = isinstance(instance, expected)
        if typ in ("integer", "number") and isinstance(instance, bool):
            ok = False
        if not ok:
            errors.append(f"{path}: ожидается {typ}, получено {type(instance).__name__}")
            return errors

    if "enum" in node and instance not in node["enum"]:
        errors.append(f"{path}: значение {instance!r} не из {node['enum']}")

    if isinstance(instance, str) and "pattern" in node:
        if not re.search(node["pattern"], instance):
            errors.append(f"{path}: {instance!r} не соответствует шаблону {node['pattern']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in node and instance < node["minimum"]:
            errors.append(f"{path}: {instance} меньше минимума {node['minimum']}")

    if isinstance(instance, list):
        if "minItems" in node and len(instance) < node["minItems"]:
            errors.append(f"{path}: минимум {node['minItems']} элементов")
        if "items" in node:
            for i, item in enumerate(instance):
                errors.extend(validate(item, schema, node["items"], f"{path}[{i}]"))

    if isinstance(instance, dict):
        props = node.get("properties", {})
        for req in node.get("required", []):
            if req not in instance:
                errors.append(f"{path}: отсутствует обязательный ключ {req!r}")
        addl = node.get("additionalProperties", True)
        names = node.get("propertyNames")
        for key, value in instance.items():
            if names is not None:
                errors.extend(validate(key, schema, names, f"{path}.{key} (ключ)"))
            if key in props:
                errors.extend(validate(value, schema, props[key], f"{path}.{key}"))
            elif addl is False:
                errors.append(f"{path}: неизвестный ключ {key!r}")
            elif isinstance(addl, dict):
                errors.extend(validate(value, schema, addl, f"{path}.{key}"))
    return errors


def validate_config(cfg: Dict[str, Any]) -> List[str]:
    return validate(cfg, load_schema())


# ------------------------------------------------------------ managed blocks

def _block_res(kind: str) -> Tuple["re.Pattern[str]", "re.Pattern[str]"]:
    k = re.escape(kind)
    start = re.compile(rf"^[ \t]*<!--[ \t]*omixflow:{k}:start((?:[ \t]+[^\s>]+)*)[ \t]*-->[ \t\r]*$", re.M)
    end = re.compile(rf"^[ \t]*<!--[ \t]*omixflow:{k}:end[ \t]*-->[ \t\r]*$", re.M)
    return start, end


def outside_dir(files: List[str], directory: str) -> List[str]:
    """Files not under `directory` (e.g. the artifacts directory)."""
    d = directory.strip("/")
    return [f for f in files if not (f == d or f.startswith(d + "/"))]


def replace_managed_block(text: str, kind: str, body: str, before: Optional[str] = None) -> str:
    """Replace the content between whole-line markers `<!-- omixflow:{kind}:start -->` and
    `<!-- omixflow:{kind}:end -->` (port tracker, «Управляемые блоки»), keeping the marker
    lines verbatim. Without a block: insert it before the first line equal to `before`
    (e.g. the local tracker's `## Журнал`), else append it at the end."""
    start_re, end_re = _block_res(kind)
    starts = list(start_re.finditer(text))
    if len(starts) > 1:
        raise OmixflowError(f"блок omixflow:{kind}: маркер начала встречается {len(starts)} раза")
    content = body.rstrip("\n") + "\n"
    block = f"<!-- omixflow:{kind}:start -->\n{content}<!-- omixflow:{kind}:end -->\n"
    if not starts:
        if before is not None:
            lines = text.splitlines(keepends=True)
            for i, line in enumerate(lines):
                if line.strip() == before.strip():
                    return "".join(lines[:i]) + block + "\n" + "".join(lines[i:])
        return (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    end = end_re.search(text, starts[0].end())
    if end is None:
        raise OmixflowError(f"блок omixflow:{kind}: нет маркера конца")
    return text[:starts[0].end()] + "\n" + content + text[end.start():]


# ------------------------------------------------------------ decision points

DIALOG_PATH = PLUGIN_ROOT / "protocol" / "dialog.md"
POINTS_HEADER = "| id | Вид | Точка | Режим |"
POINT_KINDS = ("содержание", "маршрут", "внешнее")


LEAD_DEFAULT_MODE = "developer"   # mirrors lead.default in the schema (tests/test_lint.py)
LEAD_DEFAULT_TIMEOUT = "10m"      # mirrors lead.timeout in the schema
LEAD_DEFAULT_STALL = "15m"        # mirrors lead.stall in the schema
LEAD_DEFAULT_ACTIONS = {"backlog": "lead", "memory": "lead"}  # mirrors lead.actions in the schema
_DURATION_RE = re.compile(r"^([1-9][0-9]*)([smh])$")


def duration_seconds(text: str) -> int:
    m = _DURATION_RE.match(text)
    if not m:
        raise OmixflowError(f"длительность вида 30s, 10m или 1h, получено {text!r}")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]


def lead_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """lead.default, lead.timeout, lead.stall, lead.actions and lead.notify with defaults;
    durations in seconds."""
    lead = cfg.get("lead") or {}
    return {"default": lead.get("default") or LEAD_DEFAULT_MODE,
            "timeout": duration_seconds(str(lead.get("timeout") or LEAD_DEFAULT_TIMEOUT)),
            "stall": duration_seconds(str(lead.get("stall") or LEAD_DEFAULT_STALL)),
            "actions": {**LEAD_DEFAULT_ACTIONS, **(lead.get("actions") or {})},
            "notify": list(lead.get("notify") or [])}


def lead_route(cfg: Dict[str, Any], point: str) -> Dict[str, Any]:
    """Route of a question at a decision point for a session with a lead (protocol/lead.md):
    lead.policy.{point}, else lead.default, else developer; timeout in seconds."""
    kinds = dict(decision_points())
    if point not in kinds:
        raise OmixflowError(f"неизвестная точка решения {point!r}; есть: {', '.join(kinds)}")
    settings = lead_settings(cfg)
    mode = ((cfg.get("lead") or {}).get("policy") or {}).get(point) or settings["default"]
    return {"point": point, "kind": kinds[point], "mode": mode, "timeout": settings["timeout"]}


def decision_points(path: Path = DIALOG_PATH) -> List[Tuple[str, str]]:
    """(id, kind) of every decision point, in table order, from protocol/dialog.md."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == POINTS_HEADER]
    if len(starts) != 1:
        raise OmixflowError(f"{path}: нужна ровно одна таблица с заголовком {POINTS_HEADER!r}")
    points: List[Tuple[str, str]] = []
    for line in lines[starts[0] + 2:]:
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not re.fullmatch(r"`[^`]+`", cells[0]):
            raise OmixflowError(f"{path}: строка точки решения не по формату: {line.strip()}")
        points.append((cells[0].strip("`"), cells[1]))
    return points


# ---------------------------------------------------------------- frontmatter

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)


def parse_frontmatter(path: Path) -> Tuple[Dict[str, Any], str]:
    require_yaml()
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise OmixflowError(f"фронтматтер должен быть объектом: {path}")
    return meta, text[m.end():]


# ------------------------------------------------------------------- adapters

@dataclass
class AdapterFile:
    port: str
    name: str
    layer: str  # "plugin" | "project"
    path: Path
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def capabilities(self) -> List[str]:
        caps = self.meta.get("capabilities") or []
        return [str(c) for c in caps]

    @property
    def extends(self) -> Optional[str]:
        ext = self.meta.get("extends")
        return str(ext) if ext else None


def adapter_path(port: str, name: str, layer: str, root: Path) -> Path:
    if layer == "plugin":
        return PLUGIN_ROOT / "adapters" / port / f"{name}.md"
    if layer == "project":
        return root / OVERRIDE_REL / port / f"{name}.md"
    raise OmixflowError(f"неизвестный слой адаптера: {layer}")


def _load_adapter(port: str, name: str, layer: str, root: Path) -> AdapterFile:
    path = adapter_path(port, name, layer, root)
    if not path.exists():
        raise OmixflowError(f"адаптер {layer}:{port}/{name} не найден: {path}")
    meta, _ = parse_frontmatter(path)
    declared_port = meta.get("port")
    if declared_port != port:
        raise OmixflowError(f"{path}: фронтматтер port={declared_port!r}, ожидается {port!r}")
    declared_name = meta.get("name")
    if declared_name and declared_name != name:
        raise OmixflowError(f"{path}: фронтматтер name={declared_name!r}, ожидается {name!r}")
    return AdapterFile(port=port, name=name, layer=layer, path=path, meta=meta)


def resolve_adapter(port: str, name: str, root: Path,
                    layer: Optional[str] = None,
                    _seen: Optional[List[str]] = None) -> List[AdapterFile]:
    """Return the adapter chain base → leaf. The leaf is the project file when it
    exists, otherwise the plugin file; `extends` links are followed recursively."""
    if port not in PORTS:
        raise OmixflowError(f"неизвестный порт: {port} (ожидается один из {', '.join(PORTS)})")
    _seen = list(_seen or [])
    if layer is None:
        layer = "project" if adapter_path(port, name, "project", root).exists() else "plugin"
    key = f"{layer}:{port}/{name}"
    if key in _seen:
        raise OmixflowError(f"цикл extends: {' -> '.join(_seen + [key])}")
    _seen.append(key)
    leaf = _load_adapter(port, name, layer, root)
    chain: List[AdapterFile] = []
    if leaf.extends:
        base_layer, sep, base_name = leaf.extends.partition(":")
        if not sep or base_layer not in ("omixflow", "project"):
            raise OmixflowError(
                f"{leaf.path}: extends должен иметь форму omixflow:{{name}} или project:{{name}}, "
                f"получено {leaf.extends!r}")
        base_layer = "plugin" if base_layer == "omixflow" else "project"
        chain = resolve_adapter(port, base_name, root, base_layer, _seen)
    chain.append(leaf)
    return chain


def chain_capabilities(chain: List[AdapterFile]) -> List[str]:
    seen: List[str] = []
    for a in chain:
        for c in a.capabilities:
            if c not in seen:
                seen.append(c)
    return seen


def chain_requires(chain: List[AdapterFile]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"tools": [], "bin": []}
    for a in chain:
        req = a.meta.get("requires") or {}
        for kind in ("tools", "bin"):
            for item in req.get(kind) or []:
                if item not in out[kind]:
                    out[kind].append(str(item))
    return out


def port_contract(port: str) -> Dict[str, Any]:
    path = PLUGIN_ROOT / "adapters" / port / "PORT.md"
    if not path.exists():
        raise OmixflowError(f"контракт порта не найден: {path}")
    meta, _ = parse_frontmatter(path)
    return {
        "required": [str(x) for x in meta.get("required") or []],
        "optional": [str(x) for x in meta.get("optional") or []],
        "config": [str(x) for x in meta.get("config") or []],
        "path": path,
    }


def adapters_for(cfg: Dict[str, Any], port: str) -> List[str]:
    """Adapter names configured for a port (lang may list several)."""
    if port == "lang":
        return [str(x) for x in cfg.get("lang") or []]
    section = cfg.get(port) or {}
    name = section.get("adapter") if isinstance(section, dict) else None
    if not name and port == "workspace":
        name = "git"
    return [str(name)] if name else []


# --------------------------------------------------------------------- agents

def resolve_agent(role: str, root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Which agent file serves a role, and which project rules extend it.

    Replacement happens two ways: an explicit mapping in flow.yaml
    (`agents: {coder: my-coder}` → .claude/agents/my-coder.md) or, as Claude Code
    itself does, a project agent with the same name (.claude/agents/coder.md
    overrides the plugin's omixflow:coder). `subagent_type` is the scoped plugin
    name for plugin agents and the bare name for project agents."""
    mapping = cfg.get("agents") or {}
    target = str(mapping.get(role, role))
    project_agent = root / ".claude" / "agents" / f"{target}.md"
    plugin_agent = PLUGIN_ROOT / "agents" / f"{target}.md"
    if project_agent.exists():
        agent, layer, replaced = project_agent, "project", True
        subagent_type = target
    else:
        agent, layer, replaced = plugin_agent, "plugin", False
        subagent_type = f"omixflow:{target}"
    rules = root / OVERRIDE_REL / "agents" / f"{role}.md"
    return {
        "role": role,
        "agent": str(agent) if agent.exists() else None,
        "subagent_type": subagent_type,
        "layer": layer,
        "replaced": replaced,
        "rules": [str(rules)] if rules.exists() else [],
    }


def resolve_script(name: str, root: Path) -> Optional[Path]:
    project = root / OVERRIDE_REL / "scripts" / name
    if project.exists():
        return project
    plugin = PLUGIN_ROOT / "scripts" / name
    return plugin if plugin.exists() else None


def resolve_adapter_script(port: str, name: str, key: str, root: Path) -> Optional[Path]:
    """A script declared in an adapter's `scripts:` map, resolved relative to that
    adapter file. The leaf of the chain wins, so a project adapter can shadow a
    plugin script by declaring the same key."""
    chain = resolve_adapter(port, name, root)
    for adapter in reversed(chain):
        scripts = adapter.meta.get("scripts") or {}
        rel = scripts.get(key)
        if rel:
            path = (adapter.path.parent / str(rel)).resolve()
            if not path.exists():
                raise OmixflowError(f"{adapter.path}: scripts.{key} указывает на несуществующий {path}")
            return path
    return None


def artifacts_script(root: Path, cfg: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """The `scripts.artifacts` of the tracker adapter when it declares the capability
    `artifacts` (port tracker, «Артефакты в задаче»), else None."""
    cfg = cfg if cfg is not None else load_config(root)
    for name in adapters_for(cfg, "tracker"):
        if "artifacts" in chain_capabilities(resolve_adapter("tracker", name, root)):
            return resolve_adapter_script("tracker", name, "artifacts", root)
    return None


# ---------------------------------------------------------------- base branch

_NUM_RE = re.compile(r"\d+")


def _version_key(name: str) -> Tuple[int, ...]:
    return tuple(int(n) for n in _NUM_RE.findall(name))


def list_branches(root: Path) -> List[str]:
    out = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin")
    if not out:
        return []
    names: List[str] = []
    for line in out.splitlines():
        n = line.strip()
        if n.startswith("origin/"):
            n = n[len("origin/"):]
        if n in ("HEAD", "") or n in names:
            continue
        names.append(n)
    return names


def resolve_base_branch(cfg: Dict[str, Any], root: Path) -> Optional[str]:
    spec = str(config_get(cfg, "workspace.base") or "auto")
    if spec == "auto":
        head = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
        if head:
            return head[len("origin/"):] if head.startswith("origin/") else head
        for fallback in ("main", "master"):
            if branch_exists(root, fallback):
                return fallback
        return None
    if ":" in spec:
        pattern, mode = spec.rsplit(":", 1)
        if mode != "latest":
            raise OmixflowError(f"workspace.base: неизвестный режим {mode!r} (поддерживается latest)")
        matches = [b for b in list_branches(root) if fnmatch.fnmatch(b, pattern)]
        if not matches:
            return None
        return sorted(matches, key=_version_key)[-1]
    return spec


def branch_exists(root: Path, name: str) -> bool:
    return (git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None
            or git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}") is not None)


# ------------------------------------------------------------ foreign repos

def _commit_of(root: Path, ref: str) -> Optional[str]:
    return git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") or None


def resolve_repo_ref(repo_root: Path, ref: Optional[str],
                     fallback_cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Full commit sha of `ref` in a foreign repository (workspace.repos), or None.

    `auto`/absent means the foreign project's base branch: its own flow.yaml via
    resolve_base_branch, else `fallback_cfg` (default: none, i.e. the remote default
    branch, then main/master). A branch prefers `origin/{name}` over the local branch
    so that the snapshot is reproducible for other executors; tags and shas resolve as
    given. No fetch."""
    if not ref or ref == "auto":
        cfg = load_config(repo_root) if config_path(repo_root).exists() else (fallback_cfg or {})
        ref = resolve_base_branch(cfg, repo_root)
        if not ref:
            return None
    if ref.startswith("-"):
        return None
    for candidate in (f"refs/remotes/origin/{ref}", f"refs/heads/{ref}", ref):
        sha = _commit_of(repo_root, candidate)
        if sha:
            return sha
    return None


def repo_checkout_state(repo_root: Path) -> Dict[str, Any]:
    """HEAD sha and whether tracked files differ from it. Untracked files and
    `.claude/worktrees/` (research-worktrees live there) do not make a checkout dirty."""
    head = _commit_of(repo_root, "HEAD")
    status = git(repo_root, "status", "--porcelain", "--untracked-files=no", "--",
                 ".", ":(exclude).claude/worktrees")
    return {"head": head, "dirty": bool(status)}


_SCP_RE = re.compile(r"^(?:[^@/:]+@)?([^:/]+):(?!//)(.+)$")


def normalize_remote(url: str) -> str:
    """`host/owner/repo` identity of a remote URL: ssh and https forms of the same
    repository compare equal (scheme, user, port, trailing `.git` and `/` dropped,
    host lower-cased)."""
    u = url.strip()
    m = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.*)$", u, re.I)
    if m:
        host, path = m.groups()
    else:
        m = _SCP_RE.match(u)
        if not m:
            return u.rstrip("/")
        host, path = m.groups()
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{host.lower()}/{path.strip('/')}"


# -------------------------------------------------------------- mcp discovery

def known_mcp_servers(root: Path) -> List[str]:
    names: List[str] = []
    for path in (Path.home() / ".claude.json", root / ".mcp.json"):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = data.get("mcpServers") or {}
        names.extend(servers.keys())
        # project-scoped servers inside ~/.claude.json
        for proj in (data.get("projects") or {}).values():
            names.extend((proj.get("mcpServers") or {}).keys())
    return sorted(set(names))


def tool_server(tool_pattern: str) -> Optional[str]:
    """mcp__youtrack__* → youtrack"""
    m = re.match(r"^mcp__([^_]+(?:_[^_]+)*?)__", tool_pattern)
    return m.group(1) if m else None


def which(binary: str) -> Optional[str]:
    from shutil import which as _which
    return _which(binary)


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")
