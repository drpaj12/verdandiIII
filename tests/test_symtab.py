"""Symbol table tests: declared names and their uses, derived from an AST snapshot."""

from __future__ import annotations

import unittest
from typing import Any

from verdandi.symtab import Symbol, symbol_rows


def leaf(kind: str, name: str, loc: str, sub: str = "") -> dict[str, Any]:
    return {"kind": kind, "sub": sub, "name": name, "loc": loc, "children": []}


def module(name: str, loc: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "MODULE",
        "sub": "",
        "name": name,
        "loc": loc,
        "children": [
            {"kind": "LIST", "sub": "", "name": "", "loc": loc, "children": children}
        ],
    }


def ast(modules: list[dict[str, Any]], form: str = "ELABORATED") -> dict[str, Any]:
    return {
        "kind": "ast",
        "form": form,
        "roots": [
            {"kind": "UNIT", "sub": "", "name": "m.v", "loc": "m.v:1:1", "children": modules}
        ],
    }


def one_module() -> dict[str, Any]:
    """A module whose input clk is declared once and used twice."""
    port = {
        "kind": "PORT_DECL",
        "sub": "input",
        "name": "",
        "loc": "m.v:1:11",
        "children": [leaf("DECLARATOR", "clk", "m.v:1:17")],
    }
    assign = {
        "kind": "CONT_ASSIGN",
        "sub": "",
        "name": "",
        "loc": "m.v:2:1",
        "children": [
            leaf("IDENT", "clk", "m.v:2:11"),
            {"kind": "BINARY", "sub": "+", "name": "", "loc": "m.v:2:15", "children": [
                leaf("IDENT", "clk", "m.v:2:15")
            ]},
        ],
    }
    return module("m", "m.v:1:1", [port, assign])


class SymbolRowsTest(unittest.TestCase):
    def test_declarations_and_uses(self) -> None:
        rows = symbol_rows(ast([one_module()]))
        self.assertEqual(
            rows,
            [
                Symbol(
                    module="m",
                    name="clk",
                    declaration="m.v:1:17",
                    uses=("m.v:2:11", "m.v:2:15"),
                )
            ],
        )

    def test_instance_name_is_a_declaration(self) -> None:
        instance = {
            "kind": "INSTANTIATION",
            "sub": "",
            "name": "counter2",
            "loc": "m.v:3:3",
            "children": [leaf("INSTANCE", "count", "m.v:3:12")],
        }
        rows = symbol_rows(ast([module("m", "m.v:1:1", [instance])]))
        self.assertEqual(
            rows,
            [Symbol(module="m", name="count", declaration="m.v:3:12", uses=())],
        )

    def test_use_without_declaration_is_not_a_symbol(self) -> None:
        assign = {
            "kind": "CONT_ASSIGN",
            "sub": "",
            "name": "",
            "loc": "m.v:2:1",
            "children": [leaf("IDENT", "ghost", "m.v:2:11")],
        }
        rows = symbol_rows(ast([module("m", "m.v:1:1", [assign])]))
        self.assertEqual(rows, [])

    def test_scopes_are_separate_and_ordered(self) -> None:
        first = module("a", "m.v:1:1", [
            {"kind": "PORT_DECL", "sub": "input", "name": "", "loc": "m.v:1:11",
             "children": [leaf("DECLARATOR", "clk", "m.v:1:17")]},
        ])
        second = module("b", "m.v:4:1", [
            {"kind": "PORT_DECL", "sub": "input", "name": "", "loc": "m.v:4:11",
             "children": [leaf("DECLARATOR", "clk", "m.v:4:17")]},
        ])
        rows = symbol_rows(ast([first, second]))
        self.assertEqual(
            [(row.module, row.name, row.declaration) for row in rows],
            [("a", "clk", "m.v:1:17"), ("b", "clk", "m.v:4:17")],
        )

    def test_non_ast_snapshot_has_no_symbols(self) -> None:
        self.assertEqual(symbol_rows({"kind": "ir", "modules": []}), [])


if __name__ == "__main__":
    unittest.main()
