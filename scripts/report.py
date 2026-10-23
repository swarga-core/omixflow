#!/usr/bin/env python3
"""Check an agent's report against the tree and the gate logs (skills implement 2.2/2.3,
review 4): the orchestrator reads a verdict instead of the report.

    report.py baseline --out FILE [--root DIR] [--artifacts DIR]
    report.py check --role coder|tester --report REPORT_PATH [--root DIR] [--artifacts DIR]
                    [--baseline FILE] [--verify FILE | --also GATE ...] [--test-glob GLOB ...]
                    [--declaration REGEX] [--conflicts FILE ... | --conflicts none] [--amend-decision Dn ...]
                    [--json]

`baseline` records the uncommitted tree before an assignment (the paths of `git status` with
the hash of each file's content) so that `check --baseline` charges the agent only with what
changed since: in implement the tester works on top of the coder's uncommitted step, in
review the coder, the tester and the coder again share one uncommitted fix pass, in a base sync
the coder resolves a merge that already stopped. Without a baseline the whole uncommitted tree is
the agent's — in a sync, all of it but the files outside the merge (below).

What `check` verifies, each against evidence the agent cannot write:
- the file exists and ends with its last section (coder: NOTES, tester: SUMMARY); a reply
  that starts with `REPORT_PATH refused by the harness` is the report (runtime.md, «Отказ
  записи») — the first line is dropped and the verdict says so;
- every section of the role's format is present (`NAME:` or `NAME (…):`);
- TREE STATE equals `git status --short` of ROOT: the claimed lines are normalised (the
  format's indentation and notes are dropped, only porcelain lines count, the artifacts
  directory is left out on both sides), and both the collapsed form (`?? dir/`) and the
  expanded one (`--untracked-files=all`) are accepted; a `*.orig` or `*.rej` leftover is a
  problem, and so is a copy probe.py left unrestored in `{git-dir}/omixflow-probes`;
- a base sync (coder `MODE: sync`, the merge or rebase still in progress — MERGE_HEAD or
  REBASE_HEAD — and STEP `sync…`, a RESOLUTIONS section or --conflicts): RESOLUTIONS replaces
  FILES and names every conflicted file (--conflicts, else MERGE_MSG; `--conflicts none`, alone —
  no conflicts, unless MERGE_MSG names some; an empty value is the call's error); MUTATIONS and
  BYTES CHECK count, in the files either side changes since the base or a conflict names, only
  the lines a three-way merge would not have produced — current minus (HEAD + the other side −
  the merge base) (SwAIS T-14: 93 tests of T-13 from the base), in any other file the lines
  added against the baseline's blob or HEAD (a dirty file of the developer's the coder added a
  line to: only that line). Without --baseline
  a file HEAD has that neither side changes since the base and no conflict names is left out,
  with a warning: a dirty file of the developer's (G-5 mewria MEW-28), or the coder's edit that
  only a baseline taken once the merge stopped tells apart; a file HEAD has not (a seam test the
  coder made) stays the agent's. A known limit:
  a test file the task renamed while the base added tests to the old path — the base's tests
  count as the coder's (`git show {ref}:./{new path}` has no such file on the other side);
- SPEC AMENDMENTS (coder): the task's spec.md diffed against the baseline's snapshot of it
  (`baseline --task TASK_DIR`; the only base when artifacts are kept outside git or when
  uncommitted edits preceded the assignment), else against HEAD when tracked; a change
  with `none`, a claim without a change, a change inside Contracts, Intent or Out of
  Scope, and a changed, added or removed decision choice (a `- Dn …:` item without its
  `rests on:` part, however it wraps) are problems — the last two are a stop for the
  orchestrator's scope-change point, not the coder's amendment; without a snapshot and
  untracked, the verdict says the section was not checked. A decision named by
  `--amend-decision` (repeatable; G-66: a review fix the orchestrator ordered changes the
  mechanism a decision's text names, not the choice) may change its text: the fact
  «Dn: правка текста по заданию оркестратора — было «…», стало «…»» (the changed part of
  the choice with some words around it: a reversed choice or another decision under the
  same number shows there) instead of the stop; an added or removed decision stays a stop;
  a named decision whose choice did not change is a warning (with only its `rests on`
  changed: the flag was not needed), one absent from the snapshot's Decisions is the
  call's error (exit 3), and so is the flag with `--role tester`;
- MUTATIONS: new test declarations (lang adapter `tests.declaration`, else --declaration)
  in the agent's changed test files (`tests.files` globs across the lang adapters, else
  --test-glob; a binary file is not a test) are counted as added minus removed; that many
  MUTATIONS lines are due (`none` is allowed when the count is zero); an outcome is RED, or
  GREEN followed by a strengthening that ends in RED, or `no probe possible: {why}` — the
  excuses of 0.7.1 («schema unchanged», «existing behaviour», «not requested») and the
  `PROBE NOT RUN` messages of probe.py are a FAIL. Without known globs the verdict says
  MUTATIONS were not checked;
- gates: `STATUS: stopped` with `GATES: not run — …` is a stop, reported as such; else every
  gate of the step set (`resolve.py verify --at step` plus --also, or --verify FILE) has an
  outcome (coder: GATES; tester: RUN RESULT for test, CHECKPOINT GATES for the rest); a
  background gate names its `gate.py` run (coder: on the gate's line; tester: in BACKGROUND
  GATES) and, for the exit-code criterion, the run's exit file agrees with the outcome; the
  script runs no gate itself;
- BYTES CHECK is not `n/a` when the agent's diff adds non-ASCII text lines, and names every
  such file (by its path, or by a tail of it from a `/` that no other such file shares);
- SUPPRESSIONS CHECK is present; SCRATCH not `clean` becomes the log.md line;
- NOTES (coder; G-70, a heuristic): an item that states behaviour is a warning — a claim
  about behaviour outside the step carries a probe or `unverified: {why}` (agents/coder.md,
  NOTES). Markers, outside code spans: a failure verb («падает», «упадёт», `fails`,
  `throws`) whose subject is not a test, a gate or lint; an HTTP 4xx/5xx or SQLSTATE code
  after a verb of response («даёт 500», «получит 500», `returns 503`, «дал бы ошибку
  22P02»); a bare SQLSTATE (`23505`). No warning when the item is marked `unverified`, or
  the claim's sentence (split on `.`/`;` outside code; with the next one when it refers
  back, «Это закреплено пробой») says how it was probed — a probe word («проба»,
  «проверен», «закреплено», «показала», `checked`, `P10 shows`, RED/GREEN; a colour is no
  probe), an arrow after a command in backticks or before an outcome (`` `cmd` → 500 ``,
  `→ RED`); another arrow may be the claim itself.

The verdict always carries what the orchestrator acts on without reading the report: each
gate with its outcome, NOTES (when not `none`), `not declared` gates, the tester's FAILURES
and CODE BUGS FOUND, the untracked lines of TREE STATE. A warning (`- ПРЕДУПРЕЖДЕНИЕ: …`,
`warnings` in --json) is for the orchestrator alone: it neither returns the report nor
stops, and leaves the exit code as it is.

Exit 0 — ok, or a stop (`VERDICT: ok` / `VERDICT: stopped`); exit 1 — return the report to
the agent: the output holds the message to send, point by point; exit 2 — the report is
missing or broken; exit 3 — the orchestrator's own error (config, --also, --verify,
--baseline, --amend-decision), nothing about the agent. --json prints one object. The script checks claims
against git and gate logs; it replaces neither `resolve.py verify` nor the orchestrator's
checks.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omixflow_lib as lib  # noqa: E402
import probe  # noqa: E402

OK, RETURN, BROKEN, USAGE = 0, 1, 2, 3
REFUSED = "REPORT_PATH refused by the harness"
SECTIONS = {
    "coder": ["STEP", "FILES", "PROJECT SPECS UPDATED", "SPEC AMENDMENTS", "GATES", "FIX ITERATIONS", "MUTATIONS",
              "BYTES CHECK", "SUPPRESSIONS CHECK", "SCRATCH", "TREE STATE", "SUMMARY", "NOTES"],
    "tester": ["TESTS WRITTEN", "RUN RESULT", "BACKGROUND GATES", "CHECKPOINT GATES", "ITERATIONS", "MUTATIONS",
               "BYTES CHECK", "SUPPRESSIONS CHECK", "SCRATCH", "TREE STATE", "SUMMARY"],
}
OPTIONAL = ["FAILURES", "CODE BUGS FOUND", "STATUS"]
LAST = {"coder": "NOTES", "tester": "SUMMARY"}
KNOWN = sorted({s for names in SECTIONS.values() for s in names} | set(OPTIONAL)
               | {"FILES CREATED", "FILES MODIFIED", "RESOLUTIONS"}, key=len, reverse=True)
EXCUSES = ("schema is unchanged", "schema unchanged", "existing behaviour", "existing behavior",
           "no probe was requested", "not requested", "none was requested")
NOT_RUN_REASONS = probe.NOT_RUN_PHRASES     # an input error of probe.py pasted as a reason
SECTION_HEAD_RE = re.compile(r"^(" + "|".join(re.escape(k) for k in KNOWN) + r")(?: \([^\n]*\))?:(.*)$")
PORCELAIN_RE = re.compile(r"^[ MADRCU?!]{2} \S")
OUTCOME_RE = re.compile(r"(?:→|->)\s*(RED|GREEN)\b")
GATE_LINE_RE = re.compile(r"^\s*-?\s*([a-z0-9]+):\s*(PASS|FAIL|n/a|not declared)\b(.*)$", re.I)
GATE_RUN_RE = re.compile(r"gate\.py\s+([A-Za-z0-9._-]+)(?:,?\s*EXIT\s+(\d+))?")
BACKGROUND_RE = re.compile(r"^\s*-?\s*([a-z0-9]+):\s*gate\.py\s+([A-Za-z0-9._-]+)(?:,?\s*EXIT\s+(\d+))?", re.I)
MUTATION_LINE_RE = re.compile(r"^\s*-\s+(.+)$")
NOTE_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
# A statement of behaviour in NOTES (G-70, T-12: «enterRunStep упадёт на уникальном индексе — 23505 и 500 на сдаче»),
# matched outside code spans (NUnit's `Throws.TypeOf<…>` is code, not a claim): a failure verb; an HTTP 4xx/5xx or
# SQLSTATE code after a verb of response — a bare three-digit number is a count, a limit or a line (550 > 500,
# «401 из 500», «строка ~455»); a bare SQLSTATE. Calibrated on 178 coder reports with NOTES (SwAIS, mewria).
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
NOT_A_QUANTITY = (r"(?![\w:/%-]|\.\d|\s*(?i:ms\b|мс\b|[kmg]b\b|[кмг]б\b|lines?\b|rows?\b|bytes?\b|files?\b|tests?\b|nodes?\b"
                  r"|fields?\b|строк|байт|файл|тест|шаг|узл|пол[еяй]))")
SQLSTATE = r"(?:08|22|23|25|40|42|53|55|57)[\dA-Z]{3}"
CLAIM_RE = re.compile(
    r"(?i:(?<![а-яё])(?:пада(?:ет|ют|ть)|упад[её]т|упадут)(?![а-яё])"     # not «бросает»: T-5's API notes, 14 false
    r"|\b(?:fails|throws|crashes|(?:will|would|may|might) (?:fail|throw|crash))\b)"
    r"|(?i:\b(?:(?:от)?да(?:[её]т|ст|ют|дут)|дал[аио]?\s+бы|верн[её]т|вернут|вернул[аио]?\s+бы|возвраща(?:ет|ют)"
    r"|получ(?:ит|ат|ает|ают)|отвеча(?:ет|ют)|ответ(?:ит|ят)|returns?|gives?|responds?|answers?|yields?)"
    r"(?:\s+(?:with|an?|the|HTTP|status|code|error|с|статус\w*|код\w*|ошибк\w*|PostgreSQL|Postgres|pg|SQLSTATE)){0,3}\s+)"
    r"(?:[45]\d\d|" + SQLSTATE + r")" + NOT_A_QUANTITY +
    r"|(?<![\w:./#+=-])" + SQLSTATE + r"(?![\w:/%-]|\.\d)")
# the subject of a failure that is the coder's own check, not the product: «гейт lint падает», «the test fails»,
# «23514 в тесте» (two words either side); a run and a build are the product's in SwAIS (pipeline runs, the build step)
OWN_CHECK_RE = re.compile(r"(?i:тест\w*|test\w*|гейт\w*|gates?|lint\w*)")
# the sentence of the claim says how it was probed: a probe in words (SwAIS: «Проба V71 показала», «закреплено
# пробой», «P10 shows», «проверен в обоих режимах») counts as one; a colour does not, only the outcome RED/GREEN
PROBE_WORD_RE = re.compile(
    r"(?i:(?<![а-яё])(?:проб(?:а|ой|ы|е|у|ам|ами|ах)?|мутант\w*|провер(?:ен|ена|ено|ены|ил|ила|или|ялось)|закрепл\w*"
    r"|подтвержд\w*|показал\w*|измерен\w*|воспроизвед\w*)(?![а-яё])"
    r"|(?<![-\w])(?:probes?|probed|checked|verified|measured|confirmed|reproduced|observed)\b"
    r"|\b[A-Z]\d+\s+show(?:s|ed)\b)"
    r"|\b(?:RED|GREEN)\b")
UNVERIFIED_RE = re.compile(r"\bunverified\b", re.I)     # the item's own mark, in backticks or not
SENTENCE_END_RE = re.compile(r"[.;!?](?=\s|$)")          # `index.ts`, `0.5`, `.orig` end nothing
BACK_REFERENCE_RE = re.compile(r"\s*(?:Это|Так|This|That)\b")   # «Это закреплено пробой» is about the sentence before
# `command → result` — the arrow of a probe follows a command in backticks or leads to an outcome; any other arrow
# may be the claim itself (T-6 step 2: «чтение отдаёт [["member"]] → разбор Zod падает → 500»)
PROBE_ARROW_RE = re.compile(r"`[^`\n]+`\s*(?:→|->)|(?:→|->)\s*(?:RED|GREEN|PASS|FAIL|EXIT\b|exit\s+\d)")


# ------------------------------------------------------------------ report parsing

def parse_report(text: str) -> Dict[str, List[str]]:
    """Sections of the fixed report format: a known `NAME:` (or `NAME (…):`) at line start
    opens a section; FILES CREATED and FILES MODIFIED fold into FILES."""
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        m = SECTION_HEAD_RE.match(line)
        if m:
            name = m.group(1)
            if name.startswith("FILES "):
                name = "FILES"
            current = name
            sections.setdefault(current, [])
            rest = m.group(2).strip()
            if rest:
                sections[current].append(rest)
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def section_text(sections: Dict[str, List[str]], name: str) -> str:
    return "\n".join(sections.get(name, [])).strip()


def is_none(body: str) -> bool:
    """`none`, `- none`, `none: …` — an empty section in the agents' formats."""
    return body.lstrip("-* ").lower().startswith("none")


