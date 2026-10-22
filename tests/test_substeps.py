"""Sub-step tests (L2): the proc stop points, the opt order and the opt fixed point.

The recording test needs the odin3 binding, the library and the LPM tech library; the opt
order test reads the Odin III source and skips without ODIN3_ROOT.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import verdandi.odin3.substeps as substeps_module
from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from tests.micros import COUNTER2, IFELSE_REG
from tests.test_record import techlib, write_micro
from verdandi.odin3.record import record
from verdandi.odin3.substeps import (
    ITERATION_PREFIX,
    OPT_LOOP,
    OPT_PROLOGUE,
    SUBSTEPS,
    expand,
    matches,
    opt_loop,
)
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
        # opt_share is WHEN_FULL in the source, so plain opt never runs it and opt -full does.
        tokens = {
            _OPT_SUB_PASS[sub]: when
            for sub, when in re.findall(
                r"\{\s*ODIN3_OPT_SUB_([A-Z]+)\s*,\s*(WHEN_[A-Z_]+)\s*\}", body
            )
        }
        self.assertEqual(tokens.get("opt_share"), "WHEN_FULL")
        self.assertIn("opt_share", opt_loop(True))
        self.assertNotIn("opt_share", opt_loop(False))


class IterationCapCommentTest(unittest.TestCase):
    def test_cap_comment_cites_the_plan_and_the_library_cap(self) -> None:
        source = Path(substeps_module.__file__).read_text(encoding="utf-8")
        lines = source.splitlines()
        index = next(
            number for number, line in enumerate(lines) if line.startswith("OPT_MAX_ITERATIONS =")
        )
        comment = "\n".join(lines[max(0, index - 4) : index]).lower()
        # 10 is the recorder's cap, not the library's (ODIN3_OPT_MAX_ITERATIONS = 10000).
        self.assertIn("10000", comment)
        self.assertIn("plan", comment)


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


class FsmSubstepsTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_fsm_children_are_detect_then_fsm(self) -> None:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; fsm"
            )
            code = record(
                [source], COUNTER2[0], out, techlib=library, script=script,
                odin3_root=ODIN3_ROOT,
            )
            self.assertEqual(code, 0)
            trace = load(out)
            fsm = next(step for step in trace.steps if step.anchor == "pass:fsm")
            children = trace.children(fsm.id)
            self.assertEqual([child.title for child in children], ["fsm_detect", "fsm"])
            for child in children:
                self.assertEqual(child.level, 2, child.title)
                self.assertEqual(child.parent, fsm.id, child.title)
                self.assertIsNotNone(trace.snapshot(child), child.title)


class OptIterationNestingTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_iteration_groups_nest_their_sub_passes(self) -> None:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(IFELSE_REG, Path(tmp))
            out = Path(tmp) / "trace"
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; opt -full"
            )
            code = record(
                [source], IFELSE_REG[0], out, techlib=library, script=script,
                odin3_root=ODIN3_ROOT,
            )
            self.assertEqual(code, 0)
            trace = load(out)
            opt = next(
                step for step in trace.steps if step.anchor == "pass:opt" and step.level == 1
            )
            children = trace.children(opt.id)
            prologue = children[: len(OPT_PROLOGUE)]
            self.assertEqual([step.title for step in prologue], OPT_PROLOGUE)
            groups = [step for step in children if step.title.startswith(ITERATION_PREFIX)]
            self.assertGreaterEqual(len(groups), 2, "the loop stopped before a repeat")
            for step in prologue:
                self.assertEqual((step.level, step.parent), (2, opt.id), step.title)
            for group in groups:
                self.assertEqual((group.level, group.parent), (2, opt.id), group.title)
                nested = trace.children(group.id)
                self.assertEqual([step.title for step in nested], opt_loop(True), group.title)
                for step in nested:
                    self.assertEqual((step.level, step.parent), (2, group.id), step.title)


class IterationGroupSnapshotTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_iteration_group_shares_its_last_child_snapshot(self) -> None:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(IFELSE_REG, Path(tmp))
            out = Path(tmp) / "trace"
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; opt -full"
            )
            code = record(
                [source], IFELSE_REG[0], out, techlib=library, script=script,
                odin3_root=ODIN3_ROOT,
            )
            self.assertEqual(code, 0)
            trace = load(out)
            opt = next(s for s in trace.steps if s.anchor == "pass:opt" and s.level == 1)
            groups = [
                step for step in trace.children(opt.id) if step.title.startswith(ITERATION_PREFIX)
            ]
            self.assertTrue(groups, "no iteration group")
            for group in groups:
                children = trace.children(group.id)
                self.assertTrue(children, group.title)
                self.assertEqual(group.level, 2, group.title)
                self.assertEqual(children[-1].level, 2, group.title)
                # The group's end state is its last child's: one file, not two identical copies.
                self.assertEqual(group.snapshot, children[-1].snapshot, group.title)
                self.assertNotEqual(group.snapshot, f"{group.id}.json", group.title)
                self.assertEqual(trace.snapshot(group), trace.snapshot(children[-1]), group.title)


if __name__ == "__main__":
    unittest.main()
