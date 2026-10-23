"""The text of a snapshot slice as a Graphviz dot digraph (spec 7, plan Task 11).

Pure: no Qt and no Graphviz call. A node is keyed by ``(module, id)``; two nodes are neighbours
when one net connects them (any pin of the one to any pin of the other). The slice is the diff's
touched nodes plus ``rings`` rings of neighbours; only nets with both ends inside the slice become
edges, so the picture shows the touched objects and their immediate wiring. Every edge carries
its net's name as the label; an unnamed internal net is labelled ``net <id>``, and
``show_net_names=False`` drops the labels. An unnamed node is labelled by its key.

The step diff is drawn in colour (D4): an added node green, a changed node amber, a removed
object (absent from the after snapshot, so it has no place in the graph) a dashed red node of its
own; an added or changed net colours its edge. The Data pane renders this text with
``dot -Tsvg`` when Graphviz is installed.
"""

from __future__ import annotations

from typing import Any

from verdandi.trace import Diff

NodeKey = tuple[str, int]
# Driver, sink, net name, net id.
Edge = tuple[NodeKey, NodeKey, str, int]

# Node attributes per diff class, in the diff strip's colours (green, red, amber).
CLASS_STYLES = {
    "added": 'color="#1a7f37", fillcolor="#dafbe1", penwidth=2, style="filled"',
    "changed": 'color="#9a6700", fillcolor="#fff8c5", penwidth=2, style="filled"',
    "removed": 'color="#cf222e", penwidth=2, style="dashed"',
}

# Edge attributes per diff class: colour only, as a fill on an edge has no meaning.
EDGE_STYLES = {
    "added": 'color="#1a7f37", penwidth=2',
    "changed": 'color="#9a6700", penwidth=2',
}


def _quote(text: str) -> str:
    """A double-quoted dot string with backslashes and quotes escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def net_label(net_name: str, net_id: int) -> str:
    """The edge label of a net: its name, else ``net <id>`` for an unnamed internal net."""
    return net_name or f"net {net_id}"


def node_classes(diff: Diff) -> dict[NodeKey, str]:
    """The diff's added and changed nodes as key -> class, for the after snapshot's nodes.

    A removed node is not in the after snapshot, so it has no key here; it is drawn as its
    own dashed node instead.
    """
    classes: dict[NodeKey, str] = {}
    for name, refs in (("added", diff.added), ("changed", diff.changed)):
        for ref in refs:
            if ref.kind == "node":
                classes[(ref.module, ref.id)] = name
    return classes


def net_classes(diff: Diff) -> dict[NodeKey, str]:
    """The diff's added and changed nets as key -> class; a removed net is not drawn."""
    classes: dict[NodeKey, str] = {}
    for name, refs in (("added", diff.added), ("changed", diff.changed)):
        for ref in refs:
            if ref.kind == "net":
                classes[(ref.module, ref.id)] = name
    return classes


def _removed_lines(diff: Diff) -> list[str]:
    """The diff's removed objects as dashed red nodes, in key order.

    A removed object is absent from the after snapshot, so it has no place in the wiring; a
    node of its own still shows what the step removed.
    """
    found: list[tuple[str, str]] = []
    for ref in diff.removed:
        key = f"{ref.module}:{ref.kind}:{ref.id}"
        if ref.kind == "node":
            label = ref.name or f"{ref.module}:{ref.id}"
        else:
            label = f"{ref.kind} {ref.name}" if ref.name else f"{ref.kind} {ref.id}"
        found.append(
            (key, f"  {_quote(key)} [label={_quote(label)}, {CLASS_STYLES['removed']}];")
        )
    return [line for _, line in sorted(found)]


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
    sink and carries the net name and id. A pin naming a node outside the module is skipped, as
    the recorder's snapshot never holds one.
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
        net_id = int(net["id"])
        ends = drivers + sinks
        for index, first in enumerate(ends):
            for second in ends[index + 1 :]:
                neighbours[first].add(second)
                neighbours[second].add(first)
        for driver in drivers:
            for sink in sinks:
                edges.add((driver, sink, net_name, net_id))
        ends_by_net[(name, net_id)] = set(ends)
    return names, neighbours, edges, ends_by_net


def slice_dot(
    snapshot: dict[str, Any], diff: Diff, rings: int = 1, *, show_net_names: bool = True
) -> str:
    """The dot digraph of the diff's touched nodes plus ``rings`` rings of neighbours.

    A ``node`` ref is itself; a ``net`` ref contributes its connected nodes (the endpoints are
    what the picture can draw); a ``wire`` ref has no graph connections. Every drawn edge is
    labelled with its net's name, or ``net <id>`` when the net has none, unless
    ``show_net_names`` is false. Deterministic: node lines sorted by ``(module, id)`` and edges
    by their fields.
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
    classes = node_classes(diff)
    classes_by_net = net_classes(diff)
    lines = ["digraph slice {"]
    for key in sorted(touched):
        label = names[key] or f"{key[0]}:{key[1]}"
        attributes = [f"label={_quote(label)}"]
        kind = classes.get(key)
        if kind is not None:
            attributes.append(CLASS_STYLES[kind])
        lines.append(f"  {_quote(f'{key[0]}:{key[1]}')} [{', '.join(attributes)}];")
    lines.extend(_removed_lines(diff))
    for driver, sink, net_name, net_id in sorted(edges):
        if driver in touched and sink in touched:
            attributes = []
            if show_net_names:
                attributes.append(f"label={_quote(net_label(net_name, net_id))}")
            kind = classes_by_net.get((driver[0], net_id))
            if kind is not None:
                attributes.append(EDGE_STYLES[kind])
            suffix = f" [{', '.join(attributes)}]" if attributes else ""
            lines.append(
                f"  {_quote(f'{driver[0]}:{driver[1]}')} -> "
                f"{_quote(f'{sink[0]}:{sink[1]}')}{suffix};"
            )
    lines.append("}")
    return "\n".join(lines) + "\n"
