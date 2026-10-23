"""The Code pane: the Odin III source of the step's functions at a chosen call depth (D8).

One read-only tab per file named by the step's ``CodeRef`` records, or at depth > 0 by their
callees as well. A file is read from ``ODIN3_ROOT`` (or the root given to the pane, which the
entry point takes from the ``codeRoot`` app setting); every function span shown is highlighted
in its depth's colour and the view scrolls to the first one. A missing file shows
``source not available: <file>`` in its tab instead of raising. The depth control follows the
call graph of ``verdandi.callgraph``; a note beside it names the source that graph came from
(the code-review-graph database, marked "file scope" when a record covered no single function,
or a static scan), so the two are never confused.

The pane also opens whole files in extra tabs: a Source-tree click (D9) and an example source
clicked in the Data pane (D6, ``open_example``). An example source is the trace's own copy
(``src/<basename>``), not the Odin III tree; it opens at the clicked loc's line, highlighted and
centred. Extra tabs sit beside the step's source tabs and survive a step change, so a click into
an example does not vanish on the next step.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from verdandi.callgraph import (
    MAX_DEPTH,
    SOURCE_GRAPH,
    SOURCE_NO_TREE,
    SOURCE_SCAN,
    Expansion,
    Span,
    expand,
)
from verdandi.gui.verilogpane import read_source
from verdandi.provenance import Loc
from verdandi.trace import Step, Trace

HIGHLIGHT = QColor("#ddf4ff")
CALLEE_HIGHLIGHTS = (
    QColor("#e6f7ea"),
    QColor("#fff4d6"),
    QColor("#f0e8ff"),
    QColor("#ffe8e8"),
    QColor("#e8f2ff"),
)


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


def depth_highlight(depth: int) -> QColor:
    """The body colour of one depth: the step's own blue, then a callee's own shade."""
    if depth == 0:
        return HIGHLIGHT
    return CALLEE_HIGHLIGHTS[(depth - 1) % len(CALLEE_HIGHLIGHTS)]


class CodePane:
    """The step's code locations as file tabs; each shown function span is highlighted."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.widget = QWidget()
        self.depth_box = QSpinBox()
        self.depth_box.setObjectName("depth-control")
        self.depth_box.setRange(0, MAX_DEPTH)
        self.depth_box.setValue(0)
        self.depth_box.setToolTip("how many rings of callees the pane follows")
        self.depth_box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.note = QLabel()
        self.note.setObjectName("source-note")
        self.note.setWordWrap(True)
        self.note.setVisible(False)
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(QLabel("Depth:"))
        controls_layout.addWidget(self.depth_box)
        controls_layout.addStretch(1)
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(controls)
        layout.addWidget(self.note)
        layout.addWidget(self.tabs, 1)
        self._step: Step | None = None
        self._trace: Trace | None = None
        self._spans: list[Span] = []
        self._files: dict[str, QPlainTextEdit] = {}
        self._extras: dict[str, QPlainTextEdit] = {}
        self._extra_titles: dict[str, str] = {}
        self.depth_box.valueChanged.connect(self._rerender)

    def show(self, step: Step, trace: Trace) -> None:
        self._step = step
        self._trace = trace
        self._render()

    def shown_spans(self) -> list[Span]:
        """The function spans the pane currently shows, in depth order."""
        return list(self._spans)

    def open_file(self, file: str) -> None:
        """Open one file of the source tree whole in its own tab (a source-tree click)."""
        root = code_root(self.root)
        self._open_extra(f"file:{file}", Path(file).name, self._whole_editor(file, root))

    def open_example(self, loc: Loc, sources: Path) -> None:
        """Open the trace's copy of an example source at ``loc``'s line (D6).

        The trace keeps its sources by basename (``src/<basename>``); a loc whose file the trace
        does not hold opens a tab that says so instead of raising.
        """
        name = Path(loc.file).name
        path = sources / name
        editor = (
            self._whole_editor_at(path, loc)
            if path.is_file()
            else self._unavailable(loc.file)
        )
        self._open_extra(f"example:{name}", name, editor)

    def _open_extra(self, key: str, title: str, editor: QPlainTextEdit) -> None:
        """Put a whole-file editor in an extra tab, replacing an earlier tab of the same key."""
        previous = self._extras.get(key)
        if previous is not None:
            index = self.tabs.indexOf(previous)
            if index >= 0:
                self.tabs.removeTab(index)
            previous.deleteLater()
        self._extras[key] = editor
        self._extra_titles[key] = title
        self.tabs.addTab(editor, title)
        self.tabs.setCurrentWidget(editor)

    def _readd_extras(self, current: QWidget | None) -> None:
        """Re-add the extra tabs after a step render; keep the user's tab when it survives."""
        for key, editor in self._extras.items():
            self.tabs.addTab(editor, self._extra_titles[key])
        if current is not None and self.tabs.indexOf(current) >= 0:
            self.tabs.setCurrentWidget(current)

    def _rerender(self, _value: int = 0) -> None:
        if self._step is not None and self._trace is not None:
            self._render()

    def _render(self) -> None:
        current = self.tabs.currentWidget()
        self.tabs.clear()
        self._files = {}
        if self._step is None:
            self._readd_extras(current)
            return
        root = code_root(self.root)
        expansion = expand(root, self._step.code, self.depth_box.value())
        self._spans = list(expansion.spans)
        self._set_note(expansion, self.depth_box.value())
        groups: dict[str, list[Span]] = {}
        for span in expansion.spans:
            groups.setdefault(span.file, []).append(span)
        for file, spans in groups.items():
            editor = self._editor(file, root, spans)
            self.tabs.addTab(editor, self._title(file, spans))
            self._files[file] = editor
        self._readd_extras(current)

    def _set_note(self, expansion: Expansion, depth: int) -> None:
        """Name the call-graph source in use; depth 0 needs no graph and shows no note."""
        if depth <= 0 or not expansion.spans:
            self.note.clear()
            self.note.setVisible(False)
            return
        if expansion.source == SOURCE_GRAPH:
            text = "call graph: code-review-graph DB"
            if expansion.file_scope:
                text = f"{text} (file scope)"
        elif expansion.source == SOURCE_SCAN:
            if expansion.scanned:
                text = "call graph: static scan of " + ", ".join(expansion.scanned)
            else:
                text = "call graph: static scan (no readable file)"
        elif expansion.source == SOURCE_NO_TREE:
            text = "call graph: no source tree (set ODIN3_ROOT or the codeRoot setting)"
        else:
            text = f"call graph: {expansion.source}"
        self.note.setText(text)
        self.note.setVisible(True)

    @staticmethod
    def _title(file: str, spans: list[Span]) -> str:
        if len(spans) == 1 and spans[0].function is not None:
            return spans[0].function
        return Path(file).name

    def _editor(self, file: str, root: Path | None, spans: list[Span]) -> QPlainTextEdit:
        path = None if root is None else root / file
        if path is None or not path.is_file():
            editor = QPlainTextEdit(f"source not available: {file}")
            editor.setReadOnly(True)
            return editor
        editor = QPlainTextEdit(read_source(path))
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        first = True
        for span in spans:
            shown = self._highlight_span(
                editor, span.line, span.end_line, depth_highlight(span.depth)
            )
            if shown and first:
                self._scroll_to(editor, span.line)
                first = False
        return editor

    def _whole_editor(self, file: str, root: Path | None) -> QPlainTextEdit:
        path = None if root is None else root / file
        if path is None or not path.is_file():
            return self._unavailable(file)
        editor = QPlainTextEdit(read_source(path))
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        return editor

    def _whole_editor_at(self, path: Path, loc: Loc) -> QPlainTextEdit:
        """A whole example source, its loc's line range highlighted and the line centred."""
        editor = QPlainTextEdit(read_source(path))
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlight_span(editor, loc.line, loc.end_line, HIGHLIGHT)
        self._scroll_to(editor, loc.line)
        return editor

    @staticmethod
    def _unavailable(file: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(f"source not available: {file}")
        editor.setReadOnly(True)
        return editor

    def _highlight_span(
        self, editor: QPlainTextEdit, line: int, end_line: int, colour: QColor
    ) -> bool:
        """Highlight one span; False when it names no line of the editor's text."""
        document = editor.document()
        first = document.findBlockByNumber(max(0, line - 1))
        last = document.findBlockByNumber(max(0, end_line - 1))
        if not first.isValid():
            return False
        if last.blockNumber() < first.blockNumber():
            last = first
        cursor = QTextCursor(document)
        cursor.setPosition(first.position())
        cursor.setPosition(last.position() + last.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(colour)
        editor.setExtraSelections([*editor.extraSelections(), selection])
        return True

    @staticmethod
    def _scroll_to(editor: QPlainTextEdit, line: int) -> None:
        document = editor.document()
        block = document.findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        scroll = QTextCursor(document)
        scroll.setPosition(block.position())
        editor.setTextCursor(scroll)
        editor.centerCursor()
