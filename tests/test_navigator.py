"""Navigator tests on a hand-made trace written by the Task 2 save and load."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from verdandi.navigator import Navigator
from verdandi.trace import FORMAT_VERSION, Diff, Manifest, ObjRef, Step, Trace, load, save


def make_manifest() -> Manifest:
    return Manifest(
        version=FORMAT_VERSION,
        program="odin3",
        program_version="1.0.0",
        abi=1,
        source_commit="0123456789abcdef",
        files=["counter2.v"],
        top="counter2",
        arch=None,
        script="read_verilog counter2.v; proc",
        stage_map_version=1,
        recorded="2026-10-22T12:00:00Z",
    )


def make_steps() -> list[Step]:
    q3 = ObjRef(module="counter2", kind="net", id=10, name="q[3]")
    dff = ObjRef(module="counter2", kind="node", id=3, name="$dff")
    return [
        Step(
            id="s0001",
            parent=None,
            level=0,
            title="Read architecture",
            anchor="stage:Read architecture",
            snapshot="s0001.json",
        ),
        Step(
            id="s0002",
            parent="s0001",
            level=1,
            title="read_arch",
            anchor="pass:read_arch",
            snapshot="s0002.json",
        ),
        Step(
            id="s0003",
            parent="s0001",
            level=1,
            title="read_techlib",
            anchor="pass:read_techlib",
            snapshot="s0003.json",
            diff=Diff(added=[q3], removed=[], changed=[], by_name=False),
        ),
        Step(
            id="s0004",
            parent=None,
            level=0,
            title="Processes",
            anchor="stage:Processes",
            snapshot="s0004.json",
        ),
        Step(
            id="s0005",
            parent="s0004",
            level=1,
            title="proc",
            anchor="pass:proc",
            snapshot="s0005.json",
            diff=Diff(added=[], removed=[], changed=[q3], by_name=False),
        ),
        Step(
            id="s0006",
            parent="s0005",
            level=2,
            title="iteration 1",
            anchor="sub:proc:1",
            snapshot="s0006.json",
        ),
        Step(
            id="s0007",
            parent="s0004",
            level=1,
            title="opt",
            anchor="pass:opt",
            snapshot="s0007.json",
            diff=Diff(added=[], removed=[dff], changed=[], by_name=False),
        ),
        Step(
            id="s0008",
            parent=None,
            level=0,
            title="ABC: logic optimisation and K-LUT mapping",
            anchor="stage:ABC",
            snapshot="s0008.json",
        ),
    ]


def make_trace(directory: Path) -> Trace:
    """Write the hand-made trace and load it back, as the player does."""
    steps = make_steps()
    snapshots: dict[str, dict[str, Any]] = {}
    for step in steps:
        if step.snapshot is not None:
            snapshots[step.snapshot] = {"kind": "ir", "modules": []}
    save(directory, make_manifest(), steps, snapshots, [])
    return load(directory)


class NavigatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.trace = make_trace(Path(self._tmp.name) / "trace")

    def ids(self, *steps: Step) -> list[str]:
        return [step.id for step in steps]

    def test_next_in_out_back(self) -> None:
        navigator = Navigator(self.trace)
        self.assertEqual(navigator.current().id, "s0001")
        self.assertEqual(navigator.next().id, "s0004")
        self.assertEqual(navigator.step_in().id, "s0005")
        self.assertEqual(navigator.next().id, "s0007")
        self.assertEqual(navigator.step_out().id, "s0004")
        self.assertEqual(navigator.back().id, "s0007")
        self.assertEqual(navigator.back().id, "s0005")
        self.assertEqual(navigator.back().id, "s0004")
        self.assertEqual(navigator.back().id, "s0001")
        self.assertEqual(navigator.back().id, "s0001")

    def test_next_climbs_to_parent_sibling(self) -> None:
        navigator = Navigator(self.trace)
        navigator.jump_stage(1)
        self.assertEqual(navigator.step_in().id, "s0005")
        self.assertEqual(navigator.step_in().id, "s0006")
        self.assertEqual(navigator.next().id, "s0007")
        self.assertEqual(navigator.next().id, "s0008")
        self.assertEqual(navigator.next().id, "s0008")

    def test_jump_stage(self) -> None:
        navigator = Navigator(self.trace)
        self.assertEqual(navigator.jump_stage(0).id, "s0001")
        self.assertEqual(navigator.jump_stage(1).id, "s0004")
        self.assertEqual(navigator.jump_stage(2).id, "s0008")
        with self.assertRaises(IndexError):
            navigator.jump_stage(3)
        with self.assertRaises(IndexError):
            navigator.jump_stage(-1)

    def test_follow_net(self) -> None:
        navigator = Navigator(self.trace)
        matches = navigator.follow("q[3]")
        self.assertEqual(self.ids(*matches), ["s0003", "s0005"])
        self.assertEqual(navigator.current().id, "s0003")
        self.assertEqual(self.ids(*navigator.follow("$dff")), ["s0007"])
        self.assertEqual(navigator.follow("nope"), [])
        self.assertEqual(navigator.current().id, "s0007")

    def test_back_after_jump(self) -> None:
        navigator = Navigator(self.trace)
        self.assertEqual(navigator.jump_stage(2).id, "s0008")
        self.assertEqual(navigator.back().id, "s0001")
        self.assertEqual(navigator.back().id, "s0001")


if __name__ == "__main__":
    unittest.main()
