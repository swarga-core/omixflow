#!/usr/bin/env python3
"""Kanban board of the tracker adapter `kanban` (adapters/tracker/kanban.md).

    board.py [--project DIR] init
    board.py [--project DIR] create --title T [--type TYPE] [--kind task|epic] [--parent ID]
                                    [--slug S] [--from FILE]                  # prints the id
    board.py [--project DIR] get ID                                          # JSON with rev
    board.py [--project DIR] list [--column C] [--kind K] [--parent ID] [--owner U]
    board.py [--project DIR] path ID
    board.py [--project DIR] ref ID                                          # markdown reference for a PR
    board.py [--project DIR] epic ID                                         # JSON progress of an epic
    board.py [--project DIR] describe ID --from FILE [--rev REV]             # replace task.md
    board.py [--project DIR] comment ID --text TEXT [--author A]
    board.py [--project DIR] move ID --to COLUMN [--resolution R]
    board.py [--project DIR] set ID KEY=VALUE ...
    board.py [--project DIR] link ID OTHER
    board.py [--project DIR] batch --from FILE                               # JSON list of writes, one commit
    board.py [--project DIR] render                                          # rebuild board.md
    board.py [--project DIR] pull                                            # fetch and rebase the board
    board.py [--project DIR] publish ID --from TASK_DIR                      # working copy → card
    board.py [--project DIR] checkout ID --to TASK_DIR [--force]             # card → working copy
    board.py [--project DIR] import --from-local [--dir DIR] [--apply]       # move a local tracker here
    board.py [--project DIR] doctor                                          # JSON checks for doctor
    board.py [--project DIR] detect                                          # JSON draft config or null

The board is the branch `tracker.branch` (default `board`), unrelated to the code,
checked out as a worktree at `tracker.dir` (default `.tasks/board`) of the main
checkout. Columns are folders (backlog, working, review, done); a card is the folder
`{column}/{ID}-{slug}/` with task.md, state.yaml (the formal record of the task),
comments.md and, once the pipeline publishes them, the task artifacts. The status of
a task is its column and nothing else. Ids are `{tracker.project}-{n}`. An epic groups
child tasks (`parent`); it moves by hand, except that the first child taken into work
lifts it from backlog to working. A child closes in done, canceled or not.

Every write is one transaction: take a lock in the common git dir; with
`tracker.push` (default) fetch `origin/{branch}` and rebase the board onto it; apply
the change, rebuild board.md and commit; push. A push refused as non-fast-forward
(`! [rejected]`, a concurrent write) undoes the local commit and repeats the transaction
(a new id is computed for `create`, a stale revision fails `describe`); a server refusal
(`! [remote rejected]`) or no connection undoes it and fails without retries: the board
never keeps an unpublished write. Reads use the local board; `pull` refreshes it, and
`checkout` without a connection warns and reads the local board. Commands find
the board from any worktree of the repository. `describe` writes task.md only while the
task card is in backlog: after Start the session owns it and publishes it (an epic has
no session and stays writable).

`batch --from FILE` (`-` reads stdin) runs a JSON list of writes as one transaction: one
commit, one push. An operation is `{"op": ..., ...}` with the arguments of its command
(create: title, type, kind, parent, slug, text or from, and `as` naming the new card for
later operations as `$name` in id, other, parent; describe: id, text or from, rev;
comment: id, text, author; move: id, to, resolution; set: id, pairs; link: id, other;
publish: id, from). The whole list is checked before the board is touched; a failed
operation or push leaves the board as it was.

`import --from-local` moves the tasks of the `local` tracker (`.tasks/backlog` by default)
onto the board: a preview without `--apply`, one transaction with it. Tasks in work and
unfinished multitasks block the import; closed tasks bring their artifacts along.

`doctor` and `detect` are the adapter hooks `scripts.doctor` and `scripts.detect`
(protocol/adapters.md): checks of the board for doctor.py, and a draft tracker config
for `doctor --init` when the repository already has a board branch.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TypeVar

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "scripts"))
import omixflow_lib as lib  # noqa: E402

COLUMNS = ("backlog", "working", "review", "done")
KINDS = ("task", "epic")
TYPES = ("feature", "bug", "chore", "docs")
RESOLUTIONS = ("done", "canceled", "skipped")
# Resolution changes only with the column (move): it is set in done and cleared elsewhere.
SETTABLE = ("title", "type", "owner", "parent", "external", "blocked")
# The board owns these state.yaml fields and comments.md; the session owns task.md and the
# pipeline fields after Start (protocol/artifacts.md, «Хранение в задаче трекера»).
BOARD_OWNED = lib.CARD_FIELDS
BOARD_FILES = ("comments.md",)
DEFAULT_BRANCH = "board"
DEFAULT_DIR = ".tasks/board"
EXIT_STALE = 3
REMOTE = "origin"
RETRIES = 3
SANDBOX_HINT = ("в песочнице Claude Code ssh-агент недоступен — команды доски с tracker.push "
                "запускать вне песочницы (adapters/tracker/kanban.md, «Песочница»)")
T = TypeVar("T")

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
                     "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e",
                     "yu", "ya"]))

README = """# Доска задач

Доска трекера `kanban` плагина OMIXFlow: ветка `{branch}`, открытая worktree
в `{dir}/` основного дерева. Задачи — папки в колонках `backlog/`, `working/`,
`review/`, `done/`; статус задачи это её колонка. Карточка `{{ID}}-{{slug}}/` хранит
`task.md` (постановка), `state.yaml` (формальная запись и состояние пайплайна),
`comments.md` и артефакты задачи.

Вид доски: [board.md](board.md), его строит скрипт. Доска меняется только скриптом
`board.py` адаптера `kanban`: он берёт блокировку, перестраивает вид и коммитит.
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def slugify(title: str, limit: int = 40) -> str:
    out = []
    for ch in title.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    if len(slug) > limit:
        cut = slug[:limit]
        slug = cut.rsplit("-", 1)[0] if "-" in cut else cut
    return slug or "task"


def git(cwd: Path, *args: str) -> str:
    out = lib.git(cwd, *args)
    if out is None:
        raise lib.OmixflowError(f"git {' '.join(args)} не выполнился в {cwd}")
    return out


