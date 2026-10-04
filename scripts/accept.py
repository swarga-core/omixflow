#!/usr/bin/env python3
"""Git side of the lead's merge acceptance (protocol/lead.md, «Приёмка мержа»).

    accept.py plan BRANCH --into INTO [--project DIR]
    accept.py prepare --into INTO --path PATH [--project DIR]
    accept.py merge BRANCH --tree PATH
    accept.py commit --tree PATH --message MSG
    accept.py abort --tree PATH
    accept.py cleanup --path PATH [--project DIR]
    accept.py retire --branch BRANCH [--worktree PATH] [--project DIR]

`plan` (read-only) prints JSON: the worktree that has INTO checked out and whether
it is clean, or a temporary worktree path to create when INTO is checked out nowhere;
whether BRANCH is in sync with INTO (`synced`: INTO moved past the branch only in the
artifacts directory, if at all), how far INTO moved, and the files the branch changes. Git refuses one branch in two
worktrees, so the merge happens where INTO is checked out (clean) or in a temporary
worktree, never in a task session's worktree.

`merge` squashes BRANCH into the tree without committing and checks the index
against the branch diff: a staged file the branch did not change stops the merge
(exit 4); a branch file INTO already has identically is not staged and is only
listed (`already_in_into`). Exit 3: conflicts (JSON lists them). On exit 3 or 4
the tree is reset to its head. `commit` prints the short hash. `abort` resets a staged squash.

`retire` removes a finished session's worktree (tracked-clean only) and deletes its
branch, printing the branch tip for recovery. A worktree with submodules (exit 5)
needs the removal order of the workspace adapter; a branch checked out anywhere
is refused.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402

EXIT_CONFLICT = 3
EXIT_INDEX = 4
EXIT_SUBMODULE = 5


def run_git(root: Path, *args: str) -> str:
    out = lib.git(root, *args)
    if out is None:
        raise lib.OmixflowError(f"git {' '.join(args)} не выполнился в {root}")
    return out


def lines(text: str) -> List[str]:
    return [line for line in text.splitlines() if line]


def worktree_of(root: Path, branch: str) -> Optional[Path]:
    """The worktree that has `branch` checked out, if any."""
    current: Optional[str] = None
    for line in run_git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}" and current:
            return Path(current)
    return None


def clean(tree: Path) -> bool:
    """Tracked files only: untracked files and `.claude/worktrees/` don't block a merge."""
    return not lib.repo_checkout_state(tree)["dirty"]


def temp_path(root: Path, into: str) -> Path:
    return root / ".claude" / "worktrees" / ("accept-" + re.sub(r"[^A-Za-z0-9._-]+", "-", into))


def artifacts_dir(root: Path) -> str:
    try:
        return str(lib.config_get(lib.load_config(root), "artifacts.dir") or ".tasks")
    except lib.OmixflowError:
        return ".tasks"


def plan(root: Path, branch: str, into: str) -> Dict[str, Any]:
    for ref in (branch, into):
        if lib.git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}") is None:
            raise lib.OmixflowError(f"ветки {ref!r} нет")
    tree = worktree_of(root, into)
    into_head = run_git(root, "rev-parse", into)
    fork = run_git(root, "merge-base", branch, into)
    into_code = lib.outside_dir(lines(run_git(root, "diff", "--name-only", fork, into)), artifacts_dir(root))
    synced = not into_code
    return {
        "branch": branch, "into": into, "into_head": into_head,
        "tree": str(tree) if tree else None,
        "tree_clean": clean(tree) if tree else None,
        "temp": None if tree else str(temp_path(root, into)),
        "synced": synced, "into_code_files": into_code[:20],
        "into_ahead": int(run_git(root, "rev-list", "--count", f"{branch}..{into}")),
        "files": lines(run_git(root, "diff", "--name-only", f"{into}...{branch}")),
        "stat": run_git(root, "diff", "--shortstat", f"{into}...{branch}"),
    }


def merge(tree: Path, branch: str) -> Dict[str, Any]:
    if not clean(tree):
        raise lib.OmixflowError(f"дерево {tree} не чистое: приёмка только на чистом дереве")
    expected = sorted(lines(run_git(tree, "diff", "--name-only", f"HEAD...{branch}")))
    result = lib.git(tree, "merge", "--squash", branch)
    conflicts = sorted(lines(lib.git(tree, "diff", "--name-only", "--diff-filter=U") or ""))
    if result is None or conflicts:
        lib.git(tree, "reset", "--merge")
        return {"status": "conflict", "conflicts": conflicts}
    staged = sorted(lines(run_git(tree, "diff", "--cached", "--name-only")))
    extra = [f for f in staged if f not in expected]
    if extra:
        lib.git(tree, "reset", "--merge")
        return {"status": "index-mismatch", "extra": extra}
    return {"status": "staged", "files": staged,
            "already_in_into": [f for f in expected if f not in staged]}


