"""L3 event tests: the per-pass DEBUG log lines, parsed into events.

The opt_expr test needs the odin3 binding, the library and the LPM tech library; the unknown
pass test is pure.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import verdandi.odin3.events as events_module
from tests.helpers import HAVE_ODIN3
from tests.micros import AND_ZERO
from tests.test_record import techlib, write_micro
from verdandi.odin3.events import events


class ExcludedFormatsTest(unittest.TestCase):
    def test_object_naming_formats_left_out_are_documented(self) -> None:
        source = Path(events_module.__file__).read_text(encoding="utf-8")
        # Two DEBUG formats that name an object still get no pattern; the list says why.
        self.assertIn("exchange.c:66", source)
        self.assertIn("write_formats.c:235", source)


class EventsTest(unittest.TestCase):
    def test_events_unknown_pass(self) -> None:
        self.assertEqual(events("nope", ["x"]), [])

    @unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
    def test_events_opt_expr(self) -> None:
        import odin3

        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(AND_ZERO, Path(tmp))
            design = odin3.Design(odin3.default())
            try:
                design.run_pass("read_techlib", str(library))
                design.run_pass("read_verilog", f'--nolatches --vtr-compat "{source}"')
                design.run_pass("proc", "")
                with design.odin3.capture_log() as records:
                    design.odin3.call(
                        "odin3_log_set_level", design.odin3.lib.ODIN3_LOG_DEBUG
                    )
                    design.run_pass("opt_expr", "")
            finally:
                design.close()
        found = events("opt_expr", [record.message for record in records])
        anchors = [anchor for _title, anchor in found]
        self.assertTrue(
            any(anchor.startswith("rule:opt_expr:") for anchor in anchors), anchors
        )
        self.assertTrue(
            any(title.startswith("opt_expr: ") for title, _anchor in found), found
        )


if __name__ == "__main__":
    unittest.main()
