"""The text of a snapshot slice as a Graphviz dot digraph (spec 7, plan Task 11).

Pure: no Qt and no Graphviz call. A node is keyed by ``(module, id)``; two nodes are neighbours
when one net connects them (any pin of the one to any pin of the other). The slice is the diff's
touched nodes plus ``rings`` rings of neighbours; only nets with both ends inside the slice become
edges, so the picture shows the touched objects and their immediate wiring. Every edge carries a
net label: the core's net name when it reports one; otherwise the name the AST declares inside
the net's source span, suffixed with the module-qualified id (``clk [counter2:1]``); otherwise
``net <module>:<id>``. ``show_net_names=False`` drops the labels. An unnamed node is labelled by
its key.

The step diff is drawn in colour (D4): an added node green, a changed node amber, a removed
object (absent from the after snapshot, so it has no place in the graph) a dashed red node of its
own, labelled "removed <kind> <name>" so it cannot be mistaken for a live edge label; an added or
changed net colours its edge. The Data pane renders this text with ``dot -Tsvg`` when Graphviz is
installed.

Provenance (D5, D6): every drawn node carries a stable SVG element id ``vnd-<module>-<id>``, so
the Data pane's graph widget can hit-test a click against the node. With ``show_provenance`` the
node label gains a second, small line with its first source row's badge (the file's basename and
the line) and the node carries the full reference as a tooltip.
"""

from __future__ import annotations

from typing import Any

from verdandi.provenance import Loc, object_loc
from verdandi.symtab import symbol_rows
from verdandi.trace import Diff

NodeKey = tuple[str, int]
# Driver, sink, net name, net id.
Edge = tuple[NodeKey, NodeKey, str, int]
# The small provenance badge's font colour, shared by the data panes.
PROVENANCE_COLOR = "#57606a"

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


def node_element_id(module: str, node_id: int) -> str:
    """The SVG element id of a drawn node, for the graph's click hit test (D6)."""
    return f"vnd-{module}-{node_id}"


def node_locs(snapshot: dict[str, Any]) -> dict[NodeKey, Loc]:
    """Each IR node's first source row, keyed by ``(module, id)``; nodes without one are absent."""
    found: dict[NodeKey, Loc] = {}
    for module in snapshot.get("modules", []):
        name = str(module.get("name", ""))
        for node in module.get("nodes", []):
            loc = object_loc(node)
            if loc is not None:
                found[(name, int(node["id"]))] = loc
    return found


def _quote(text: str) -> str:
    """A double-quoted dot string with backslashes and quotes escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _html(text: str) -> str:
    """Text escaped for a Graphviz HTML-like label's text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _node_label(label: str, badge: str | None) -> str:
    """A node label: plain, or with the provenance badge as a second small line (D5)."""
    if badge is None:
        return _quote(label)
    return (
        "<<TABLE BORDER=\"0\" CELLBORDER=\"0\" CELLSPACING=\"0\">"
        f"<TR><TD>{_html(label)}</TD></TR>"
        f"<TR><TD><FONT POINT-SIZE=\"9\" COLOR=\"{PROVENANCE_COLOR}\">"
        f"{_html(badge)}</FONT></TD></TR></TABLE>>"
    )


def net_label(net_name: str, net_id: int, module: str, derived_name: str = "") -> str:
    """The edge label of a net: the core's name, else the AST name plus its qualified id.

    Odin III reports no name for the playthrough trace's nets, and net ids repeat per module, so
    the fallbacks carry the module: ``<declared name> [<module>:<id>]`` when the AST declares a
    name inside the net's source span, else ``net <module>:<id>``.
    """
    if net_name:
        return net_name
    if derived_name:
        return f"{derived_name} [{module}:{net_id}]"
    return f"net {module}:{net_id}"


