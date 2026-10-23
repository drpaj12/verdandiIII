"""Graph slice tests: the touched nodes and one ring, labelled nets, the diff's colours."""

from __future__ import annotations

import copy
import unittest
from typing import Any

from verdandi.graph import net_classes, node_classes, slice_dot
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

    def test_unnamed_net_labelled_by_qualified_id(self) -> None:
        """An unnamed net's edge carries net <module>:<id>, as net ids repeat per module."""
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
        self.assertIn('"counter2:3" -> "counter2:4" [label="net counter2:12"]', dot)

    def test_unnamed_net_named_from_the_ast(self) -> None:
        """A declaration inside the net's source span names the net, with its qualified id."""
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot["modules"][0]["nets"].append(
            {
                "id": 12,
                "name": "",
                "drivers": [3],
                "sinks": [4],
                "sources": [["m.v", 2, 3, 2, 12]],
            }
        )
        ast: dict[str, Any] = {
            "kind": "ast",
            "form": "ELABORATED",
            "roots": [
                {
                    "kind": "MODULE",
                    "sub": "",
                    "name": "counter2",
                    "loc": "m.v:1:1",
                    "children": [
                        {
                            "kind": "DECLARATOR",
                            "sub": "",
                            "name": "sum",
                            "loc": "m.v:2:7",
                            "children": [],
                        }
                    ],
                }
            ],
        }
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 3, "c")],
            by_name=False,
        )
        dot = slice_dot(snapshot, diff, ast=ast)
        self.assertIn(
            '"counter2:3" -> "counter2:4" [label="sum [counter2:12]"]', dot
        )

    def test_ast_name_outside_the_net_span_is_not_used(self) -> None:
        """A declaration on another line does not name the net; the qualified fallback stays."""
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot["modules"][0]["nets"].append(
            {
                "id": 12,
                "name": "",
                "drivers": [3],
                "sinks": [4],
                "sources": [["m.v", 2, 3, 2, 12]],
            }
        )
        ast: dict[str, Any] = {
            "kind": "ast",
            "form": "PARSED",
            "roots": [
                {
                    "kind": "MODULE",
                    "sub": "",
                    "name": "counter2",
                    "loc": "m.v:1:1",
                    "children": [
                        {
                            "kind": "DECLARATOR",
                            "sub": "",
                            "name": "sum",
                            "loc": "m.v:3:7",
                            "children": [],
                        }
                    ],
                }
            ],
        }
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 3, "c")],
            by_name=False,
        )
        dot = slice_dot(snapshot, diff, ast=ast)
        self.assertIn('label="net counter2:12"', dot)

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
        line = _node_line(dot, "counter2:1")
        self.assertIn('label="counter2:1"', line)

    def test_diff_classes(self) -> None:
        diff = Diff(
            added=[ObjRef("counter2", "node", 3, "c"), ObjRef("counter2", "net", 11, "n2")],
            removed=[ObjRef("counter2", "node", 4, "d")],
            changed=[ObjRef("counter2", "node", 1, "a")],
            by_name=False,
        )
        self.assertEqual(
            node_classes(diff), {("counter2", 3): "added", ("counter2", 1): "changed"}
        )
        self.assertEqual(net_classes(diff), {("counter2", 11): "added"})

    def test_added_node_is_solid_green(self) -> None:
        diff = Diff(
            added=[ObjRef("counter2", "node", 3, "c")],
            removed=[],
            changed=[],
            by_name=False,
        )
        line = _node_line(slice_dot(SNAPSHOT, diff), "counter2:3")
        self.assertIn('color="#1a7f37"', line)
        self.assertIn('style="filled"', line)

    def test_changed_node_is_amber(self) -> None:
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "node", 1, "a")],
            by_name=False,
        )
        line = _node_line(slice_dot(SNAPSHOT, diff), "counter2:1")
        self.assertIn('color="#9a6700"', line)

    def test_removed_node_is_a_dashed_red_node(self) -> None:
        """A removed node is not in the after snapshot, so it is drawn as its own node."""
        diff = Diff(
            added=[],
            removed=[ObjRef("counter2", "node", 4, "d")],
            changed=[],
            by_name=False,
        )
        line = _node_line(slice_dot(SNAPSHOT, diff), "counter2:node:4")
        self.assertIn('label="removed node d"', line)
        self.assertIn('color="#cf222e"', line)
        self.assertIn('style="dashed"', line)

    def test_removed_net_is_a_dashed_red_node(self) -> None:
        """A removed net's label is prefixed, so it cannot collide with a live edge label."""
        diff = Diff(
            added=[],
            removed=[ObjRef("counter2", "net", 11, "n2")],
            changed=[],
            by_name=False,
        )
        line = _node_line(slice_dot(SNAPSHOT, diff), "counter2:net:11")
        self.assertIn('label="removed net n2"', line)
        self.assertIn('style="dashed"', line)

    def test_removed_unnamed_object_is_qualified(self) -> None:
        """An unnamed removed object names its module-qualified id, not a bare id."""
        diff = Diff(
            added=[],
            removed=[ObjRef("counter2", "net", 11, "")],
            changed=[],
            by_name=False,
        )
        line = _node_line(slice_dot(SNAPSHOT, diff), "counter2:net:11")
        self.assertIn('label="removed net counter2:11"', line)

    def test_changed_net_colours_its_edge(self) -> None:
        diff = Diff(
            added=[],
            removed=[],
            changed=[ObjRef("counter2", "net", 10, "n1")],
            by_name=False,
        )
        dot = slice_dot(SNAPSHOT, diff)
        line = next(
            line for line in dot.splitlines() if '"counter2:1" -> "counter2:2"' in line
        )
        self.assertIn('label="n1"', line)
        self.assertIn('color="#9a6700"', line)

    def test_added_net_colours_its_edge_green(self) -> None:
        diff = Diff(
            added=[ObjRef("counter2", "net", 11, "n2")],
            removed=[],
            changed=[],
            by_name=False,
        )
        dot = slice_dot(SNAPSHOT, diff)
        line = next(
            line for line in dot.splitlines() if '"counter2:2" -> "counter2:3"' in line
        )
        self.assertIn('color="#1a7f37"', line)


def _node_line(dot: str, key: str) -> str:
    """The dot line that defines the node ``key``."""
    marker = f'"{key}" ['
    return next(line for line in dot.splitlines() if marker in line)


if __name__ == "__main__":
    unittest.main()
