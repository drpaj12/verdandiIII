"""IR and AST snapshot tests against the Odin III binding (skipped without the library)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import odin3

from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from tests.micros import COUNTER2, IFELSE_REG, Micro
from verdandi.odin3 import ast_snapshot, ir_snapshot, keep_all_asts, node_count


def write_micro(micro: Micro, directory: Path) -> Path:
    """Write the micro's text to <directory>/<top>.v and return the path."""
    top, text = micro
    path = directory / f"{top}.v"
    path.write_text(text, encoding="utf-8")
    return path


def techlib() -> Path | None:
    """The LPM tech library the recorder reads first, when the Odin III tree is around."""
    if ODIN3_ROOT is None:
        return None
    path = ODIN3_ROOT / "lib" / "lpm.o3lib"
    return path if path.is_file() else None


def read_design(path: Path, *passes: str, keep_asts: bool = False) -> odin3.Design:
    """A design that read the Verilog at path, then ran each pass in order."""
    design = odin3.Design()
    if keep_asts:
        keep_all_asts(design)
    library = techlib()
    if library is not None:
        design.run_pass("read_techlib", f'"{library}"')
    design.run_pass("read_verilog", f'"{path}"')
    for name in passes:
        design.run_pass(name)
    return design


@unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
class SnapshotTest(unittest.TestCase):
    def test_counter_snapshot(self) -> None:
        top, text = COUNTER2
        always_line = next(
            number for number, line in enumerate(text.splitlines(), 1) if "always" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(COUNTER2, Path(tmp)), "proc")
            self.addCleanup(design.close)
            snapshot = ir_snapshot(design)
        self.assertEqual(snapshot["kind"], "ir")
        self.assertEqual([module["name"] for module in snapshot["modules"]], [top])
        nodes = snapshot["modules"][0]["nodes"]
        dffs = [node for node in nodes if node["type"] == "$dff"]
        self.assertTrue(dffs, "no $dff after proc")
        self.assertTrue(
            any(source[1] == always_line for node in dffs for source in node["sources"]),
            f"no $dff source on the always line {always_line}",
        )
        self.assertEqual(node_count(snapshot), len(nodes))

    def test_snapshot_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(IFELSE_REG, Path(tmp)), "proc")
            self.addCleanup(design.close)
            first = json.dumps(ir_snapshot(design), sort_keys=True, indent=1)
            second = json.dumps(ir_snapshot(design), sort_keys=True, indent=1)
        self.assertEqual(first, second)

    def test_dead_objects_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(COUNTER2, Path(tmp)), "proc", "opt", "opt_clean")
            self.addCleanup(design.close)
            snapshot = ir_snapshot(design)
            listed = 0
            dead = 0
            for module_snapshot in snapshot["modules"]:
                module = design.module(module_snapshot["name"])
                if module is None:
                    self.fail(f"{module_snapshot['name']}: not in the design")
                highest = 0
                for node in module_snapshot["nodes"]:
                    self.assertTrue(
                        odin3.Node(design, module.id, node["id"]).is_live,
                        f"node {node['id']} is listed but not live",
                    )
                    listed += 1
                    highest = max(highest, node["id"])
                dead += sum(
                    1
                    for ident in range(1, highest)
                    if not odin3.Node(design, module.id, ident).is_live
                )
        self.assertGreater(listed, 0)
        self.assertGreater(dead, 0, "opt_clean freed no slots: the skip is untested")

    def test_ast_forms(self) -> None:
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(COUNTER2, Path(tmp)), keep_asts=True)
            self.addCleanup(design.close)
            parsed = ast_snapshot(design, "PARSED")
            elaborated = ast_snapshot(design, "ELABORATED")
        self.assertIsNotNone(parsed)
        self.assertIsNotNone(elaborated)
        assert parsed is not None
        assert elaborated is not None
        self.assertEqual(parsed["kind"], "ast")
        self.assertEqual(parsed["form"], "PARSED")
        self.assertEqual(elaborated["form"], "ELABORATED")
        self.assertIn(top, [root["name"] for root in elaborated["roots"]])
        self.assertGreater(node_count(parsed), 0)
        self.assertGreater(node_count(elaborated), 0)