def claim_marker(text: str) -> Optional["re.Match[str]"]:
    """The first CLAIM_RE marker of TEXT outside its code spans whose subject is not the coder's
    own check (OWN_CHECK_RE among the two words either side) and whose sentence — with the next
    one when that refers back, «Это закреплено пробой» — says nothing of a probe (PROBE_WORD_RE
    outside code, PROBE_ARROW_RE); None as well when the item is marked `unverified`. Positions
    are TEXT's: a code span is blanked, not removed."""
    if UNVERIFIED_RE.search(text):
        return None
    masked = CODE_SPAN_RE.sub(lambda c: " " * len(c.group(0)), text)
    ends = [e.end() for e in SENTENCE_END_RE.finditer(masked)]
    for m in CLAIM_RE.finditer(masked):
        near = masked[:m.start()].split()[-2:] + masked[m.end():].split()[:2]
        if any(OWN_CHECK_RE.fullmatch(w.strip(".,;:!?()«»\"'—")) for w in near):
            continue
        later = [e for e in ends if e > m.start()]
        a = max([e for e in ends if e <= m.start()], default=0)
        b = later[0] if later else len(text)
        if later and BACK_REFERENCE_RE.match(masked, b):
            b = later[1] if len(later) > 1 else len(text)
        if not PROBE_WORD_RE.search(masked[a:b]) and not PROBE_ARROW_RE.search(text[a:b]):
            return m
    return None


