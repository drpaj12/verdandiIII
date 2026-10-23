"""The Data pane: snapshot tables, an AST tree, a symbol table and the dot-rendered slice.

An IR step shows the touched nodes and nets in tables (the "all objects" box shows everything)
and, when Graphviz is on PATH, a picture of the slice whose edges carry the net names. An AST
step shows its tree and the symbol table derived from it. A step with an ABC picture renders
that instead. A structure badge names what the pane shows: "IR after <pass> (netlist)",
"AST (parsed)" / "AST (elaborated)", "ABC network (picture)" or "symbol table". Without ``dot``
the pane keeps its tables and shows no picture, and never raises.
"""

from __future__ import annotations

import json
import subprocess
from shutil import which
from typing import Any

from PySide6.QtCore import QByteArray
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdandi.graph import slice_dot
from verdandi.gui.explainpane import pass_name
from verdandi.symtab import symbol_rows
from verdandi.trace import Diff, Step, Trace

NODE_HEADERS = ("ID", "Name", "Type", "Params")
NET_HEADERS = ("ID", "Name", "Drivers", "Sinks")
SYMBOL_HEADERS = ("Module", "Name", "Declaration", "Uses")
NO_STRUCTURE = "log event (no snapshot)"


def structure_name(step: Step, snapshot: dict[str, Any]) -> str:
    """The badge naming the structure the step's snapshot shows (D3)."""
    kind = snapshot.get("kind")
    if kind == "ast":
        form = str(snapshot.get("form", "")).lower()
        return f"AST ({form})" if form else "AST"
    if kind == "ir":
        return f"IR after {pass_name(step.anchor) or step.title} (netlist)"
    return f"unknown structure ({kind})"


def render_dot(dot_text: str) -> bytes | None:
    """The SVG Graphviz draws for ``dot_text``; None without ``dot`` or on any failure."""
    executable = which("dot")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "-Tsvg"],
            input=dot_text.encode("utf-8"),
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def touched_ids(diff: Diff | None) -> dict[str, set[tuple[str, int]]]:
    """The diff's objects as kind -> {(module, id)}; every kind present, maybe empty."""
    found: dict[str, set[tuple[str, int]]] = {"node": set(), "net": set(), "wire": set()}
    if diff is None:
        return found
    for ref in (*diff.added, *diff.removed, *diff.changed):
        found.setdefault(ref.kind, set()).add((ref.module, ref.id))
    return found


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    return table


def _set_row(table: QTableWidget, values: tuple[Any, ...]) -> None:
    row = table.rowCount()
    table.insertRow(row)
    for column, value in enumerate(values):
        table.setItem(row, column, QTableWidgetItem(str(value)))


