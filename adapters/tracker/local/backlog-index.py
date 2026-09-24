#!/usr/bin/env python3
"""Generate the README.md index of a local-tracker directory (adapter tracker/local).

    backlog-index.py [--dir DIR] [--check]

Scans `*.md` files with frontmatter (id, title, status, type, target, origin,
external) and rewrites `README.md` in that directory. --check exits 1 when the
index is stale instead of writing. DIR defaults to tracker.dir from flow.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "scripts"))
import omixflow_lib as lib  # noqa: E402

HEADER = (
    "# Локальный трекер\n\n"
    "Индекс генерируется скриптом адаптера `tracker/local`, руками не правится.\n"
    "Формат файлов и статусы: `adapters/tracker/local.md` плагина OMIXFlow.\n\n"
)
COLUMNS = ["id", "title", "status", "type", "target", "origin", "external"]


def scan(d: Path) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted(d.glob("*.md")):
        if path.name == "README.md":
            continue
        meta, _ = lib.parse_frontmatter(path)
        if not meta.get("id"):
            continue
        rows.append({c: ("" if meta.get(c) is None else str(meta.get(c))) for c in COLUMNS} | {"file": path.name})
    return rows


def render(rows: List[Dict[str, Any]]) -> str:
    lines = [HEADER, "| " + " | ".join(COLUMNS) + " |", "|" + "|".join("---" for _ in COLUMNS) + "|"]
    for r in rows:
        cells = [f"[{r['id']}]({r['file']})"] + [r[c] or "—" for c in COLUMNS[1:]]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--check", action="store_true")
    ns = ap.parse_args(argv)
    root = lib.find_project_root(Path(ns.project) if ns.project else None)
    if ns.dir:
        d = Path(ns.dir)
    else:
        cfg = lib.load_config(root)
        d = root / str(lib.config_get(cfg, "tracker.dir") or ".tasks/backlog")
    if not d.exists():
        print(f"omixflow/local: каталога {d} нет", file=sys.stderr)
        return 2
    content = render(scan(d))
    readme = d / "README.md"
    current = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if ns.check:
        if current != content:
            print(f"индекс устарел: {readme}")
            return 1
        print("индекс актуален")
        return 0
    readme.write_text(content, encoding="utf-8")
    print(f"{readme}: {content.count(chr(10)) - HEADER.count(chr(10)) - 3} задач")
    return 0


if __name__ == "__main__":
    sys.exit(main())