def cmd_plan(ns: argparse.Namespace) -> int:
    print(json.dumps(plan(lib.find_project_root(ns.project), ns.branch, ns.into), ensure_ascii=False, indent=2))
    return 0


def cmd_prepare(ns: argparse.Namespace) -> int:
    root = lib.find_project_root(ns.project)
    holder = worktree_of(root, ns.into)
    if holder is not None:
        raise lib.OmixflowError(f"{ns.into} уже открыта в {holder}: мержить там, временный worktree не нужен")
    run_git(root, "worktree", "add", "-q", str(ns.path), ns.into)
    print(ns.path)
    return 0


def cmd_merge(ns: argparse.Namespace) -> int:
    result = merge(Path(ns.tree), ns.branch)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"staged": 0, "conflict": EXIT_CONFLICT, "index-mismatch": EXIT_INDEX}[result["status"]]


def cmd_commit(ns: argparse.Namespace) -> int:
    tree = Path(ns.tree)
    if run_git(tree, "diff", "--cached", "--name-only") == "":
        raise lib.OmixflowError("в индексе ничего нет: сначала accept.py merge")
    run_git(tree, "commit", "-q", "-m", ns.message)
    print(run_git(tree, "rev-parse", "--short", "HEAD"))
    return 0


def cmd_abort(ns: argparse.Namespace) -> int:
    run_git(Path(ns.tree), "reset", "--merge")
    print("aborted")
    return 0


def cmd_cleanup(ns: argparse.Namespace) -> int:
    root = lib.find_project_root(ns.project)
    run_git(root, "worktree", "remove", str(ns.path))
    print("removed")
    return 0


def cmd_retire(ns: argparse.Namespace) -> int:
    root = lib.find_project_root(ns.project)
    worktree = None
    if ns.worktree is not None:
        worktree = Path(ns.worktree).resolve()
        listed = {Path(line[len("worktree "):]).resolve()
                  for line in run_git(root, "worktree", "list", "--porcelain").splitlines()
                  if line.startswith("worktree ")}
        if worktree not in listed:
            raise lib.OmixflowError(f"{worktree} не worktree этого репозитория")
        if (worktree / ".gitmodules").exists():
            print(json.dumps({"status": "submodule", "worktree": str(worktree)}, ensure_ascii=False))
            print("omixflow: worktree с submodule: снос по порядку адаптера workspace (git.md)", file=sys.stderr)
            return EXIT_SUBMODULE
        if not clean(worktree):
            raise lib.OmixflowError(f"{worktree}: незакоммиченные изменения, снос откладывается")
        run_git(root, "worktree", "remove", str(worktree))
    holder = worktree_of(root, ns.branch)
    if holder is not None:
        raise lib.OmixflowError(f"ветка {ns.branch} открыта в {holder}: не удаляю")
    tip = run_git(root, "rev-parse", "--short", ns.branch)
    run_git(root, "branch", "-D", ns.branch)
    print(json.dumps({"status": "retired", "branch": ns.branch, "tip": tip,
                      "worktree": str(worktree) if worktree else None}, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("branch")
    p.add_argument("--into", required=True)
    p.add_argument("--project", type=Path, default=None)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("prepare")
    p.add_argument("--into", required=True)
    p.add_argument("--path", type=Path, required=True)
    p.add_argument("--project", type=Path, default=None)
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("merge")
    p.add_argument("branch")
    p.add_argument("--tree", required=True)
    p.set_defaults(fn=cmd_merge)

    p = sub.add_parser("commit")
    p.add_argument("--tree", required=True)
    p.add_argument("--message", required=True)
    p.set_defaults(fn=cmd_commit)

    p = sub.add_parser("abort")
    p.add_argument("--tree", required=True)
    p.set_defaults(fn=cmd_abort)

    p = sub.add_parser("retire")
    p.add_argument("--branch", required=True)
    p.add_argument("--worktree", default=None)
    p.add_argument("--project", type=Path, default=None)
    p.set_defaults(fn=cmd_retire)

    p = sub.add_parser("cleanup")
    p.add_argument("--path", type=Path, required=True)
    p.add_argument("--project", type=Path, default=None)
    p.set_defaults(fn=cmd_cleanup)

    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
