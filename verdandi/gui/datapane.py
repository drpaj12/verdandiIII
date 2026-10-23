"""The Data pane: snapshot tables, an AST tree, a symbol table and the dot-rendered slice.

An IR step shows the touched nodes and nets in tables (the "all objects" box shows everything)
and, when Graphviz is on PATH, a picture of the slice whose edges carry the net labels. An AST
step shows its tree and the symbol table derived from it. A step with an ABC picture renders
that instead; without ``dot`` the badge stays "ABC network (picture)" and a note beside it says
the picture is unavailable. A structure badge names what the pane shows: "IR after <pass or
stage> (netlist)", "AST (parsed)" / "AST (elaborated)", "ABC network (picture)", "symbol table"
while that tab is visible, or "log event (no snapshot)". A re-render (a new step or a checkbox)
keeps the tab the user chose when that tab still shows, and never forces a tab on a toggle.

The graph's net labels come from the core's net name when it reports one; on the recorded
playthrough trace it reports none, so label derivation falls back to the AST (see
``verdandi.graph``).

Provenance (D5, D6): every node and net row, every AST node and every symbol table row carries
its loc from the trace as a small grey badge in a "Provenance" column. The graph's nodes carry
their loc as a second, small label line and a tooltip. A "show all provenance" checkbox (checked
by default) hides and shows every badge. Clicking a graph node, a table row or cell, or an AST
tree node reports that object's loc through ``on_source_clicked``, which the window points at
the Code pane; a click on an object without a loc reports nothing.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from functools import partial
from shutil import which
from typing import Any

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QBrush, QColor
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

from verdandi.graph import PROVENANCE_COLOR, node_element_id, slice_dot
from verdandi.gui.explainpane import pass_name
from verdandi.gui.graphview import SvgGraph
from verdandi.provenance import Loc, loc_from_text, object_loc
from verdandi.symtab import symbol_rows
from verdandi.trace import Diff, Step, Trace

NODE_HEADERS = ("ID", "Name", "Type", "Params", "Provenance")
NET_HEADERS = ("ID", "Name", "Drivers", "Sinks", "Provenance")
SYMBOL_HEADERS = ("Module", "Name", "Declaration", "Uses", "Provenance")
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


def _set_row(table: QTableWidget, values: tuple[Any, ...], loc: Loc | None = None) -> None:
    """Append one row; every cell carries ``loc`` so a click on any column opens the source."""
    row = table.rowCount()
    table.insertRow(row)
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        if loc is not None:
            item.setData(Qt.ItemDataRole.UserRole, loc)
            if column == len(values) - 1:
                _style_badge(item, loc)
        table.setItem(row, column, item)


def _style_badge(item: QTableWidgetItem, loc: Loc) -> None:
    """Make a provenance cell read as a small grey badge, with the full reference on hover."""
    item.setForeground(QBrush(QColor(PROVENANCE_COLOR)))
    item.setToolTip(loc.reference)


def graph_targets(snapshot: dict[str, Any]) -> dict[str, Loc]:
    """The graph's drawn nodes and their locs, keyed by SVG element id (D6)."""
    found: dict[str, Loc] = {}
    for module in snapshot.get("modules", []):
        name = str(module.get("name", ""))
        for node in module.get("nodes", []):
            loc = object_loc(node)
            if loc is not None:
                found[node_element_id(name, int(node["id"]))] = loc
    return found


