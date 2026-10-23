"""Graph slice tests: the dot text holds the touched nodes and one ring of neighbours."""

from __future__ import annotations

import unittest
from typing import Any

from verdandi.graph import slice_dot
from verdandi.trace import Diff, ObjRef

SNAPSHOT: dict[str, Any] = {
    "kind": "ir",
    "modules": [
        {
            "name": "counter2",
            "nodes": [
                {"id": 1, "name": "a", "type": "$dff", "params": {}, "pins": [], "sources": []},
                {"id": 2, "name": "b", "type": "$not", "params": {}, "pins": [], "sources": []},
                {"id": 3, "name": "c", "type": "$and", "params": {}, "pins": [], "sources": []},
                {"id": 4, "name": "d", "type": "$xor", "params": {}, "pins": [], "sources": []},
            ],
            "nets": [
                {"id": 10, "name": "n1", "drivers": [1], "sinks": [2], "sources": []},
                {"id": 11, "name": "n2", "drivers": [2], "sinks": [3], "sources": []},
            ],
            "wires": [],
        }
    ],
}


class SliceDotTest(unittest.TestCase):
    def test_slice_dot(self) -> None:
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 1, "a")],
            by_name=False,
        )
        dot = slice_dot(SNAPSHOT, diff)
        self.assertTrue(dot.startswith("digraph"))
        self.assertIn('"counter2:1"', dot)
        self.assertIn('"counter2:2"', dot)
        self.assertNotIn('"counter2:3"', dot)
        self.assertNotIn('"counter2:4"', dot)
        self.assertIn('"counter2:1" -> "counter2:2"', dot)


if __name__ == "__main__":
    unittest.main()
