"""Notes: the anchor format, a directory load, stale anchors, and the shipped notes (spec 3, D10).

A note is one markdown file whose first line is ``anchor: <anchor>``, then a blank line, then
at most 15 lines of text. ``stale`` lists the anchors no current source backs, so a renamed pass
or a changed ABC script shows up as a stale note instead of silent advice.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from verdandi.cli import main
from verdandi.notes import load_notes, shipped_dir, stale
from verdandi.odin3.locator import Locator

if HAVE_ODIN3:
    import odin3

PASS_NOTES = {
    "pass:proc",
    "pass:opt_expr",
    "pass:opt_merge",
    "pass:opt_clean",
    "pass:hardmap",
    "pass:lower",
    "pass:flatten",
    "pass:wreduce",
}

ABC_NOTES = {
    "abc:strash",
    "abc:ifraig",
    "abc:scorr",
    "abc:dc2",
    "abc:dch",
    "abc:if",
    "abc:mfs2",
}


def write_note(directory: Path, name: str, text: str) -> Path:
    """Write one note file into ``directory`` and return its path."""
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def stage_titles() -> set[str]:
    """The stage titles of the recorder's stage map, as the check-notes command reads them."""
    path = Path(__file__).resolve().parent.parent / "verdandi" / "odin3" / "stages.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {stage["title"] for stage in data["stages"]}


class NoteLoadTest(unittest.TestCase):
    def test_note_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_note(
                directory,
                "proc.md",
                "anchor: pass:proc\n\nproc lowers processes.\n\nIt runs per module.\n",
            )
            write_note(directory, "lower.md", "anchor: stage:Lower\n\nbits.\n")
            notes = load_notes(directory)
            self.assertEqual(set(notes), {"pass:proc", "stage:Lower"})
            self.assertEqual(notes["pass:proc"], "proc lowers processes.\n\nIt runs per module.")
            self.assertEqual(notes["stage:Lower"], "bits.")
            over_long = "anchor: pass:opt\n\n" + "\n".join(f"line {n}" for n in range(16))
            write_note(directory, "long.md", over_long + "\n")
            with self.assertRaises(ValueError) as raised:
                load_notes(directory)
            self.assertIn("long.md", str(raised.exception))

    def test_missing_anchor_line_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = write_note(directory, "bad.md", "Pass: proc\n\nno anchor line.\n")
            with self.assertRaises(ValueError) as raised:
                load_notes(directory)
            self.assertIn(path.name, str(raised.exception))

    def test_stale_pass_flagged(self) -> None:
        notes = {
            "pass:nope": "x",
            "pass:proc": "x",
            "stage:Processes": "x",
            "stage:Nope": "x",
            "abc:strash": "x",
            "abc:bogus": "x",
            "func:demo_helper": "x",
            "rule:opt_expr:const_and": "x",
        }
        anchors = stale(notes, {"proc", "opt"}, Locator(None), {"Processes"})
        # Without a source tree the function and rule anchors cannot be checked: they are
        # left alone rather than reported, and the shipped notes carry none of them.
        self.assertEqual(anchors, ["abc:bogus", "pass:nope", "stage:Nope"])

    @unittest.skipUnless(HAVE_ODIN3 and ODIN3_ROOT is not None, "needs odin3 and ODIN3_ROOT")
    def test_shipped_notes_not_stale(self) -> None:
        notes = load_notes(shipped_dir())
        for title in stage_titles():
            self.assertIn(f"stage:{title}", notes)
        for anchor in PASS_NOTES | ABC_NOTES:
            self.assertIn(anchor, notes)
        assert ODIN3_ROOT is not None
        passes = set(odin3.default().passes())
        self.assertEqual(stale(notes, passes, Locator(ODIN3_ROOT), stage_titles()), [])


class CheckNotesCliTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3 and ODIN3_ROOT is not None, "needs odin3 and ODIN3_ROOT")
    def test_cli_check_notes(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["check-notes"])
        self.assertEqual(code, 0, out.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_note(directory, "stale.md", "anchor: pass:nope\n\nwhy it was true.\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["check-notes", "--notes", str(directory)])
            self.assertEqual(code, 1)
            self.assertIn("pass:nope", out.getvalue())


if __name__ == "__main__":
    unittest.main()
