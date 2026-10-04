#!/usr/bin/env python3
"""Base drift of a task branch (port workspace, capability `sync`).

    sync.py check DIR [--ref REF]
    sync.py record DIR --how merge|rebase --base-sha SHA --commit SHA

DIR is the task (or part) directory with state.yaml; its `base` names the base
branch. `check` is read-only and prints JSON: the base ref used (local branch,
else origin/{base}), its head, the fork point, how many commits the branch is
behind and ahead, whether the branch changed anything outside the artifacts
directory (`code_changed`), whether the tree is dirty, and the strategy chosen by
`workspace.sync` (auto: rebase while the branch holds only artifacts, merge once it
holds code). `moved` counts only base changes outside the artifacts directory: a base
that moved in artifacts alone (tracker `local` files, notes) needs no sync. `record` appends a finished sync to `syncs` in state.yaml.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402
import state as st  # noqa: E402

MODES = ("auto", "merge", "rebase")
HOWS = ("merge", "rebase")


def git_or_fail(root: Path, *args: str) -> str:
    out = lib.git(root, *args)
    if out is None:
        raise lib.OmixflowError(f"git {' '.join(args)} не выполнился в {root}")
    return out


def base_ref(root: Path, base: str, explicit: Optional[str]) -> str:
    if explicit:
        candidates = [explicit]
    else:
        candidates = [f"refs/heads/{base}", f"refs/remotes/origin/{base}"]
    for ref in candidates:
        if lib.git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is not None:
            return ref
    raise lib.OmixflowError(f"база {base!r} не найдена ни локально, ни как origin/{base}")


def check(d: Path, explicit_ref: Optional[str] = None) -> Dict[str, Any]:
    state = st.load(d)
    base = state.get("base")
    if not base:
        raise lib.OmixflowError(f"в {st.path_of(d)} нет base")
    root = lib.find_project_root(d)
    cfg = lib.load_config(root)
    artifacts = str(lib.config_get(cfg, "artifacts.dir") or ".tasks").strip("/")
    mode = str(lib.config_get(cfg, "workspace.sync") or "auto")
    if mode not in MODES:
        raise lib.OmixflowError(f"workspace.sync должен быть одним из {MODES}, получено {mode!r}")
    ref = base_ref(root, str(base), explicit_ref)
    head = git_or_fail(root, "rev-parse", ref)
    fork = git_or_fail(root, "merge-base", "HEAD", ref)
    behind = int(git_or_fail(root, "rev-list", "--count", f"HEAD..{ref}"))
    ahead = int(git_or_fail(root, "rev-list", "--count", f"{ref}..HEAD"))
    changed = [f for f in git_or_fail(root, "diff", "--name-only", fork, "HEAD").splitlines() if f]
    code: List[str] = lib.outside_dir(changed, artifacts)
    base_changed = [f for f in git_or_fail(root, "diff", "--name-only", fork, ref).splitlines() if f]
    base_code = lib.outside_dir(base_changed, artifacts)
    strategy = mode if mode != "auto" else ("merge" if code else "rebase")
    return {
        "base": base, "ref": ref, "base_head": head, "fork_point": fork,
        "behind": behind, "ahead": ahead, "moved": bool(base_code),
        "moved_artifacts_only": behind > 0 and not base_code, "base_code_files": base_code[:20],
        "code_changed": bool(code), "code_files": code[:20],
        "dirty": lib.repo_checkout_state(root)["dirty"],
        "mode": mode, "strategy": strategy,
    }


def cmd_check(ns: argparse.Namespace) -> int:
    print(json.dumps(check(Path(ns.dir).resolve(), ns.ref), ensure_ascii=False, indent=2))
    return 0


def cmd_record(ns: argparse.Namespace) -> int:
    d = Path(ns.dir).resolve()
    state = st.load(d)
    syncs = list(state.get("syncs") or [])
    syncs.append({"base_sha": ns.base_sha, "commit": ns.commit, "how": ns.how, "at": st.now()})
    state["syncs"] = syncs
    st.save(d, state)
    print(len(syncs))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check")
    p.add_argument("dir")
    p.add_argument("--ref", default=None)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("record")
    p.add_argument("dir")
    p.add_argument("--how", choices=HOWS, required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--commit", required=True)
    p.set_defaults(fn=cmd_record)

    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except lib.OmixflowError as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