class Board:
    def __init__(self, project: Optional[Path]) -> None:
        self.root = lib.find_project_root(project)
        cfg = self.cfg = lib.load_config(self.root)
        self.prefix = str(lib.config_get(cfg, "tracker.project") or "")
        if not re.fullmatch(r"[A-Z][A-Z0-9]*", self.prefix):
            raise lib.OmixflowError("tracker.project должен быть префиксом номеров: латиница в верхнем регистре, например T")
        self.branch = str(lib.config_get(cfg, "tracker.branch") or DEFAULT_BRANCH)
        self.rel_dir = str(lib.config_get(cfg, "tracker.dir") or DEFAULT_DIR)
        push = lib.config_get(cfg, "tracker.push")
        self.push_enabled = True if push is None else bool(push)
        # Relative to the root when git prints it relative; no --path-format (git 2.31+).
        self.common = (self.root / git(self.root, "rev-parse", "--git-common-dir")).resolve()
        self.id_re = re.compile(rf"^({re.escape(self.prefix)}-(\d+))(?:-[a-z0-9-]+)?$")
        # Commit messages of the batch in progress: its writes commit once, at the end.
        self.pending: Optional[List[str]] = None

    # ------------------------------------------------------------ location
    def worktrees(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        cur: Dict[str, str] = {}
        for line in git(self.root, "worktree", "list", "--porcelain").splitlines() + [""]:
            if not line:
                if cur:
                    items.append(cur)
                cur = {}
            elif line.startswith("worktree "):
                cur["path"] = line[len("worktree "):]
            elif line.startswith("branch "):
                cur["branch"] = line[len("branch refs/heads/"):]
        return items

    def main_tree(self) -> Path:
        return Path(self.worktrees()[0]["path"])

    def location(self) -> Optional[Path]:
        for wt in self.worktrees():
            if wt.get("branch") == self.branch:
                return Path(wt["path"])
        return None

    def board(self) -> Path:
        loc = self.location()
        if loc is None:
            raise lib.OmixflowError(f"доска не открыта: нет worktree ветки {self.branch}; board.py init")
        return loc

    @contextmanager
    def locked(self) -> Iterator[None]:
        with open(self.common / "omixflow-board.lock", "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---------------------------------------------------------------- remote
    def remote_on(self) -> bool:
        if not self.push_enabled:
            return False
        if lib.git(self.root, "remote", "get-url", REMOTE) is None:
            raise lib.OmixflowError(f"tracker.push: true, но у репозитория нет remote {REMOTE}: "
                                    "добавь remote или поставь tracker.push: false")
        return True

    def remote_ref(self) -> Optional[str]:
        ref = f"refs/remotes/{REMOTE}/{self.branch}"
        return ref if lib.git(self.root, "rev-parse", "--verify", "--quiet", ref) is not None else None

    def fetch(self) -> None:
        proc = subprocess.run(["git", "-C", str(self.root), "fetch", "-q", REMOTE],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise NoConnection(f"нет связи с {REMOTE}: доска не обновлена ({proc.stderr.strip()}); {SANDBOX_HINT}")

    def refresh(self) -> None:
        """Bring the local board onto the remote one before a change."""
        if not self.remote_on():
            return
        self.fetch()
        ref = self.remote_ref()
        if ref is None:
            return
        board = self.board()
        if lib.git(board, "rebase", "-q", ref) is None:
            lib.git(board, "rebase", "--abort")
            raise lib.OmixflowError("локальная доска расходится с удалённой и не перебазируется: "
                                    "разрешить вручную в worktree доски")

    def head(self) -> str:
        return git(self.board(), "rev-parse", "HEAD")

    def restore(self, head: str) -> None:
        board = self.board()
        git(board, "reset", "-q", "--hard", head)
        git(board, "clean", "-fdq")

    def _before_push(self) -> None:
        """Hook for tests: runs between the local commit and the push."""

    def push(self) -> Tuple[str, str]:
        """Push the board: ("ok" | "rejected" | "failed" | "offline", git's message).
        Only a non-fast-forward refusal (`! [rejected]`) is a concurrent write worth a retry;
        `! [remote rejected]` is the server's refusal (error, hook, branch rule)."""
        self._before_push()
        proc = subprocess.run(["git", "-C", str(self.board()), "push", "-q", REMOTE,
                               f"{self.branch}:{self.branch}"], capture_output=True, text=True)
        if proc.returncode == 0:
            return "ok", ""
        err = proc.stderr.strip()
        if "[remote rejected]" in err:
            return "failed", err
        if "[rejected]" in err or "non-fast-forward" in err or "fetch first" in err:
            return "rejected", err
        return "offline", err

    def transaction(self, fn: Callable[[], T]) -> T:
        with self.locked():
            for _ in range(RETRIES):
                self.refresh()
                head = self.head()
                try:
                    result = fn()
                except Exception:
                    self.restore(head)
                    raise
                if not self.push_enabled or self.head() == head:
                    return result
                status, detail = self.push()
                if status == "ok":
                    return result
                self.restore(head)
                if status == "failed":
                    raise lib.OmixflowError(f"{REMOTE} отклонил push доски: запись отменена, доска не изменилась "
                                            f"({detail}); повтор не поможет, пока не устранена причина на стороне "
                                            f"{REMOTE}")
                if status == "offline":
                    raise NoConnection(f"нет связи с {REMOTE}: запись отменена, доска не изменилась ({detail}); "
                                       f"{SANDBOX_HINT}")
            raise lib.OmixflowError(f"push доски отклонён {RETRIES} раза подряд: доска занята, повтори позже")

    def pull(self) -> str:
        with self.locked():
            self.refresh()
            return self.head()[:8]

    # ---------------------------------------------------------------- cards
    def cards(self) -> Dict[str, Path]:
        board = self.board()
        found: Dict[str, Path] = {}
        for column in COLUMNS:
            col = board / column
            for d in sorted(col.iterdir()) if col.exists() else []:
                m = self.id_re.match(d.name)
                if m and d.is_dir():
                    found[m.group(1)] = d
        return found

    def card(self, cid: str) -> Path:
        path = self.cards().get(cid)
        if path is None:
            raise lib.OmixflowError(f"нет карточки {cid}")
        return path

    def next_id(self) -> str:
        numbers = [int(self.id_re.match(p.name).group(2)) for p in self.cards().values()]
        return f"{self.prefix}-{max(numbers, default=0) + 1}"

    @staticmethod
    def read_state(card: Path) -> Dict[str, Any]:
        lib.require_yaml()
        return lib.yaml.safe_load((card / "state.yaml").read_text(encoding="utf-8")) or {}

    @staticmethod
    def write_state(card: Path, state: Dict[str, Any]) -> None:
        state["updated"] = now()
        (card / "state.yaml").write_text(
            lib.yaml.safe_dump(state, sort_keys=False, allow_unicode=True, default_flow_style=False),
            encoding="utf-8")

    @staticmethod
    def rev(card: Path) -> str:
        return hashlib.sha1((card / "task.md").read_bytes()).hexdigest()[:12]

    def summary(self, cid: str, card: Path) -> Dict[str, Any]:
        st = self.read_state(card)
        return {"id": cid, "kind": st.get("kind"), "title": st.get("title"), "type": st.get("type"),
                "column": card.parent.name, "owner": st.get("owner"), "parent": st.get("parent"),
                "blocked": st.get("blocked"), "resolution": st.get("resolution"), "path": str(card)}

    # ---------------------------------------------------------------- commit
    def commit(self, message: str) -> None:
        if self.pending is not None:
            self.pending.append(message)
            return
        board = self.board()
        for column in COLUMNS:
            col = board / column
            col.mkdir(exist_ok=True)
            keep = col / ".gitkeep"
            has_cards = any(d.is_dir() for d in col.iterdir())
            if has_cards and keep.exists():
                keep.unlink()
            elif not has_cards and not keep.exists():
                keep.write_text("", encoding="utf-8")
        (board / "board.md").write_text(self.render(), encoding="utf-8")
        git(board, "add", "-A")
        if git(board, "status", "--porcelain"):
            git(board, "commit", "-q", "-m", message)

    def render(self) -> str:
        cards = self.cards()
        states = {cid: self.read_state(p) for cid, p in cards.items()}
        board = self.board()

        def link(cid: str) -> str:
            return f"[{cid}]({cards[cid].relative_to(board).as_posix()}/task.md)"

        lines = ["# Доска", "", "Строится скриптом `board.py`, руками не правится.", ""]
        epics = [cid for cid in cards if states[cid].get("kind") == "epic"]
        if epics:
            lines += ["## Эпики", ""]
            for eid in sorted(epics, key=self.number):
                p = self.progress(eid, cards, states)
                note = f" (отменено {p['canceled']})" if p["canceled"] else ""
                lines.append(f"- {link(eid)} {states[eid].get('title')} · {p['closed']}/{p['total']} закрыто{note}")
                for c in p["children"]:
                    mark = f" ✗ {c['resolution']}" if c["resolution"] not in (None, "done") else ""
                    lines.append(f"  - {c['id']} ({c['column']}{mark})")
            lines.append("")
        for column in COLUMNS:
            in_col = sorted((c for c in cards if cards[c].parent.name == column), key=self.number)
            lines += [f"## {column} ({len(in_col)})", ""]
            for cid in in_col:
                st = states[cid]
                parts = [f"- {link(cid)} {st.get('title')}"]
                parts += [x for x in (st.get("kind") if st.get("kind") == "epic" else st.get("type"),
                                      st.get("owner")) if x]
                text = " · ".join(parts)
                if st.get("parent"):
                    text += f" · эпик {st['parent']}"
                if st.get("resolution") and st.get("resolution") != "done":
                    text += f" · ✗ {st['resolution']}"
                if st.get("blocked"):
                    text += f" · ⛔ {st['blocked']}"
                lines.append(text)
            lines.append("")
        return "\n".join(lines)

    def progress(self, eid: str, cards: Dict[str, Path], states: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Children of an epic and how many are closed (in done) and canceled."""
        children = [{"id": c, "title": states[c].get("title"), "column": cards[c].parent.name,
                     "resolution": states[c].get("resolution")}
                    for c in sorted(cards, key=self.number) if states[c].get("parent") == eid]
        closed = [c for c in children if c["column"] == "done"]
        canceled = [c for c in closed if c["resolution"] in ("canceled", "skipped")]
        return {"id": eid, "title": states[eid].get("title"), "column": cards[eid].parent.name,
                "children": children, "total": len(children), "closed": len(closed),
                "canceled": len(canceled), "complete": bool(children) and len(closed) == len(children)}

    def epic(self, eid: str) -> Dict[str, Any]:
        cards = self.cards()
        states = {cid: self.read_state(p) for cid, p in cards.items()}
        if eid not in cards:
            raise lib.OmixflowError(f"нет карточки {eid}")
        if states[eid].get("kind") != "epic":
            raise lib.OmixflowError(f"{eid} не эпик")
        return self.progress(eid, cards, states)

    def ref(self, cid: str) -> str:
        """Markdown reference to the task for a PR body: the card path changes with its
        column, so the link goes to board.md of the board branch."""
        title = self.read_state(self.card(cid)).get("title")
        url = lib.git(self.root, "remote", "get-url", REMOTE) or ""
        m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", url)
        where = (f"[доска](https://github.com/{m.group(1)}/{m.group(2)}/blob/{self.branch}/board.md)" if m
                 else f"доска: ветка `{self.branch}`, `board.md`")
        return f"{cid} «{title}» · {where}"

    def number(self, cid: str) -> int:
        return int(cid.rsplit("-", 1)[1])

    # -------------------------------------------------------------- commands
    def init(self) -> str:
        loc = self.location()
        if loc is not None:
            return f"доска уже открыта: {loc}"
        remote = self.remote_on()
        if remote:
            self.fetch()
        target = self.main_tree() / self.rel_dir
        if lib.git(self.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{self.branch}") is None:
            ref = self.remote_ref() if remote else None
            if ref is not None:
                git(self.root, "branch", self.branch, ref)
            else:
                empty = git(self.root, "hash-object", "-t", "tree", "/dev/null")
                sha = git(self.root, "commit-tree", empty, "-m", "board: init")
                git(self.root, "branch", self.branch, sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        git(self.root, "worktree", "add", "-q", str(target), self.branch)
        board = self.board()
        if not (board / "README.md").exists():
            (board / "README.md").write_text(README.format(branch=self.branch, dir=self.rel_dir), encoding="utf-8")
        self.commit("board: init")
        if remote and self.push()[0] != "ok":
            raise lib.OmixflowError(f"доска создана локально, но не опубликована в {REMOTE}: "
                                    "проверь связь и права, затем board.py pull")
        return str(board)

    def create(self, title: str, typ: str, kind: str, parent: Optional[str], slug: Optional[str],
               text: str) -> str:
        if kind not in KINDS:
            raise lib.OmixflowError(f"вид карточки: {KINDS}")
        if typ not in TYPES:
            raise lib.OmixflowError(f"тип задачи: {TYPES}")
        if parent:
            self.check_parent(parent)
        if not title.strip():
            raise lib.OmixflowError("название не может быть пустым")
        cid = self.next_id()
        card = self.board() / "backlog" / f"{cid}-{slugify(slug or title)}"
        card.mkdir(parents=True)
        (card / "task.md").write_text(f"# {cid}: {title}\n\n## Исходная формулировка\n\n{text.strip()}\n",
                                      encoding="utf-8")
        state = {"schema": 1, "id": cid, "kind": kind, "title": title, "type": typ, "owner": None,
                 "parent": parent, "links": [], "external": None, "resolution": None, "blocked": None,
                 "created": today()}
        self.write_state(card, state)
        self.commit(f"board: {cid} create")
        return cid

    def check_parent(self, parent: str, child: Optional[str] = None) -> None:
        if parent == child:
            raise lib.OmixflowError(f"{child} не может быть родителем самому себе")
        if self.read_state(self.card(parent)).get("kind") != "epic":
            raise lib.OmixflowError(f"{parent} не эпик: родителем задачи может быть только эпик")

    def describe(self, cid: str, text: str, expect: Optional[str]) -> str:
        card = self.card(cid)
        if card.parent.name != "backlog" and self.read_state(card).get("kind") != "epic":
            raise lib.OmixflowError(f"{cid} в {card.parent.name}: после Start постановкой владеет рабочая копия "
                                    "сессии; правится task.md рабочей копии и публикуется")
        if expect is not None and self.rev(card) != expect:
            raise StaleRevision(f"{cid}: task.md изменился после чтения (ревизия {self.rev(card)}, "
                                f"ожидалась {expect}); перечитать и повторить")
        (card / "task.md").write_text(text, encoding="utf-8")
        self.commit(f"board: {cid} describe")
        return self.rev(card)

    def comment(self, cid: str, text: str, author: str) -> None:
        card = self.card(cid)
        path = card / "comments.md"
        head = "" if path.exists() else "# Комментарии\n\n"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{head}- {today()} {author}: {text.strip()}\n")
        self.commit(f"board: {cid} comment")

    def move(self, cid: str, column: str, resolution: Optional[str]) -> str:
        if column not in COLUMNS:
            raise lib.OmixflowError(f"колонка: {COLUMNS}")
        if resolution and resolution not in RESOLUTIONS:
            raise lib.OmixflowError(f"резолюция: {RESOLUTIONS}")
        if resolution and column != "done":
            raise lib.OmixflowError("резолюция только при переезде в done")
        card = self.card(cid)
        source = card.parent.name
        target = self.relocate(card, column)
        state = self.read_state(target)
        state["resolution"] = (resolution or "done") if column == "done" else None
        self.write_state(target, state)
        note = ""
        parent = self.cards().get(state.get("parent") or "")
        if column == "working" and parent is not None and parent.parent.name == "backlog":
            lifted = self.relocate(parent, "working")
            self.write_state(lifted, self.read_state(lifted))
            note = f", эпик {state['parent']} → working"
        self.commit(f"board: {cid} move {source} → {column}{note}")
        return str(target)

    def relocate(self, card: Path, column: str) -> Path:
        target = self.board() / column / card.name
        if card.parent.name != column:
            target.parent.mkdir(exist_ok=True)
            shutil.move(str(card), str(target))
        return target

    def set_fields(self, cid: str, pairs: List[str]) -> List[str]:
        """Set formal fields; returns warnings. A new title rewrites the heading of task.md
        while the session does not own it (backlog, or an epic)."""
        card = self.card(cid)
        state = self.read_state(card)
        warnings: List[str] = []
        for pair in pairs:
            key, sep, value = pair.partition("=")
            if not sep or key not in SETTABLE:
                hint = "; резолюция меняется с колонкой: move --to done --resolution R" if key == "resolution" else ""
                raise lib.OmixflowError(f"ожидается KEY=VALUE, KEY из {SETTABLE}: {pair!r}{hint}")
            val: Any = value if value not in ("", "null") else None
            if key == "type" and val not in TYPES:
                raise lib.OmixflowError(f"тип задачи: {TYPES}")
            if key == "title" and not val:
                raise lib.OmixflowError("название не может быть пустым")
            if key == "parent" and val is not None:
                self.check_parent(val, cid)
            if key == "title":
                warnings += self.retitle(cid, card, state, val)
            state[key] = val
        self.write_state(card, state)
        self.commit(f"board: {cid} set {' '.join(p.split('=', 1)[0] for p in pairs)}")
        return warnings

    def retitle(self, cid: str, card: Path, state: Dict[str, Any], title: str) -> List[str]:
        if card.parent.name != "backlog" and state.get("kind") != "epic":
            return [f"{cid} в {card.parent.name}: заголовок task.md принадлежит рабочей копии сессии, "
                    "поправить его там"]
        path = card / "task.md"
        head, sep, rest = path.read_text(encoding="utf-8").partition("\n")
        if not head.startswith(f"# {cid}: "):
            return [f"{cid}: первая строка task.md не вида «# {cid}: …», заголовок не тронут"]
        path.write_text(f"# {cid}: {title}{sep}{rest}", encoding="utf-8")
        return []

    def link(self, a: str, b: str) -> None:
        if a == b:
            raise lib.OmixflowError("карточка не связывается сама с собой")
        cards = {a: self.card(a), b: self.card(b)}
        for me, other in ((a, b), (b, a)):
            st = self.read_state(cards[me])
            links = list(st.get("links") or [])
            if other not in links:
                links.append(other)
            st["links"] = links
            self.write_state(cards[me], st)
        self.commit(f"board: {a} link {b}")


def card_files(root: Path) -> Dict[str, bytes]:
    """Relative path → content of every file under `root`, except the board-owned ones."""
    out: Dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel not in BOARD_FILES:
            out[rel] = path.read_bytes()
    return out


def publish(b: "Board", cid: str, source: Path) -> int:
    """Copy the working copy into the card: additive, comments.md untouched, state.yaml
    merged (board-owned fields from the card, the rest from the working copy)."""
    if not (source / "state.yaml").exists():
        raise lib.OmixflowError(f"{source}: нет state.yaml, публиковать нечего")
    card = b.card(cid)
    files = card_files(source)
    for rel, data in files.items():
        if rel == "state.yaml":
            continue
        target = card / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    working = lib.yaml.safe_load(files["state.yaml"].decode("utf-8")) or {}
    board_state = b.read_state(card)
    merged = dict(working)
    for key in BOARD_OWNED:
        if key in board_state:
            merged[key] = board_state[key]
    b.write_state(card, merged)
    b.commit(f"board: {cid} publish")
    return len(files)


def checkout(b: "Board", cid: str, target: Path, force: bool) -> str:
    """Restore the working copy from the card: afterwards it equals the card (files the card
    lacks are removed); refuse to clobber a different copy without --force. Without a
    connection it reads the local board and warns (a read, like `pull` in «Свежесть»)."""
    with b.locked():
        try:
            b.refresh()
        except NoConnection as e:
            print(f"omixflow: {e}; рабочая копия восстановлена из локальной доски, она может отставать "
                  f"от {REMOTE}", file=sys.stderr)
    card = b.card(cid)
    theirs = card_files(card)
    mine = card_files(target) if target.exists() else {}
    if not force:
        differs = sorted(rel for rel in mine if rel != "state.yaml" and theirs.get(rel) != mine[rel])
        if differs:
            raise lib.OmixflowError(f"{target}: рабочая копия отличается от карточки ({', '.join(differs[:5])}); "
                                    "неопубликованная работа? перезапись только с --force")
    for rel, data in theirs.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for rel in set(mine) - set(theirs):
        (target / rel).unlink()
    for d in sorted((p for p in target.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return str(target)


# op → (required arguments, optional arguments)
BATCH_OPS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "create": (("title",), ("type", "kind", "parent", "slug", "text", "from", "as")),
    "describe": (("id",), ("text", "from", "rev")),
    "comment": (("id", "text"), ("author",)),
    "move": (("id", "to"), ("resolution",)),
    "set": (("id", "pairs"), ()),
    "link": (("id", "other"), ()),
    "publish": (("id", "from"), ()),
}
ALIAS_RE = re.compile(r"^\$[A-Za-z0-9_-]+$")


def load_batch(b: "Board", source: str) -> List[Dict[str, Any]]:
    """Read and check the whole batch before the board is touched: known operations and
    arguments, values the commands accept, aliases defined before use; text files are read
    now, so a retried transaction replays the same batch."""
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as e:
        raise lib.OmixflowError(f"пакет: не JSON ({e})")
    if not isinstance(ops, list) or not ops:
        raise lib.OmixflowError("пакет: ожидается непустой JSON-список операций")
    aliases: set = set()
    out: List[Dict[str, Any]] = []
    for n, op in enumerate(ops, 1):
        def fail(msg: str) -> lib.OmixflowError:
            return lib.OmixflowError(f"пакет, операция {n}: {msg}; доска не тронута")
        if not isinstance(op, dict) or op.get("op") not in BATCH_OPS:
            raise fail(f"ожидается объект с op из {tuple(BATCH_OPS)}")
        required, optional = BATCH_OPS[op["op"]]
        # null for an optional argument means "not given", as an omitted CLI flag
        args = {k: v for k, v in op.items() if k != "op" and not (v is None and k in optional)}
        missing = [k for k in required if args.get(k) in (None, "", [])]
        unknown = sorted(set(args) - set(required) - set(optional))
        if missing or unknown:
            raise fail(f"{op['op']}: " + "; ".join(x for x in (missing and f"нет {', '.join(missing)}",
                                                                unknown and f"лишнее {', '.join(unknown)}") if x))
        not_text = sorted(k for k, v in args.items() if k != "pairs" and not isinstance(v, str))
        if not_text:
            raise fail(f"{op['op']}: значения {', '.join(not_text)} — строки")
        refs = [args.get(k) for k in ("id", "other", "parent")]
        if op["op"] == "set":
            if not isinstance(args["pairs"], list) or not all(isinstance(p, str) for p in args["pairs"]):
                raise fail("set: pairs — список строк KEY=VALUE")
            for pair in args["pairs"]:
                key, sep, value = pair.partition("=")
                if not sep or key not in SETTABLE:
                    raise fail(f"set: ожидается KEY=VALUE, KEY из {SETTABLE}: {pair!r}")
                if key == "parent":
                    refs.append(value)
        for ref in refs:
            if isinstance(ref, str) and ref.startswith("$") and ref not in aliases:
                raise fail(f"алиас {ref} не задан созданием выше")
        if op["op"] == "create":
            args.setdefault("type", str(lib.config_get(b.cfg, "tracker.create_defaults.type") or "feature"))
            args.setdefault("kind", "task")
            if args["type"] not in TYPES or args["kind"] not in KINDS:
                raise fail(f"create: тип из {TYPES}, вид из {KINDS}")
            alias = args.get("as")
            if alias is not None:
                if not isinstance(alias, str) or not ALIAS_RE.match(alias) or alias in aliases:
                    raise fail(f"as: новый алиас вида $имя, а не {alias!r}")
                aliases.add(alias)
        if op["op"] in ("create", "describe"):
            if "text" in args and "from" in args:
                raise fail(f"{op['op']}: text или from, не оба")
            if "from" in args:
                try:
                    args["text"] = Path(args.pop("from")).read_text(encoding="utf-8")
                except OSError as e:
                    raise fail(f"{op['op']}: {e}")
            if op["op"] == "describe" and "text" not in args:
                raise fail("describe: нет text или from")
        if op["op"] == "move" and (args["to"] not in COLUMNS or args.get("resolution") not in (None, *RESOLUTIONS)):
            raise fail(f"move: колонка из {COLUMNS}, резолюция из {RESOLUTIONS}")
        if op["op"] == "comment":
            args.setdefault("author", lib.git(b.root, "config", "user.name") or "unknown")
        if op["op"] == "publish":
            args["from"] = str(Path(args["from"]).resolve())
        out.append({"op": op["op"], **args})
    return out


def run_batch(b: "Board", ops: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """All operations in one transaction and one commit; returns the result and warnings."""
    def apply() -> Tuple[Dict[str, str], List[str]]:
        created: Dict[str, str] = {}
        warnings: List[str] = []

        def ref(value: Any) -> Any:
            return created[value] if isinstance(value, str) and value.startswith("$") else value

        b.pending = []
        try:
            for n, op in enumerate(ops, 1):
                try:
                    kind = op["op"]
                    if kind == "create":
                        cid = b.create(op["title"], op["type"], op["kind"], ref(op.get("parent")), op.get("slug"),
                                       op.get("text", ""))
                        created[op.get("as") or f"#{n}"] = cid
                    elif kind == "describe":
                        b.describe(ref(op["id"]), op["text"], op.get("rev"))
                    elif kind == "comment":
                        b.comment(ref(op["id"]), op["text"], op["author"])
                    elif kind == "move":
                        b.move(ref(op["id"]), op["to"], op.get("resolution"))
                    elif kind == "set":
                        pairs = [f"{k}={ref(v) if k == 'parent' else v}"
                                 for k, _, v in (p.partition("=") for p in op["pairs"])]
                        warnings += b.set_fields(ref(op["id"]), pairs)
                    elif kind == "link":
                        b.link(ref(op["id"]), ref(op["other"]))
                    elif kind == "publish":
                        publish(b, ref(op["id"]), Path(op["from"]))
                except (lib.OmixflowError, OSError) as e:
                    cls = type(e) if isinstance(e, lib.OmixflowError) else lib.OmixflowError
                    raise cls(f"пакет, операция {n} ({op['op']}): {e}; доска не изменилась") from e
            messages = b.pending
        finally:
            b.pending = None
        b.commit(batch_message(b, messages))
        return created, warnings

    created, warnings = b.transaction(apply)
    return {"commit": b.head()[:8], "created": created, "ops": len(ops)}, warnings


def batch_message(b: "Board", messages: List[str]) -> str:
    """Subject with the cards the batch touched, body with one line per write."""
    lines = [m[len("board: "):] if m.startswith("board: ") else m for m in messages]
    ids: List[str] = []
    for line in lines:
        for cid in re.findall(rf"\b{re.escape(b.prefix)}-\d+\b", line):
            if cid not in ids:
                ids.append(cid)
    subject = f"board: batch — {len(lines)} записей: {', '.join(ids)}" if ids else f"board: batch — {len(lines)} записей"
    return subject + "\n\n" + "\n".join(f"- {line}" for line in lines)


class StaleRevision(lib.OmixflowError):
    pass


class NoConnection(lib.OmixflowError):
    """origin is unreachable (network, credentials, or the sandbox without the ssh agent)."""


LOCAL_COLUMNS = {"draft": "backlog", "ready": "backlog", "in_work": "working", "in_review": "review",
                 "done": "done", "canceled": "done"}
LOCAL_DIR = ".tasks/backlog"
MULTITASK_RE = re.compile(r"^<!-- omixflow:multitask:start", re.M)
JOURNAL_RE = re.compile(r"^## Журнал[ \t]*$", re.M)


def local_tasks(src: Path) -> List[Dict[str, Any]]:
    """Task files of the `local` tracker (adapters/tracker/local.md, «Формат файла»)."""
    tasks = []
    for path in sorted(src.glob("*.md")) if src.is_dir() else []:
        if path.name == "README.md":
            continue
        meta, body = lib.parse_frontmatter(path)
        if not meta.get("id"):
            continue
        description, *rest = JOURNAL_RE.split(body, maxsplit=1)
        journal = rest[0] if rest else ""
        tasks.append({"slug": str(meta["id"]), "title": str(meta.get("title") or meta["id"]),
                      "status": str(meta.get("status") or "draft"), "type": str(meta.get("type") or "feature"),
                      "created": str(meta.get("created") or today()), "origin": meta.get("origin"),
                      "target": meta.get("target"), "external": meta.get("external"),
                      "links": [str(x) for x in meta.get("links") or []], "description": description.strip(),
                      "journal": [ln for ln in journal.splitlines() if ln.startswith("- ")],
                      "multitask": bool(MULTITASK_RE.search(body))})
    return tasks


def import_local(b: "Board", src: Path, artifacts: Path, apply: bool) -> List[str]:
    """Move the local tracker onto the board; returns one report line per task."""
    if not src.is_dir():
        raise lib.OmixflowError(f"нет каталога трекера local: {src}")
    cards = b.cards()
    known = {}
    for cid, card in cards.items():
        mark = str(b.read_state(card).get("imported") or "")
        if mark.startswith("local:"):
            known[mark[len("local:"):]] = cid
    tasks = [t for t in local_tasks(src) if t["slug"] not in known]
    blocked = [t for t in tasks if t["status"] not in LOCAL_COLUMNS or t["status"] in ("in_work", "in_review")
               or (t["multitask"] and t["status"] not in ("done", "canceled"))]
    if blocked:
        raise lib.OmixflowError(
            "перенос отменён, сначала довести на local: " + ", ".join(
                f"{t['slug']} ({t['status']}{', мультизадача' if t['multitask'] else ''})" for t in blocked))
    tasks.sort(key=lambda t: (t["created"], t["slug"]))
    first = int(b.next_id().rsplit("-", 1)[1])
    ids = {**known, **{t["slug"]: f"{b.prefix}-{first + i}" for i, t in enumerate(tasks)}}
    report = []
    for t in tasks:
        cid, column = ids[t["slug"]], LOCAL_COLUMNS[t["status"]]
        art = artifacts / t["slug"]
        has_art = art.is_dir() and any(art.iterdir())
        lost = [x for x in t["links"] if x not in ids]
        report.append(f"{t['slug']} → {cid} ({column}{', артефакты' if has_art else ''}"
                      f"{', без связей: ' + ', '.join(lost) if lost else ''})")
        if apply:
            write_imported(b, b.board() / column / f"{cid}-{slugify(t['slug'])}", cid, t, ids,
                           art if has_art else None)
    if apply and tasks:
        b.commit(f"board: import {len(tasks)} from local")
    return report


def write_imported(b: "Board", card: Path, cid: str, t: Dict[str, Any], ids: Dict[str, str],
                   art: Optional[Path]) -> None:
    card.mkdir(parents=True)
    pipeline: Dict[str, Any] = {}
    if art is not None:
        for rel, data in card_files(art).items():
            if rel != "state.yaml":
                (card / rel).parent.mkdir(parents=True, exist_ok=True)
                (card / rel).write_bytes(data)
        if (art / "state.yaml").exists():
            pipeline = {k: v for k, v in (b.read_state(art)).items() if k not in BOARD_OWNED and k != "updated"}
    if not (card / "task.md").exists():
        note = " · ".join(x for x in (f"перенесено из local: `{t['slug']}`",
                                      t["origin"] and f"происхождение: {t['origin']}",
                                      t["target"] and f"репозиторий: {t['target']}") if x)
        body = t["description"] if re.search(r"^## ", t["description"], re.M) \
            else f"## Исходная формулировка\n\n{t['description']}"
        (card / "task.md").write_text(f"# {cid}: {t['title']}\n\n> {note}\n\n{body}\n", encoding="utf-8")
    state = {"schema": 1, "id": cid, "kind": "task", "title": t["title"],
             "type": t["type"] if t["type"] in TYPES else "feature", "owner": None, "parent": None,
             "links": [ids[x] for x in t["links"] if x in ids], "external": t["external"],
             "resolution": {"done": "done", "canceled": "canceled"}.get(t["status"]), "blocked": None,
             "created": t["created"], "imported": f"local:{t['slug']}", **pipeline}
    b.write_state(card, state)
    if t["journal"]:
        (card / "comments.md").write_text("# Комментарии\n\n" + "\n".join(t["journal"]) + "\n", encoding="utf-8")


def diagnose(project: Optional[Path]) -> List[Dict[str, str]]:
    """Checks of the board for doctor.py: prefix, worktree, .gitignore, status_map, remote."""
    checks: List[Dict[str, str]] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    try:
        b = Board(project)
    except lib.OmixflowError as e:
        add("prefix", "FAIL", str(e))
        return checks
    add("prefix", "OK", f"номера {b.prefix}-{{n}}")
    run = f"python3 {HERE} --project {b.root}"
    loc, expected = b.location(), b.main_tree() / b.rel_dir
    remote_ref = b.remote_ref()
    if loc is None:
        if lib.git(b.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{b.branch}") is not None:
            how = f"откроет ветку {b.branch}"
        elif remote_ref:
            how = f"подхватит доску с {REMOTE}"
        else:
            how = "создаст ветку доски" + (f" и опубликует её в {REMOTE}" if b.push_enabled else "")
        add("board", "FAIL", f"доска не открыта: {run} init ({how})")
    elif loc.resolve() != expected.resolve():
        add("board", "WARN", f"доска открыта в {loc}, а tracker.dir указывает на {expected}")
    else:
        add("board", "OK", f"ветка {b.branch} в {b.rel_dir}")
    top = b.rel_dir.strip("/").split("/")[0]
    if lib.git(b.main_tree(), "check-ignore", "-q", f"{b.rel_dir}/README.md") is None:
        add("gitignore", "FAIL", f"{b.rel_dir} не игнорируется кодовыми ветками: добавить /{top}/* в .gitignore")
    else:
        add("gitignore", "OK", f"{b.rel_dir} игнорируется")
    if loc is not None:
        try:
            imported = {str(b.read_state(p).get("imported") or "") for p in b.cards().values()}
            left = [t for t in local_tasks(b.main_tree() / LOCAL_DIR) if f"local:{t['slug']}" not in imported]
        except lib.OmixflowError:
            left = []
        if left:
            add("local", "WARN", f"в {LOCAL_DIR} {len(left)} задач трекера local: перенести на доску — "
                                 f"{run} import --from-local (превью), затем с --apply")
    if lib.config_get(b.cfg, "tracker.status_map"):
        add("status_map", "WARN", "kanban не использует tracker.status_map: статус это колонка карточки")
    if not b.push_enabled:
        add("remote", "OK", "tracker.push: false, доска только в этом клоне")
    elif lib.git(b.root, "remote", "get-url", REMOTE) is None:
        add("remote", "FAIL", f"tracker.push: true, но нет remote {REMOTE}: добавить remote или tracker.push: false")
    elif remote_ref is None:
        add("remote", "WARN", f"на {REMOTE} нет ветки {b.branch}: её опубликует init или следующая запись")
    else:
        add("remote", "OK", f"{REMOTE}/{b.branch}")
    return checks


def detect(project: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Draft config for `doctor --init`: the repository already has a board branch
    (local or `origin/`); the prefix is the most common one among its cards."""
    root = lib.find_project_root(project)
    for ref in (f"refs/heads/{DEFAULT_BRANCH}", f"refs/remotes/{REMOTE}/{DEFAULT_BRANCH}"):
        if not set(COLUMNS) & set((lib.git(root, "ls-tree", "--name-only", ref) or "").splitlines()):
            continue
        names = (lib.git(root, "ls-tree", "-d", "--name-only", ref, *(f"{c}/" for c in COLUMNS)) or "").splitlines()
        prefixes = [m.group(1) for n in names if (m := re.match(r"[a-z]+/([A-Z][A-Z0-9]*)-\d+(?:-|$)", n))]
        project_key = max(set(prefixes), key=prefixes.count) if prefixes else "CHANGE-ME"
        return {"tracker": {"adapter": "kanban", "project": project_key}, "artifacts": {"tracked": False}}
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--type", default=None)
    p.add_argument("--kind", default="task")
    p.add_argument("--parent", default=None)
    p.add_argument("--slug", default=None)
    p.add_argument("--from", dest="source", default=None)
    p = sub.add_parser("get")
    p.add_argument("id")
    p = sub.add_parser("list")
    for flag in ("--column", "--kind", "--parent", "--owner"):
        p.add_argument(flag, default=None)
    p = sub.add_parser("path")
    p.add_argument("id")
    p = sub.add_parser("ref")
    p.add_argument("id")
    p = sub.add_parser("epic")
    p.add_argument("id")
    p = sub.add_parser("describe")
    p.add_argument("id")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--rev", default=None)
    p = sub.add_parser("comment")
    p.add_argument("id")
    p.add_argument("--text", required=True)
    p.add_argument("--author", default=None)
    p = sub.add_parser("move")
    p.add_argument("id")
    p.add_argument("--to", required=True)
    p.add_argument("--resolution", default=None)
    p = sub.add_parser("set")
    p.add_argument("id")
    p.add_argument("pairs", nargs="+")
    p = sub.add_parser("link")
    p.add_argument("id")
    p.add_argument("other")
    p = sub.add_parser("batch")
    p.add_argument("--from", dest="source", required=True)
    p = sub.add_parser("publish")
    p.add_argument("id")
    p.add_argument("--from", dest="source", required=True)
    p = sub.add_parser("checkout")
    p.add_argument("id")
    p.add_argument("--to", dest="target", required=True)
    p.add_argument("--force", action="store_true")
    sub.add_parser("render")
    sub.add_parser("pull")
    p = sub.add_parser("import")
    p.add_argument("--from-local", dest="from_local", action="store_true", required=True)
    p.add_argument("--dir", default=None)
    p.add_argument("--apply", action="store_true")
    sub.add_parser("doctor")
    sub.add_parser("detect")
    ns = ap.parse_args(argv)

    try:
        if ns.cmd == "doctor":
            print(json.dumps(diagnose(ns.project), ensure_ascii=False, indent=2))
            return 0
        if ns.cmd == "detect":
            print(json.dumps(detect(ns.project), ensure_ascii=False))
            return 0
        b = Board(ns.project)
        if ns.cmd == "init":
            with b.locked():
                print(b.init())
        elif ns.cmd == "pull":
            print(b.pull())
        elif ns.cmd == "create":
            text = Path(ns.source).read_text(encoding="utf-8") if ns.source else ""
            typ = ns.type or str(lib.config_get(b.cfg, "tracker.create_defaults.type") or "feature")
            print(b.transaction(lambda: b.create(ns.title, typ, ns.kind, ns.parent, ns.slug, text)))
        elif ns.cmd == "get":
            card = b.card(ns.id)
            info = b.summary(ns.id, card)
            comments = card / "comments.md"
            info.update({"rev": b.rev(card), "state": b.read_state(card),
                         "task_md": (card / "task.md").read_text(encoding="utf-8"),
                         "comments": comments.read_text(encoding="utf-8") if comments.exists() else ""})
            print(json.dumps(info, ensure_ascii=False, indent=2))
        elif ns.cmd == "list":
            rows = [b.summary(cid, p) for cid, p in sorted(b.cards().items(), key=lambda kv: b.number(kv[0]))]
            for key in ("column", "kind", "parent", "owner"):
                want = getattr(ns, key)
                if want is not None:
                    rows = [r for r in rows if r.get(key) == want]
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif ns.cmd == "path":
            print(b.card(ns.id))
        elif ns.cmd == "ref":
            print(b.ref(ns.id))
        elif ns.cmd == "epic":
            print(json.dumps(b.epic(ns.id), ensure_ascii=False, indent=2))
        elif ns.cmd == "describe":
            text = Path(ns.source).read_text(encoding="utf-8")
            print(b.transaction(lambda: b.describe(ns.id, text, ns.rev)))
        elif ns.cmd == "comment":
            author = ns.author or lib.git(b.root, "config", "user.name") or "unknown"
            b.transaction(lambda: b.comment(ns.id, ns.text, author))
        elif ns.cmd == "move":
            print(b.transaction(lambda: b.move(ns.id, ns.to, ns.resolution)))
        elif ns.cmd == "set":
            for warning in b.transaction(lambda: b.set_fields(ns.id, ns.pairs)):
                print(f"omixflow: {warning}", file=sys.stderr)
        elif ns.cmd == "link":
            b.transaction(lambda: b.link(ns.id, ns.other))
        elif ns.cmd == "batch":
            result, warnings = run_batch(b, load_batch(b, ns.source))
            for warning in warnings:
                print(f"omixflow: {warning}", file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False))
        elif ns.cmd == "publish":
            source = Path(ns.source).resolve()
            print(b.transaction(lambda: publish(b, ns.id, source)))
        elif ns.cmd == "checkout":
            print(checkout(b, ns.id, Path(ns.target).resolve(), ns.force))
        elif ns.cmd == "import":
            src = Path(ns.dir).resolve() if ns.dir else b.main_tree() / LOCAL_DIR
            art = b.main_tree() / str(lib.config_get(b.cfg, "artifacts.dir") or ".tasks")
            report = (b.transaction(lambda: import_local(b, src, art, True)) if ns.apply
                      else import_local(b, src, art, False))
            print("\n".join(report) if report else "переносить нечего")
            if report and not ns.apply:
                print("превью: запись на доску — с --apply")
        elif ns.cmd == "render":
            b.transaction(lambda: b.commit("board: render"))
        return 0
    except StaleRevision as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return EXIT_STALE
    except (lib.OmixflowError, OSError) as e:
        print(f"omixflow: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
