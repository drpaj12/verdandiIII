"""The Code pane: the Odin III source at the current step's code locations.

One read-only tab per ``CodeRef``. A file is read from ``ODIN3_ROOT`` (or the root given to the
pane, which the entry point takes from the ``codeRoot`` app setting), the ``line..end_line``
lines are highlighted and the view scrolls to the first one; a missing file shows ``source not
available: <file>`` in its tab instead of raising.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from verdandi.gui.verilogpane import read_source
from verdandi.trace import CodeRef, Step, Trace

HIGHLIGHT = QColor("#ddf4ff")


def code_root(root: Path | None) -> Path | None:
    """The explicit root, else ``ODIN3_ROOT`` when it names a directory, else None."""
    if root is not None:
        return root
    value = os.environ.get("ODIN3_ROOT")
    if value:
        path = Path(value)
        if path.is_dir():
            return path
    return None


class CodePane:
    """The step's code locations as tabs; the function span of each is highlighted."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.widget = QWidget()
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def show(self, step: Step, trace: Trace) -> None:
        self.tabs.clear()
        root = code_root(self.root)
        for ref in step.code:
            self.tabs.addTab(self._editor(ref, root), ref.function or Path(ref.file).name)

    def _editor(self, ref: CodeRef, root: Path | None) -> QPlainTextEdit:
        path = None if root is None else root / ref.file
        if path is None or not path.is_file():
            editor = QPlainTextEdit(f"source not available: {ref.file}")
            editor.setReadOnly(True)
            return editor
        editor = QPlainTextEdit(read_source(path))
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlight_lines(editor, ref.line, ref.end_line)
        return editor

    def _highlight_lines(self, editor: QPlainTextEdit, line: int, end_line: int) -> None:
        document = editor.document()
        first = document.findBlockByNumber(max(0, line - 1))
        last = document.findBlockByNumber(max(0, end_line - 1))
        if last.blockNumber() < first.blockNumber():
            last = first
        cursor = QTextCursor(document)
        cursor.setPosition(first.position())
        cursor.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(HIGHLIGHT)
        editor.setExtraSelections([selection])
        scroll = QTextCursor(document)
        scroll.setPosition(first.position())
        editor.setTextCursor(scroll)
        editor.centerCursor()
