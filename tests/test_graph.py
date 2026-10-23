"""Graph slice tests: the touched nodes and one ring, labelled nets, the diff's colours."""

from __future__ import annotations

import copy
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

    def test_net_label_on_edge(self) -> None:
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 1, "a")],
            by_name=False,
        )
        dot = slice_dot(SNAPSHOT, diff)
        self.assertIn('label="n1"', dot)

    def test_net_labels_hidden(self) -> None:
        """The toggle drops the edge labels and keeps the edges themselves."""
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 1, "a")],
            by_name=False,
        )
        dot = slice_dot(SNAPSHOT, diff, show_net_names=False)
        self.assertNotIn('label="n1"', dot)
        self.assertIn('"counter2:1" -> "counter2:2"', dot)

    def test_unnamed_net_labelled_by_id(self) -> None:
        """An internal net has no name; its edge still carries net <id>."""
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot["modules"][0]["nets"].append(
            {"id": 12, "name": "", "drivers": [3], "sinks": [4], "sources": []}
        )
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 3, "c")],
            by_name=False,
        )
        dot = slice_dot(snapshot, diff)
        self.assertIn('"counter2:3" -> "counter2:4" [label="net 12"]', dot)

    def test_named_nodes_fallback_to_key(self) -> None:
        """An unnamed IR node is labelled by its key, so no graph node is blank."""
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot["modules"][0]["nodes"][0]["name"] = ""
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 1, "")],
            by_name=False,
        )
        dot = slice_dot(snapshot, diff)
        self.assertIn('[label="counter2:1"]', dot)


if __name__ == "__main__":
    unittest.main()