def _ast_declarations(ast: dict[str, Any]) -> dict[str, list[tuple[str, int, int, str]]]:
    """Module -> (file, line, col, name) for each declaration the AST symbol table records."""
    found: dict[str, list[tuple[str, int, int, str]]] = {}
    for symbol in symbol_rows(ast):
        parts = symbol.declaration.rsplit(":", 2)
        if len(parts) != 3:
            continue
        file, line, col = parts
        try:
            position = (file, int(line), int(col))
        except ValueError:
            continue
        found.setdefault(symbol.module, []).append((*position, symbol.name))
    return found


def ast_net_names(
    snapshot: dict[str, Any], ast: dict[str, Any] | None
) -> dict[NodeKey, str]:
    """Each unnamed net's display name as the AST declares it, keyed by ``(module, id)``.

    A net's source span is the text the core locates it at. A DECLARATOR or INSTANCE whose
    ``file:line:col`` falls inside that span declares the net's name. A net with no declaration
    inside its spans, or with two different ones, gets no derived name.
    """
    if ast is None:
        return {}
    declarations = _ast_declarations(ast)
    names: dict[NodeKey, str] = {}
    for module in snapshot.get("modules", []):
        module_name = str(module.get("name", ""))
        module_declarations = declarations.get(module_name, [])
        for net in module.get("nets", []):
            if str(net.get("name", "")):
                continue
            found: set[str] = set()
            for source in net.get("sources", []):
                if len(source) < 5:
                    continue
                file = str(source[0])
                first_line, first_col = int(source[1]), int(source[2])
                last_line, last_col = int(source[3]), int(source[4])
                for decl_file, decl_line, decl_col, decl_name in module_declarations:
                    if decl_file != file:
                        continue
                    if not first_line <= decl_line <= last_line:
                        continue
                    if decl_line == first_line and decl_col < first_col:
                        continue
                    if decl_line == last_line and decl_col >= last_col:
                        continue
                    found.add(decl_name)
            if len(found) == 1:
                names[(module_name, int(net["id"]))] = found.pop()
    return names


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
        if ref.name:
            label = f"removed {ref.kind} {ref.name}"
        else:
            label = f"removed {ref.kind} {ref.module}:{ref.id}"
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
    snapshot: dict[str, Any],
    diff: Diff,
    rings: int = 1,
    *,
    show_net_names: bool = True,
    ast: dict[str, Any] | None = None,
    show_provenance: bool = False,
) -> str:
    """The dot digraph of the diff's touched nodes plus ``rings`` rings of neighbours.

    A ``node`` ref is itself; a ``net`` ref contributes its connected nodes (the endpoints are
    what the picture can draw); a ``wire`` ref has no graph connections. Every drawn edge is
    labelled with its net's name, or with the AST declaration name and module-qualified id, or
    ``net <module>:<id>`` when there is neither, unless ``show_net_names`` is false. ``ast`` is
    an AST snapshot whose declarations name unnamed nets. ``show_provenance`` adds each node's
    source line as a second, small label line and a tooltip. Every node carries an SVG element id
    whether or not its badge shows. Deterministic: node lines sorted by ``(module, id)`` and
    edges by their fields.
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
    derived_names = ast_net_names(snapshot, ast)
    locations = node_locs(snapshot)
    lines = ["digraph slice {"]
    for key in sorted(touched):
        label = names[key] or f"{key[0]}:{key[1]}"
        loc = locations.get(key)
        shown = loc if show_provenance else None
        attributes = [
            f"label={_node_label(label, None if shown is None else shown.badge)}",
            f"id={_quote(node_element_id(*key))}",
        ]
        kind = classes.get(key)
        if kind is not None:
            attributes.append(CLASS_STYLES[kind])
        if shown is not None:
            attributes.append(f"tooltip={_quote(shown.reference)}")
        lines.append(f"  {_quote(f'{key[0]}:{key[1]}')} [{', '.join(attributes)}];")
    lines.extend(_removed_lines(diff))
    for driver, sink, net_name, net_id in sorted(edges):
        if driver in touched and sink in touched:
            attributes = []
            if show_net_names:
                derived = derived_names.get((driver[0], net_id), "")
                attributes.append(
                    f"label={_quote(net_label(net_name, net_id, driver[0], derived))}"
                )
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
