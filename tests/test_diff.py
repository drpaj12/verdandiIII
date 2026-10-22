"""Snapshot diff tests on hand-made IR snapshot dicts."""

from __future__ import annotations

import unittest
from typing import Any

from verdandi.diff import diff
from verdandi.trace import Diff, ObjRef


def node(
    ident: int,
    name: str,
    *,
    type_name: str = "$add",
    params: dict[str, Any] | None = None,
    pins: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": ident,
        "name": name,
        "type": type_name,
        "params": {} if params is None else params,
        "pins": [] if pins is None else pins,
        "sources": [],
    }


def net(
    ident: int,
    name: str,
    *,
    drivers: list[int] | None = None,
    sinks: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "id": ident,
        "name": name,
        "drivers": [] if drivers is None else drivers,
        "sinks": [] if sinks is None else sinks,
        "sources": [],
    }


def wire(ident: int, name: str) -> dict[str, Any]:
    return {"id": ident, "name": name}


def module(
    name: str,
    *,
    nodes: list[dict[str, Any]] | None = None,
    nets: list[dict[str, Any]] | None = None,
    wires: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "nodes": [] if nodes is None else nodes,
        "nets": [] if nets is None else nets,
        "wires": [] if wires is None else wires,
    }


def ir(*modules: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "ir", "modules": list(modules)}


