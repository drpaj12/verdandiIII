"""IR and AST snapshots of an Odin III design, as JSON-ready dicts.

A snapshot is deterministic: the binding yields modules in creation order and objects in ID
order, live objects only, so equal designs give equal dicts and
``json.dumps(snapshot, sort_keys=True, indent=1)`` gives byte-identical text. Timestamps are
not part of a snapshot (they live only in ``manifest.json``).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import odin3

_FORMS = ("PARSED", "ELABORATED")


def _source_rows(item: odin3.Node | odin3.Net) -> list[list[Any]]:
    """The object's provenance as [file, line, col, end_line, end_col] rows."""
    return [[s.file, s.line, s.col, s.end_line, s.end_col] for s in item.sources()]


def _node_ids(pins: list[odin3.Pin]) -> list[int]:
    """The IDs of the nodes the pins belong to, in pin order, each ID once."""
    seen: set[int] = set()
    ids: list[int] = []
    for pin in pins:
        ident = pin.node().id
        if ident not in seen:
            seen.add(ident)
            ids.append(ident)
    return ids


def _node_params(node: odin3.Node) -> dict[str, int | str]:
    """The node's parameters, PROC-kind values skipped (spec 5, snapshots).

    A PROC value is a $proc's whole RTLIL body: unbounded text that the node-count size guard
    cannot bound, so it stays out of the snapshot. params() lists names and values together in
    parameter order, which is the order param_kind indexes into.
    """
    params = node.params()
    return {
        name: value
        for index, (name, value) in enumerate(params.items())
        if node.param_kind(index) != "PROC"
    }


def _node_dict(node: odin3.Node) -> dict[str, Any]:
    pins = []
    for pin in node.pins():
        net = pin.net()
        pins.append({"port": pin.port, "bit": pin.bit, "net": None if net is None else net.id})
    return {
        "id": node.id,
        "name": node.name,
        "type": node.type_name,
        "params": _node_params(node),
        "pins": pins,
        "sources": _source_rows(node),
    }


def _net_dict(net: odin3.Net) -> dict[str, Any]:
    pins = net.pins()
    drivers = net.drivers()
    return {
        "id": net.id,
        "name": net.name,
        "drivers": _node_ids(drivers),
        "sinks": _node_ids(pins[len(drivers):]),
        "sources": _source_rows(net),
    }


def ir_snapshot(design: odin3.Design) -> dict[str, Any]:
    """The design's live IR: modules (creation order) with their nodes, nets and wires."""
    modules = [
        {
            "name": module.name,
            "nodes": [_node_dict(node) for node in module.nodes()],
            "nets": [_net_dict(net) for net in module.nets()],
            "wires": [{"id": wire.id, "name": wire.name} for wire in module.wires()],
        }
        for module in design.modules()
    ]
    return {"kind": "ir", "modules": modules}


def _ast_stores(design: odin3.Design) -> list[odin3.Ast]:
    """Every AST store the design holds, in the order it received them.

    The binding is imported here, not at module level, so this module (and the package) imports
    and test discovery skips, instead of raising, where odin3 is absent.
    """
    binding = importlib.import_module("odin3")
    count = int(design.get("odin3_design_get_ast_count", "uint32_t"))
    return [
        binding.Ast(design, design.get("odin3_design_get_ast_at", "odin3_ast *", index))
        for index in range(count)
    ]


def _ast_roots(ast: odin3.Ast) -> list[dict[str, Any]]:
    """The store's UNIT roots as nested dicts; an explicit stack, as the AST may be deep."""
    roots: list[dict[str, Any]] = []
    stack: list[tuple[odin3.AstNode, dict[str, Any]]] = []
    for root in ast.roots():
        out: dict[str, Any] = {
            "kind": root.kind,
            "sub": root.sub,
            "name": root.name,
            "loc": root.loc,
            "children": [],
        }
        roots.append(out)
        stack.append((root, out))
    while stack:
        node, out = stack.pop()
        for child in node.children():
            child_out: dict[str, Any] = {
                "kind": child.kind,
                "sub": child.sub,
                "name": child.name,
                "loc": child.loc,
                "children": [],
            }
            out["children"].append(child_out)
            stack.append((child, child_out))
    return roots


def ast_snapshot(design: odin3.Design, form: str) -> dict[str, Any] | None:
    """The AST of the latest read run in form "PARSED" or "ELABORATED", else None.

    Design.ast() returns the newest store, which is the elaborated one when both were kept;
    walk odin3_design_get_ast_at by index instead, and match the store's run and form.
    """
    wanted = form.upper()
    if wanted not in _FORMS:
        raise ValueError(f"ast_snapshot: form must be one of {_FORMS}, not {form!r}")
    stores = _ast_stores(design)
    if not stores:
        return None
    latest = max(store.run for store in stores)
    for store in stores:
        if store.run == latest and store.form.upper() == wanted:
            return {"kind": "ast", "form": wanted, "roots": _ast_roots(store)}
    return None


def node_count(snapshot: dict[str, Any]) -> int:
    """The snapshot's size in nodes: IR nodes, or every AST node (roots included)."""
    kind = snapshot.get("kind")
    if kind == "ir":
        return sum(len(module["nodes"]) for module in snapshot.get("modules", []))
    if kind == "ast":
        total = 0
        stack = list(snapshot.get("roots", []))
        while stack:
            node = stack.pop()
            total += 1
            stack.extend(node["children"])
        return total
    raise ValueError(f"node_count: unknown snapshot kind {kind!r}")


def keep_all_asts(design: odin3.Design) -> None:
    """Keep both the PARSED and the ELABORATED store at the end of every later read run.

    The library's default (ODIN3_KEEP_AST_NONE) drops a read's stores when it ends, so the
    PARSED form is gone before ast_snapshot can walk it. The Python binding has no dedicated
    method for odin3_design_set_keep_ast, so call the ABI through Design.call with the
    library's ODIN3_KEEP_AST_ALL constant (present in the 1.0.0 wheel and the source build).
    """
    design.call("odin3_design_set_keep_ast", design.odin3.lib.ODIN3_KEEP_AST_ALL)
