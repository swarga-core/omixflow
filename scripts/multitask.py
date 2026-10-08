#!/usr/bin/env python3
"""Multitask block and dependency map (see protocol/multitask.md).

The block lives inside a task description between
<!-- omixflow:multitask:start --> and <!-- omixflow:multitask:end -->. Both
markers occupy a whole line; a marker quoted inline in prose is not a marker, and a
second start-marker line is an error. The start marker may carry attributes
` key=value` (known key: `profile`, absent = full):
<!-- omixflow:multitask:start profile=research -->. Unknown or duplicate keys and an
unknown profile are marker errors: validate, meta, ready and file reject them;
extract, has, set and waves tolerate them (a declared known profile is used, full
otherwise) and keep the marker line verbatim.
The optional `repo` column names a repository from workspace.repos (`—` = home);
it is emitted after `title` only when some row uses it, is valid only in a
non-mutating profile and can be set only while the part is `pending`.
--repos is the comma-separated list of workspace.repos names to check against.
All commands read text from --from FILE (or stdin) and never touch the tracker:
the skill fetches the description, runs the script, writes the result back
through the tracker adapter.

    multitask.py extract  --from F                 # rows as JSON
    multitask.py meta     --from F                 # {profile, attrs, repos} as JSON
    multitask.py validate --from F [--repos a,b]   # DAG + format checks, exit 1 on error
    multitask.py waves    --from F [--json]        # topological waves
    multitask.py ready    --from F [--owner U] [--parallel N]   # parts whose deps are done
    multitask.py set      --from F --part P k=v... [--repos a,b]  # rewrite only that row
    multitask.py add-part --from F --part "slug — title" --depends D [--repo R] [--repos a,b]
                                                   # repeated refine: append a pending part
    multitask.py render   --rows ROWS.json [--profile NAME]     # block from rows
    multitask.py seed     --parts "slug — title" ... [--depends D ...] [--repo R ...]
                          [--profile NAME] [--repos a,b] [--from F]  # new block (all pending)
    multitask.py file     --from F --id ID --title T   # multitask.md skeleton
    multitask.py has      --from F                 # exit 0 if the text contains a block
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402
from state import DEFAULT_PROFILE, PROFILES, check_profile  # noqa: E402

MARK_START = "<!-- omixflow:multitask:start -->"
MARK_END = "<!-- omixflow:multitask:end -->"
# Whole-line markers; group 1 of START_RE holds the raw attribute tokens.
# `\r` counts as trailing whitespace so CRLF texts match (`$` under re.M sits before `\n`).
START_RE = re.compile(r"^[ \t]*<!--[ \t]*omixflow:multitask:start((?:[ \t]+[^\s>]+)*)[ \t]*-->[ \t\r]*$", re.M)
END_RE = re.compile(r"^[ \t]*<!--[ \t]*omixflow:multitask:end[ \t]*-->[ \t\r]*$", re.M)
ATTR_RE = re.compile(r"^([a-z][a-z0-9_-]*)=([^\s>]+)$")
MARKER_KEYS = ("profile",)
EDITABLE = ("status", "owner", "branch", "commit", "title", "depends", "repo")
COLUMNS = ["#", "part", "title", "depends", "owner", "status", "branch", "commit"]
STATUSES = ("pending", "in-work", "in-review", "done", "blocked", "skipped")
TERMINAL = ("done", "skipped")
ACTIVE = ("in-work", "in-review")
EMPTY = "—"
SLUG_RE = lib.SLUG_RE

Row = Dict[str, Any]


# ------------------------------------------------------------------ text io

def read_text(path: Optional[str]) -> str:
    if path in (None, "-"):
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _start_match(text: str) -> Optional["re.Match[str]"]:
    starts = list(START_RE.finditer(text))
    if len(starts) > 1:
        raise lib.OmixflowError("больше одного блока omixflow:multitask в тексте")
    return starts[0] if starts else None


def find_block(text: str) -> Optional[Tuple[int, int]]:
    start = _start_match(text)
    if start is None:
        return None
    end = END_RE.search(text, start.end())
    if end is None:
        raise lib.OmixflowError("найден маркер начала блока, но нет маркера конца")
    return start.start(), end.end()


def _attr_tokens(text: str) -> List[str]:
    start = _start_match(text)
    return start.group(1).split() if start else []


def marker_attrs(text: str) -> Dict[str, str]:
    """Well-formed attributes of the start marker; the first occurrence of a key wins."""
    attrs: Dict[str, str] = {}
    for token in _attr_tokens(text):
        m = ATTR_RE.match(token)
        if m and m.group(1) not in attrs:
            attrs[m.group(1)] = m.group(2)
    return attrs


def marker_errors(text: str) -> List[str]:
    errors: List[str] = []
    seen: List[str] = []
    for token in _attr_tokens(text):
        m = ATTR_RE.match(token)
        if not m:
            errors.append(f"атрибут маркера {token!r}: ожидается key=value")
            continue
        key, value = m.groups()
        if key in seen:
            errors.append(f"атрибут маркера {key!r} повторяется")
        seen.append(key)
        if key not in MARKER_KEYS:
            errors.append(f"неизвестный атрибут маркера {key!r}; известные: {', '.join(MARKER_KEYS)}")
        elif key == "profile" and value not in PROFILES:
            errors.append(f"неизвестный профиль {value}")
    return errors


def declared_profile(text: str) -> str:
    """Profile for row validation under tolerance: a declared known profile, else full."""
    value = marker_attrs(text).get("profile", DEFAULT_PROFILE)
    return value if value in PROFILES else DEFAULT_PROFILE


def strict_profile(text: str) -> str:
    """Profile of a block whose marker must be clean; raises on marker errors."""
    errors = marker_errors(text)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    return marker_attrs(text).get("profile", DEFAULT_PROFILE)


def slugify(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"[\s_]+", "-", v)
    v = re.sub(r"[^a-z0-9-]", "", v)
    v = re.sub(r"-{2,}", "-", v).strip("-")
    return v


# ------------------------------------------------------------------- parse

def _split_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse_rows(block: str) -> List[Row]:
    lines = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return []
    header = [h.strip().lower() for h in _split_row(lines[0])]
    rows: List[Row] = []
    for ln in lines[2:]:
        cells = _split_row(ln)
        if all(c == "" for c in cells):
            continue
        data = {header[i]: (cells[i] if i < len(cells) else "") for i in range(len(header))}
        depends_raw = data.get("depends", "")
        depends = [] if depends_raw in (EMPTY, "-", "") else [d.strip() for d in depends_raw.split(",") if d.strip()]
        rows.append({
            "n": int(data.get("#") or len(rows) + 1) if str(data.get("#", "")).isdigit() else len(rows) + 1,
            "part": data.get("part", ""),
            "title": data.get("title", ""),
            "depends": depends,
            "depends_raw": depends_raw,
            "owner": None if data.get("owner", "") in (EMPTY, "-", "") else data.get("owner"),
            "status": data.get("status", "") or "pending",
            "branch": None if data.get("branch", "") in (EMPTY, "-", "") else data.get("branch"),
            "commit": None if data.get("commit", "") in (EMPTY, "-", "") else data.get("commit"),
            "repo": None if data.get("repo", "") in (EMPTY, "-", "") else data.get("repo"),
        })
    return rows


def block_header(text: str) -> List[str]:
    """Lower-cased column names of the block's table header (empty when there is none)."""
    span = find_block(text)
    if span is None:
        return []
    lines = [ln for ln in text[span[0]:span[1]].splitlines() if ln.strip().startswith("|")]
    return [h.lower() for h in _split_row(lines[0])] if lines else []


