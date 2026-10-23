"""The Data pane: snapshot tables, an AST tree and the dot-rendered touched slice.

An IR step shows the touched nodes and nets in tables (the "all objects" box shows everything)
and, when Graphviz is on PATH, a picture of the slice. An AST step shows its tree. A step with
an ABC picture renders that instead. Without ``dot`` the pane keeps its tables and shows no
picture, and never raises.
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdandi.graph import slice_dot
from verdandi.trace import Diff, Step, Trace

NODE_HEADERS = ("ID", "Name", "Type", "Params")
NET_HEADERS = ("ID", "Name", "Drivers", "Sinks")


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
    """The step's snapshot: nodes and nets tables, AST tree, graph picture."""

    def __init__(self) -> None:
        self.widget = QWidget()
        self.all_box = QCheckBox("all objects")
        self.tabs = QTabWidget()
        self.node_table = _table(NODE_HEADERS)
        self.net_table = _table(NET_HEADERS)
        self.ast_tree = QTreeWidget()
        self.ast_tree.setHeaderLabel("AST")
        self.svg = QSvgWidget()
        self._graph_page = QWidget()
        graph_layout = QVBoxLayout(self._graph_page)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.addWidget(self.svg)
        self.tabs.addTab(self.node_table, "Nodes")
        self.tabs.addTab(self.net_table, "Nets")
        self.tabs.addTab(self.ast_tree, "AST")
        self.tabs.addTab(self._graph_page, "Graph")
        layout = QVBoxLayout(self.widget)
        layout.addWidget(self.all_box)
        layout.addWidget(self.tabs, 1)
        self._step: Step | None = None
        self._trace: Trace | None = None
        self.all_box.toggled.connect(self._rerender)

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
        self._set_tabs(nodes=True, nets=True, ast=False, graph=False)
        snapshot = self._trace.snapshot(self._step)
        if snapshot is None:
            return
        kind = snapshot.get("kind")
        if kind == "ir":
            self._fill_tables(snapshot, self._step.diff)
            self._render_slice(snapshot, self._step.diff)
        elif kind == "ast":
            self._set_tabs(nodes=False, nets=False, ast=True, graph=False)
            self._fill_ast(snapshot)
        if self._step.picture is not None:
            self._render_picture(self._step.picture)

    def _set_tabs(self, *, nodes: bool, nets: bool, ast: bool, graph: bool) -> None:
        for page, visible in (
            (self.node_table, nodes),
            (self.net_table, nets),
            (self.ast_tree, ast),
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

    def _render_slice(self, snapshot: dict[str, Any], diff: Diff | None) -> None:
        if diff is None or not (diff.added or diff.removed or diff.changed):
            return
        svg = render_dot(slice_dot(snapshot, diff))
        if svg is None:
            return
        self.svg.load(QByteArray(svg))
        self._set_tabs(nodes=True, nets=True, ast=False, graph=True)

    def _render_picture(self, name: str) -> None:
        if self._trace is None:
            return
        path = self._trace.directory / "pic" / name
        if not path.is_file():
            return
        svg = render_dot(path.read_text(encoding="utf-8"))
        if svg is None:
            return
        self.svg.load(QByteArray(svg))
        self._set_tabs(nodes=False, nets=False, ast=False, graph=True)
