"""Code locator tests on a fixture tree and on the real Odin III source tree."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.helpers import ODIN3_ROOT
from verdandi.odin3.locator import Locator

FIXTURE = Path(__file__).resolve().parent / "fixture_src"
DEMO = Path("src/passes/demo/demo.c")
DEMO_LOG = "demo: module '%s': %s on %s '%s'"


class FixtureLocatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.locator = Locator(FIXTURE)

    def test_fixture_pass_found(self) -> None:
        self.assertEqual(self.locator.pass_files("demo"), [DEMO])

    def test_functions_spans(self) -> None:
        refs = self.locator.functions(DEMO)
        self.assertEqual(
            [(ref.file, ref.function, ref.line, ref.end_line) for ref in refs],
            [
                (str(DEMO), "demo_helper", 3, 5),
                (str(DEMO), "demo_pass_run", 12, 20),
            ],
        )

    def test_find_text(self) -> None:
        refs = self.locator.find_text(self.locator.pass_files("demo"), DEMO_LOG)
        self.assertEqual(
            [(ref.file, ref.function, ref.line, ref.end_line) for ref in refs],
            [(str(DEMO), "demo_pass_run", 14, 14)],
        )

    def test_locator_without_root(self) -> None:
        locator = Locator(None)
        self.assertEqual(locator.pass_files("demo"), [])
        self.assertEqual(locator.functions(DEMO), [])
        self.assertEqual(locator.find_text([DEMO], DEMO_LOG), [])
        self.assertEqual(locator.commit(), "unknown")


@unittest.skipUnless(ODIN3_ROOT is not None, "ODIN3_ROOT is not set")
class RealTreeLocatorTest(unittest.TestCase):
    def test_real_tree(self) -> None:
        assert ODIN3_ROOT is not None
        locator = Locator(ODIN3_ROOT)
        self.assertIn(Path("src/passes/proc/proc_pass.c"), locator.pass_files("proc"))
        self.assertIn(Path("src/passes/partial_map/register.c"), locator.pass_files("hardmap"))
        self.assertTrue(locator.pass_files("read_verilog"))

    def test_real_tree_opt_family_pass_files(self) -> None:
        assert ODIN3_ROOT is not None
        locator = Locator(ODIN3_ROOT)
        expected = sorted(
            path.relative_to(ODIN3_ROOT) for path in (ODIN3_ROOT / "src/passes/opt").glob("*.c")
        )
        self.assertEqual(len(expected), 34)
        self.assertEqual(locator.pass_files("opt"), expected)
        self.assertEqual(locator.pass_files("wreduce"), expected)

    def test_real_tree_find_text_opt_expr(self) -> None:
        assert ODIN3_ROOT is not None
        locator = Locator(ODIN3_ROOT)
        refs = locator.find_text(
            locator.pass_files("opt"), "opt_expr: module '%s': %s on %s '%s'"
        )
        self.assertIn(("src/passes/opt/expr.c", 322), [(ref.file, ref.line) for ref in refs])


if __name__ == "__main__":
    unittest.main()
