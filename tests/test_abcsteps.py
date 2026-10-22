"""ABC opened up (spec 6a): the script from the source tree, the step-by-step run, and a
recording without an ABC binary.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import HAVE_ABC, HAVE_ODIN3, ODIN3_ROOT, abc_binary
from tests.micros import COUNTER2
from tests.test_record import techlib, write_micro
from verdandi.odin3.abcsteps import (
    TITLES,
    abc_script,
    capture_abc_input,
    run_abc_steps,
)
from verdandi.odin3.record import record
from verdandi.trace import Trace, load

if HAVE_ODIN3:
    import odin3


def prepared_design(source: Path) -> odin3.Design:
    """A design lowered to the soft logic the recorder has before its ``abc`` pass."""
    library = techlib()
    assert library is not None
    design = odin3.Design()
    design.run_pass("read_techlib", f'"{library}"')
    design.run_pass("read_verilog", f'--nolatches --vtr-compat "{source}"')
    for command in ("proc", "fsm", "opt", "flatten", "opt -full", "wreduce", "lower"):
        name, _, arguments = command.partition(" ")
        design.run_pass(name, arguments)
    return design


def odin3_abc_binary() -> str | None:
    """The abc pass's child engine (odin3-abc) in the Odin III build, when there is one.

    A script other than the embedded default runs in this child (odin3_abc_route), and the
    binding's process is not the build's executable, so the test names the child explicitly.
    """
    if ODIN3_ROOT is None:
        return None
    found = sorted(
        ODIN3_ROOT.glob("build/*/odin3-abc"),
        key=lambda path: (path.parent.name != "release", str(path)),
    )
    for candidate in found:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None

# A small two-level combinational network: enough soft logic for strash and if -K.
BAND = """\
.model band
.inputs a b c d
.outputs y
.names a b c d n1
11-- 1
--11 1
.names n1 y
0 1
.end
"""


class ScriptTest(unittest.TestCase):
    @unittest.skipUnless(ODIN3_ROOT is not None, "ODIN3_ROOT")
    def test_abc_script_from_tree(self) -> None:
        assert ODIN3_ROOT is not None
        commands = abc_script(ODIN3_ROOT, 6)
        self.assertEqual(commands[0], "strash")
        self.assertIn("if -K 6 -v", commands)
        self.assertNotIn("print_stats", commands)

    def test_abc_script_reads_the_given_path(self) -> None:
        # "abc --script FILE": the replay follows FILE, not lib/abc/vtr.abc.
        with tempfile.TemporaryDirectory() as tmp:
            given = Path(tmp) / "custom.abc"
            given.write_text("# a comment\nstrash\nif -K {K} -v\nprint_stats\n", encoding="utf-8")
            self.assertEqual(abc_script(None, 4, script=given), ["strash", "if -K 4 -v"])


class StepsTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ABC, "a standalone ABC binary")
    def test_abc_steps_counter(self) -> None:
        binary = abc_binary()
        assert binary is not None
        with tempfile.TemporaryDirectory() as tmp:
            blif = Path(tmp) / "band.blif"
            blif.write_text(BAND, encoding="utf-8")
            steps = run_abc_steps(binary, blif, abc_script(None, 6), Path(tmp) / "steps")
            self.assertEqual(len(steps), 7)
            by_command = {step.command.split()[0]: step for step in steps}
            self.assertGreater(by_command["strash"].stats["and"], 0)
            self.assertGreater(by_command["if"].stats["nd"], 0)
            for step in steps:
                self.assertTrue(step.dot.is_file(), step.command)
                self.assertTrue(
                    step.dot.read_text(encoding="utf-8").startswith("digraph"), step.command
                )


# A module with no soft logic: its abc pass writes no exchange run.
PASS_THROUGH = "module pass_through(input a, output y);\n  assign y = a;\nendmodule\n"


@unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
class CaptureTest(unittest.TestCase):
    def test_capture_clears_a_stale_run(self) -> None:
        # A capture replays whatever BLIF it finds: a run that writes none must not resurface
        # the previous capture's files.
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "abc"
            design = prepared_design(write_micro(COUNTER2, Path(tmp)))
            try:
                self.assertEqual(len(capture_abc_input(design, 6, workdir)), 1)
            finally:
                design.close()
            plain = Path(tmp) / "pass_through.v"
            plain.write_text(PASS_THROUGH, encoding="utf-8")
            design = prepared_design(plain)
            try:
                self.assertEqual(capture_abc_input(design, 6, workdir), [])
            finally:
                design.close()

    def test_capture_quotes_the_workdir(self) -> None:
        # odin3 splits pass arguments on blanks unless the value is double-quoted.
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            workdir = Path(tmp) / "a dir" / "abc"
            design = prepared_design(source)
            try:
                self.assertEqual(len(capture_abc_input(design, 6, workdir)), 1)
            finally:
                design.close()


@unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
@unittest.skipUnless(HAVE_ABC, "a standalone ABC binary")
class RecordedStepsTest(unittest.TestCase):
    """The recorder's ABC sub-steps from the real pass: one per script command (spec 6a)."""

    def record_counter2(self, tmp: str) -> tuple[Path, Trace]:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        top, _text = COUNTER2
        source = write_micro(COUNTER2, Path(tmp))
        out = Path(tmp) / "trace"
        code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
        self.assertEqual(code, 0)
        return out, load(out)

    def test_record_counter_abc_children(self) -> None:
        # Both sides mapped two LUTs: ABC's network node count (nd) is 4 on either side (2 LUTs
        # and 2 output-buffer nodes), so the replay illustrates the linked run, not differs.
        with tempfile.TemporaryDirectory() as tmp:
            out, trace = self.record_counter2(tmp)
            abc_step = next(step for step in trace.steps if step.anchor == "pass:abc")
            children = trace.children(abc_step.id)
            self.assertEqual(len(children), 7)
            assert ODIN3_ROOT is not None
            words = [command.split()[0] for command in abc_script(ODIN3_ROOT, 6)]
            self.assertEqual(
                [child.anchor for child in children], [f"abc:{word}" for word in words]
            )
            self.assertEqual([child.title for child in children], [TITLES[word] for word in words])
            for child in children:
                self.assertEqual(child.level, 2, child.title)
                self.assertEqual(child.parent, abc_step.id, child.title)
                self.assertIsNone(child.snapshot, child.title)
                self.assertIsNotNone(child.picture, child.title)
                picture = out / "pic" / str(child.picture)
                self.assertTrue(picture.is_file(), child.title)
                self.assertTrue(
                    picture.read_text(encoding="utf-8").startswith("digraph"), child.title
                )
                self.assertFalse(child.illustration, child.title)


    def test_record_uses_the_given_abc_script(self) -> None:
        # "abc --script FILE" replays FILE's commands, not lib/abc/vtr.abc.
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        child = odin3_abc_binary()
        if child is None:
            self.skipTest("no odin3-abc in the Odin III build")
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            given = Path(tmp) / "custom.abc"
            given.write_text("strash\nif -K 6\nprint_stats\n", encoding="utf-8")
            out = Path(tmp) / "trace"
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; fsm; opt; flatten; opt -full; wreduce; lower; "
                f'abc --lut 6 --script "{given}"'
            )
            with mock.patch.dict(os.environ):
                os.environ["ODIN3_ABC_EXE"] = child
                code = record(
                    [source], top, out, techlib=library, script=script, odin3_root=ODIN3_ROOT
                )
            self.assertEqual(code, 0)
            trace = load(out)
            abc_step = next(step for step in trace.steps if step.anchor == "pass:abc")
            children = trace.children(abc_step.id)
            self.assertEqual([child.anchor for child in children], ["abc:strash", "abc:if"])
            self.assertEqual(
                [child.title for child in children], [TITLES["strash"], TITLES["if"]]
            )

    def test_record_two_abc_commands(self) -> None:
        # Each abc command captures and replays in its own directory: both L1 steps open up,
        # and the second one's files do not overwrite the first one's.
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; fsm; opt; flatten; opt -full; wreduce; lower; abc --lut 6; abc --lut 6"
            )
            code = record(
                [source], top, out, techlib=library, script=script, odin3_root=ODIN3_ROOT
            )
            self.assertEqual(code, 0)
            trace = load(out)
            abc_steps = [step for step in trace.steps if step.anchor == "pass:abc"]
            self.assertEqual(len(abc_steps), 2)
            pictures: set[str] = set()
            for abc_step in abc_steps:
                children = trace.children(abc_step.id)
                self.assertEqual(len(children), 7, abc_step.title)
                pictures.update(str(child.picture) for child in children)
            self.assertEqual(len(pictures), 14)
            for name in pictures:
                path = out / "pic" / name
                self.assertTrue(path.is_file(), name)
                self.assertTrue(path.read_text(encoding="utf-8").startswith("digraph"), name)


@unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
class NoBinaryTest(unittest.TestCase):
    def test_abc_without_binary(self) -> None:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            stderr = io.StringIO()
            with mock.patch.dict(os.environ):
                os.environ.pop("ODIN3_ABC", None)
                os.environ.pop("ODIN3_ROOT", None)
                with contextlib.redirect_stderr(stderr):
                    code = record(
                        [source], top, out, techlib=library, abc=None, odin3_root=None
                    )
            self.assertEqual(code, 0)
            trace = load(out)
            abc_step = next(step for step in trace.steps if step.anchor == "pass:abc")
            self.assertEqual(trace.children(abc_step.id), [])
            warnings = [line for line in stderr.getvalue().splitlines() if "warning" in line]
            abc_warnings = [line for line in warnings if "ABC" in line]
            self.assertEqual(len(abc_warnings), 1, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
