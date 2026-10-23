"""The text of a snapshot slice as a Graphviz dot digraph (spec 7, plan Task 11).

Pure: no Qt and no Graphviz call. A node is keyed by ``(module, id)``; two nodes are neighbours
when one net connects them (any pin of the one to any pin of the other). The slice is the diff's
touched nodes plus ``rings`` rings of neighbours; only nets with both ends inside the slice become
edges, so the picture shows the touched objects and their immediate wiring. The Data pane renders
this text with ``dot -Tsvg`` when Graphviz is installed.
"""

from __future__ import annotations

from typing import Any

from verdandi.trace import Diff

NodeKey = tuple[str, int]
Edge = tuple[NodeKey, NodeKey, str]


def _quote(text: str) -> str:
    """A double-quoted dot string with backslashes and quotes escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _module_parts(
    module: dict[str, Any],
) -> tuple[
    dict[NodeKey, str],
    dict[NodeKey, set[NodeKey]],
    set[Edge],
    dict[NodeKey, set[NodeKey]],
]:
    """One module's node names, adjacency, drawing edges and each net's connected nodes.

    Adjacency is undirected (every pair of pins on the same net); an edge is directed driver to
    sink and carries the net name. A pin naming a node outside the module is skipped, as the
    recorder's snapshot never holds one.
    """
    name = str(module.get("name", ""))
    names: dict[NodeKey, str] = {}
    for node in module.get("nodes", []):
        names[(name, int(node["id"]))] = str(node.get("name", ""))
    neighbours: dict[NodeKey, set[NodeKey]] = {key: set() for key in names}
    edges: set[Edge] = set()
    ends_by_net: dict[NodeKey, set[NodeKey]] = {}
    for net in module.get("nets", []):
        drivers = [
            key for key in ((name, int(ident)) for ident in net.get("drivers", [])) if key in names
        ]
        sinks = [
            key for key in ((name, int(ident)) for ident in net.get("sinks", [])) if key in names
        ]
        net_name = str(net.get("name", ""))
        ends = drivers + sinks
        for index, first in enumerate(ends):
            for second in ends[index + 1 :]:
                neighbours[first].add(second)
                neighbours[second].add(first)
        for driver in drivers:
            for sink in sinks:
                edges.add((driver, sink, net_name))
        ends_by_net[(name, int(net["id"]))] = set(ends)
    return names, neighbours, edges, ends_by_net


def slice_dot(snapshot: dict[str, Any], diff: Diff, rings: int = 1) -> str:
    """The dot digraph of the diff's touched nodes plus ``rings`` rings of neighbours.

    A ``node`` ref is itself; a ``net`` ref contributes its connected nodes (the endpoints are
    what the picture can draw); a ``wire`` ref has no graph connections. Deterministic: node
    lines sorted by ``(module, id)`` and edges by their three fields.
    """
    if snapshot.get("kind") != "ir":
        raise ValueError("slice_dot: only an IR snapshot has a graph")
    names: dict[NodeKey, str] = {}
    neighbours: dict[NodeKey, set[NodeKey]] = {}
    edges: set[Edge] = set()
    ends_by_net: dict[NodeKey, set[NodeKey]] = {}
    for module in snapshot.get("modules", []):
        module_names, module_neighbours, module_edges, module_ends = _module_parts(module)
        names.update(module_names)
        neighbours.update(module_neighbours)
        edges |= module_edges
        ends_by_net.update(module_ends)
    touched: set[NodeKey] = set()
    for ref in (*diff.added, *diff.removed, *diff.changed):
        key = (ref.module, ref.id)
        if ref.kind == "node" and key in names:
            touched.add(key)
        elif ref.kind == "net":
            touched |= ends_by_net.get(key, set())
    for _ in range(max(0, rings)):
        grown = set(touched)
        for key in touched:
            grown |= neighbours.get(key, set())
        touched = grown
    lines = ["digraph slice {"]
    for key in sorted(touched):
        lines.append(f"  {_quote(f'{key[0]}:{key[1]}')} [label={_quote(names[key])}];")
    for driver, sink, net_name in sorted(edges):
        if driver in touched and sink in touched:
            lines.append(
                f"  {_quote(f'{driver[0]}:{driver[1]}')} -> "
                f"{_quote(f'{sink[0]}:{sink[1]}')} [label={_quote(net_name)}];"
            )
    lines.append("}")
    return "\n".join(lines) + "\n"
