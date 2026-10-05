"""Tests for adapters/tracker/kanban/board.py: the kanban board on its own branch."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "adapters" / "tracker" / "kanban" / "board.py"
spec = importlib.util.spec_from_file_location("board", SCRIPT)
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)

CFG = ("version: 1\ntracker: {adapter: kanban, project: T, push: false}\nforge: none\nlang: [ts]\n"
       "workspace: {base: main, branch: 'task/{id}'}\nverify: {test: 'true'}\n"
       "artifacts: {tracked: false}\n")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class BoardCase(unittest.TestCase):
    """A git project with an initialised local board (push: false)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        git(self.root, "config", "user.name", "dev")
        git(self.root, "config", "user.email", "dev@x")
        cfg = self.root / ".claude" / "omixflow" / "flow.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(CFG, encoding="utf-8")
        (self.root / ".gitignore").write_text("/.tasks/\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        self.assertEqual(self.call("init")[0], 0)
        self.board = self.root / ".tasks" / "board"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args: str, project: Path = None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = board.main(["--project", str(project or self.root), *args])
        return code, out.getvalue().strip(), err.getvalue().strip()

    def ok(self, *args: str, project: Path = None) -> str:
        code, out, err = self.call(*args, project=project)
        self.assertEqual(code, 0, err)
        return out

    def create(self, title: str, *extra: str, text: str = "Постановка.") -> str:
        src = Path(self.tmp.name) / "draft.md"
        src.write_text(text, encoding="utf-8")
        return self.ok("create", "--title", title, "--from", str(src), *extra)


class BoardTests(BoardCase):
    def test_init_creates_unrelated_branch_and_worktree(self):
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertTrue((self.board / "README.md").exists())
        self.assertTrue((self.board / "board.md").exists())
        for column in board.COLUMNS:
            self.assertTrue((self.board / column / ".gitkeep").exists(), column)
        self.assertEqual(git(self.board, "rev-parse", "--abbrev-ref", "HEAD"), "board")
        base = subprocess.run(["git", "-C", str(self.root), "merge-base", "main", "board"],
                              capture_output=True, text=True)
        self.assertNotEqual(base.returncode, 0, "board must share no history with code")
        self.assertIn("уже открыта", self.ok("init"))

    def test_create_ids_slugs_and_files(self):
        self.assertEqual(self.create("Функция snake_case"), "T-1")
        self.assertEqual(self.create("Эпик: текстовые утилиты", "--kind", "epic"), "T-2")
        card = self.board / "backlog" / "T-1-funktsiya-snake-case"
        self.assertTrue(card.is_dir())
        self.assertEqual((card / "task.md").read_text(encoding="utf-8"),
                         "# T-1: Функция snake_case\n\n## Исходная формулировка\n\nПостановка.\n")
        state = json.loads(self.ok("get", "T-1"))["state"]
        self.assertEqual((state["id"], state["kind"], state["type"], state["owner"], state["links"]),
                         ("T-1", "task", "feature", None, []))
        self.assertFalse((self.board / "backlog" / ".gitkeep").exists())
        self.assertIn("board: T-2 create", git(self.board, "log", "--format=%s"))
        self.assertTrue(self.ok("path", "T-2").endswith("backlog/T-2-epik-tekstovye-utility"))

    def test_parent_must_be_epic(self):
        self.create("Задача")
        code, _, err = self.call("create", "--title", "Дочерняя", "--parent", "T-1")
        self.assertEqual(code, 2)
        self.assertIn("не эпик", err)
        self.create("Эпик", "--kind", "epic")
        self.assertEqual(self.create("Дочерняя", "--parent", "T-2"), "T-3")
        self.assertEqual(json.loads(self.ok("list", "--parent", "T-2"))[0]["id"], "T-3")

    def test_found_from_another_worktree(self):
        self.create("Задача")
        wt = Path(self.tmp.name) / "wt"
        git(self.root, "worktree", "add", "-q", "-b", "task/T-1", str(wt), "main")
        self.assertEqual(self.ok("path", "T-1", project=wt), self.ok("path", "T-1"))
        self.assertEqual(self.create_from(wt, "Ещё задача"), "T-2")

    def create_from(self, project: Path, title: str) -> str:
        return self.ok("create", "--title", title, project=project)

    def test_describe_with_revision(self):
        self.create("Задача")
        rev = json.loads(self.ok("get", "T-1"))["rev"]
        new = Path(self.tmp.name) / "new.md"
        new.write_text("# T-1: Задача\n\n## Уточнённая формулировка\n\nТочнее.\n", encoding="utf-8")
        new_rev = self.ok("describe", "T-1", "--from", str(new), "--rev", rev)
        self.assertNotEqual(new_rev, rev)
        code, _, err = self.call("describe", "T-1", "--from", str(new), "--rev", rev)
        self.assertEqual(code, 3)
        self.assertIn("изменился после чтения", err)
        self.assertIn("Точнее.", json.loads(self.ok("get", "T-1"))["task_md"])

    def test_comment_move_resolution(self):
        self.create("Задача")
        self.ok("comment", "T-1", "--text", "взял в работу", "--author", "anna")
        self.assertIn("anna: взял в работу", json.loads(self.ok("get", "T-1"))["comments"])
        self.assertTrue(self.ok("move", "T-1", "--to", "working").endswith("working/T-1-zadacha"))
        self.assertTrue((self.board / "backlog" / ".gitkeep").exists())
        self.assertFalse((self.board / "working" / ".gitkeep").exists())
        self.assertEqual(self.call("move", "T-1", "--to", "review", "--resolution", "canceled")[0], 2)
        self.ok("move", "T-1", "--to", "done", "--resolution", "canceled")
        info = json.loads(self.ok("get", "T-1"))
        self.assertEqual((info["column"], info["resolution"]), ("done", "canceled"))
        self.ok("move", "T-1", "--to", "working")
        self.assertIsNone(json.loads(self.ok("get", "T-1"))["resolution"])
        self.assertIn("board: T-1 move done → working", git(self.board, "log", "-1", "--format=%s"))

    def test_set_and_link(self):
        self.create("A")
        self.create("B")
        self.ok("set", "T-1", "owner=anna", "blocked=ждёт API")
        info = json.loads(self.ok("get", "T-1"))
        self.assertEqual((info["owner"], info["blocked"]), ("anna", "ждёт API"))
        self.ok("set", "T-1", "blocked=null")
        self.assertIsNone(json.loads(self.ok("get", "T-1"))["blocked"])
        for bad in (("T-1", "column=done"), ("T-1", "type=epic"), ("T-1", "parent=T-2"), ("T-1", "owner")):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("set", *bad)[0], 2)
        self.ok("link", "T-1", "T-2")
        self.ok("link", "T-1", "T-2")
        self.assertEqual(json.loads(self.ok("get", "T-1"))["state"]["links"], ["T-2"])
        self.assertEqual(json.loads(self.ok("get", "T-2"))["state"]["links"], ["T-1"])
        self.assertEqual(self.call("link", "T-1", "T-1")[0], 2)

    def test_board_md_sections_and_epic_progress(self):
        self.create("Эпик", "--kind", "epic")
        self.create("Первая", "--parent", "T-1")
        self.create("Вторая", "--parent", "T-1")
        self.ok("move", "T-2", "--to", "done")
        self.ok("set", "T-3", "blocked=ждёт дизайн", "owner=anna")
        self.create("Третья")
        self.ok("move", "T-4", "--to", "done", "--resolution", "canceled")
        text = (self.board / "board.md").read_text(encoding="utf-8")
        self.assertIn("- [T-1](backlog/T-1-epik/task.md) Эпик · 1/2 закрыто", text)
        self.assertIn("  - T-2 (done)", text)
        self.assertIn("## backlog (2)", text)
        self.assertIn("- [T-3](backlog/T-3-vtoraya/task.md) Вторая · feature · anna · эпик T-1 · ⛔ ждёт дизайн", text)
        self.assertIn("## done (2)", text)
        self.assertIn("Третья · feature · ✗ canceled", text)
        self.assertLess(text.index("## Эпики"), text.index("## backlog"))

    def test_epic_lifts_with_first_child_and_reports_completion(self):
        self.create("Эпик", "--kind", "epic")
        self.create("Первая", "--parent", "T-1")
        self.create("Вторая", "--parent", "T-1")
        self.assertFalse(json.loads(self.ok("epic", "T-1"))["complete"])
        self.ok("move", "T-2", "--to", "working")
        self.assertEqual(json.loads(self.ok("get", "T-1"))["column"], "working")
        self.assertIn("эпик T-1 → working", git(self.board, "log", "-1", "--format=%s"))
        self.ok("move", "T-1", "--to", "review")
        self.ok("move", "T-3", "--to", "working")
        self.assertEqual(json.loads(self.ok("get", "T-1"))["column"], "review", "only a backlog epic is lifted")
        self.ok("move", "T-2", "--to", "done")
        p = json.loads(self.ok("epic", "T-1"))
        self.assertEqual((p["closed"], p["total"], p["complete"]), (1, 2, False))
        self.ok("move", "T-3", "--to", "done", "--resolution", "canceled")
        p = json.loads(self.ok("epic", "T-1"))
        self.assertEqual((p["closed"], p["canceled"], p["complete"]), (2, 1, True))
        text = (self.board / "board.md").read_text(encoding="utf-8")
        self.assertIn("Эпик · 2/2 закрыто (отменено 1)", text)
        self.assertIn("  - T-3 (done ✗ canceled)", text)
        self.assertEqual(self.call("epic", "T-2")[0], 2)
        self.create("Пустой эпик", "--kind", "epic")
        self.assertFalse(json.loads(self.ok("epic", "T-4"))["complete"], "an epic without children is not complete")

    def test_concurrent_creates_get_unique_ids(self):
        def create(i: int) -> str:
            return subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.root), "create",
                                   "--title", f"Задача {i}"], capture_output=True, text=True).stdout.strip()
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(create, range(10)))
        self.assertEqual(sorted(ids, key=lambda x: int(x[2:])), [f"T-{n}" for n in range(1, 11)])

    def test_missing_source_file_is_an_error_not_a_traceback(self):
        self.create("Задача")
        code, _, err = self.call("describe", "T-1", "--from", str(self.root / "nope.md"))
        self.assertEqual(code, 2)
        self.assertIn("nope.md", err)

    def test_bad_prefix_and_missing_board(self):
        cfg = self.root / ".claude" / "omixflow" / "flow.yaml"
        cfg.write_text(CFG.replace("project: T", "project: t1"), encoding="utf-8")
        code, _, err = self.call("list")
        self.assertEqual(code, 2)
        self.assertIn("tracker.project", err)
        cfg.write_text(CFG.replace("project: T", "project: T, branch: other"), encoding="utf-8")
        code, _, err = self.call("list")
        self.assertIn("доска не открыта", err)


