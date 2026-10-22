"""IR and AST snapshot tests against the Odin III binding (skipped without the library)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from tests.micros import COUNTER2, IFELSE_REG, Micro
from verdandi.odin3 import ast_snapshot, ir_snapshot, keep_all_asts, node_count

if HAVE_ODIN3:
    import odin3

_ROOT = Path(__file__).resolve().parent.parent


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
    def assert_snapshot_complete(self, design: odin3.Design, snapshot: dict[str, Any]) -> None:
        """Assert the snapshot lists every live object the IR counts.

        Without this, a snapshot that silently dropped live objects would pass every other
        test here; the module's counts are the library's own live totals.
        """
        modules = snapshot["modules"]
        self.assertEqual(
            [module_snapshot["name"] for module_snapshot in modules],
            [module.name for module in design.modules()],
            "modules in the snapshot",
        )
        for module_snapshot in modules:
            module = design.module(module_snapshot["name"])
            self.assertIsNotNone(module, f"{module_snapshot['name']}: not in the design")
            assert module is not None
            self.assertEqual(
                len(module_snapshot["nodes"]), module.node_count(), f"{module.name}: nodes"
            )
            self.assertEqual(
                len(module_snapshot["nets"]), module.net_count(), f"{module.name}: nets"
            )
            self.assertEqual(
                len(module_snapshot["wires"]), module.wire_count(), f"{module.name}: wires"
            )

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
        self.assert_snapshot_complete(design, snapshot)
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
            self.assert_snapshot_complete(design, snapshot)
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

    def test_completeness_rejects_a_dropped_node(self) -> None:
        """The completeness assertion fails a snapshot that lost a live node."""
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(COUNTER2, Path(tmp)), "proc")
            self.addCleanup(design.close)
            snapshot = ir_snapshot(design)
        for module_snapshot in snapshot["modules"]:
            module_snapshot["nodes"].pop()
        with self.assertRaises(self.failureException):
            self.assert_snapshot_complete(design, snapshot)

    def test_proc_body_param_skipped(self) -> None:
        """A $proc's BODY (unbounded RTLIL text) is not embedded in the snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            design = read_design(write_micro(COUNTER2, Path(tmp)))  # pre-proc: $proc is live
            self.addCleanup(design.close)
            snapshot = ir_snapshot(design)
            proc_params = 0
            for module_snapshot in snapshot["modules"]:
                module = design.module(module_snapshot["name"])
                assert module is not None
                listed = {node["id"]: node["params"] for node in module_snapshot["nodes"]}
                for node in module.nodes():
                    params = node.params()
                    for index, name in enumerate(params):
                        if node.param_kind(index) == "PROC":
                            proc_params += 1
                            self.assertNotIn(
                                name, listed[node.id], f"node {node.id}: PROC param {name}"
                            )
        self.assertGreater(proc_params, 0, "no PROC param before proc: the skip is untested")

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


@unittest.skipIf(os.environ.get("VERDANDI_DISCOVERY_PROBE") == "1", "the probe's child")
class DiscoveryTest(unittest.TestCase):
    def test_discovery_skips_without_odin3(self) -> None:
        """Discovery with no odin3 on the path skips its tests; it does not raise.

        -S keeps site-packages (where the odin3 wheel lives) and PYTHONPATH is cleared, so the
        child sees the binding as absent, as a machine without the wheel does.
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "ODIN3_ROOT", "ODIN3_LIB")
        }
        env["VERDANDI_DISCOVERY_PROBE"] = "1"
        result = subprocess.run(
            [sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped=", result.stderr)