def extract(text: str) -> List[Row]:
    span = find_block(text)
    if span is None:
        raise lib.OmixflowError("в тексте нет блока omixflow:multitask")
    return parse_rows(text[span[0]:span[1]])


# ------------------------------------------------------------------ render

def start_marker(profile: str = DEFAULT_PROFILE) -> str:
    if profile == DEFAULT_PROFILE:
        return MARK_START
    return f"<!-- omixflow:multitask:start profile={profile} -->"


def render(rows: List[Row], profile: str = DEFAULT_PROFILE) -> str:
    with_repo = any(r.get("repo") for r in rows)
    columns = COLUMNS[:3] + ["repo"] + COLUMNS[3:] if with_repo else COLUMNS
    out = [start_marker(profile), "| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for i, r in enumerate(rows, 1):
        depends = ", ".join(r.get("depends") or []) or EMPTY
        cells = [str(i), r["part"], r.get("title", "")]
        if with_repo:
            cells.append(r.get("repo") or EMPTY)
        cells += [depends, r.get("owner") or EMPTY, r.get("status") or "pending",
                  r.get("branch") or EMPTY, r.get("commit") or EMPTY]
        out.append("| " + " | ".join(cells) + " |")
    out.append(MARK_END)
    return "\n".join(out)


def replace_block(text: str, rows: List[Row], profile: str = DEFAULT_PROFILE) -> str:
    block = render(rows, profile)
    span = find_block(text)
    if span is None:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block + "\n"
    return text[:span[0]] + block + text[span[1]:]


# ---------------------------------------------------------------- validate

def parse_repos(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def validate(rows: List[Row], profile: str = DEFAULT_PROFILE,
             repos: Optional[List[str]] = None) -> List[str]:
    """Row checks; `repos` (workspace.repos names), when given, bounds the `repo` column."""
    if profile not in PROFILES:
        raise lib.OmixflowError(f"неизвестный профиль {profile}")
    mutates = PROFILES[profile]["mutates"]
    errors: List[str] = []
    if not rows:
        return ["блок пуст: нет ни одной части"]
    names = [r["part"] for r in rows]
    for r in rows:
        p = r["part"]
        if not SLUG_RE.match(p or ""):
            errors.append(f"часть {p!r}: slug должен быть kebab-case")
        if not r.get("title"):
            errors.append(f"часть {p!r}: пустой title")
        if r.get("depends_raw", None) == "":
            errors.append(f"часть {p!r}: колонка depends пуста; укажи зависимости или «—»")
        for d in r["depends"]:
            if d not in names:
                errors.append(f"часть {p!r}: зависимость {d!r} не существует")
            if d == p:
                errors.append(f"часть {p!r}: зависит сама от себя")
        if r["status"] not in STATUSES:
            errors.append(f"часть {p!r}: статус {r['status']!r} не из {STATUSES}")
        if r["status"] in ACTIVE and not r.get("owner"):
            errors.append(f"часть {p!r}: статус {r['status']} без owner")
        repo = r.get("repo")
        if repo is not None:
            if not SLUG_RE.match(repo):
                errors.append(f"часть {p!r}: repo {repo!r} должен быть slug")
            elif repos is not None and repo not in repos:
                errors.append(f"часть {p!r}: repo {repo!r} нет в workspace.repos ({', '.join(repos) or 'пусто'})")
            if mutates:
                errors.append(f"часть {p!r}: repo {repo!r} недопустим в мутирующем профиле {profile}")
    dupes = {n for n in names if names.count(n) > 1}
    for n in sorted(dupes):
        errors.append(f"дубликат части {n!r}")
    if not errors:
        try:
            waves(rows)
        except lib.OmixflowError as e:
            errors.append(str(e))
    return errors


def waves(rows: List[Row]) -> List[List[str]]:
    deps = {r["part"]: list(r["depends"]) for r in rows}
    remaining = dict(deps)
    result: List[List[str]] = []
    while remaining:
        wave = sorted(p for p, d in remaining.items() if not [x for x in d if x in remaining])
        if not wave:
            raise lib.OmixflowError("цикл в карте зависимостей: " + ", ".join(sorted(remaining)))
        result.append(wave)
        for p in wave:
            remaining.pop(p)
    return result


def ready(rows: List[Row], owner: Optional[str] = None, parallel: Optional[int] = None) -> Dict[str, Any]:
    by = {r["part"]: r for r in rows}
    ready_parts: List[str] = []
    blocked_by_skip: List[str] = []
    for r in rows:
        if r["status"] != "pending":
            continue
        deps = [by[d] for d in r["depends"] if d in by]
        if any(d["status"] == "skipped" for d in deps):
            blocked_by_skip.append(r["part"])
        elif all(d["status"] == "done" for d in deps):
            ready_parts.append(r["part"])
    mine_active = [r["part"] for r in rows if r["status"] in ACTIVE and owner and r.get("owner") == owner]
    repo_key = {r["part"]: r.get("repo") or EMPTY for r in rows}
    ready_keys = {repo_key[p] for p in ready_parts}
    order: List[str] = []  # repos in order of first appearance in the block
    for r in rows:
        if repo_key[r["part"]] not in order:
            order.append(repo_key[r["part"]])
    ready_by_repo = {k: [p for p in ready_parts if repo_key[p] == k] for k in order if k in ready_keys}
    active_repos: List[str] = []
    for part in mine_active:
        if repo_key[part] not in active_repos:
            active_repos.append(repo_key[part])
    return {
        "ready": ready_parts,
        "blocked": [r["part"] for r in rows if r["status"] == "blocked"],
        "blocked_by_skipped_dependency": blocked_by_skip,
        "active": [{"part": r["part"], "owner": r.get("owner"), "status": r["status"]} for r in rows if r["status"] in ACTIVE],
        "mine_active": mine_active,
        "all_terminal": all(r["status"] in TERMINAL for r in rows),
        "slots": max(0, parallel - len(mine_active)) if parallel is not None else None,
        "ready_by_repo": ready_by_repo,
        "active_repos": active_repos,
    }


def render_waves(rows: List[Row]) -> str:
    by = {r["part"]: r for r in rows}
    lines = []
    for i, wave in enumerate(waves(rows), 1):
        items = []
        for p in wave:
            deps = by[p]["depends"]
            items.append(p + (f" ← {', '.join(deps)}" if deps else ""))
        lines.append(f"Волна {i}: " + "; ".join(items))
    return "\n".join(lines)


def block_meta(text: str) -> Dict[str, Any]:
    """Profile, attributes and non-home repos of the block; rejects marker errors."""
    rows = extract(text)
    profile = strict_profile(text)
    repos: List[str] = []
    for r in rows:
        repo = r.get("repo")
        if repo and repo not in repos:
            repos.append(repo)
    return {"profile": profile, "attrs": marker_attrs(text), "repos": repos}


def _cell_value(key: str, cell: str) -> Any:
    if key == "depends":
        return [] if cell in (EMPTY, "-", "") else [d.strip() for d in cell.split(",") if d.strip()]
    return None if cell in (EMPTY, "-", "") else cell


def _cell_text(key: str, value: Any) -> str:
    if key == "depends":
        return ", ".join(value) or EMPTY
    return value if value is not None else EMPTY


def set_row(text: str, part: str, pairs: List[str]) -> str:
    """Rewrite only the target row line; everything else stays byte-for-byte.

    Changed cells take the new value, the rest keep their stripped original content;
    when no cell value changes the text is returned unchanged.
    """
    span = find_block(text)
    if span is None:
        raise lib.OmixflowError("в тексте нет блока omixflow:multitask")
    changes = _parse_changes(part, pairs)
    if changes.get("repo", EMPTY) not in (EMPTY, "-", "") and "repo" not in block_header(text):
        return _set_with_repo_column(text, part, changes)
    block = text[span[0]:span[1]]
    lines = block.splitlines(keepends=True)
    table = [i for i, ln in enumerate(lines) if ln.strip().startswith("|")]
    if len(table) < 2:
        raise lib.OmixflowError(f"части {part!r} нет в блоке")
    header = [h.lower() for h in _split_row(lines[table[0]])]
    if "repo" in changes and "repo" not in header:
        changes.pop("repo")  # «—» in a block without the column: nothing to write
    for k in changes:
        if k not in header:
            raise lib.OmixflowError(f"колонки {k!r} нет в заголовке блока")
    if "part" not in header:
        raise lib.OmixflowError(f"части {part!r} нет в блоке")
    part_col = header.index("part")
    target = None
    for i in table[2:]:
        cells = _split_row(lines[i])
        if part_col < len(cells) and cells[part_col] == part:
            target = i
            break
    if target is None:
        raise lib.OmixflowError(f"части {part!r} нет в блоке")
    cells = _split_row(lines[target])
    cells += [""] * (len(header) - len(cells))
    if "repo" in changes:
        status = (cells[header.index("status")] if "status" in header else "") or "pending"
        if status != "pending":
            raise lib.OmixflowError(f"часть {part!r} в статусе {status}: repo меняется только у pending")
    changed = False
    for k, v in changes.items():
        col = header.index(k)
        new = _cell_value(k, v)
        if new != _cell_value(k, cells[col]):
            cells[col] = _cell_text(k, new)
            changed = True
    if not changed:
        return text
    line = lines[target]
    eol = line[len(line.rstrip("\r\n")):]
    lines[target] = "| " + " | ".join(cells) + " |" + eol
    return text[:span[0]] + "".join(lines) + text[span[1]:]


def _parse_changes(part: str, pairs: List[str]) -> Dict[str, str]:
    changes: Dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise lib.OmixflowError(f"ожидается key=value, получено {pair!r}")
        k, v = pair.split("=", 1)
        if k not in EDITABLE:
            raise lib.OmixflowError(f"нельзя менять колонку {k!r}")
        if k == "status" and v not in STATUSES:
            raise lib.OmixflowError(f"статус {v!r} не из {STATUSES}")
        if "|" in v or "\n" in v or "\r" in v:
            raise lib.OmixflowError(f"значение {k}={v!r}: символы «|» и перевод строки недопустимы в ячейке")
        if k == "title" and v in (EMPTY, "-", ""):
            raise lib.OmixflowError(f"часть {part!r}: пустой title")
        changes[k] = v
    return changes


def _apply_to_row(row: Row, changes: Dict[str, str]) -> None:
    for k, v in changes.items():
        if k == "depends":
            row["depends"] = [] if v in (EMPTY, "-", "") else [d.strip() for d in v.split(",") if d.strip()]
        elif k in ("owner", "branch", "commit", "repo"):
            row[k] = None if v in (EMPTY, "-", "") else v
        else:
            row[k] = v


def _set_with_repo_column(text: str, part: str, changes: Dict[str, str]) -> str:
    """The first non-empty `repo` in a block without the column: the block is re-rendered
    with the column (the marker keeps its profile; other rows keep their values)."""
    profile = strict_profile(text)
    rows = extract(text)
    row = next((r for r in rows if r["part"] == part), None)
    if row is None:
        raise lib.OmixflowError(f"части {part!r} нет в блоке")
    if row.get("status", "pending") != "pending":
        raise lib.OmixflowError(f"часть {part!r} в статусе {row['status']}: repo меняется только у pending")
    _apply_to_row(row, changes)
    return replace_block(text, rows, profile)


def parse_part_spec(spec: str) -> Tuple[str, str]:
    """'slug — title' (or 'slug - title') → (slug, title)."""
    if "—" in spec:
        slug, title = spec.split("—", 1)
    elif " - " in spec:
        slug, title = spec.split(" - ", 1)
    else:
        raise lib.OmixflowError(f"часть должна быть в форме 'slug — title': {spec!r}")
    return slugify(slug), title.strip()


def add_part(text: str, spec: str, depends: str, repo: Optional[str]) -> str:
    """Append a `pending` part to an existing block (a repeated refine). Other rows and the
    marker stay byte-for-byte; a first non-empty `repo` re-renders the block with the column."""
    span = find_block(text)
    if span is None:
        raise lib.OmixflowError("в тексте нет блока omixflow:multitask")
    profile = strict_profile(text)
    slug, title = parse_part_spec(spec)
    rows = extract(text)
    if any(r["part"] == slug for r in rows):
        raise lib.OmixflowError(f"часть {slug!r} уже есть в блоке")
    if "|" in title or "\n" in title:
        raise lib.OmixflowError(f"часть {slug!r}: символы «|» и перевод строки недопустимы в title")
    new: Row = {"part": slug, "title": title, "depends": [], "owner": None, "status": "pending",
                "branch": None, "commit": None, "repo": None}
    _apply_to_row(new, {"depends": depends, "repo": repo or EMPTY})
    header = block_header(text)
    if new["repo"] and "repo" not in header:
        return replace_block(text, rows + [new], profile)
    values = {"#": str(len(rows) + 1), "part": slug, "title": title, "repo": new["repo"] or EMPTY,
              "depends": ", ".join(new["depends"]) or EMPTY, "owner": EMPTY, "status": "pending",
              "branch": EMPTY, "commit": EMPTY}
    line = "| " + " | ".join(values.get(h, "") for h in header) + " |"
    block = text[span[0]:span[1]]
    lines = block.splitlines(keepends=True)
    last = max(i for i, ln in enumerate(lines) if ln.strip().startswith("|"))
    eol = lines[last][len(lines[last].rstrip("\r\n")):] or "\n"
    lines.insert(last + 1, line + eol)
    return text[:span[0]] + "".join(lines) + text[span[1]:]


def multitask_file(rows: List[Row], task_id: str, title: str, profile: str = DEFAULT_PROFILE,
                   repo_column: Optional[bool] = None) -> str:
    """multitask.md skeleton; `repo_column` says whether the block has a `repo` column
    (default: some row names a repo)."""
    if repo_column is None:
        repo_column = any(r.get("repo") for r in rows)
    out = [f"# Мультизадача {task_id}: {title}", "",
           "Определение частей и их постановки. Статусы живут только в блоке описания задачи",
           "(`protocol/multitask.md`).", "",
           "## Части", ""]
    for r in rows:
        deps = ", ".join(r["depends"]) or "нет"
        out += [f"### {r['part']} — {r['title']}", "",
                f"- Зависит от: {deps}"]
        if repo_column:
            out.append(f"- Репозиторий: {r.get('repo') or 'домашний'}")
        out += ["",
                "#### Постановка", "", "{что делает часть; из описания задачи или refine}", "",
                "#### Критерии приёмки", "", "- {критерий}", ""]
    out += ["## Граф", "", "```", render_waves(rows), "```", "",
            "## Интеграция", ""]
    if PROFILES[profile]["part_integration"] == "commit":
        out += ["- Стратегия: части коммитятся по пути `.tasks/" + task_id + "/{part}/` в `task/" + task_id
                + "`, веток и worktree частей нет, сообщение `docs(" + task_id + "): research {part} — {title}`."]
    else:
        out += ["- Стратегия: по `workspace.integration` (squash в ветку мультизадачи одним коммитом).",
                "- Ветка мультизадачи: `task/" + task_id + "`; ветки частей: `task/" + task_id + "-{part}`."]
    out += ["- Порядок: по волнам; внутри волны части независимы.", ""]
    return "\n".join(out)


# --------------------------------------------------------------- commands

def cmd_extract(ns) -> int:
    rows = extract(read_text(ns.from_))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(ns) -> int:
    text = read_text(ns.from_)
    rows = extract(text)
    errors = marker_errors(text) + validate(rows, declared_profile(text), parse_repos(ns.repos))
    if errors:
        for e in errors:
            print(f"ошибка: {e}")
        return 1
    print(f"ok: {len(rows)} частей, {len(waves(rows))} волн")
    return 0


def cmd_waves(ns) -> int:
    text = read_text(ns.from_)
    rows = extract(text)
    errors = validate(rows, declared_profile(text))
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.json:
        print(json.dumps(waves(rows), ensure_ascii=False))
    else:
        print(render_waves(rows))
    return 0


def cmd_ready(ns) -> int:
    text = read_text(ns.from_)
    rows = extract(text)
    strict_profile(text)
    print(json.dumps(ready(rows, ns.owner, ns.parallel), ensure_ascii=False, indent=2))
    return 0


def cmd_set(ns) -> int:
    text = read_text(ns.from_)
    out = set_row(text, ns.part, ns.pairs)
    errors = validate(extract(out), declared_profile(out), parse_repos(ns.repos))
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.in_place and ns.from_ not in (None, "-"):
        Path(ns.from_).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


def cmd_add_part(ns) -> int:
    text = read_text(ns.from_)
    out = add_part(text, ns.part, ns.depends, ns.repo)
    errors = validate(extract(out), strict_profile(out), parse_repos(ns.repos))
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.in_place and ns.from_ not in (None, "-"):
        Path(ns.from_).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


def cmd_render(ns) -> int:
    rows = json.loads(Path(ns.rows).read_text(encoding="utf-8"))
    print(render(rows, check_profile(ns.profile)))
    return 0


def cmd_seed(ns) -> int:
    rows: List[Row] = []
    for spec in ns.parts:
        slug, title = parse_part_spec(spec)
        rows.append({"part": slug, "title": title, "depends": [], "depends_raw": None,
                     "owner": None, "status": "pending", "branch": None, "commit": None})
    for r, deps in zip(rows, ns.depends or []):
        r["depends"] = [] if deps in (EMPTY, "-", "") else [d.strip() for d in deps.split(",") if d.strip()]
    for r, repo in zip(rows, ns.repo or []):
        r["repo"] = None if repo in (EMPTY, "-", "") else repo
    for r in rows:
        r["depends_raw"] = ", ".join(r["depends"]) or EMPTY
    profile = check_profile(ns.profile)
    errors = validate(rows, profile, parse_repos(ns.repos))
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.from_:
        text = read_text(ns.from_)
        if find_block(text) is not None:
            raise lib.OmixflowError("в тексте уже есть блок; сидинг повторно не выполняется")
        sys.stdout.write(replace_block(text, rows, profile))
    else:
        print(render(rows, profile))
    return 0


def cmd_meta(ns) -> int:
    print(json.dumps(block_meta(read_text(ns.from_)), ensure_ascii=False, indent=2))
    return 0


def cmd_file(ns) -> int:
    text = read_text(ns.from_)
    rows = extract(text)
    profile = strict_profile(text)
    errors = validate(rows, profile)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    print(multitask_file(rows, ns.id, ns.title, profile, repo_column="repo" in block_header(text)))
    return 0


def cmd_has(ns) -> int:
    return 0 if find_block(read_text(ns.from_)) is not None else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_from(p):
        p.add_argument("--from", dest="from_", default=None, help="файл с текстом описания или - для stdin")

    def add_repos(p):
        p.add_argument("--repos", default=None, help="имена workspace.repos через запятую")

    for name, fn in (("extract", cmd_extract), ("has", cmd_has), ("meta", cmd_meta)):
        p = sub.add_parser(name); add_from(p); p.set_defaults(fn=fn)
    p = sub.add_parser("validate"); add_from(p); add_repos(p); p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("waves"); add_from(p); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_waves)
    p = sub.add_parser("ready"); add_from(p); p.add_argument("--owner", default=None)
    p.add_argument("--parallel", type=int, default=None, help="лимит одновременных частей владельца")
    p.set_defaults(fn=cmd_ready)
    p = sub.add_parser("set"); add_from(p); add_repos(p); p.add_argument("--part", required=True)
    p.add_argument("pairs", nargs="+"); p.add_argument("--in-place", action="store_true"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("add-part"); add_from(p); add_repos(p)
    p.add_argument("--part", required=True, help="'slug — title'")
    p.add_argument("--depends", required=True, help="slug'и через запятую или «—»: ответ обязателен")
    p.add_argument("--repo", default=None, help="имя из workspace.repos или «—» (домашний)")
    p.add_argument("--in-place", action="store_true"); p.set_defaults(fn=cmd_add_part)
    p = sub.add_parser("render"); p.add_argument("--rows", required=True)
    p.add_argument("--profile", default=DEFAULT_PROFILE); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("seed"); add_from(p); add_repos(p); p.add_argument("--parts", nargs="+", required=True)
    p.add_argument("--depends", nargs="*", default=None, help="по одному значению на часть, в том же порядке; «—» = нет")
    p.add_argument("--repo", nargs="*", default=None, help="по одному значению на часть, в том же порядке; «—» = домашний")
    p.add_argument("--profile", default=DEFAULT_PROFILE)
    p.set_defaults(fn=cmd_seed)
    p = sub.add_parser("file"); add_from(p); p.add_argument("--id", required=True); p.add_argument("--title", required=True)
    p.set_defaults(fn=cmd_file)

    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
