"""The Source pane (D9): a lazy directory tree of ODIN3_ROOT, zoomed to the step's file.

The tree lists a directory's children the first time it expands, so opening the pane never walks
the checkout; a ``.c`` file expands to its functions (the section-6 scan). The current step's
file path is expanded and the file item highlighted. A click on any file (or one of its
functions) opens the file in the Code pane; the pane itself keeps the keyboard, as the step tree
does.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from verdandi.gui.codepane import code_root
from verdandi.odin3.locator import Locator
from verdandi.trace import CodeRef, Step, Trace

PATH_ROLE = int(Qt.ItemDataRole.UserRole)
DIR_ROLE = PATH_ROLE + 1
LINE_ROLE = PATH_ROLE + 2
END_ROLE = PATH_ROLE + 3


class SourcePane:
    """A collapsible tree of the source tree, zoomed to the step's first code record."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.widget = QWidget()
        self.note = QLabel()
        self.note.setObjectName("source-tree-note")
        self.note.setWordWrap(True)
        self.note.setVisible(False)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.itemExpanded.connect(self._ensure_children)
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.note)
        layout.addWidget(self.tree, 1)
        self._resolved: Path | None = None
        self._ready = False
        self._loaded: set[str] = set()
        self._locator: Locator | None = None
        self._root_item: QTreeWidgetItem | None = None
        self._marked: QTreeWidgetItem | None = None

    def file_of(self, item: QTreeWidgetItem) -> str | None:
        """The file a tree item names; None for the root or a directory.

        A function item names its file, so a click on a function opens the file too.
        """
        path = str(item.data(0, PATH_ROLE) or "")
        if not path or bool(item.data(0, DIR_ROLE)):
            return None
        return path

    def show(self, step: Step, trace: Trace) -> None:
        root = code_root(self.root)
        if not self._ready or root != self._resolved:
            self._load(root)
        self._mark(None)
        if self._resolved is None or self._root_item is None:
            return
        ref = self._zoom_ref(step)
        if ref is None:
            return
        item = self._root_item
        for part in Path(ref.file).parts:
            self._ensure_children(item)
            child = self._child_named(item, part)
            if child is None:
                return
            item.setExpanded(True)
            item = child
        self._mark(item)
        self._ensure_children(item)
        item.setExpanded(True)
        function = self._function_item(item, ref)
        self.tree.scrollToItem(function if function is not None else item)

    def _zoom_ref(self, step: Step) -> CodeRef | None:
        """The record the tree zooms to: the step's first code record."""
        return step.code[0] if step.code else None

    def _load(self, root: Path | None) -> None:
        self._ready = True
        self._resolved = root
        self._loaded = set()
        self._marked = None
        self._locator = Locator(root) if root is not None else None
        self.tree.clear()
        self._root_item = None
        if root is None:
            self.note.setText("no source tree (set ODIN3_ROOT or the codeRoot setting)")
            self.note.setVisible(True)
            self.tree.setVisible(False)
            return
        self.note.clear()
        self.note.setVisible(False)
        self.tree.setVisible(True)
        item = QTreeWidgetItem([root.name or str(root)])
        item.setData(0, PATH_ROLE, "")
        item.setData(0, DIR_ROLE, True)
        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        self.tree.addTopLevelItem(item)
        self._root_item = item

    def _ensure_children(self, item: QTreeWidgetItem) -> None:
        """List a directory's children, or a .c file's functions, once."""
        path = str(item.data(0, PATH_ROLE) or "")
        if path in self._loaded or self._resolved is None:
            return
        self._loaded.add(path)
        if bool(item.data(0, DIR_ROLE)):
            self._fill_directory(item, path)
        else:
            self._fill_functions(item, path)

    def _fill_directory(self, item: QTreeWidgetItem, path: str) -> None:
        assert self._resolved is not None
        directory = self._resolved / path if path else self._resolved
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda entry: (not entry.is_dir(), entry.name.casefold()),
            )
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            child = QTreeWidgetItem([entry.name])
            try:
                relative = str(entry.relative_to(self._resolved))
            except ValueError:
                continue
            child.setData(0, PATH_ROLE, relative)
            child.setData(0, DIR_ROLE, entry.is_dir())
            if entry.is_dir() or entry.suffix == ".c":
                child.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )
            item.addChild(child)

    def _fill_functions(self, item: QTreeWidgetItem, path: str) -> None:
        if self._locator is None or not path.endswith(".c"):
            return
        for span in self._locator.functions(Path(path)):
            child = QTreeWidgetItem([span.function or ""])
            child.setData(0, PATH_ROLE, path)
            child.setData(0, DIR_ROLE, False)
            child.setData(0, LINE_ROLE, span.line)
            child.setData(0, END_ROLE, span.end_line)
            item.addChild(child)

    @staticmethod
    def _child_named(item: QTreeWidgetItem, name: str) -> QTreeWidgetItem | None:
        for row in range(item.childCount()):
            child = item.child(row)
            if child is not None and child.text(0) == name:
                return child
        return None

    @staticmethod
    def _function_item(item: QTreeWidgetItem, ref: CodeRef) -> QTreeWidgetItem | None:
        """The function item a record names, by name first, else by the line it covers."""
        if ref.function is not None:
            for row in range(item.childCount()):
                child = item.child(row)
                if child is not None and child.text(0) == ref.function:
                    return child
        for row in range(item.childCount()):
            child = item.child(row)
            if child is None:
                continue
            start = int(child.data(0, LINE_ROLE) or 0)
            end = int(child.data(0, END_ROLE) or 0)
            if start <= ref.line <= end:
                return child
        return None

    def _mark(self, item: QTreeWidgetItem | None) -> None:
        """Highlight the zoomed file item the way the step tree marks its current step."""
        if self._marked is not None:
            self._marked.setData(0, Qt.ItemDataRole.BackgroundRole, None)
            self._marked.setData(0, Qt.ItemDataRole.ForegroundRole, None)
        self._marked = item
        if item is not None:
            item.setData(0, Qt.ItemDataRole.BackgroundRole, QBrush(self.tree.palette().highlight()))
            item.setData(
                0, Qt.ItemDataRole.ForegroundRole, QBrush(self.tree.palette().highlightedText())
            )