def unprobed_claims(lines: List[str]) -> List[str]:
    """The NOTES items (a bullet with its continuation lines) that state behaviour with no word
    of a probe — claim_marker — each named by an excerpt around the marker. A heuristic: the
    orchestrator is warned before such a note becomes a question to the lead or the developer,
    the report is not returned for it."""
    items: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        if NOTE_ITEM_RE.match(line) or not items or not line[:1].isspace():
            items.append(line.strip())
        else:
            items[-1] += " " + line.strip()
    out = []
    for item in items:
        text = " ".join(NOTE_ITEM_RE.sub("", item, count=1).split())
        m = None if is_none(text) else claim_marker(text)
        if not m:
            continue
        start = max(0, m.start() - 25) if len(text) > 90 else 0
        excerpt = ("…" if start else "") + text[start:start + 90] + ("…" if start + 90 < len(text) else "")
        out.append(f"NOTES: «{excerpt}» — утверждение о поведении без пробы: нужна проба (`команда → результат`) "
                   "или `unverified: {почему не проверить в шаге}`")
    return out


# ------------------------------------------------------------------ evidence

def probe_copies_left(root: Path) -> Tuple[Optional[Path], List[str]]:
    """The copies probe.py left unrestored (`{git-dir}/omixflow-probes`, probe.py «2.»): the
    files they belong to, relative to the worktree's top level (as probe.py keys them)."""
    git_dir = (lib.git_raw(root, "rev-parse", "--absolute-git-dir") or "").strip()
    if not git_dir:
        return None, []
    base = Path(git_dir) / "omixflow-probes"
    if not base.is_dir():
        return base, []
    return base, sorted(str(c.relative_to(base))[: -len(".orig")] for c in base.rglob("*.orig") if c.is_file())


def status_lines(root: Path, artifacts: str, expanded: bool) -> List[str]:
    args = ["status", "--short"] + (["--untracked-files=all"] if expanded else [])
    out = lib.git_raw(root, *args) or ""
    keep = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].split(" -> ")[-1].strip('"')
        if lib.outside_dir([path], artifacts):
            keep.append(line.rstrip())
    return keep


def normalise_claimed(lines: List[str], artifacts: str) -> List[str]:
    """The TREE STATE lines of a report as porcelain lines: indentation and notes dropped,
    the artifacts directory left out."""
    out = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.lstrip()
        # the format indents the snapshot by two spaces; a porcelain line keeps its own leading
        # space (` M path`) only when the indentation is exactly the format's
        candidate = line[2:] if line.startswith("  ") and PORCELAIN_RE.match(line[2:]) else stripped
        if not PORCELAIN_RE.match(candidate):
            if PORCELAIN_RE.match(" " + candidate):   # ` M path` whose leading space was trimmed
                candidate = " " + candidate
            else:
                continue
        path = candidate[3:].split(" -> ")[-1].strip('"')
        if lib.outside_dir([path], artifacts):
            out.append(candidate)
    return out


def changed_paths(root: Path, artifacts: str) -> List[str]:
    return lib.changed_files(root, None, artifacts)


def content_hash(root: Path, path: str, store: bool = False) -> Optional[str]:
    """The blob id of PATH's content; with STORE the blob is written to the object store
    (only the store changes, never the tree) so a later check can diff against it."""
    out = lib.git(root, "hash-object", *(["-w"] if store else []), "--", path)
    return out or None


def snapshot(root: Path, artifacts: str, store: bool = False) -> Dict[str, Optional[str]]:
    """Path → content hash of every uncommitted change (deleted: None)."""
    return {p: content_hash(root, p, store) for p in changed_paths(root, artifacts)}


def agent_delta(root: Path, artifacts: str, baseline: Optional[Dict[str, Optional[str]]]) -> List[str]:
    """The paths the agent changed: everything uncommitted, or, with a baseline, only what
    differs from it."""
    now = snapshot(root, artifacts)
    if baseline is None:
        return sorted(now)
    return sorted(p for p, h in now.items() if baseline.get(p, "∅") != h)


def sync_other(root: Path) -> Optional[str]:
    """The other side of a merge or rebase in progress (MERGE_HEAD, REBASE_HEAD); None when none."""
    for ref in ("MERGE_HEAD", "REBASE_HEAD"):
        if lib.git(root, "rev-parse", "-q", "--verify", ref):
            return ref
    return None


def merge_conflicts(root: Path) -> List[str]:
    """The conflicted files git noted in MERGE_MSG (`# Conflicts:` lines) — the list survives
    `git add` of the resolutions, which empties `git diff --diff-filter=U`."""
    git_dir = (lib.git_raw(root, "rev-parse", "--absolute-git-dir") or "").strip()
    try:
        text = (Path(git_dir) / "MERGE_MSG").read_text(encoding="utf-8", errors="replace") if git_dir else ""
    except OSError:
        return []
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^#?\s*Conflicts:\s*$", line):
            inside = True
            continue
        if inside:
            m = re.match(r"^#?\s+(\S.*)$", line)
            if not m:
                break
            out.append(m.group(1).strip())
    return out


def sync_base(root: Path, other: str) -> Optional[str]:
    """The common ancestor of the merge: `merge-base HEAD MERGE_HEAD`; in a rebase, the parent of the
    commit being applied (`REBASE_HEAD^`)."""
    if other == "REBASE_HEAD":
        return lib.git(root, "rev-parse", "-q", "--verify", "REBASE_HEAD^")
    return lib.git(root, "merge-base", "HEAD", other)


def sync_files(root: Path, other: str, base: Optional[str]) -> Set[str]:
    """The files a sync touches: those either side changed since the merge base (`diff {base} HEAD`
    and `diff {base} {other}`; without a base, HEAD against OTHER). A dirty file neither side
    changes is no work of the sync (G-5 mewria MEW-28: the founder's edit in `knowledge/` charged
    to the coder's BYTES CHECK)."""
    pairs = [(base, "HEAD"), (base, other)] if base else [("HEAD", other)]
    out: Set[str] = set()
    for a, b in pairs:
        out.update(lib.git_paths(root, "diff", "--name-only", "--no-renames", "-z", a, b) or [])
    return out


