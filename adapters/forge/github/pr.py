#!/usr/bin/env python3
"""GitHub forge adapter script for OMIXFlow pr-review.

Wraps the `gh` CLI; every JSON response is parsed here, never through shell
variables (multi-line review bodies break `echo "$VAR" | jq`).

    pr.py user
    pr.py view    <pr>                       # pr = number or URL; repo from remote when a number
    pr.py files   <pr> [--names]
    pr.py reviews-mine <pr>                  # real reviews by me (non-empty body or a verdict), rounds, previous SHA
    pr.py threads <pr> [--mine]
    pr.py build-payload --dir DIR --sha SHA --event EVENT
    pr.py validate --dir DIR <pr>            # inline lines vs diff hunks; exit 1 on problems
    pr.py submit --dir DIR <pr>
    pr.py reply <pr> --file replies.json     # sequential; stops at the first failure
    pr.py permalink <pr> --sha SHA <path> [<line> [<end>]]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PR_URL_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)")
HEADER_RE = re.compile(
    r"^### \S+ — (?P<path>[^,]+), "
    r"(?:line (?P<line>\d+)|lines (?P<start>\d+)-(?P<end>\d+)(?: \(multi-line\))?)\s*$",
    re.MULTILINE,
)
FENCE_RE = re.compile(r"````\n(.*?)\n````", re.DOTALL)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class GhError(Exception):
    pass


# ------------------------------------------------------------------ gh io

def gh(*args: str, stdin: Optional[str] = None) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip() or f"gh {' '.join(args)} failed ({proc.returncode})")
    return proc.stdout


def gh_json(*args: str, stdin: Optional[str] = None) -> Any:
    return json.loads(gh(*args, stdin=stdin))


def paginate(endpoint: str) -> List[Any]:
    out: List[Any] = []
    page = 1
    sep = "&" if "?" in endpoint else "?"
    while True:
        chunk = gh_json("api", f"{endpoint}{sep}per_page=100&page={page}")
        if not isinstance(chunk, list):
            raise GhError(f"{endpoint}: ожидался список")
        out.extend(chunk)
        if len(chunk) < 100:
            return out
        page += 1


def repo_from_remote() -> Tuple[str, str]:
    data = gh_json("repo", "view", "--json", "owner,name")
    return data["owner"]["login"], data["name"]


def parse_pr_ref(ref: str, remote: Optional[Tuple[str, str]] = None) -> Tuple[str, str, int]:
    m = PR_URL_RE.search(ref)
    if m:
        return m.group("owner"), m.group("repo"), int(m.group("number"))
    if ref.lstrip("#").isdigit():
        owner, repo = remote or repo_from_remote()
        return owner, repo, int(ref.lstrip("#"))
    raise GhError(f"не PR: {ref!r} (ожидается номер или URL)")


# ------------------------------------------------------------ pure logic

def real_reviews(reviews: Iterable[Dict[str, Any]], me: str) -> List[Dict[str, Any]]:
    """Reviews that count as rounds: mine, and either carrying a verdict or a
    non-empty body. GitHub records every standalone thread reply as a separate
    COMMENTED review with an empty body; those are not rounds."""
    out = []
    for r in reviews:
        if (r.get("user") or {}).get("login") != me:
            continue
        state = r.get("state")
        body = (r.get("body") or "").strip()
        if state in ("APPROVED", "CHANGES_REQUESTED") or body:
            out.append(r)
    out.sort(key=lambda r: r.get("submitted_at") or "")
    return out


def valid_lines_from_patch(patch: str) -> set:
    """RIGHT-side lines a review comment may attach to: added and context lines."""
    valid = set()
    new_line: Optional[int] = None
    for line in patch.splitlines():
        m = HUNK_RE.match(line)
        if m:
            new_line = int(m.group(1))
            continue
        if new_line is None:
            continue
        if line.startswith("+"):
            valid.add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith("\\"):
            continue
        else:
            valid.add(new_line)
            new_line += 1
    return valid


def parse_comments(text: str) -> List[Dict[str, Any]]:
    """Parse pr-comments.md: headers `### ID — `path`, line N` (or `lines A-B`)
    followed by a 4-backtick fenced body. The outer fence is four backticks so
    bodies may contain nested three-backtick code fences."""
    matches = list(HEADER_RE.finditer(text))
    comments: List[Dict[str, Any]] = []
    for i, m in enumerate(matches):
        chunk = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        fence = FENCE_RE.search(chunk)
        if not fence:
            raise GhError(f"нет тела в 4-бэктиковом фенсе после заголовка: {m.group(0).strip()}")
        body = fence.group(1).strip()
        path = m.group("path").strip().strip("`")
        if m.group("line"):
            comments.append({"path": path, "side": "RIGHT", "line": int(m.group("line")), "body": body})
        else:
            start, end = int(m.group("start")), int(m.group("end"))
            if start == end:
                comments.append({"path": path, "side": "RIGHT", "line": end, "body": body})
            else:
                comments.append({"path": path, "side": "RIGHT", "start_line": start,
                                 "start_side": "RIGHT", "line": end, "body": body})
    return comments


def find_problems(comments: List[Dict[str, Any]], files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hunks = {f["filename"]: valid_lines_from_patch(f.get("patch") or "") for f in files}
    problems = []
    for c in comments:
        valid = hunks.get(c["path"], set())
        end = c["line"]
        start = c.get("start_line", end)
        if start not in valid or end not in valid:
            problems.append({"path": c["path"], "start": start, "end": end,
                             "reason": "строка вне diff hunks" if c["path"] in hunks else "файл не в diff PR"})
    return problems


# --------------------------------------------------------------- commands

def cmd_user(ns) -> int:
    print(json.dumps(gh_json("api", "user", "--jq", "{login, name}"), ensure_ascii=False))
    return 0


def cmd_view(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    d = gh_json("pr", "view", str(n), "--repo", f"{owner}/{repo}", "--json",
                "number,title,headRefName,headRefOid,baseRefName,author,state,body,url,isDraft")
    print(json.dumps({
        "owner": owner, "repo": repo, "number": d["number"], "title": d["title"],
        "head_ref": d["headRefName"], "head_sha": d["headRefOid"], "base_ref": d["baseRefName"],
        "author": (d.get("author") or {}).get("login"), "state": d["state"], "draft": d.get("isDraft"),
        "url": d.get("url"), "body": d.get("body") or "",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_files(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    files = paginate(f"repos/{owner}/{repo}/pulls/{n}/files")
    if ns.names:
        for f in files:
            print(f["filename"])
    else:
        print(json.dumps(files, ensure_ascii=False))
    return 0


def current_login() -> str:
    # `--jq .login` prints a bare string (jq -r semantics), not JSON.
    return gh("api", "user", "--jq", ".login").strip()


def cmd_reviews_mine(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    me = current_login()
    reviews = paginate(f"repos/{owner}/{repo}/pulls/{n}/reviews")
    mine = real_reviews(reviews, me)
    print(json.dumps({
        "me": me,
        "rounds": len(mine),
        "previous_sha": mine[-1]["commit_id"] if mine else None,
        "previous_review_id": mine[-1]["id"] if mine else None,
        "reviews": [{"id": r["id"], "state": r["state"], "commit_id": r["commit_id"],
                     "submitted_at": r.get("submitted_at"), "body_len": len((r.get("body") or "").strip())}
                    for r in mine],
    }, ensure_ascii=False, indent=2))
    return 0


THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          comments(first: 50) {
            nodes { databaseId author { login } body path line originalLine outdated createdAt }
          }
        }
      }
    }
  }
}
"""


