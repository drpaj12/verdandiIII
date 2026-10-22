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
from verdandi.odin3.abcsteps import TITLES, abc_script, run_abc_steps
from verdandi.odin3.record import record
from verdandi.trace import Trace, load

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