def sync_new_lines(root: Path, path: str, other: str, base: Optional[str] = None) -> List[str]:
    """The lines of PATH a three-way merge would not have produced: current minus (HEAD + OTHER −
    BASE), as multisets of whitespace-normalised lines — the agent's own in a sync. A test both
    sides kept is no new test (SwAIS T-14: 93 tests of T-13 from the base), and a line both sides
    added independently and the merge keeps twice is no new line either (review: `it.each([` in an
    auto-merged file of T-16). Without a base: current minus the larger side."""
    try:
        current = (root / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    def lines_at(ref: str) -> Counter:
        blob = lib.git_raw(root, "show", f"{ref}:./{path}")     # `./`: relative to ROOT, not to the top level
        return Counter(" ".join(l.split()) for l in (blob or "").splitlines())

    ours, theirs = lines_at("HEAD"), lines_at(other)
    if base:
        common = lines_at(base)
        have = Counter({k: n for k in set(ours) | set(theirs)
                        if (n := ours[k] + theirs[k] - common[k]) > 0})
    else:
        have = ours | theirs
    new = []
    for line in current:
        key = " ".join(line.split())
        if have[key] > 0:
            have[key] -= 1
        else:
            new.append(line)
    return new


BYTES_FORM_HINT = ("по файлу: `- {file}: {что за не-ASCII: Cyrillic, typographic …}; invisible and escapes: "
                   "none — verified by bytes`, невидимые и escape — строкой `{file:line} — U+XXXX`")


def uncovered(files: List[str], section: str, root: Optional[Path] = None) -> List[str]:
    """The files BYTES CHECK does not name (G-71: a per-file line covers Cyrillic comments and
    test names). The section is split into whole path-like tokens (`keys.ts:29` → `keys.ts`;
    an absolute path under the root made relative, `./` and `…/` dropped); a file is named when a token equals its path or a
    tail of it from a `/` on — `http/actions.test.ts`, `…/registry.ts`, as T-10 wrote them —
    that no other file of the list ends with. `packages/ui/src/index.ts` does not name
    `packages/server/src/index.ts`, `vendor/src/a.ts` does not name `src/a.ts`, `a.ts.snap`
    does not name `a.ts`."""
    tokens = set()
    for raw in re.findall(r"[\w./@+…-]+", section):
        token = re.sub(r"^(?:\.\.\.|…|\.)/", "", raw).rstrip(".")
        if token.startswith("/") and root is not None:     # an absolute path under the root, symlinks resolved
            try:
                token = str(Path(token).resolve().relative_to(root.resolve()))
            except (OSError, ValueError):
                pass
        if token:
            tokens.add(token)

    def tails(f: str) -> List[str]:
        parts = f.split("/")
        return ["/".join(parts[i:]) for i in range(len(parts))]

    def unique(tail: str, f: str) -> bool:
        return not any(o != f and (o == tail or o.endswith("/" + tail)) for o in files)

    def spaced(f: str) -> bool:     # a name with a space never forms one token: the whole path, as written
        return " " in f and re.search(r"(?<![\w./-])" + re.escape(f) + r"(?![\w-]|\.\w)", section) is not None

    return [f for f in files if not spaced(f) and not any(tail in tokens and unique(tail, f) for tail in tails(f))]


def is_binary(root: Path, path: str) -> bool:
    try:
        return b"\0" in (root / path).read_bytes()[:8192]
    except OSError:
        return False


def diff_lines(root: Path, path: str, baseline: Optional[Dict[str, Optional[str]]] = None) -> Tuple[List[str], List[str]]:
    """(added, removed) lines of PATH: against its blob in BASELINE when it has one (the
    agent extended a file an earlier agent left uncommitted: only its own lines count),
    else against HEAD; an untracked file without a baseline blob is all added."""
    try:
        current = (root / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        current = []
    before: Optional[List[str]] = None
    if baseline and baseline.get(path):
        blob = lib.git_raw(root, "cat-file", "-p", str(baseline[path]))
        if blob is not None:
            before = blob.splitlines()
    if before is None:
        tracked = lib.git(root, "ls-files", "--error-unmatch", "--", path) is not None
        if not tracked:
            return current, []
        diff = lib.git_raw(root, "diff", "HEAD", "--", path) or ""
        added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        return added, removed
    added, removed = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, current, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += before[i1:i2]
        if tag in ("replace", "insert"):
            added += current[j1:j2]
    return added, removed


def new_declarations_in(added: List[str], removed: List[str], rx: "re.Pattern[str]") -> List[str]:
    """Added declaration lines without an identical (whitespace-normalised) removed one: a
    moved test is not new, a renamed or replaced one is (its body deserves a probe). Each line
    the adapter's `tests.declaration` matches is one test — every `[TestCase(…)]` of a method."""
    gone = Counter(" ".join(l.split()) for l in removed if rx.search(l))
    new = []
    for l in added:
        if not rx.search(l):
            continue
        key = " ".join(l.split())
        if gone[key] > 0:
            gone[key] -= 1
        else:
            new.append(key)
    return new


SHOWN_DECLARATIONS = 5


def declarations_shown(lines: List[str]) -> str:
    """The first new declarations of a file for an error (G-72 mewria MEW-34: 22 lines for 31
    `[TestCase]`s — the count alone did not show what is counted)."""
    def span(l: str) -> str:    # a template literal's backticks inside: a double-backtick span
        cut = l[:80] + ("…" if len(l) > 80 else "")
        return f"`` {cut} ``" if "`" in cut else f"`{cut}`"
    shown = "; ".join(span(l) for l in lines[:SHOWN_DECLARATIONS])
    more = len(lines) - SHOWN_DECLARATIONS
    return shown + (f"; ещё {more}" if more > 0 else "")


def lang_tests(root: Path) -> List[Tuple[List[str], Optional[str]]]:
    """(globs, declaration) per lang adapter chain (the leaf's values win within a chain);
    the globs of several languages are all test files."""
    out: List[Tuple[List[str], Optional[str]]] = []
    try:
        cfg = lib.load_config(root)
        for name in lib.adapters_for(cfg, "lang"):
            globs: List[str] = []
            declaration: Optional[str] = None
            for adapter in lib.resolve_adapter("lang", name, root):   # a project extension adds to the base
                tests = adapter.meta.get("tests") or {}
                if isinstance(tests, dict):
                    for g in tests.get("files") or []:
                        if str(g) not in globs:
                            globs.append(str(g))
                    if tests.get("declaration"):
                        declaration = str(tests["declaration"])        # the leaf's regex wins
            if globs:
                out.append((globs, declaration))
    except lib.OmixflowError:
        pass
    return out


def gate_exit(root: Path, name: str) -> Optional[str]:
    git_dir = lib.git(root, "rev-parse", "--absolute-git-dir")
    if not git_dir:
        return None
    try:
        return (Path(git_dir) / "omixflow-gates" / f"{name}.exit").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def verify_plan(root: Path, verify_file: Optional[str], also: List[str]) -> Dict[str, Any]:
    """The step set; an OmixflowError is the orchestrator's (config or --also), not the agent's."""
    if verify_file:
        try:
            return json.loads(Path(verify_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise lib.OmixflowError(f"--verify {verify_file}: {e}")
    also = [a for a in also if a and a.lower() != "none"]
    return lib.verify_plan(lib.load_config(root), root, "step", also=also or None)


def gate_criteria(root: Path) -> Dict[str, str]:
    try:
        verify = lib.load_config(root).get("verify") or {}
    except lib.OmixflowError:
        return {}
    return {name: str(gate.get("criterion", "exit-code")) for name, gate in verify.items() if isinstance(gate, dict)}


STOP_SECTIONS = ("Contracts", "Out of Scope", "Intent")   # a coder's change here is a stop, not an amendment
DECISION_ITEM_RE = re.compile(r"^\s*(?:-\s+|###\s+)(?:\*\*)?(D\d+)\b")   # `- D1:`, `- D1 (A1, D-283):`, `- **D1 — …**`, `### D1`
RESTS_ON_RE = re.compile(r"rests\s+on:", re.I)


def spec_before(root: Path, spec: Path, baseline_spec: Optional[Dict[str, Any]]) -> Optional[str]:
    """The spec's text before the assignment: the baseline's blob when the baseline recorded
    it (`report.py baseline --task`; the only base when artifacts are kept outside git or
    when earlier uncommitted edits exist), else HEAD's copy of a tracked file; None when
    there is nothing to compare against."""
    if baseline_spec and baseline_spec.get("blob"):
        text = lib.git_raw(root, "cat-file", "-p", str(baseline_spec["blob"]))
        if text is not None:
            return text
    try:
        rel = spec.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if lib.git(root, "ls-files", "--error-unmatch", "--", rel) is None:
        return None
    return lib.git_raw(root, "show", f"HEAD:./{rel}")       # `./`: a root nested in a larger repository


def spec_diff_sections(before_text: str, current_text: str) -> Dict[str, List[str]]:
    """Changed lines grouped by the `##` section they fall in (trailing whitespace ignored,
    section names as written in the first line of the heading); empty when unchanged."""
    def prepared(text: str) -> List[str]:
        """Lines with trailing whitespace dropped and blank lines removed; a heading inside
        a code fence is neutralised so it opens no section."""
        out: List[str] = []
        fenced = False
        for l in text.splitlines():
            l = l.rstrip()
            if l.lstrip().startswith("```"):
                fenced = not fenced
            if not l.strip():
                continue
            out.append((" " + l) if fenced and l.startswith("#") else l)
        return out

    before, current = prepared(before_text), prepared(current_text)

    def section_of(lines: List[str], idx: int) -> str:
        for i in range(idx, -1, -1):
            if lines[i].startswith("## "):
                return lines[i][3:].strip()
        return "(преамбула)"

    out: Dict[str, List[str]] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, current, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for i in range(i1, i2):
            out.setdefault(section_of(before, i), []).append("-" + before[i])
        for j in range(j1, j2):
            out.setdefault(section_of(current, j), []).append("+" + current[j])
    return out


def decision_items(text: str) -> Dict[str, str]:
    """Decision id → its whole item (continuation lines and the `rests on:` part included),
    whitespace-normalised."""
    found = lib.section_lines(text, "Decisions")
    if not found:
        return {}
    items: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in found[1][1:]:
        m = DECISION_ITEM_RE.match(line)
        if m:
            current = m.group(1)
            items[current] = [line]
        elif current and line.strip() and not line.startswith("## "):
            items[current].append(line)
        elif current and line.startswith("## "):
            break
    return {key: " ".join(" ".join(lines).split()) for key, lines in items.items()}


def decision_choices(text: str) -> Dict[str, str]:
    """Decision id → the text of its choice: the whole bullet (continuation lines included)
    without its `rests on:` part, whitespace-normalised. A coder may correct the facts a
    decision rests on; the choice, however it wraps, is the developer's."""
    return {key: RESTS_ON_RE.split(item, maxsplit=1)[0].strip() for key, item in decision_items(text).items()}


def changed_excerpt(old: str, new: str, context: int = 25, width: int = 140) -> Tuple[str, str]:
    """The part where OLD and NEW differ, with CONTEXT characters around it, each cut to WIDTH:
    what the orchestrator reads before it writes «выбор не менялся» — a mechanism renamed, a
    choice reversed, or another decision under the same number."""
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    tail = 0
    while tail < min(len(old), len(new)) - start and old[-1 - tail] == new[-1 - tail]:
        tail += 1

    def cut(t: str) -> str:
        a = max(0, start - context)
        a = t.rfind(" ", 0, a) + 1 if a else 0                      # whole words at both ends
        b = min(len(t), len(t) - tail + context, a + width)
        b = next((i for i in range(b, min(len(t), a + width)) if t[i] == " "), b)
        return ("…" if a else "") + t[a:b] + ("…" if b < len(t) else "")
    return cut(old), cut(new)


def check_spec_amendments(root: Path, report_path: Path, sections: Dict[str, List[str]], problems: List[str],
                          verified: List[str], facts: List[str], unchecked: List[str],
                          baseline_spec: Optional[Dict[str, Any]] = None, amend: Sequence[str] = (),
                          warnings: Optional[List[str]] = None) -> None:
    """The coder amends the spec and says so; a change to a contract, a decision's choice, the
    intent or the scope is a stop, not an amendment (agents/coder.md, «The spec learns»).
    AMEND — the decisions whose text the orchestrator ordered changed (--amend-decision):
    their change is a fact; one not in the snapshot's Decisions raises OmixflowError (the
    call's error), one left unchanged is a warning."""
    warnings = warnings if warnings is not None else []
    claimed = section_text(sections, "SPEC AMENDMENTS")
    claimed_none = not claimed or is_none(claimed)
    spec = report_path.parent.parent / "spec.md"
    if not spec.exists():
        unchecked.append(f"SPEC AMENDMENTS не сверены: нет {spec}")
        return
    before = spec_before(root, spec, baseline_spec)
    if before is None:
        unchecked.append("SPEC AMENDMENTS не сверены: нет снимка spec.md — `report.py baseline --task TASK_DIR` "
                         "перед заданием (артефакты вне git сверяются только по снимку)")
        return
    try:
        current = spec.read_text(encoding="utf-8")
    except OSError:
        return
    changed = spec_diff_sections(before, current)
    base_name = "снимка baseline" if baseline_spec and baseline_spec.get("blob") else "HEAD"
    before_d, after_d = decision_choices(before), decision_choices(current)
    unknown = [d for d in amend if d not in before_d]
    if unknown:
        raise lib.OmixflowError(f"--amend-decision {', '.join(unknown)}: такого решения нет в «Decisions» spec.md "
                                f"(против {base_name}) — флаг разрешает правку текста существующего решения")
    changed_choices = sorted(k for k in set(before_d) | set(after_d) if before_d.get(k) != after_d.get(k))
    ordered = [k for k in changed_choices if k in amend and k in after_d]   # a text edit, not a removal
    before_items, after_items = decision_items(before), decision_items(current)
    for k in amend:
        if k in changed_choices:
            continue
        if before_items.get(k) != after_items.get(k):
            warnings.append(f"--amend-decision {k}: выбор {k} против {base_name} не изменён, правка только в `rests on` — "
                            "флаг не нужен: факты, на которых стоит решение, coder правит сам")
        else:
            warnings.append(f"--amend-decision {k}: пункт {k} против {base_name} не изменён — правки по заданию "
                            "в spec.md нет")
    for k in ordered:
        was, now = changed_excerpt(before_d[k], after_d[k])
        facts.append(f"{k}: правка текста по заданию оркестратора — было «{was}», стало «{now}»")
    changed_choices = [k for k in changed_choices if k not in ordered]
    if not changed and claimed_none:
        verified.append(f"SPEC AMENDMENTS: none, spec.md не менялся (против {base_name})")
        return
    if changed and claimed_none:
        problems.append("SPEC AMENDMENTS: none, а spec.md изменён в секциях "
                        + ", ".join(f"«{s}»" for s in changed) + " — назвать каждую правку и чему научила реализация")
    elif not changed:
        problems.append(f"SPEC AMENDMENTS называет правки, а spec.md против {base_name} не изменён")
    stop = [s for s in changed if s.lower() in {x.lower() for x in STOP_SECTIONS}]
    if changed_choices:
        stop.append("Decisions " + ", ".join(changed_choices))
    elif "Decisions" in changed and not before_d and not after_d:
        stop.append("Decisions — пункты решений не распознаны (`- D1:`, `- **D1 — …**`, `### D1`), "
                    "правка в секции считается сменой решения")
    if stop:
        problems.append("SPEC AMENDMENTS: правка в " + ", ".join(f"«{s}»" for s in stop)
                        + " — это смена объёма, решения или контракта: не правка coder'а, а остановка "
                          "(STATUS: stopped) и точка scope-change; вернуть spec.md и остановиться")
    if changed and not claimed_none:
        facts.append("SPEC AMENDMENTS: " + " ".join(claimed.split())[:400])
        if not stop:
            verified.append("SPEC AMENDMENTS: spec.md изменён в " + ", ".join(f"«{s}»" for s in changed) + ", правки названы")


def check_project_specs(root: Path, report_path: Path, sections: Dict[str, List[str]], problems: List[str],
                        verified: List[str], unchecked: List[str]) -> None:
    """PROJECT SPECS UPDATED against `specs.mode` (protocol/phases.md, SDD invariant): under
    `adr` every path listed lies in `specs.adr_dir` and exists, and a record that existed at
    the base of the branch (state.yaml `base`) is not among the branch's edits — records
    added on the branch may be refined until the merge; under `none` the section is `none`;
    `descriptions` is the reviewer's judgement, not the script's."""
    try:
        cfg = lib.load_config(root)
        mode = str(lib.config_value(cfg, "specs.mode") or "descriptions")
        adr_dir = str(lib.config_value(cfg, "specs.adr_dir") or "docs/decisions").strip("/")
    except lib.OmixflowError:
        unchecked.append("PROJECT SPECS UPDATED не сверены: конфиг не прочитан")
        return
    body = section_text(sections, "PROJECT SPECS UPDATED")
    listed: List[str] = []
    for l in sections.get("PROJECT SPECS UPDATED", []):
        if is_none(l.strip()):
            continue
        # the path: the first token with a slash and a file name — quoted or bare, mewria's `- path — D1: `add``
        m = re.search(r"(?<![\w@/])(/?(?:[\w.\-]+/)+[\w.\-]+\.\w+)", l)
        if m:
            path = m.group(1)
            if path.startswith("/"):
                try:
                    path = Path(path).resolve().relative_to(root.resolve()).as_posix()
                except ValueError:
                    pass
            listed.append(path.rstrip(":"))
    if mode == "none":
        if body and not is_none(body):
            problems.append("PROJECT SPECS UPDATED: при specs.mode none секция — `none`; ничего сверх spec.md задачи")
        else:
            verified.append("PROJECT SPECS UPDATED: none (specs.mode none)")
        return
    if mode != "adr":
        return
    if not listed:
        verified.append("PROJECT SPECS UPDATED: none — шаг без записи решения (specs.mode adr)")
        return
    base_sha: Optional[str] = None
    try:
        lib.require_yaml()
        state = lib.yaml.safe_load((report_path.parent.parent / "state.yaml").read_text(encoding="utf-8")) or {}
        if isinstance(state, dict) and state.get("base"):
            base_sha = lib.base_commit(root, str(state["base"]))
    except (OSError, ValueError, lib.OmixflowError):
        base_sha = None
    for rel in listed:
        if not rel.startswith(adr_dir + "/"):
            problems.append(f"PROJECT SPECS UPDATED: `{rel}` вне {adr_dir}/ — при specs.mode adr шаг пишет записи решений, не описания")
            continue
        if not (root / rel).exists():
            problems.append(f"PROJECT SPECS UPDATED: записи `{rel}` нет в дереве")
            continue
        if base_sha is None:
            unchecked.append(f"PROJECT SPECS UPDATED: `{rel}` — была ли запись в базе ветки, не сверено (нет base в state.yaml)")
            continue
        at_base = lib.git(root, "cat-file", "-e", f"{base_sha}:./{rel}") is not None
        if at_base:
            problems.append(f"PROJECT SPECS UPDATED: запись `{rel}` была в базе ветки и правлена — записи базы только дописываются; "
                            "новое решение — новая запись (`supersedes:`)")
    if not any(p.startswith("PROJECT SPECS UPDATED") for p in problems):
        verified.append("PROJECT SPECS UPDATED: записи решений в " + adr_dir + "/ на месте: " + ", ".join(listed))


# ------------------------------------------------------------------ checks

def check(role: str, report_path: Path, root: Path, artifacts: str, plan: Optional[Dict[str, Any]],
          langs: List[Tuple[List[str], Optional[str]]], criteria: Dict[str, str],
          baseline: Optional[Dict[str, Optional[str]]] = None,
          baseline_spec: Optional[Dict[str, Any]] = None, conflicts: Optional[List[str]] = None,
          amend: Sequence[str] = ()) -> Dict[str, Any]:
    result: Dict[str, Any] = {"role": role, "report": str(report_path), "verdict": "ok", "problems": [],
                              "verified": [], "facts": [], "warnings": [], "unchecked": [], "refused": False,
                              "scratch_line": None}
    problems: List[str] = result["problems"]
    verified: List[str] = result["verified"]
    facts: List[str] = result["facts"]
    warnings: List[str] = result["warnings"]

    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        result.update(verdict="broken", problems=[f"отчёта нет: {report_path}"])
        return result
    lines = text.splitlines()
    if lines and lines[0].strip().startswith(REFUSED):
        result["refused"] = True
        text = "\n".join(lines[1:])
    sections = parse_report(text)
    if LAST[role] not in sections:
        result.update(verdict="broken", problems=[f"отчёт без последнего раздела {LAST[role]}: обрезан или не дописан"])
        return result
    # a base sync (coder MODE: sync, agents/coder.md «Sync mode»): the merge is still in progress,
    # the report lists RESOLUTIONS instead of FILES, and the agent's work is what neither side had
    other = sync_other(root) if role == "coder" else None
    sync = other is not None and (conflicts is not None
                                  or section_text(sections, "STEP").lower().startswith("sync")
                                  or "RESOLUTIONS" in sections)
    result["sync"] = other if sync else None
    base = sync_base(root, other) if sync else None
    if conflicts is not None and other is None:
        result["unchecked"].append("--conflicts без идущего слияния: слияние уже закоммичено или отменено — отчёт "
                                   "сверен как отчёт шага; синхронизацию сверять до коммита слияния")
    required = [("RESOLUTIONS" if s == "FILES" and sync else s) for s in SECTIONS[role]]
    missing = [s for s in required if s not in sections]
    if missing:
        problems.append("нет разделов: " + ", ".join(missing))
    else:
        verified.append("разделы формата на месте")
    listed: List[str] = []
    if sync:
        # `--conflicts none` (an empty list) is «no conflicts»; git's own record in MERGE_MSG still wins
        listed = conflicts or merge_conflicts(root)
        if conflicts == [] and listed:
            facts.append(f"--conflicts none, а MERGE_MSG называет конфликты: {', '.join(listed)} — сверены они")
        unnamed = uncovered(listed, section_text(sections, "RESOLUTIONS"), root) if listed else []
        if unnamed:
            problems.append(f"RESOLUTIONS не называет конфликтные файлы: {unnamed} — строка `{{file}} — {{как разрешён}}` на каждый")
        elif listed:
            verified.append(f"RESOLUTIONS: все {len(listed)} конфликтных файлов названы")
        elif conflicts == []:
            verified.append("RESOLUTIONS: конфликтов нет (--conflicts none, в MERGE_MSG их тоже нет)")
        else:
            result["unchecked"].append("RESOLUTIONS не сверены: список конфликтов не передан (--conflicts) и нет в MERGE_MSG")
        facts.append(f"синхронизация: идёт слияние с {other}; новое в MUTATIONS и BYTES CHECK — "
                     + (f"то, чего не дало бы трёхстороннее слияние HEAD и {other} от их общей базы" if base else
                        f"то, чего нет ни в HEAD, ни в {other} (общей базы нет)"))

    # a stop is not a failed report
    status = section_text(sections, "STATUS").lower()
    gates_text = section_text(sections, "GATES") if role == "coder" else section_text(sections, "RUN RESULT")
    stopped = status.startswith("stopped") or gates_text.lower().startswith("not run")
    if stopped:
        facts.append(f"остановка агента: {section_text(sections, 'STATUS') or gates_text.splitlines()[0]}")

    # TREE STATE
    claimed = normalise_claimed(sections.get("TREE STATE", []), artifacts)
    short, expanded = status_lines(root, artifacts, False), status_lines(root, artifacts, True)
    if set(claimed) in (set(short), set(expanded)):
        verified.append(f"TREE STATE совпадает с git status ({len(claimed)} строк)")
    else:
        actual = expanded if len(set(claimed) ^ set(expanded)) < len(set(claimed) ^ set(short)) else short
        extra, absent = sorted(set(claimed) - set(actual)), sorted(set(actual) - set(claimed))
        problems.append("TREE STATE расходится с `git status --short`: "
                        + (f"лишние в отчёте {extra}; " if extra else "") + (f"нет в отчёте {absent}" if absent else ""))
    untracked = [l for l in claimed if l.startswith("??")]
    for l in expanded:          # the real tree, every file: a collapsed `?? dir/` line hides a copy inside
        if re.search(r"\.(orig|rej)$", l):
            hint = (f" (если это копия probe.py до 0.9.1, а не остаток слияния или patch: `probe.py restore "
                    f"--root {root} --file {l[3:-len('.orig')]}`)" if l.endswith(".orig") else "")
            problems.append(f"TREE STATE: остаток пробы в дереве — {l}{hint}")
    # probe.py keeps its copies in the git directory, out of `git status`; not `base`, the merge base of a sync
    # (0.9.4 shadowed it: three-way counting fell back to HEAD + the other side)
    probes_dir, left = probe_copies_left(root)
    if left:
        problems.append(f"TREE STATE: пробы не восстановлены, копии в {probes_dir}: {', '.join(left[:5])} — "
                        f"`python3 {{корень плагина}}/scripts/probe.py restore --root {root}`")
    if untracked:
        facts.append("неотслеживаемые по TREE STATE: " + ", ".join(l[3:] for l in untracked))

    # SPEC AMENDMENTS (coder): the diff of the task's spec.md against its committed state
    if role == "coder":
        check_spec_amendments(root, report_path, sections, problems, verified, facts, result["unchecked"], baseline_spec,
                              amend, warnings)
        check_project_specs(root, report_path, sections, problems, verified, result["unchecked"])

    # MUTATIONS
    delta = agent_delta(root, artifacts, baseline)
    touched: Set[str] = (sync_files(root, other, base) | set(listed)) if sync else set()

    def lines_of(path: str) -> Tuple[List[str], List[str]]:
        """(added, removed) of PATH: a file of the merge against what the three-way merge gives, any other
        against the baseline's blob or HEAD (review 0.9.6 R2-1: with a baseline, a line the coder added to
        the developer's dirty file charged him with all the developer's lines)."""
        if sync and path in touched:
            return sync_new_lines(root, path, other, base), []
        return diff_lines(root, path, baseline)

    if sync and baseline is None:   # with a baseline taken once the merge started, the delta is the agent's already
        # a file neither side changes is no work of the merge — unless HEAD has no such file: one the coder made
        # during the sync (a seam test) is his, a dirty file of the developer's (mewria R-2) is not
        outside = [p for p in delta if p not in touched
                   and lib.git(root, "cat-file", "-e", f"HEAD:./{p}") is not None]
        delta = [p for p in delta if p not in outside]
        if outside:
            warnings.append(f"вне слияния (их не меняет ни одна сторона; MUTATIONS и BYTES CHECK по ним не сверены): "
                            f"{', '.join(outside[:10])}{' …' if len(outside) > 10 else ''} — правку coder'а в таких "
                            f"файлах сверяет только `--baseline`, снятый после начала слияния (implement 1a)")
    mutation_lines = [l for l in sections.get("MUTATIONS", []) if MUTATION_LINE_RE.match(l)
                      and (OUTCOME_RE.search(l) or "no probe possible" in l.lower())]
    mutations = section_text(sections, "MUTATIONS")
    if not langs:
        result["unchecked"].append("MUTATIONS не сверены: у адаптера lang нет tests.files — сверить руками "
                                   "(implement 2.2) и добавить tests во фронтматтер адаптера")
    else:
        new_declarations = 0
        per_file: List[str] = []
        shown: List[str] = []       # the same, with the declarations themselves: an error shows what is counted
        for globs, declaration in langs:
            rx = re.compile(declaration) if declaration else None
            for path in lib.area_files(globs, delta):
                if is_binary(root, path):
                    continue
                if rx is None:
                    per_file.append(f"{path}: тестовый файл изменён (объявления не считаются: у адаптера нет tests.declaration)")
                    shown.append(per_file[-1])
                    continue
                added, removed = lines_of(path)
                found = new_declarations_in(added, removed, rx)
                if found:
                    new_declarations += len(found)
                    per_file.append(f"{path}: новых тестов {len(found)}")
                    shown.append(f"{per_file[-1]} — {declarations_shown(found)}")
        unit = ("строка MUTATIONS на каждую строку, которую находит tests.declaration адаптера lang: где он считает "
                "случаи параметризованного теста ([TestCase]), — на случай")
        if is_none(mutations) and new_declarations:
            problems.append(f"MUTATIONS: none, но новых тестов {new_declarations} ({'; '.join(shown)}); {unit}")
        elif new_declarations > len(mutation_lines):
            problems.append(f"MUTATIONS: новых тестов {new_declarations} ({'; '.join(shown)}), строк с исходом "
                            f"{len(mutation_lines)}: проба на каждый новый тест и утверждение; {unit}")
        for l in mutation_lines:
            low = l.lower()
            if "no probe possible" in low:
                if any(e in low for e in EXCUSES):
                    problems.append(f"MUTATIONS: отговорка вместо причины — {l.strip()}")
                elif any(r in low for r in NOT_RUN_REASONS):
                    problems.append(f"MUTATIONS: проба не была запущена (ошибка вызова probe.py), не причина — {l.strip()}")
                continue
            outcomes = OUTCOME_RE.findall(l)
            if outcomes and outcomes[-1] == "GREEN":
                problems.append(f"MUTATIONS: исход GREEN без усиления и повторной пробы до RED — {l.strip()}")
        if not any(p.startswith("MUTATIONS") for p in problems):
            verified.append(f"MUTATIONS: новых тестов {new_declarations}, строк с исходом {len(mutation_lines)}"
                            + (f" ({'; '.join(per_file)})" if per_file else ""))

    # gates
    reported: Dict[str, Tuple[str, str]] = {}
    runs: Dict[str, Tuple[str, Optional[str]]] = {}    # gate → (gate.py run name, claimed EXIT)
    if role == "coder":
        for l in sections.get("GATES", []):
            m = GATE_LINE_RE.match(l)
            if m:
                reported[m.group(1).lower()] = (m.group(2).upper(), m.group(3))
                r = GATE_RUN_RE.search(m.group(3))
                if r:
                    runs[m.group(1).lower()] = (r.group(1), r.group(2))
    else:
        rr = section_text(sections, "RUN RESULT")
        m = re.match(r"^\s*(PASS|FAIL)\b(.*)$", rr, re.I)
        if m:
            reported["test"] = (m.group(1).upper(), m.group(2))
        for l in sections.get("CHECKPOINT GATES", []):
            for m in re.finditer(r"([a-z0-9]+):\s*(PASS|FAIL|not declared|n/a)\b", l, re.I):
                reported[m.group(1).lower()] = (m.group(2).upper(), "")
        for l in sections.get("BACKGROUND GATES", []):
            m = BACKGROUND_RE.match(l)
            if m:
                runs[m.group(1).lower()] = (m.group(2), m.group(3))
    gate_section = "GATES" if role == "coder" else "RUN RESULT / CHECKPOINT GATES"
    for name, (outcome, _) in reported.items():
        facts.append(f"гейт {name}: {outcome}")
    if stopped:
        verified.append("гейты не сверялись: агент остановился до них")
    elif plan is None:
        result["unchecked"].append("набор гейтов не сверен: нет плана verify")
    else:
        due = [g["name"] for g in plan.get("gates", [])] if role == "coder" else (
            [g["name"] for g in plan.get("gates", []) if g.get("also")] + ["test"])
        absent = [n for n in due if n not in reported]
        if absent:
            problems.append(f"{gate_section}: нет исхода гейтов {', '.join(absent)}")
        else:
            verified.append(f"{gate_section}: исходы всех гейтов набора ({', '.join(due)})")
        for name in [g for g, (o, _) in reported.items() if o == "NOT DECLARED"]:
            facts.append(f"гейт {name}: not declared — дефект плана, строка в log.md")
        background = {g["name"] for g in plan.get("gates", []) if g.get("background")}
        for name in background:
            if name in reported and name not in runs:
                problems.append(f"{gate_section}: фоновый гейт {name} без имени gate.py ({{метка}}-{name})")
        for name, (run_name, claimed_exit) in runs.items():
            actual = gate_exit(root, run_name)
            outcome = reported.get(name, ("", ""))[0]
            if actual is None:
                problems.append(f"{gate_section}: лога gate.py {run_name} нет (не запускался или имя не то)")
            elif criteria.get(name, "exit-code") in ("exit-code", "rerun-compare-set") and outcome in ("PASS", "FAIL") \
                    and (actual == "0") != (outcome == "PASS"):
                problems.append(f"{gate_section}: {name} заявлен {outcome}, а EXIT {actual} у {run_name}")
            elif claimed_exit and claimed_exit != actual:
                problems.append(f"{gate_section}: {name}: в отчёте EXIT {claimed_exit}, в логе {actual}")
            else:
                verified.append(f"{gate_section}: {run_name} EXIT {actual} как заявлено")

    # BYTES CHECK
    non_ascii = [p for p in delta if not is_binary(root, p)
                 and any(any(ord(ch) > 127 for ch in l)
                         for l in lines_of(p)[0])]
    bytes_check = section_text(sections, "BYTES CHECK")
    if non_ascii and (not bytes_check or bytes_check.lstrip("-* ").lower().startswith("n/a")):
        problems.append(f"BYTES CHECK: n/a, а в диффе не-ASCII строки: {non_ascii} — `n/a` только при "
                        f"ASCII-диффе; {BYTES_FORM_HINT}")
    elif non_ascii and uncovered(non_ascii, bytes_check, root):
        problems.append(f"BYTES CHECK не называет файлы диффа с не-ASCII строками: {uncovered(non_ascii, bytes_check, root)}; "
                        f"{BYTES_FORM_HINT}")
    elif "BYTES CHECK" in sections:
        verified.append("BYTES CHECK соответствует диффу")

    # SUPPRESSIONS CHECK, SCRATCH, the sections the orchestrator acts on
    if not section_text(sections, "SUPPRESSIONS CHECK"):
        problems.append("SUPPRESSIONS CHECK пуст")
    scratch = section_text(sections, "SCRATCH")
    if scratch and not scratch.lower().startswith("clean"):
        result["scratch_line"] = f"- SCRATCH {report_path.stem}: {scratch.splitlines()[0]}"
    notes = section_text(sections, "NOTES")
    if notes and not is_none(notes):
        facts.append("NOTES: " + " ".join(notes.split())[:400])
        warnings += unprobed_claims(sections.get("NOTES", []))
    for name in ("FAILURES", "CODE BUGS FOUND"):
        body = section_text(sections, name)
        if body and not is_none(body):
            facts.append(f"{name}: " + " ".join(body.split())[:400])

    result["verdict"] = "return" if problems else ("stopped" if stopped else "ok")
    return result


def render(result: Dict[str, Any]) -> str:
    head = f"VERDICT: {result['verdict']}"
    if result["refused"]:
        head += " (ответ REPORT_PATH refused by the harness: файл записал оркестратор)"
    out = [head]
    if result["verdict"] in ("ok", "stopped"):
        out += [f"- {v}" for v in result["verified"]]
    elif result["verdict"] == "broken":
        out += [f"- {p}" for p in result["problems"]]
        return "\n".join(out)
    else:
        out.append("Сообщение агенту (отправить как есть):")
        out.append("The report was checked against the tree and the gate logs; fix these points and report again "
                   "with the same REPORT_PATH:")
        out += [f"{i}. {p}" for i, p in enumerate(result["problems"], 1)]
    for f in result["facts"]:
        out.append(f"- {f}")
    for w in result["warnings"]:
        out.append(f"- ПРЕДУПРЕЖДЕНИЕ: {w}")
    for u in result["unchecked"]:
        out.append(f"- НЕ СВЕРЕНО: {u}")
    if result["scratch_line"]:
        out.append(result["scratch_line"])
    return "\n".join(out)


class Parser(argparse.ArgumentParser):
    def error(self, message: str):   # a usage error is the orchestrator's, exit 3
        print(f"report.py: {message}", file=sys.stderr)
        sys.exit(USAGE)


def decision_id(value: str) -> str:
    """`D3` (or `d3`) of --amend-decision; anything else is a usage error."""
    v = value.strip().upper()
    if not re.fullmatch(r"D\d+", v):
        raise argparse.ArgumentTypeError(f"не номер решения: {value!r} (ожидается D{{n}}, например D3)")
    return v


def cmd_baseline(ns: argparse.Namespace, root: Path, artifacts: str) -> int:
    snap = snapshot(root, artifacts, store=True)
    record: Dict[str, Any] = {"root": str(root), "artifacts": artifacts, "files": snap}
    spec_note = ""
    if ns.task:
        spec = Path(ns.task).resolve() / "spec.md"
        if spec.exists():   # the blob is stored whether or not the file is tracked: the only base for untracked artifacts
            blob = content_hash(root, str(spec), store=True)
            record["spec"] = {"path": str(spec), "blob": blob}
            if blob:   # a ref keeps the blob out of `git gc`'s reach (loose objects are pruned after two weeks)
                lib.git(root, "update-ref", f"refs/omixflow/snapshots/{spec.parent.name}/{blob}", blob)
            spec_note = f", spec.md snapshot blob {blob}"     # the orchestrator writes the blob into log.md
        else:
            spec_note = ", no spec.md"
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"baseline: {len(snap)} uncommitted paths{spec_note} → {out}")
    return 0


def cmd_check(ns: argparse.Namespace, root: Path, artifacts: str) -> int:
    baseline = None
    if ns.baseline:
        try:
            loaded = json.loads(Path(ns.baseline).read_text(encoding="utf-8"))
            baseline = loaded["files"]
            baseline_spec = loaded.get("spec")
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"report.py: --baseline {ns.baseline}: {e}", file=sys.stderr)
            return USAGE
    else:
        baseline_spec = None
    langs = lang_tests(root)
    if ns.test_glob:
        langs = [(list(ns.test_glob), ns.declaration)]
    elif ns.declaration:
        langs = [(g, ns.declaration) for g, _ in langs] or [([], ns.declaration)]
    amend = sorted(set(ns.amend_decision))
    if amend and ns.role != "coder":
        print("report.py: --amend-decision — только с --role coder: правки spec.md сверяются в SPEC AMENDMENTS coder'а",
              file=sys.stderr)
        return USAGE
    try:
        plan = verify_plan(root, ns.verify, ns.also)
    except lib.OmixflowError as e:
        print(f"report.py: план гейтов не получен: {e}", file=sys.stderr)
        return USAGE
    conflicts = None if ns.conflicts is None else [c.strip() for c in ns.conflicts]
    if conflicts is not None and "" in conflicts:      # an empty substitution of {CONFLICTS}, not «none»
        print("report.py: --conflicts: пустое значение — файлы или `none`, когда конфликтов нет", file=sys.stderr)
        return USAGE
    if conflicts and any(c.lower() == "none" for c in conflicts):
        if len(conflicts) > 1:
            print(f"report.py: --conflicts: `none` — только одно, без файлов (передано: {' '.join(conflicts)})", file=sys.stderr)
            return USAGE
        conflicts = []
    try:
        result = check(ns.role, Path(ns.report), root, artifacts.strip("/"), plan, langs, gate_criteria(root), baseline,
                       baseline_spec, conflicts, amend)
    except lib.OmixflowError as e:      # the call's error (an --amend-decision of no decision of the spec): exit 3, not a return
        print(f"report.py: {e}", file=sys.stderr)
        return USAGE
    print(json.dumps(result, ensure_ascii=False, indent=2) if ns.json else render(result))
    return {"ok": OK, "stopped": OK, "return": RETURN, "broken": BROKEN}[result["verdict"]]


def main(argv: Optional[List[str]] = None) -> int:
    ap = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    p = sub.add_parser("baseline")
    p.add_argument("--out", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--artifacts", default=None)
    p.add_argument("--task", default=None, help="TASK_DIR: its spec.md is snapshotted for the SPEC AMENDMENTS check")
    p.set_defaults(fn=cmd_baseline)
    p = sub.add_parser("check")
    p.add_argument("--role", required=True, choices=sorted(SECTIONS))
    p.add_argument("--report", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--artifacts", default=None, help="artifacts directory, default from flow.yaml (.tasks)")
    p.add_argument("--baseline", default=None, help="file of `report.py baseline` taken before the assignment")
    p.add_argument("--verify", default=None, help="JSON of resolve.py verify for the step; default: computed")
    p.add_argument("--also", nargs="+", action="extend", default=[], help="checkpoint gates of the step (`none` ignored)")
    p.add_argument("--test-glob", nargs="+", action="extend", default=[], help="test file globs; default: lang adapters' `tests.files`")
    p.add_argument("--declaration", default=None, help="regex of a test declaration; default: adapters' `tests.declaration`")
    p.add_argument("--conflicts", nargs="+", default=None,
                   help="conflicted files of a base sync (the CONFLICTS of MODE: sync), `none` alone for none; "
                        "default: MERGE_MSG")
    p.add_argument("--amend-decision", nargs="+", action="extend", default=[], type=decision_id, metavar="Dn",
                   help="a decision whose text the orchestrator ordered changed (a review fix of the mechanism, "
                        "not the choice): a fact, not a stop; repeatable")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_check)
    ns = ap.parse_args(argv)
    root = lib.find_project_root(Path(ns.root) if ns.root else None)
    try:
        artifacts = ns.artifacts or str(lib.config_get(lib.load_config(root), "artifacts.dir") or ".tasks")
    except lib.OmixflowError:
        artifacts = ns.artifacts or ".tasks"
    return ns.fn(ns, root, artifacts.strip("/"))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:       # a crash is the call's error: exit 1 would read as «return the report»
        traceback.print_exc()
        sys.exit(USAGE)
