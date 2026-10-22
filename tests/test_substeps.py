"""Sub-step tests (L2): the proc stop points, the opt order and the opt fixed point.

The recording test needs the odin3 binding, the library and the LPM tech library; the opt
order test reads the Odin III source and skips without ODIN3_ROOT.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from tests.micros import COUNTER2, IFELSE_REG
from tests.test_record import techlib, write_micro
from verdandi.odin3.record import record
from verdandi.odin3.substeps import ITERATION_PREFIX, OPT_LOOP, SUBSTEPS, expand, matches
from verdandi.trace import load

# The enum suffix of each opt sub-pass in src/passes/opt/opt_loop.c's k_default_loop.
_OPT_SUB_PASS = {
    "MUXTREE": "opt_muxtree",
    "REDUCE": "opt_reduce",
    "MERGE": "opt_merge",
    "SHARE": "opt_share",
    "DFF": "opt_dff",
    "CLEAN": "opt_clean",
    "EXPR": "opt_expr",
}


def read_script(library: Path, source: Path) -> str:
    """The commands up to a bare ``proc``: read the techlib, the micro, then proc."""
    return (
        f'read_techlib "{library}"; '
        f'read_verilog --nolatches --vtr-compat "{source}"; '
        "proc"
    )


class ProcSubstepsTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_proc_substeps_counter(self) -> None:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            code = record(
                [source],
                top,
                out,
                techlib=library,
                script=read_script(library, source),
                odin3_root=ODIN3_ROOT,
            )
            self.assertEqual(code, 0)
            trace = load(out)
            proc = next(step for step in trace.steps if step.anchor == "pass:proc")
            children = trace.children(proc.id)
            self.assertEqual([child.title for child in children], SUBSTEPS["proc"])
            self.assertEqual(len(children), 5)
            for child in children:
                self.assertEqual(child.level, 2, child.title)
                self.assertEqual(child.parent, proc.id, child.title)
                self.assertIsNotNone(trace.snapshot(child), child.title)
                self.assertFalse(child.illustration, child.title)
            last = trace.snapshot(children[-1])
            real = trace.snapshot(proc)
            assert last is not None and real is not None
            self.assertTrue(matches(last, real), "the full stop point differs from proc")


class OptOrderTest(unittest.TestCase):
    @unittest.skipUnless(ODIN3_ROOT is not None, "ODIN3_ROOT")
    def test_opt_order_from_source(self) -> None:
        assert ODIN3_ROOT is not None
        path = ODIN3_ROOT / "src" / "passes" / "opt" / "opt_loop.c"
        self.assertTrue(path.is_file(), path)
        text = path.read_text(encoding="utf-8")
        body = text.split("k_default_loop[] = {", 1)[1].split("};", 1)[0]
        subs = re.findall(r"ODIN3_OPT_SUB_([A-Z]+)", body)
        self.assertTrue(subs, "no steps in k_default_loop")
        # opt_share is conditional (WHEN_FULL), so compare the always-run order without it and
        # pin its place right after opt_merge on both sides (Yosys's order).
        source = [_OPT_SUB_PASS[sub] for sub in subs]
        expected = [command for command in OPT_LOOP if command != "opt_share"]
        self.assertEqual([name for name in source if name != "opt_share"], expected)
        self.assertEqual(source.index("opt_share"), source.index("opt_merge") + 1)
        self.assertEqual(OPT_LOOP.index("opt_share"), OPT_LOOP.index("opt_merge") + 1)


class OptFixedPointTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_opt_iterations_reach_fixed_point(self) -> None:
        import odin3

        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(IFELSE_REG, Path(tmp))
            design = odin3.Design(odin3.default())
            try:
                design.run_pass("read_techlib", str(library))
                design.run_pass(
                    "read_verilog", f'--nolatches --vtr-compat "{source}"'
                )
                design.run_pass("proc", "")
                entries = expand(design, "opt -full")
            finally:
                design.close()
        iterations = [
            snapshot for title, snapshot, _log in entries if title.startswith(ITERATION_PREFIX)
        ]
        self.assertGreaterEqual(len(iterations), 2, "the loop stopped before a repeat")
        self.assertLessEqual(len(iterations), 10)
        self.assertEqual(iterations[-1], iterations[-2], "the loop did not reach a fixed point")


if __name__ == "__main__":
    unittest.main()
