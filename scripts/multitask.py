#!/usr/bin/env python3
"""Multitask block and dependency map (see protocol/multitask.md).

The block lives inside a task description between
<!-- omixflow:multitask:start --> and <!-- omixflow:multitask:end -->.
All commands read text from --from FILE (or stdin) and never touch the tracker:
the skill fetches the description, runs the script, writes the result back
through the tracker adapter.

    multitask.py extract  --from F                 # rows as JSON
    multitask.py validate --from F                 # DAG + format checks, exit 1 on error
    multitask.py waves    --from F [--json]        # topological waves
    multitask.py ready    --from F [--owner U]     # parts whose deps are done
    multitask.py set      --from F --part P k=v... # update a row; prints the whole text
    multitask.py render   --rows ROWS.json         # block from rows
    multitask.py seed     --parts "slug — title" ... [--from F]   # new block (all pending)
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

MARK_START = "<!-- omixflow:multitask:start -->"
MARK_END = "<!-- omixflow:multitask:end -->"
COLUMNS = ["#", "part", "title", "depends", "owner", "status", "branch", "commit"]
STATUSES = ("pending", "in-work", "in-review", "done", "blocked", "skipped")
TERMINAL = ("done", "skipped")
ACTIVE = ("in-work", "in-review")
EMPTY = "—"
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

Row = Dict[str, Any]


# ------------------------------------------------------------------ text io

def read_text(path: Optional[str]) -> str:
    if path in (None, "-"):
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def find_block(text: str) -> Optional[Tuple[int, int]]:
    s = text.find(MARK_START)
    if s < 0:
        return None
    e = text.find(MARK_END, s)
    if e < 0:
        raise lib.OmixflowError("найден маркер начала блока, но нет маркера конца")
    return s, e + len(MARK_END)


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
        })
    return rows


def extract(text: str) -> List[Row]:
    span = find_block(text)
    if span is None:
        raise lib.OmixflowError("в тексте нет блока omixflow:multitask")
    return parse_rows(text[span[0]:span[1]])


# ------------------------------------------------------------------ render

def render(rows: List[Row]) -> str:
    out = [MARK_START, "| " + " | ".join(COLUMNS) + " |", "|" + "|".join("---" for _ in COLUMNS) + "|"]
    for i, r in enumerate(rows, 1):
        depends = ", ".join(r.get("depends") or []) or EMPTY
        out.append("| " + " | ".join([
            str(i), r["part"], r.get("title", ""), depends,
            r.get("owner") or EMPTY, r.get("status") or "pending",
            r.get("branch") or EMPTY, r.get("commit") or EMPTY,
        ]) + " |")
    out.append(MARK_END)
    return "\n".join(out)


def replace_block(text: str, rows: List[Row]) -> str:
    block = render(rows)
    span = find_block(text)
    if span is None:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block + "\n"
    return text[:span[0]] + block + text[span[1]:]


# ---------------------------------------------------------------- validate

def validate(rows: List[Row]) -> List[str]:
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


def ready(rows: List[Row], owner: Optional[str] = None) -> Dict[str, Any]:
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
    return {
        "ready": ready_parts,
        "blocked": [r["part"] for r in rows if r["status"] == "blocked"],
        "blocked_by_skipped_dependency": blocked_by_skip,
        "active": [{"part": r["part"], "owner": r.get("owner"), "status": r["status"]} for r in rows if r["status"] in ACTIVE],
        "mine_active": mine_active,
        "all_terminal": all(r["status"] in TERMINAL for r in rows),
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


def multitask_file(rows: List[Row], task_id: str, title: str) -> str:
    out = [f"# Мультизадача {task_id}: {title}", "",
           "Определение частей и их постановки. Статусы живут только в блоке описания задачи",
           "(`protocol/multitask.md`).", "",
           "## Части", ""]
    for r in rows:
        deps = ", ".join(r["depends"]) or "нет"
        out += [f"### {r['part']} — {r['title']}", "",
                f"- Зависит от: {deps}", "",
                "#### Постановка", "", "{что делает часть; из описания задачи или refine}", "",
                "#### Критерии приёмки", "", "- {критерий}", ""]
    out += ["## Граф", "", "```", render_waves(rows), "```", "",
            "## Интеграция", "",
            "- Стратегия: по `workspace.integration` (squash в ветку мультизадачи одним коммитом).",
            "- Ветка мультизадачи: `task/" + task_id + "`; ветки частей: `task/" + task_id + "-{part}`.",
            "- Порядок: по волнам; внутри волны части независимы.", ""]
    return "\n".join(out)


# --------------------------------------------------------------- commands

def cmd_extract(ns) -> int:
    rows = extract(read_text(ns.from_))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(ns) -> int:
    rows = extract(read_text(ns.from_))
    errors = validate(rows)
    if errors:
        for e in errors:
            print(f"ошибка: {e}")
        return 1
    print(f"ok: {len(rows)} частей, {len(waves(rows))} волн")
    return 0


def cmd_waves(ns) -> int:
    rows = extract(read_text(ns.from_))
    errors = validate(rows)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.json:
        print(json.dumps(waves(rows), ensure_ascii=False))
    else:
        print(render_waves(rows))
    return 0


def cmd_ready(ns) -> int:
    rows = extract(read_text(ns.from_))
    print(json.dumps(ready(rows, ns.owner), ensure_ascii=False, indent=2))
    return 0


def cmd_set(ns) -> int:
    text = read_text(ns.from_)
    rows = extract(text)
    target = [r for r in rows if r["part"] == ns.part]
    if not target:
        raise lib.OmixflowError(f"части {ns.part!r} нет в блоке")
    row = target[0]
    for pair in ns.pairs:
        if "=" not in pair:
            raise lib.OmixflowError(f"ожидается key=value, получено {pair!r}")
        k, v = pair.split("=", 1)
        if k not in ("status", "owner", "branch", "commit", "title", "depends"):
            raise lib.OmixflowError(f"нельзя менять колонку {k!r}")
        if k == "status" and v not in STATUSES:
            raise lib.OmixflowError(f"статус {v!r} не из {STATUSES}")
        if k == "depends":
            row["depends"] = [] if v in (EMPTY, "-", "") else [d.strip() for d in v.split(",") if d.strip()]
        else:
            row[k] = None if v in (EMPTY, "-", "") else v
    errors = validate(rows)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    out = replace_block(text, rows)
    if ns.in_place and ns.from_ not in (None, "-"):
        Path(ns.from_).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


def cmd_render(ns) -> int:
    rows = json.loads(Path(ns.rows).read_text(encoding="utf-8"))
    print(render(rows))
    return 0


def cmd_seed(ns) -> int:
    rows: List[Row] = []
    for spec in ns.parts:
        if "—" in spec:
            slug, title = spec.split("—", 1)
        elif " - " in spec:
            slug, title = spec.split(" - ", 1)
        else:
            raise lib.OmixflowError(f"часть должна быть в форме 'slug — title': {spec!r}")
        slug = slugify(slug)
        rows.append({"part": slug, "title": title.strip(), "depends": [], "depends_raw": None,
                     "owner": None, "status": "pending", "branch": None, "commit": None})
    for r, deps in zip(rows, ns.depends or []):
        r["depends"] = [] if deps in (EMPTY, "-", "") else [d.strip() for d in deps.split(",") if d.strip()]
    for r in rows:
        r["depends_raw"] = ", ".join(r["depends"]) or EMPTY
    errors = validate(rows)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    if ns.from_:
        text = read_text(ns.from_)
        if find_block(text) is not None:
            raise lib.OmixflowError("в тексте уже есть блок; сидинг повторно не выполняется")
        sys.stdout.write(replace_block(text, rows))
    else:
        print(render(rows))
    return 0


def cmd_file(ns) -> int:
    rows = extract(read_text(ns.from_))
    errors = validate(rows)
    if errors:
        raise lib.OmixflowError("; ".join(errors))
    print(multitask_file(rows, ns.id, ns.title))
    return 0


def cmd_has(ns) -> int:
    return 0 if find_block(read_text(ns.from_)) is not None else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_from(p):
        p.add_argument("--from", dest="from_", default=None, help="файл с текстом описания или - для stdin")

    for name, fn in (("extract", cmd_extract), ("validate", cmd_validate), ("has", cmd_has)):
        p = sub.add_parser(name); add_from(p); p.set_defaults(fn=fn)

    p = sub.add_parser("waves"); add_from(p); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_waves)
    p = sub.add_parser("ready"); add_from(p); p.add_argument("--owner", default=None); p.set_defaults(fn=cmd_ready)
    p = sub.add_parser("set"); add_from(p); p.add_argument("--part", required=True)
    p.add_argument("pairs", nargs="+"); p.add_argument("--in-place", action="store_true"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("render"); p.add_argument("--rows", required=True); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("seed"); add_from(p); p.add_argument("--parts", nargs="+", required=True)
    p.add_argument("--depends", nargs="*", default=None, help="по одному значению на часть, в том же порядке; «—» = нет")
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