class DataPane:
    """The step's snapshot: nodes and nets tables, AST tree, symbol table, graph picture."""

    def __init__(self) -> None:
        self.widget = QWidget()
        self.badge = QLabel()
        self.badge.setObjectName("structure-badge")
        self.badge.setWordWrap(True)
        self.note = QLabel()
        self.note.setObjectName("structure-note")
        self.note.setWordWrap(True)
        self.note.setVisible(False)
        self.all_box = QCheckBox("all objects")
        self.net_names_box = QCheckBox("net names")
        self.net_names_box.setChecked(True)
        self.provenance_box = QCheckBox("show all provenance")
        self.provenance_box.setObjectName("provenance-toggle")
        self.provenance_box.setChecked(True)
        self.provenance_box.setToolTip("show the source line of every object, or hide all badges")
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        boxes_layout = QHBoxLayout()
        boxes_layout.setContentsMargins(0, 0, 0, 0)
        boxes_layout.addWidget(self.all_box)
        boxes_layout.addWidget(self.net_names_box)
        boxes_layout.addStretch(1)
        provenance_layout = QHBoxLayout()
        provenance_layout.setContentsMargins(0, 0, 0, 0)
        provenance_layout.addWidget(self.provenance_box)
        provenance_layout.addStretch(1)
        controls_layout.addLayout(boxes_layout)
        controls_layout.addLayout(provenance_layout)
        self.tabs = QTabWidget()
        self.node_table = _table(NODE_HEADERS)
        self.net_table = _table(NET_HEADERS)
        self.ast_tree = QTreeWidget()
        self.ast_tree.setHeaderLabels(["AST", "Provenance"])
        self.symbol_table = _table(SYMBOL_HEADERS)
        self.graph = SvgGraph()
        self._graph_page = QWidget()
        graph_layout = QVBoxLayout(self._graph_page)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.graph)
        self.tabs.addTab(self.node_table, "Nodes")
        self.tabs.addTab(self.net_table, "Nets")
        self.tabs.addTab(self.ast_tree, "AST")
        self.tabs.addTab(self.symbol_table, "Symbols")
        self.tabs.addTab(self._graph_page, "Graph")
        layout = QVBoxLayout(self.widget)
        layout.addWidget(self.badge)
        layout.addWidget(self.note)
        layout.addWidget(controls)
        layout.addWidget(self.tabs, 1)
        self._step: Step | None = None
        self._trace: Trace | None = None
        self._structure = NO_STRUCTURE
        self._tables = (self.node_table, self.net_table, self.symbol_table)
        self.on_source_clicked: Callable[[Loc], None] | None = None
        self.all_box.toggled.connect(self._rerender)
        self.net_names_box.toggled.connect(self._rerender)
        self.provenance_box.toggled.connect(self._rerender)
        self.tabs.currentChanged.connect(self._sync_badge)
        for table in self._tables:
            table.cellClicked.connect(partial(self._cell_clicked, table))
        self.ast_tree.itemClicked.connect(self._item_clicked)
        self.graph.on_node_clicked = self._request_source

    def show(self, step: Step, trace: Trace) -> None:
        self._step = step
        self._trace = trace
        self._render()

    def has_graph(self) -> bool:
        """True when the Graph tab holds a picture for the current step."""
        return self.tabs.isTabVisible(self.tabs.indexOf(self._graph_page))

    def _rerender(self, _checked: bool = False) -> None:
        self._render()

    def _apply_provenance(self) -> None:
        """The toggle hides or shows every badge column (D5)."""
        show = self.provenance_box.isChecked()
        for table in self._tables:
            table.setColumnHidden(table.columnCount() - 1, not show)
        self.ast_tree.setColumnHidden(1, not show)

    def _render(self) -> None:
        if self._step is None or self._trace is None:
            return
        previous = self.tabs.currentWidget()
        self.node_table.setRowCount(0)
        self.net_table.setRowCount(0)
        self.ast_tree.clear()
        self.symbol_table.setRowCount(0)
        self._apply_provenance()
        self.note.clear()
        self.note.setVisible(False)
        self._set_tabs(nodes=False, nets=False, ast=False, symbols=False, graph=False)
        self._structure = NO_STRUCTURE
        default: QWidget | None = None
        if self._step.picture is not None:
            self._structure = "ABC network (picture)"
            if self._render_picture(self._step.picture):
                self._set_tabs(nodes=False, nets=False, ast=False, symbols=False, graph=True)
                default = self._graph_page
            else:
                self.note.setText(
                    "ABC network: dot not available"
                    if which("dot") is None
                    else "ABC network: picture could not be rendered"
                )
                self.note.setVisible(True)
        snapshot = self._trace.snapshot(self._step)
        if snapshot is None:
            self._select_tab(previous, default)
            self._sync_badge()
            return
        kind = snapshot.get("kind")
        if kind == "ir":
            self._structure = structure_name(self._step, snapshot)
            self._fill_tables(snapshot, self._step.diff)
            graph = self._render_slice(snapshot, self._step.diff)
            self._set_tabs(nodes=True, nets=True, ast=False, symbols=False, graph=graph)
            default = self.node_table
        elif kind == "ast":
            self._structure = structure_name(self._step, snapshot)
            self._fill_ast(snapshot)
            self._fill_symbols(snapshot)
            self._set_tabs(nodes=False, nets=False, ast=True, symbols=True, graph=False)
            default = self.ast_tree
        self._select_tab(previous, default)
        self._sync_badge()

    def _select_tab(self, previous: QWidget | None, default: QWidget | None) -> None:
        """Keep the tab the user was on when it still shows; else the step kind's default.

        A re-render happens on every step change and on each checkbox toggle, so forcing a tab
        here would bounce the user off Graph or Symbols and hide the toggle's effect.
        """
        if previous is not None:
            index = self.tabs.indexOf(previous)
            if index >= 0 and self.tabs.isTabVisible(index):
                self.tabs.setCurrentWidget(previous)
                return
        if default is not None:
            self.tabs.setCurrentWidget(default)

    def _sync_badge(self, _index: int = -1) -> None:
        """The badge names the structure shown; a visible symbol table names itself (D3)."""
        index = self.tabs.indexOf(self.symbol_table)
        if self.tabs.currentWidget() is self.symbol_table and self.tabs.isTabVisible(index):
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
                loc = object_loc(node)
                _set_row(
                    self.node_table,
                    (
                        node["id"],
                        node.get("name", ""),
                        node.get("type", ""),
                        params,
                        loc.badge if loc is not None else "",
                    ),
                    loc,
                )
            for net in module.get("nets", []):
                if not show_all and (name, int(net["id"])) not in touched["net"]:
                    continue
                drivers = ", ".join(str(ident) for ident in net.get("drivers", []))
                sinks = ", ".join(str(ident) for ident in net.get("sinks", []))
                loc = object_loc(net)
                _set_row(
                    self.net_table,
                    (
                        net["id"],
                        net.get("name", ""),
                        drivers,
                        sinks,
                        loc.badge if loc is not None else "",
                    ),
                    loc,
                )

    def _fill_ast(self, snapshot: dict[str, Any]) -> None:
        roots = snapshot.get("roots", [])
        stack: list[tuple[dict[str, Any], QTreeWidgetItem | None]] = [
            (node, None) for node in reversed(roots)
        ]
        while stack:
            node, parent = stack.pop()
            label = str(node.get("name") or node.get("kind", ""))
            loc = loc_from_text(node.get("loc"))
            item = QTreeWidgetItem([label, loc.badge if loc is not None else ""])
            if loc is not None:
                item.setData(0, Qt.ItemDataRole.UserRole, loc)
                item.setToolTip(0, loc.reference)
                item.setForeground(1, QBrush(QColor(PROVENANCE_COLOR)))
            if parent is None:
                self.ast_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in reversed(node.get("children", [])):
                stack.append((child, item))

    def _fill_symbols(self, snapshot: dict[str, Any]) -> None:
        for symbol in symbol_rows(snapshot):
            declaration = loc_from_text(symbol.declaration)
            first_use = loc_from_text(symbol.uses[0]) if symbol.uses else declaration
            uses = "; ".join(symbol.uses) if symbol.uses else "-"
            cells: tuple[tuple[str, Loc | None], ...] = (
                (symbol.module, declaration),
                (symbol.name, declaration),
                (symbol.declaration, declaration),
                (uses, first_use),
                (declaration.badge if declaration is not None else "", declaration),
            )
            row = self.symbol_table.rowCount()
            self.symbol_table.insertRow(row)
            for column, (text, loc) in enumerate(cells):
                item = QTableWidgetItem(text)
                if loc is not None:
                    item.setData(Qt.ItemDataRole.UserRole, loc)
                    if column == len(cells) - 1:
                        _style_badge(item, loc)
                self.symbol_table.setItem(row, column, item)

    def _request_source(self, loc: Loc) -> None:
        """Report one clicked loc to the window's Code pane hook (D6)."""
        if self.on_source_clicked is not None:
            self.on_source_clicked(loc)

    def _cell_clicked(self, table: QTableWidget, row: int, column: int) -> None:
        item = table.item(row, column)
        if item is None:
            return
        loc = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(loc, Loc):
            self._request_source(loc)

    def _item_clicked(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        loc = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(loc, Loc):
            self._request_source(loc)

    def _render_slice(self, snapshot: dict[str, Any], diff: Diff | None) -> bool:
        """Load the slice picture; True when the Graph tab holds one."""
        if diff is None or not (diff.added or diff.removed or diff.changed):
            return False
        svg = render_dot(
            slice_dot(
                snapshot,
                diff,
                show_net_names=self.net_names_box.isChecked(),
                ast=self._ast_snapshot(),
                show_provenance=self.provenance_box.isChecked(),
            )
        )
        if svg is None:
            return False
        self.graph.set_graph(QByteArray(svg), graph_targets(snapshot))
        return True

    def _ast_snapshot(self) -> dict[str, Any] | None:
        """An AST snapshot of this trace, for net display names; None when it has none.

        The newest elaborated AST store wins over the parsed one; both carry the module and
        declaration locations the graph matches against a net's source span.
        """
        if self._trace is None:
            return None
        found: dict[str, Any] | None = None
        for step in self._trace.steps:
            if step.snapshot is None:
                continue
            snapshot = self._trace.snapshot(step)
            if snapshot is None or snapshot.get("kind") != "ast":
                continue
            found = snapshot
            if snapshot.get("form") == "ELABORATED":
                break
        return found

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
        self.graph.set_graph(QByteArray(svg), {})
        return True