def cmd_threads(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    me = current_login() if ns.mine else None
    threads: List[Dict[str, Any]] = []
    after: Optional[str] = None
    while True:
        args = ["api", "graphql", "-F", f"owner={owner}", "-F", f"name={repo}", "-F", f"number={n}",
                "-f", f"query={THREADS_QUERY}"]
        if after:
            args += ["-F", f"after={after}"]
        data = gh_json(*args)
        conn = data["data"]["repository"]["pullRequest"]["reviewThreads"]
        for t in conn["nodes"]:
            comments = [{
                "id": c["databaseId"], "author": (c.get("author") or {}).get("login"), "body": c["body"],
                "path": c["path"], "line": c["line"], "original_line": c["originalLine"],
                "outdated": c["outdated"], "created_at": c["createdAt"],
            } for c in t["comments"]["nodes"]]
            if me and not any(c["author"] == me for c in comments):
                continue
            threads.append({"id": t["id"], "resolved": t["isResolved"], "outdated": t["isOutdated"],
                            "path": t["path"], "line": t["line"], "comments": comments})
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
    print(json.dumps(threads, ensure_ascii=False, indent=2))
    return 0


def cmd_build_payload(ns) -> int:
    d = Path(ns.dir)
    body = (d / "pr-body.md").read_text(encoding="utf-8").strip()
    comments_file = d / "pr-comments.md"
    comments = parse_comments(comments_file.read_text(encoding="utf-8")) if comments_file.exists() else []
    if ns.event not in ("APPROVE", "COMMENT", "REQUEST_CHANGES"):
        raise GhError("event должен быть APPROVE, COMMENT или REQUEST_CHANGES")
    payload = {"commit_id": ns.sha, "body": body, "event": ns.event, "comments": comments}
    (d / "payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload.json: {len(comments)} inline, event {ns.event}, sha {ns.sha[:7]}")
    return 0


def cmd_validate(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    payload = json.loads((Path(ns.dir) / "payload.json").read_text(encoding="utf-8"))
    files = paginate(f"repos/{owner}/{repo}/pulls/{n}/files")
    problems = find_problems(payload.get("comments") or [], files)
    print(json.dumps({"problems": problems, "checked": len(payload.get("comments") or [])},
                     ensure_ascii=False, indent=2))
    return 1 if problems else 0


def cmd_submit(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    payload_path = Path(ns.dir) / "payload.json"
    out = gh_json("api", "-X", "POST", f"repos/{owner}/{repo}/pulls/{n}/reviews",
                  "--input", str(payload_path), "--jq", "{id, state, html_url, submitted_at}")
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_reply(ns) -> int:
    owner, repo, n = parse_pr_ref(ns.pr)
    replies = json.loads(Path(ns.file).read_text(encoding="utf-8"))
    posted: List[int] = []
    for i, r in enumerate(replies, 1):
        try:
            rid = gh_json("api", "-X", "POST", f"repos/{owner}/{repo}/pulls/{n}/comments",
                          "-f", f"body={r['body']}", "-F", f"in_reply_to={int(r['in_reply_to'])}",
                          "--jq", ".id")
        except GhError as e:
            print(json.dumps({"posted": posted, "failed_index": i, "error": str(e)}, ensure_ascii=False))
            return 1
        posted.append(rid)
        print(f"R{i}/{len(replies)} ok id={rid}", file=sys.stderr)
    print(json.dumps({"posted": posted}, ensure_ascii=False))
    return 0


def cmd_permalink(ns) -> int:
    owner, repo, _ = parse_pr_ref(ns.pr)
    url = f"https://github.com/{owner}/{repo}/blob/{ns.sha}/{ns.path}"
    if ns.line:
        url += f"#L{ns.line}" + (f"-L{ns.end}" if ns.end else "")
    print(url)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("user"); p.set_defaults(fn=cmd_user)
    p = sub.add_parser("view"); p.add_argument("pr"); p.set_defaults(fn=cmd_view)
    p = sub.add_parser("files"); p.add_argument("pr"); p.add_argument("--names", action="store_true"); p.set_defaults(fn=cmd_files)
    p = sub.add_parser("reviews-mine"); p.add_argument("pr"); p.set_defaults(fn=cmd_reviews_mine)
    p = sub.add_parser("threads"); p.add_argument("pr"); p.add_argument("--mine", action="store_true"); p.set_defaults(fn=cmd_threads)
    p = sub.add_parser("build-payload"); p.add_argument("--dir", required=True); p.add_argument("--sha", required=True)
    p.add_argument("--event", required=True); p.set_defaults(fn=cmd_build_payload)
    p = sub.add_parser("validate"); p.add_argument("--dir", required=True); p.add_argument("pr"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("submit"); p.add_argument("--dir", required=True); p.add_argument("pr"); p.set_defaults(fn=cmd_submit)
    p = sub.add_parser("reply"); p.add_argument("pr"); p.add_argument("--file", required=True); p.set_defaults(fn=cmd_reply)
    p = sub.add_parser("permalink"); p.add_argument("pr"); p.add_argument("--sha", required=True)
    p.add_argument("path"); p.add_argument("line", nargs="?"); p.add_argument("end", nargs="?"); p.set_defaults(fn=cmd_permalink)
    ns = ap.parse_args(argv)
    try:
        return ns.fn(ns)
    except GhError as e:
        print(f"omixflow/github: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