class DiffTest(unittest.TestCase):
    def test_added_removed_changed(self) -> None:
        before = ir(
            module(
                "top",
                nodes=[node(1, "a"), node(2, "b", params={"WIDTH": "2"}), node(4, "d")],
            )
        )
        after = ir(
            module(
                "top",
                nodes=[
                    node(1, "a"),
                    node(2, "b", params={"WIDTH": "4"}),
                    node(3, "c", type_name="$mul"),
                ],
            )
        )
        self.assertEqual(
            diff(before, after),
            Diff(
                added=[ObjRef("top", "node", 3, "c")],
                removed=[ObjRef("top", "node", 4, "d")],
                changed=[ObjRef("top", "node", 2, "b")],
                by_name=False,
            ),
        )

    def test_changed_fields(self) -> None:
        before = ir(
            module(
                "top",
                nodes=[node(1, "pins", pins=[{"port": "A", "bit": 0, "net": 5}])],
                nets=[net(5, "n", drivers=[1], sinks=[])],
            )
        )
        after = ir(
            module(
                "top",
                nodes=[node(1, "pins", pins=[{"port": "A", "bit": 0, "net": 6}])],
                nets=[net(5, "n", drivers=[], sinks=[1])],
            )
        )
        self.assertEqual(
            diff(before, after).changed,
            [ObjRef("top", "node", 1, "pins"), ObjRef("top", "net", 5, "n")],
        )

    def test_each_changed_field_alone(self) -> None:
        cases = {
            "type": (
                ir(module("top", nodes=[node(1, "a")])),
                ir(module("top", nodes=[node(1, "a", type_name="$mul")])),
                ObjRef("top", "node", 1, "a"),
            ),
            "params": (
                ir(module("top", nodes=[node(1, "a")])),
                ir(module("top", nodes=[node(1, "a", params={"WIDTH": "2"})])),
                ObjRef("top", "node", 1, "a"),
            ),
            "pins": (
                ir(module("top", nodes=[node(1, "a")])),
                ir(module("top", nodes=[node(1, "a", pins=[{"port": "Y", "bit": 0, "net": 2}])])),
                ObjRef("top", "node", 1, "a"),
            ),
            "drivers": (
                ir(module("top", nets=[net(2, "n")])),
                ir(module("top", nets=[net(2, "n", drivers=[1])])),
                ObjRef("top", "net", 2, "n"),
            ),
            "sinks": (
                ir(module("top", nets=[net(2, "n")])),
                ir(module("top", nets=[net(2, "n", sinks=[1])])),
                ObjRef("top", "net", 2, "n"),
            ),
        }
        for field, (previous, following, expected) in cases.items():
            with self.subTest(field=field):
                self.assertEqual(diff(previous, following).changed, [expected])

    def test_diff_across_compact(self) -> None:
        before = ir(
            module(
                "top",
                nodes=[node(1, "a", pins=[{"port": "Y", "bit": 0, "net": 2}])],
                nets=[net(2, "n", drivers=[1])],
                wires=[wire(3, "w")],
            )
        )
        after = ir(
            module(
                "top",
                nodes=[node(10, "a", pins=[{"port": "Y", "bit": 0, "net": 11}])],
                nets=[net(11, "n", drivers=[10])],
                wires=[wire(12, "w")],
            )
        )
        result = diff(before, after, by_name=True)
        self.assertEqual(
            result,
            Diff(added=[], removed=[], changed=[], by_name=True),
        )

    def test_by_name_change_across_compact(self) -> None:
        before = ir(module("top", nodes=[node(1, "a")], nets=[net(2, "n", drivers=[1])]))
        after = ir(
            module(
                "top",
                nodes=[node(10, "a", params={"WIDTH": "4"})],
                nets=[net(11, "n", drivers=[10])],
            )
        )
        self.assertEqual(
            diff(before, after, by_name=True),
            Diff(
                added=[],
                removed=[],
                changed=[ObjRef("top", "node", 10, "a")],
                by_name=True,
            ),
        )

    def test_absent_field_matches_empty(self) -> None:
        sparse_node = node(1, "a")
        del sparse_node["params"]
        del sparse_node["pins"]
        sparse_net = net(2, "n")
        del sparse_net["drivers"]
        del sparse_net["sinks"]
        before = ir(module("top", nodes=[sparse_node], nets=[sparse_net]))
        after = ir(module("top", nodes=[node(1, "a")], nets=[net(2, "n")]))
        self.assertEqual(diff(before, after).changed, [])
        gained = ir(
            module("top", nodes=[node(1, "a", params={"WIDTH": "2"})], nets=[net(2, "n")])
        )
        self.assertEqual(diff(before, gained).changed, [ObjRef("top", "node", 1, "a")])

    def test_duplicate_keys_raise(self) -> None:
        duplicate_ids = ir(module("top", nodes=[node(1, "a"), node(1, "b")]))
        duplicate_names = ir(module("top", nodes=[node(1, "a"), node(2, "a")]))
        with self.assertRaises(ValueError):
            diff(duplicate_ids, ir())
        with self.assertRaises(ValueError):
            diff(ir(), duplicate_ids)
        with self.assertRaises(ValueError):
            diff(duplicate_names, duplicate_names, by_name=True)

    def test_empty_names_match_by_occurrence(self) -> None:
        # Odin III leaves internal cells and nets unnamed; by name they match in snapshot order.
        before = ir(
            module(
                "top",
                nodes=[node(1, ""), node(2, "")],
                nets=[net(3, ""), net(4, "")],
            )
        )
        after = ir(
            module(
                "top",
                nodes=[node(10, ""), node(11, "")],
                nets=[net(12, ""), net(13, "")],
            )
        )
        self.assertEqual(
            diff(before, after, by_name=True),
            Diff(added=[], removed=[], changed=[], by_name=True),
        )
        shorter = ir(
            module("top", nodes=[node(10, ""), node(11, "")], nets=[net(12, "")])
        )
        self.assertEqual(
            diff(before, shorter, by_name=True),
            Diff(
                added=[],
                removed=[ObjRef("top", "net", 4, "")],
                changed=[],
                by_name=True,
            ),
        )

    def test_empty_diff(self) -> None:
        snapshot = ir(
            module("top", nodes=[node(1, "a")], nets=[net(2, "n")], wires=[wire(3, "w")])
        )
        self.assertEqual(
            diff(snapshot, snapshot),
            Diff(added=[], removed=[], changed=[], by_name=False),
        )

    def test_none_before(self) -> None:
        after = ir(
            module("top", nodes=[node(1, "a")], nets=[net(2, "n", drivers=[1])],
                   wires=[wire(3, "w")])
        )
        self.assertEqual(
            diff(None, after),
            Diff(
                added=[
                    ObjRef("top", "node", 1, "a"),
                    ObjRef("top", "net", 2, "n"),
                    ObjRef("top", "wire", 3, "w"),
                ],
                removed=[],
                changed=[],
                by_name=False,
            ),
        )

    def test_empty_ir_sides_and_ast_before_ir_after(self) -> None:
        snapshot = ir(
            module(
                "top",
                nodes=[node(1, "a")],
                nets=[net(2, "n", drivers=[1])],
                wires=[wire(3, "w")],
            )
        )
        refs = [
            ObjRef("top", "node", 1, "a"),
            ObjRef("top", "net", 2, "n"),
            ObjRef("top", "wire", 3, "w"),
        ]
        self.assertEqual(
            diff(ir(), snapshot), Diff(added=refs, removed=[], changed=[], by_name=False)
        )
        self.assertEqual(
            diff(snapshot, ir()), Diff(added=[], removed=refs, changed=[], by_name=False)
        )
        ast = {"kind": "ast", "form": "PARSED", "roots": [{"kind": "module", "name": "top"}]}
        self.assertEqual(
            diff(ast, snapshot), Diff(added=[], removed=[], changed=[], by_name=False)
        )

    def test_ast_snapshots_diff_to_empty(self) -> None:
        ast = {"kind": "ast", "form": "PARSED", "roots": [{"kind": "module", "name": "top"}]}
        before = ir(module("top", nodes=[node(1, "a")]))
        empty = Diff(added=[], removed=[], changed=[], by_name=False)
        self.assertEqual(diff(None, ast), empty)
        self.assertEqual(diff(before, ast), empty)