STATE = ROOT / "scripts" / "state.py"


def state(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(STATE), *args], capture_output=True, text=True)


class ArtifactsTests(BoardCase):
    """Working copy ↔ card: checkout, state.py init on a card record, auto-publish."""

    def start(self, title: str = "Задача") -> Path:
        self.create(title)
        work = self.root / ".tasks" / "T-1"
        self.ok("checkout", "T-1", "--to", str(work))
        return work

    def card(self) -> Path:
        return Path(self.ok("path", "T-1"))

    def test_checkout_skips_comments_and_init_completes_card_record(self):
        self.create("Задача")
        self.ok("comment", "T-1", "--text", "обсуждение")
        work = self.root / ".tasks" / "T-1"
        self.ok("checkout", "T-1", "--to", str(work))
        self.assertEqual(sorted(p.name for p in work.iterdir()), ["state.yaml", "task.md"])
        proc = state("init", str(work), "--id", "T-1", "--kind", "task", "--tier", "S", "--branch", "task/T-1",
                      "--base", "main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        st = json.loads(state("get", str(work)).stdout)
        self.assertEqual((st["title"], st["type"], st["phase"], st["tier"]), ("Задача", "feature", "refine", "S"))
        again = state("init", str(work), "--id", "T-1", "--kind", "task")
        self.assertEqual(again.returncode, 2, "a pipeline state is not a card record any more")

    def test_epic_is_not_run_by_the_pipeline(self):
        self.create("Эпик", "--kind", "epic")
        work = self.root / ".tasks" / "T-1"
        self.ok("checkout", "T-1", "--to", str(work))
        proc = state("init", str(work), "--id", "T-1", "--kind", "task")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("эпик", proc.stderr)

    def test_finish_and_step_publish_with_board_owned_fields_kept(self):
        work = self.start()
        state("init", str(work), "--id", "T-1", "--kind", "task", "--tier", "M")
        self.ok("set", "T-1", "owner=anna")
        self.ok("comment", "T-1", "--text", "с доски")
        (work / "research.md").write_text("# Research\n", encoding="utf-8")
        proc = state("finish", str(work), "refine")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        card = self.card()
        self.assertTrue((card / "research.md").exists())
        published = json.loads(self.ok("get", "T-1"))["state"]
        self.assertEqual((published["phase"], published["owner"], published["tier"]), ("start", "anna", "M"))
        self.assertIn("с доски", (card / "comments.md").read_text(encoding="utf-8"))
        state("set", str(work), "steps_total=2")
        state("step", str(work), "done", "1")
        self.assertEqual(json.loads(self.ok("get", "T-1"))["state"]["steps_done"], [1])
        self.assertIn("board: T-1 publish", git(self.board, "log", "-1", "--format=%s"))

    def test_publish_is_additive(self):
        work = self.start()
        state("init", str(work), "--id", "T-1", "--kind", "task")
        (work / "research.md").write_text("x", encoding="utf-8")
        self.ok("publish", "T-1", "--from", str(work))
        (work / "research.md").unlink()
        self.ok("publish", "T-1", "--from", str(work))
        self.assertTrue((self.card() / "research.md").exists())

    def test_checkout_protects_a_different_working_copy(self):
        work = self.start()
        state("init", str(work), "--id", "T-1", "--kind", "task")
        (work / "spec.md").write_text("неопубликовано", encoding="utf-8")
        code, _, err = self.call("checkout", "T-1", "--to", str(work))
        self.assertEqual(code, 2)
        self.assertIn("неопубликованная работа", err)
        self.ok("checkout", "T-1", "--to", str(work), "--force")
        self.assertFalse((self.card() / "spec.md").exists())

    def test_describe_only_while_in_backlog(self):
        self.create("Задача")
        self.ok("move", "T-1", "--to", "working")
        src = Path(self.tmp.name) / "late.md"
        src.write_text("# T-1: Задача\n\nПоздняя правка.\n", encoding="utf-8")
        code, _, err = self.call("describe", "T-1", "--from", str(src))
        self.assertEqual(code, 2)
        self.assertIn("рабочая копия", err)
        self.assertNotIn("Поздняя правка", json.loads(self.ok("get", "T-1"))["task_md"])
        self.create("Эпик", "--kind", "epic")
        self.ok("move", "T-2", "--to", "working")
        self.ok("describe", "T-2", "--from", str(src))

    def test_ref_links_board_md_of_the_board_branch(self):
        self.create("Задача")
        self.assertEqual(self.ok("ref", "T-1"), "T-1 «Задача» · доска: ветка `board`, `board.md`")
        git(self.root, "remote", "add", "origin", "git@github.com:org/app.git")
        self.assertEqual(self.ok("ref", "T-1"),
                         "T-1 «Задача» · [доска](https://github.com/org/app/blob/board/board.md)")

    def test_failed_publish_is_a_warning(self):
        work = self.start()
        state("init", str(work), "--id", "T-1", "--kind", "task")
        cfg = self.root / ".claude" / "omixflow" / "flow.yaml"
        cfg.write_text(CFG.replace("push: false", "push: true"), encoding="utf-8")
        proc = state("finish", str(work), "refine")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("не опубликованы", proc.stderr)
        self.assertEqual(json.loads(state("get", str(work)).stdout)["phase"], "start")


class ImportLocalTests(BoardCase):
    """board.py import --from-local: the local tracker moves onto the board."""

    def local(self, name: str, front: str, body: str) -> None:
        d = self.root / ".tasks" / "backlog"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(f"---\n{front}\n---\n\n{body}", encoding="utf-8")

    def setUp(self):
        super().setUp()
        self.local("fix-bug", "id: fix-bug\ntitle: Починить\nstatus: done\ntype: bug\ncreated: 2026-09-01\n"
                   "links: [add-feature, gone]", "Описание.\n\n## Журнал\n- 2026-09-01 создана\n")
        self.local("add-feature", "id: add-feature\ntitle: Добавить\nstatus: ready\ntype: feature\n"
                   "created: 2026-09-02\norigin: AL-1", "Сделать.\n")
        self.local("old-multi", "id: old-multi\ntitle: Старая\nstatus: canceled\ncreated: 2026-08-01",
                   "Части.\n\n<!-- omixflow:multitask:start -->\n| p |\n<!-- omixflow:multitask:end -->\n")
        (self.root / ".tasks" / "backlog" / "README.md").write_text("# Локальный трекер\n", encoding="utf-8")
        art = self.root / ".tasks" / "fix-bug"
        art.mkdir()
        (art / "task.md").write_text("# fix-bug: Починить\n\nФинальная формулировка.\n", encoding="utf-8")
        (art / "research.md").write_text("# Research\n", encoding="utf-8")
        (art / "state.yaml").write_text("id: fix-bug\nkind: task\nphase: done\nbranch: task/fix-bug\n", encoding="utf-8")

    def test_preview_writes_nothing(self):
        out = self.ok("import", "--from-local")
        self.assertIn("old-multi → T-1 (done)", out)
        self.assertIn("fix-bug → T-2 (done, артефакты, без связей: gone)", out)
        self.assertIn("add-feature → T-3 (backlog)", out)
        self.assertEqual(json.loads(self.ok("list")), [])

    def test_apply_moves_tasks_with_history_and_is_idempotent(self):
        self.ok("import", "--from-local", "--apply")
        rows = {r["id"]: r for r in json.loads(self.ok("list"))}
        self.assertEqual({k: (v["column"], v["resolution"]) for k, v in rows.items()},
                         {"T-1": ("done", "canceled"), "T-2": ("done", "done"), "T-3": ("backlog", None)})
        fix = json.loads(self.ok("get", "T-2"))
        self.assertEqual((fix["state"]["links"], fix["state"]["phase"], fix["state"]["branch"], fix["state"]["id"],
                          fix["state"]["imported"], fix["state"]["type"]),
                         (["T-3"], "done", "task/fix-bug", "T-2", "local:fix-bug", "bug"))
        self.assertIn("Финальная формулировка.", fix["task_md"])
        self.assertIn("- 2026-09-01 создана", fix["comments"])
        self.assertTrue((Path(fix["path"]) / "research.md").exists())
        add = json.loads(self.ok("get", "T-3"))["task_md"]
        self.assertIn("происхождение: AL-1", add)
        self.assertIn("## Исходная формулировка\n\nСделать.", add)
        self.assertIn("omixflow:multitask:start", json.loads(self.ok("get", "T-1"))["task_md"])
        self.assertTrue(json.loads(self.ok("get", "T-1"))["path"].endswith("done/T-1-old-multi"))
        self.assertEqual(self.ok("import", "--from-local", "--apply"), "переносить нечего")
        self.assertEqual(len(json.loads(self.ok("list"))), 3)

    def test_imported_mark_survives_the_pipeline(self):
        self.ok("import", "--from-local", "--apply")
        work = self.root / ".tasks" / "T-3"
        self.ok("checkout", "T-3", "--to", str(work))
        self.assertEqual(state("init", str(work), "--id", "T-3", "--kind", "task").returncode, 0)
        self.assertEqual(json.loads(state("get", str(work)).stdout)["imported"], "local:add-feature")
        st = work / "state.yaml"
        st.write_text("".join(ln for ln in st.read_text(encoding="utf-8").splitlines(True)
                              if not ln.startswith("imported:")), encoding="utf-8")
        state("finish", str(work), "refine")
        self.assertEqual(json.loads(self.ok("get", "T-3"))["state"]["imported"], "local:add-feature")
        self.assertEqual(self.ok("import", "--from-local"), "переносить нечего")

    def test_tasks_in_work_block_the_import(self):
        self.local("busy", "id: busy\ntitle: В работе\nstatus: in_work\ncreated: 2026-09-03", "x\n")
        self.local("multi", "id: multi\ntitle: Части\nstatus: ready\ncreated: 2026-09-04",
                   "<!-- omixflow:multitask:start -->\n<!-- omixflow:multitask:end -->\n")
        code, _, err = self.call("import", "--from-local", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("busy (in_work)", err)
        self.assertIn("multi (ready, мультизадача)", err)
        self.assertEqual(json.loads(self.ok("list")), [])

    def test_doctor_points_at_the_import(self):
        hint = {c["name"]: c for c in json.loads(self.ok("doctor"))}["local"]
        self.assertEqual(hint["status"], "WARN")
        self.assertIn("import --from-local", hint["detail"])
        self.ok("import", "--from-local", "--apply")
        self.assertNotIn("local", {c["name"] for c in json.loads(self.ok("doctor"))})


DOCTOR = ROOT / "scripts" / "doctor.py"


class DoctorHookTests(BoardCase):
    """Hooks scripts.doctor and scripts.detect, and doctor.py around them."""

    def checks(self) -> dict:
        return {c["name"]: c for c in json.loads(self.ok("doctor"))}

    def write_cfg(self, text: str) -> None:
        (self.root / ".claude" / "omixflow" / "flow.yaml").write_text(text, encoding="utf-8")

    def doctor(self, *args: str) -> dict:
        proc = subprocess.run([sys.executable, str(DOCTOR), "--project", str(self.root), "--json", *args],
                              capture_output=True, text=True)
        return {(c["section"], c["name"]): c for c in json.loads(proc.stdout)["checks"]}

    def test_healthy_local_board(self):
        self.assertEqual({k: v["status"] for k, v in self.checks().items()},
                         {"prefix": "OK", "board": "OK", "gitignore": "OK", "remote": "OK"})

    def test_problems_come_with_the_fix(self):
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        self.write_cfg(CFG.replace("push: false", "push: false, status_map: {in_work: Doing}"))
        git(self.root, "worktree", "remove", "--force", str(self.board))
        c = self.checks()
        self.assertEqual(c["board"]["status"], "FAIL")
        self.assertIn("init (откроет ветку board)", c["board"]["detail"])
        self.assertEqual(c["gitignore"]["status"], "FAIL")
        self.assertIn("/.tasks/", c["gitignore"]["detail"])
        self.assertEqual(c["status_map"]["status"], "WARN")

    def test_create_type_defaults_from_config(self):
        self.write_cfg(CFG.replace("push: false", "push: false, create_defaults: {type: chore}"))
        self.create("Без типа")
        self.create("С типом", "--type", "bug")
        self.assertEqual([c["type"] for c in json.loads(self.ok("list"))], ["chore", "bug"])

    def test_bad_prefix_stops_the_checks(self):
        self.write_cfg(CFG.replace("project: T", "project: t1"))
        self.assertEqual({k: v["status"] for k, v in self.checks().items()}, {"prefix": "FAIL"})

    def test_doctor_runs_the_hook_and_wants_untracked_artifacts(self):
        report = self.doctor()
        self.assertEqual(report[("port:tracker", "board")]["status"], "OK")
        self.assertEqual(report[("artifacts", "tracked")]["status"], "OK")
        self.write_cfg(CFG.replace("tracked: false", "tracked: true"))
        self.assertEqual(self.doctor()[("artifacts", "tracked")]["status"], "FAIL")
        self.write_cfg(CFG)
        self.assertEqual(self.doctor()[("artifacts", "lead journal")]["status"], "WARN")
        (self.root / ".gitignore").write_text("/.tasks/*\n!/.tasks/_lead/\n", encoding="utf-8")
        report = self.doctor()
        self.assertEqual(report[("artifacts", "tracked")]["status"], "OK")
        self.assertNotIn(("artifacts", "lead journal"), report)
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        self.assertIn("/.tasks/* в .gitignore", self.doctor()[("artifacts", "tracked")]["detail"])

    def test_init_detects_an_existing_board(self):
        self.create("Задача")
        (self.root / ".claude" / "omixflow" / "flow.yaml").unlink()
        self.doctor("--init")
        draft = board.lib.load_config(self.root)
        self.assertEqual((draft["tracker"], draft["artifacts"]),
                         ({"adapter": "kanban", "project": "T"}, {"dir": ".tasks", "tracked": False}))
        bare = Path(self.tmp.name) / "bare"
        subprocess.run(["git", "init", "-q", str(bare)], check=True)
        self.assertEqual(self.call("detect", project=bare)[1], "null")


class RemoteTests(unittest.TestCase):
    """Two developers: clones A and B of one bare origin, board pushed after each write."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        seed = base / "seed"
        seed.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        cfg = seed / ".claude" / "omixflow" / "flow.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(CFG.replace("push: false", "push: true"), encoding="utf-8")
        (seed / ".gitignore").write_text("/.tasks/\n", encoding="utf-8")
        git(seed, "add", "-A")
        subprocess.run(["git", "-C", str(seed), "-c", "user.name=s", "-c", "user.email=s@x", "commit", "-q",
                        "-m", "init"], check=True)
        self.origin = base / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(self.origin)], check=True)
        self.a, self.b = base / "a", base / "b"
        for clone, user in ((self.a, "anna"), (self.b, "boris")):
            subprocess.run(["git", "clone", "-q", str(self.origin), str(clone)], check=True)
            git(clone, "config", "user.name", user)
            git(clone, "config", "user.email", f"{user}@x")

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, clone: Path, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = board.main(["--project", str(clone), *args])
        return code, out.getvalue().strip(), err.getvalue().strip()

    def ok(self, clone: Path, *args: str) -> str:
        code, out, err = self.call(clone, *args)
        self.assertEqual(code, 0, err)
        return out

    def origin_cards(self) -> list:
        tree = git(self.origin, "ls-tree", "-r", "--name-only", "board")
        return sorted({p.split("/")[1] for p in tree.splitlines() if p.count("/") >= 2})

    def test_second_developer_joins_existing_board(self):
        self.ok(self.a, "init")
        self.assertIn("board", git(self.origin, "branch", "--list", "board"))
        self.ok(self.a, "create", "--title", "Первая")
        self.ok(self.b, "init")
        self.assertEqual([c["id"] for c in json.loads(self.ok(self.b, "list"))], ["T-1"])
        self.assertEqual(git(self.b / ".tasks" / "board", "rev-parse", "HEAD"), git(self.origin, "rev-parse", "board"))

    def test_stale_developer_gets_next_id_and_sees_others(self):
        self.ok(self.a, "init")
        self.ok(self.b, "init")
        self.assertEqual(self.ok(self.a, "create", "--title", "От Анны"), "T-1")
        self.assertEqual(self.ok(self.b, "create", "--title", "От Бориса"), "T-2")
        self.assertEqual(self.origin_cards(), ["T-1-ot-anny", "T-2-ot-borisa"])
        self.assertTrue(self.ok(self.a, "pull"))
        self.assertEqual([c["id"] for c in json.loads(self.ok(self.a, "list"))], ["T-1", "T-2"])

    def test_rejected_push_retries_with_a_new_id(self):
        self.ok(self.a, "init")
        self.ok(self.b, "init")
        anna = board.Board(self.a)
        fired = []

        def race():
            if not fired:
                fired.append(1)
                self.assertEqual(self.ok(self.b, "create", "--title", "Борис успел"), "T-1")
        anna._before_push = race
        cid = anna.transaction(lambda: anna.create("Анна позже", "feature", "task", None, None, ""))
        self.assertEqual(cid, "T-2")
        self.assertEqual(self.origin_cards(), ["T-1-boris-uspel", "T-2-anna-pozzhe"])

    def test_stale_describe_across_clones(self):
        self.ok(self.a, "init")
        self.ok(self.a, "create", "--title", "Общая")
        self.ok(self.b, "init")
        rev = json.loads(self.ok(self.a, "get", "T-1"))["rev"]
        mine = Path(self.tmp.name) / "b.md"
        mine.write_text("# T-1: Общая\n\nБорис уточнил.\n", encoding="utf-8")
        self.ok(self.b, "describe", "T-1", "--from", str(mine), "--rev", rev)
        theirs = Path(self.tmp.name) / "a.md"
        theirs.write_text("# T-1: Общая\n\nАнна уточнила.\n", encoding="utf-8")
        code, _, err = self.call(self.a, "describe", "T-1", "--from", str(theirs), "--rev", rev)
        self.assertEqual(code, 3, err)
        self.assertIn("Борис уточнил.", git(self.origin, "show", "board:backlog/T-1-obshchaya/task.md"))

    def test_offline_write_fails_and_leaves_board_clean(self):
        self.ok(self.a, "init")
        head = git(self.a / ".tasks" / "board", "rev-parse", "HEAD")
        self.origin.rename(self.origin.with_name("gone.git"))
        code, _, err = self.call(self.a, "create", "--title", "Без связи")
        self.assertEqual(code, 2)
        self.assertIn("нет связи", err)
        self.assertEqual(git(self.a / ".tasks" / "board", "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.a / ".tasks" / "board", "status", "--porcelain"), "")

    def test_fresh_clone_is_told_to_pick_up_the_board(self):
        self.ok(self.a, "init")
        self.ok(self.a, "create", "--title", "Первая")
        git(self.b, "fetch", "-q")
        c = {x["name"]: x for x in json.loads(self.ok(self.b, "doctor"))}
        self.assertEqual(c["board"]["status"], "FAIL")
        self.assertIn("подхватит доску с origin", c["board"]["detail"])
        self.assertEqual(c["remote"]["status"], "OK")
        self.assertEqual(json.loads(self.ok(self.b, "detect"))["tracker"], {"adapter": "kanban", "project": "T"})

    def test_push_without_origin_is_an_error(self):
        git(self.a, "remote", "remove", "origin")
        code, _, err = self.call(self.a, "init")
        self.assertEqual(code, 2)
        self.assertIn("нет remote origin", err)


class SlugTests(unittest.TestCase):
    def test_slugify(self):
        cases = {"Функция snake_case": "funktsiya-snake-case", "Щука и ёж!": "shchuka-i-ezh",
                 "Объявление": "obyavlenie", "   ": "task", "Хвосты цепочек": "khvosty-tsepochek",
                 "Очень длинный заголовок задачи про синхронизацию доски": "ochen-dlinnyy-zagolovok-zadachi-pro"}
        for title, slug in cases.items():
            with self.subTest(title=title):
                self.assertEqual(board.slugify(title), slug)


if __name__ == "__main__":
    unittest.main()
