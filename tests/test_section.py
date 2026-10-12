"""Tests for protocol sections: lib.sections_of and `resolve.py section` (runtime.md,
«Чтение протокола»)."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omixflow_lib as lib  # noqa: E402
import resolve  # noqa: E402

DOC = """# Title

intro

## Alpha

alpha text

### Alpha one

one

**Label one.** paragraph of label one
continues

**Label two** — another

## Beta

```markdown
## Not a heading
**Not a label.** inside a fence
```

beta tail
"""


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = resolve.main(list(args))
    return code, out.getvalue(), err.getvalue()


class SectionTests(unittest.TestCase):
    def test_sections_are_fence_aware_and_nest_by_level(self):
        secs = {s["title"]: s for s in lib.sections_of(DOC)}
        self.assertEqual(set(secs), {"Alpha", "Alpha one", "Label one", "Label two", "Beta"})
        self.assertEqual((secs["Alpha"]["start"], secs["Alpha"]["end"]), (5, 18))      # to `## Beta`
        self.assertEqual((secs["Alpha one"]["start"], secs["Alpha one"]["end"]), (9, 18))
        self.assertEqual((secs["Label one"]["start"], secs["Label one"]["end"]), (13, 15))  # its paragraph
        self.assertEqual(secs["Beta"]["end"], len(DOC.splitlines()) + 1)
        self.assertNotIn("Not a heading", secs)

    def test_section_lines_match_whole_titles_case_insensitively(self):
        sec, lines = lib.section_lines(DOC, "alpha one")
        self.assertEqual(lines[0], "### Alpha one")
        self.assertIsNone(lib.section_lines(DOC, "Alpha o"))
        sec, lines = lib.section_lines(DOC, "Label one.")
        self.assertEqual(len(lines), 2)

    def test_resolve_section_prints_sections_of_the_plugin_protocol_and_rejects_unknown_titles(self):
        # the shell splits unquoted «Отчёт агента» into «Отчёт and агента»: the arguments are joined
        code, out, err = run("section", "runtime.md", "«Пролог", "скила»", "«Отчёт", "агента»", "«Стоимость»")
        self.assertEqual(code, 0, err)
        self.assertIn("=== runtime.md:", out)
        self.assertIn("## Пролог скила", out)
        self.assertIn("## Отчёт агента", out)
        self.assertIn("## Стоимость", out)
        code, out, err = run("section", "runtime.md", "Пролог", "скила")     # no quotes: one title
        self.assertEqual(code, 0, err)
        self.assertIn("## Пролог скила", out)
        code, out, err = run("section", "runtime.md", "Пролог скила", "«Гейты»")   # text outside «…»: an error
        self.assertEqual(code, 2)
        self.assertIn("вне «…»", err)
        code, out, err = run("section", "lead.md", "«Лид»")                     # a label repeated: every occurrence
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("=== lead.md:"), len(lib.sections_named(
            (ROOT / "protocol" / "lead.md").read_text(encoding="utf-8"), "Лид")))
        code, out, err = run("section", "lead.md", "«Роли»")                 # a bare name is the plugin's protocol,
        self.assertEqual(code, 0, err)                                        # whatever the working directory holds
        self.assertIn("## Роли", out)
        code, out, err = run("section", "protocol/artifacts.md", "task.md")
        self.assertEqual(code, 0, err)
        self.assertIn("## Scope", out)                       # the template inside the fence stays whole
        code, out, err = run("section", "runtime.md", "Нет такой")
        self.assertEqual(code, 2)
        self.assertIn("есть: «", err)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.md"
            path.write_text(DOC)
            code, out, err = run("section", str(path), "Label two")
            self.assertEqual(code, 0, err)
            self.assertIn("**Label two** — another", out)
            # a decoy in the working directory does not shadow a bare protocol name
            (Path(tmp) / "lead.md").write_text("## Роли\n\ndecoy\n")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                code, out, err = run("section", "lead.md", "«Роли»")
                self.assertEqual(code, 0, err)
                self.assertNotIn("decoy", out)
                code, out, err = run("section", "./lead.md", "«Роли»")
                self.assertEqual(code, 0, err)
                self.assertIn("decoy", out)
            finally:
                os.chdir(cwd)

    def test_every_protocol_file_has_unique_section_titles(self):
        for path in sorted((ROOT / "protocol").glob("*.md")):
            titles = [s["title"] for s in lib.sections_of(path.read_text(encoding="utf-8")) if s["level"] < 4]
            self.assertEqual(len(titles), len(set(titles)), f"{path.name}: повторяющиеся заголовки")


if __name__ == "__main__":
    unittest.main()