class DataPane:
    """The step's snapshot: nodes and nets tables, AST tree, symbol table, graph picture."""

    def __init__(self) -> None:
        self.widget = QWidget()
        self.badge = QLabel()
        self.badge.setObjectName("structure-badge")
        self.badge.setWordWrap(True)
        self.all_box = QCheckBox("all objects")
        self.net_names_box = QCheckBox("net names")
        self.net_names_box.setChecked(True)
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.all_box)
        controls_layout.addWidget(self.net_names_box)
        self.tabs = QTabWidget()
        self.node_table = _table(NODE_HEADERS)
        self.net_table = _table(NET_HEADERS)
        self.ast_tree = QTreeWidget()
        self.ast_tree.setHeaderLabel("AST")
        self.symbol_table = _table(SYMBOL_HEADERS)
        self.svg = QSvgWidget()
        self._graph_page = QWidget()
        graph_layout = QVBoxLayout(self._graph_page)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.svg)
        self.tabs.addTab(self.node_table, "Nodes")
        self.tabs.addTab(self.net_table, "Nets")
        self.tabs.addTab(self.ast_tree, "AST")
        self.tabs.addTab(self.symbol_table, "Symbols")
        self.tabs.addTab(self._graph_page, "Graph")
        layout = QVBoxLayout(self.widget)
        layout.addWidget(self.badge)
        layout.addWidget(controls)
        layout.addWidget(self.tabs, 1)
        self._step: Step | None = None
        self._trace: Trace | None = None
        self._structure = NO_STRUCTURE
        self.all_box.toggled.connect(self._rerender)
        self.net_names_box.toggled.connect(self._rerender)
        self.tabs.currentChanged.connect(self._sync_badge)

    def show(self, step: Step, trace: Trace) -> None:
        self._step = step
        self._trace = trace
        self._render()

    def has_graph(self) -> bool:
        """True when the Graph tab holds a picture for the current step."""
        return self.tabs.isTabVisible(self.tabs.indexOf(self._graph_page))

    def _rerender(self, _checked: bool = False) -> None:
        self._render()

    def _render(self) -> None:
        if self._step is None or self._trace is None:
            return
        self.node_table.setRowCount(0)
        self.net_table.setRowCount(0)
        self.ast_tree.clear()
        self.symbol_table.setRowCount(0)
        self._set_tabs(nodes=False, nets=False, ast=False, symbols=False, graph=False)
        self._structure = NO_STRUCTURE
        if self._step.picture is not None:
            self._structure = "ABC network (picture)"
            if self._render_picture(self._step.picture):
                self._set_tabs(nodes=False, nets=False, ast=False, symbols=False, graph=True)
                self.tabs.setCurrentWidget(self._graph_page)
        snapshot = self._trace.snapshot(self._step)
        if snapshot is None:
            self._sync_badge()
            return
        kind = snapshot.get("kind")
        if kind == "ir":
            self._structure = structure_name(self._step, snapshot)
            self._fill_tables(snapshot, self._step.diff)
            graph = self._render_slice(snapshot, self._step.diff)
            self._set_tabs(nodes=True, nets=True, ast=False, symbols=False, graph=graph)
            self.tabs.setCurrentWidget(self.node_table)
        elif kind == "ast":
            self._structure = structure_name(self._step, snapshot)
            self._fill_ast(snapshot)
            self._fill_symbols(snapshot)
            self._set_tabs(nodes=False, nets=False, ast=True, symbols=True, graph=False)
            self.tabs.setCurrentWidget(self.ast_tree)
        self._sync_badge()

    def _sync_badge(self, _index: int = -1) -> None:
        """The badge names the structure shown; the symbol table names itself (D3)."""
        if self.tabs.currentWidget() is self.symbol_table:
            self.badge.setText("symbol table")
        else:
            self.badge.setText(self._structure)

    def _set_tabs(
        self, *, nodes: bool, nets: bool, ast: bool, symbols: bool, graph: bool
    ) -> None:
        for page, visible in (
            (self.node_table, nodes),
            (self.net_table, nets),
            (self.ast_tree, ast),
            (self.symbol_table, symbols),
            (self._graph_page, graph),
        ):
            self.tabs.setTabVisible(self.tabs.indexOf(page), visible)

    def _fill_tables(self, snapshot: dict[str, Any], diff: Diff | None) -> None:
        touched = touched_ids(diff)
        show_all = self.all_box.isChecked() or diff is None
        for module in snapshot.get("modules", []):
            name = str(module.get("name", ""))
            for node in module.get("nodes", []):
                if not show_all and (name, int(node["id"])) not in touched["node"]:
                    continue
                params = json.dumps(node.get("params", {}), sort_keys=True)
                _set_row(
                    self.node_table,
                    (node["id"], node.get("name", ""), node.get("type", ""), params),
                )
            for net in module.get("nets", []):
                if not show_all and (name, int(net["id"])) not in touched["net"]:
                    continue
                drivers = ", ".join(str(ident) for ident in net.get("drivers", []))
                sinks = ", ".join(str(ident) for ident in net.get("sinks", []))
                _set_row(self.net_table, (net["id"], net.get("name", ""), drivers, sinks))

    def _fill_ast(self, snapshot: dict[str, Any]) -> None:
        roots = snapshot.get("roots", [])
        stack: list[tuple[dict[str, Any], QTreeWidgetItem | None]] = [
            (node, None) for node in reversed(roots)
        ]
        while stack:
            node, parent = stack.pop()
            label = str(node.get("name") or node.get("kind", ""))
            item = QTreeWidgetItem([label])
            if parent is None:
                self.ast_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in reversed(node.get("children", [])):
                stack.append((child, item))

    def _fill_symbols(self, snapshot: dict[str, Any]) -> None:
        for symbol in symbol_rows(snapshot):
            uses = "; ".join(symbol.uses) if symbol.uses else "-"
            _set_row(
                self.symbol_table,
                (symbol.module, symbol.name, symbol.declaration, uses),
            )

    def _render_slice(self, snapshot: dict[str, Any], diff: Diff | None) -> bool:
        """Load the slice picture; True when the Graph tab holds one."""
        if diff is None or not (diff.added or diff.removed or diff.changed):
            return False
        svg = render_dot(
            slice_dot(snapshot, diff, show_net_names=self.net_names_box.isChecked())
        )
        if svg is None:
            return False
        self.svg.load(QByteArray(svg))
        return True

    def _render_picture(self, name: str) -> bool:
        """Load an ABC picture; True when the Graph tab holds one."""
        if self._trace is None:
            return False
        path = self._trace.directory / "pic" / name
        if not path.is_file():
            return False
        svg = render_dot(path.read_text(encoding="utf-8"))
        if svg is None:
            return False
        self.svg.load(QByteArray(svg))
        return True
