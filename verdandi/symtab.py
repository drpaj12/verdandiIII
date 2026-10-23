"""The symbol table of an AST snapshot: each declared name and where it is used.

The trace has no separate symbol-table snapshot: Odin III's AST carries the declarations and the
references, so the table is derived from the AST of the parse and elaborate steps. A DECLARATOR
node (a port, wire or reg name) or an INSTANCE node (an instance name) declares a symbol; an
IDENT node uses one. Scope is the enclosing MODULE. Rows follow the declaration order of the AST
and uses follow their occurrence order, so the table is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_DECLARATIONS = ("DECLARATOR", "INSTANCE")
_USES = "IDENT"


@dataclass(frozen=True)
class Symbol:
    """One declared name: its scope, declaration location and use locations."""

    module: str
    name: str
    declaration: str
    uses: tuple[str, ...]


def symbol_rows(snapshot: dict[str, Any]) -> list[Symbol]:
    """The AST snapshot's symbols, module by module; an IR snapshot has none."""
    if snapshot.get("kind") != "ast":
        return []
    rows: list[Symbol] = []
    for module in _modules(snapshot.get("roots", [])):
        rows.extend(_module_symbols(module))
    return rows


def _modules(roots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every MODULE in the AST, in document order, without descending into a nested one."""
    modules: list[dict[str, Any]] = []
    stack = list(reversed(roots))
    while stack:
        node = stack.pop()
        if node.get("kind") == "MODULE":
            modules.append(node)
            continue
        stack.extend(reversed(node.get("children", [])))
    return modules


def _module_symbols(module: dict[str, Any]) -> list[Symbol]:
    """One module's symbols: its declarations in order, each with its uses in order."""
    nodes = _module_nodes(module)
    declarations: dict[str, str] = {}
    order: list[str] = []
    for node in nodes:
        if node.get("kind") not in _DECLARATIONS:
            continue
        name = str(node.get("name", ""))
        if name and name not in declarations:
            declarations[name] = str(node.get("loc", ""))
            order.append(name)
    uses: dict[str, list[str]] = {name: [] for name in order}
    for node in nodes:
        if node.get("kind") == _USES:
            name = str(node.get("name", ""))
            if name in uses:
                uses[name].append(str(node.get("loc", "")))
    scope = str(module.get("name", ""))
    return [
        Symbol(module=scope, name=name, declaration=declarations[name], uses=tuple(uses[name]))
        for name in order
    ]


def _module_nodes(module: dict[str, Any]) -> list[dict[str, Any]]:
    """The module's nodes in AST order, not descending into a nested MODULE (no Verilog nesting)."""
    nodes: list[dict[str, Any]] = []
    stack = [module]
    while stack:
        node = stack.pop()
        nodes.append(node)
        for child in reversed(node.get("children", [])):
            if child.get("kind") != "MODULE":
                stack.append(child)
    return nodes
