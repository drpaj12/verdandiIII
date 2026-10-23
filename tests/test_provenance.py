"""Provenance loc tests: source rows, AST loc strings and their badges."""

from __future__ import annotations

import unittest

from verdandi.provenance import Loc, first_loc, loc_from_source_row, loc_from_text, object_loc


class SourceRowTest(unittest.TestCase):
    def test_source_row(self) -> None:
        loc = loc_from_source_row(["examples/m.v", 3, 7, 3, 12])
        assert loc is not None
        self.assertEqual(loc, Loc(file="examples/m.v", line=3, end_line=3))
        self.assertEqual(loc.badge, "m.v:3")
        self.assertEqual(loc.reference, "examples/m.v:3")

    def test_source_row_range(self) -> None:
        loc = loc_from_source_row(["examples/m.v", 3, 7, 5, 12])
        assert loc is not None
        self.assertEqual(loc.badge, "m.v:3-5")

    def test_source_row_without_an_end(self) -> None:
        """A row whose end line precedes its start line runs to the start line."""
        loc = loc_from_source_row(["m.v", 4, 1, 0, 0])
        assert loc is not None
        self.assertEqual(loc, Loc(file="m.v", line=4, end_line=4))

    def test_malformed_source_rows(self) -> None:
        for row in (
            None,
            [],
            ["m.v"],
            ["m.v", "x", 1, 1, 1],
            ["", 1, 1, 1, 1],
            ["m.v", 0, 1, 1, 1],
        ):
            self.assertIsNone(loc_from_source_row(row))


class LocTextTest(unittest.TestCase):
    def test_loc_text(self) -> None:
        loc = loc_from_text("examples/playthrough/playthrough.v:24:3")
        assert loc is not None
        self.assertEqual(loc.file, "examples/playthrough/playthrough.v")
        self.assertEqual(loc.line, 24)
        self.assertEqual(loc.end_line, 24)
        self.assertEqual(loc.badge, "playthrough.v:24")

    def test_malformed_loc_text(self) -> None:
        for text in (None, "", "m.v", "m.v:line:1", "m.v:0:1", "m.v:2"):
            self.assertIsNone(loc_from_text(text))


class ObjectLocTest(unittest.TestCase):
    def test_object_loc_skips_bad_rows(self) -> None:
        item = {"id": 1, "sources": [["m.v", "x", 1, 1, 1], ["m.v", 2, 3, 2, 6]]}
        loc = object_loc(item)
        assert loc is not None
        self.assertEqual(loc.badge, "m.v:2")

    def test_object_without_sources(self) -> None:
        self.assertIsNone(object_loc({"id": 1}))
        self.assertIsNone(object_loc({"id": 1, "sources": []}))

    def test_first_loc_of_a_list(self) -> None:
        loc = first_loc([["a.v", 1, 1, 1, 2], ["b.v", 2, 1, 2, 2]])
        assert loc is not None
        self.assertEqual(loc.badge, "a.v:1")
        self.assertIsNone(first_loc([]))
        self.assertIsNone(first_loc(None))


if __name__ == "__main__":
    unittest.main()
