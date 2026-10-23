"""The Verilog pane: the trace's sources with the current step's object spans highlighted.

A span is one snapshot source row ``[file, line, col, end_line, end_col]``: 1-based lines and
columns, ``end_col`` one past the last character (the recorder's convention). ``file`` is the
source as the recorder saw it, often the path given to ``read_verilog``; the pane's tabs are
keyed by basename, so a span's exact name is tried first and its basename second. Columns count
characters, so a tab is one character; one trailing ``\\r`` per line is dropped before slicing so
a CRLF source highlights the same text as an LF one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from verdandi.trace import Diff, Step, Trace

HIGHLIGHT = QColor("#fff3b0")
HIGHLIGHT_TEXT = QColor("#000000")
REMOVED_HIGHLIGHT = QColor("#ffd6d6")


def normalize_text(text: str) -> str:
    """Drop one trailing carriage return from every line; keep everything else as it is."""
    return "\n".join(line[:-1] if line.endswith("\r") else line for line in text.split("\n"))


def read_source(path: Path) -> str:
    """The file's text with universal-newline translation turned off, then normalised."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return normalize_text(handle.read())


def _line_starts(text: str) -> list[int]:
    """The offset of the first character of every line (line 1 at index 0)."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _line_bounds(text: str, starts: list[int], line: int) -> tuple[int, int]:
    """The start and end (before the newline) offsets of a 1-based line."""
    start = starts[line - 1]
    return start, starts[line] - 1 if line < len(starts) else len(text)


def span_offsets(text: str, span: Any) -> tuple[int, int] | None:
    """The (start, end) character offsets of one source row, end exclusive.

    ``None`` when the row names no line of this text. A row without an end (``end_col`` 0 or an
    end line before the start line) runs to the end of its start line.
    """
    try:
        line = int(span[1])
        col = int(span[2])
        end_line = int(span[3])
        end_col = int(span[4])
    except (IndexError, TypeError, ValueError):
        return None
    starts = _line_starts(text)
    if line < 1 or line > len(starts):
        return None
    if end_line < line or end_line > len(starts):
        end_line = line
    line_start, line_end = _line_bounds(text, starts, line)
    start = min(line_start + max(col - 1, 0), line_end)
    end_start, end_end = _line_bounds(text, starts, end_line)
    end = end_end if end_col <= 0 else min(end_start + end_col - 1, end_end)
    return start, max(end, start)


def span_text(text: str, span: Any) -> str:
    """The text one source row covers; the highlighter's own slicing rule."""
    offsets = span_offsets(text, span)
    if offsets is None:
        return ""
    start, end = offsets
    return text[start:end]


def _span_rows(snapshot: dict[str, Any] | None, refs: list[Any]) -> list[list[Any]]:
    """The source rows of ``refs`` that the IR snapshot holds; wires carry none."""
    if snapshot is None or snapshot.get("kind") != "ir":
        return []
    wanted: dict[tuple[str, str], set[int]] = {}
    for ref in refs:
        wanted.setdefault((ref.module, ref.kind), set()).add(ref.id)
    spans: list[list[Any]] = []
    for module in snapshot.get("modules", []):
        name = str(module.get("name", ""))
        for kind, field in (("node", "nodes"), ("net", "nets")):
            ids = wanted.get((name, kind), set())
            if not ids:
                continue
            for item in module.get(field, []):
                if int(item["id"]) in ids:
                    spans.extend(item.get("sources", []))
    return spans


def source_spans(snapshot: dict[str, Any] | None, diff: Diff | None) -> list[list[Any]]:
    """Every source row of the diff's added, removed and changed objects the snapshot holds.

    A removed object is absent from the snapshot a step ends with, so its spans usually come
    from earlier in the walk; ``removed_spans`` resolves them there.
    """
    if diff is None:
        return []
    return _span_rows(snapshot, [*diff.added, *diff.removed, *diff.changed])


def removed_spans(snapshot: dict[str, Any] | None, diff: Diff | None) -> list[list[Any]]:
    """The source rows of the diff's removed objects in an earlier snapshot."""
    if diff is None:
        return []
    return _span_rows(snapshot, list(diff.removed))


class VerilogPane:
    """One read-only tab per file in the trace's ``src/``; the step's spans are highlighted."""

    def __init__(self) -> None:
        self.widget = QWidget()
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        self.editors: dict[str, QPlainTextEdit] = {}
        self._directory: Path | None = None

    def show(self, step: Step, trace: Trace) -> None:
        if trace.directory != self._directory:
            self._load(trace)
        self._highlight(step, trace)

    def _load(self, trace: Trace) -> None:
        self._directory = trace.directory
        self.tabs.clear()
        self.editors = {}
        src = trace.directory / "src"
        names = (
            sorted(path.name for path in src.iterdir() if path.is_file())
            if src.is_dir()
            else []
        )
        if not names:
            editor = QPlainTextEdit("no sources in this trace")
            editor.setReadOnly(True)
            self.tabs.addTab(editor, "sources")
            return
        for name in names:
            editor = QPlainTextEdit(read_source(src / name))
            editor.setReadOnly(True)
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.tabs.addTab(editor, name)
            self.editors[name] = editor

    def _target(self, name: str) -> tuple[str, QPlainTextEdit] | None:
        """The tab key and editor for a span's file: exact name first, basename second."""
        editor = self.editors.get(name)
        if editor is not None:
            return name, editor
        base = Path(name).name
        editor = self.editors.get(base)
        if editor is None:
            return None
        return base, editor

    def _mark(self, target: QPlainTextEdit, span: Any, colour: QColor) -> bool:
        """Highlight one row in one editor; False when it names no line of the text."""
        offsets = span_offsets(target.toPlainText(), span)
        if offsets is None or offsets[1] <= offsets[0]:
            return False
        start, end = offsets
        cursor = target.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(colour)
        selection.format.setForeground(HIGHLIGHT_TEXT)
        target.setExtraSelections([*target.extraSelections(), selection])
        return True

    def _earlier_snapshot(self, step: Step, trace: Trace) -> dict[str, Any] | None:
        """The nearest IR snapshot recorded before the step; None when there is none."""
        index = next(
            (i for i, candidate in enumerate(trace.steps) if candidate is step), None
        )
        if index is None:
            return None
        for candidate in reversed(trace.steps[:index]):
            snapshot = trace.snapshot(candidate)
            if snapshot is not None and snapshot.get("kind") == "ir":
                return snapshot
        return None

    def _highlight(self, step: Step, trace: Trace) -> None:
        for editor in self.editors.values():
            editor.setExtraSelections([])
        first: str | None = None
        rows = [
            (span, HIGHLIGHT) for span in source_spans(trace.snapshot(step), step.diff)
        ]
        rows.extend(
            (span, REMOVED_HIGHLIGHT)
            for span in removed_spans(self._earlier_snapshot(step, trace), step.diff)
        )
        for span, colour in rows:
            if len(span) < 5:
                continue
            found = self._target(str(span[0]))
            if found is None:
                continue
            name, target = found
            if not self._mark(target, span, colour):
                continue
            if first is None:
                first = name
        if first is not None:
            self.tabs.setCurrentWidget(self.editors[first])

    def highlighted_texts(self) -> list[str]:
        """The highlighted text of every tab, in tab order (one entry per span)."""
        texts: list[str] = []
        for editor in self.editors.values():
            for selection in editor.extraSelections():
                selected = selection.cursor.selectedText()
                if selected:
                    texts.append(selected)
        return texts
