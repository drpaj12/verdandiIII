"""The diff strip: the added, removed and changed counts (green, red, amber) and the list."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget

from verdandi.trace import ObjRef, Step, Trace

COLORS = {"added": "#1a7f37", "removed": "#cf222e", "changed": "#9a6700"}
SIGNS = {"added": "+", "removed": "-", "changed": "~"}


class DiffStrip:
    """Three coloured count labels above a flat list of the touched objects."""

    def __init__(self) -> None:
        self.widget = QWidget()
        self.labels: dict[str, QLabel] = {}
        self.refs = QListWidget()
        counts = QWidget()
        counts_layout = QHBoxLayout(counts)
        counts_layout.setContentsMargins(0, 0, 0, 0)
        for kind in ("added", "removed", "changed"):
            label = QLabel()
            label.setObjectName(f"diff-{kind}")
            label.setStyleSheet(f"color: {COLORS[kind]}; font-weight: bold;")
            counts_layout.addWidget(label)
            self.labels[kind] = label
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(counts)
        layout.addWidget(self.refs, 1)

    def show(self, step: Step, trace: Trace) -> None:
        diff = step.diff
        groups: dict[str, list[ObjRef]] = {
            "added": diff.added if diff is not None else [],
            "removed": diff.removed if diff is not None else [],
            "changed": diff.changed if diff is not None else [],
        }
        self.refs.clear()
        for kind in ("added", "removed", "changed"):
            refs = groups[kind]
            self.labels[kind].setText(f"{SIGNS[kind]}{len(refs)} {kind}")
            for ref in refs:
                self.refs.addItem(f"{SIGNS[kind]} {ref.kind} {ref.module}.{ref.name}")
