"""Source-tree tests (D9): lazy directory tree, zoom to the step's file, click opens the file."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_navigator import make_manifest
from verdandi.trace import CodeRef, Step, Trace

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTreeWidgetItem

    from verdandi.gui.mainwindow import MainWindow

HAVE_QT = importlib.util.find_spec("PySide6") is not None

SOURCE = """int helper(int x) {
    return x;
}

int proc_pass(int y) {
    return helper(y);
}
"""


def source_tree(root: Path) -> None:
    """src/passes/proc/proc.c with two functions, a sibling directory and a hidden one."""
    path = root / "src" / "passes" / "proc" / "proc.c"
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE, encoding="utf-8")
    other = root / "src" / "other.c"
    other.write_text("int other(void) {\n    return 0;\n}\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "readme.md").write_text("docs\n", encoding="utf-8")
    (root / ".git").mkdir()


def step() -> Step:
    return Step(
        id="s0001",
        parent=None,
        level=1,
        title="proc",
        anchor="pass:proc",
        code=[CodeRef(file="src/passes/proc/proc.c", line=5, end_line=7, function="proc_pass")],
    )


def source_trace(directory: Path) -> Trace:
    return Trace(directory, make_manifest(), [step()])


def item_by_path(item: QTreeWidgetItem, path: str) -> QTreeWidgetItem | None:
    """Depth-first search of a tree item's subtree for the file item at ``path``."""
    from PySide6.QtWidgets import QTreeWidgetItem as Item

    from verdandi.gui.sourcetree import PATH_ROLE

    if not isinstance(item, Item):
        return None
    if str(item.data(0, PATH_ROLE) or "") == path:
        return item
    for row in range(item.childCount()):
        child = item.child(row)
        if child is not None:
            found = item_by_path(child, path)
            if found is not None:
                return found
    return None


def child_texts(item: QTreeWidgetItem) -> list[str]:
    return [
        child.text(0)
        for row in range(item.childCount())
        if (child := item.child(row)) is not None
    ]


def click_item(window: MainWindow, item: QTreeWidgetItem) -> None:
    """Click a Source tree item at its visual centre, scrolling it into view first."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    tree = window.source_pane.tree
    tree.scrollToItem(item)
    QApplication.processEvents()
    rect = tree.visualItemRect(item)
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    QApplication.processEvents()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SourceTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        existing = QApplication.instance()
        self.app = existing if isinstance(existing, QApplication) else QApplication([])

    def test_tree_is_lazy_until_the_zoom(self) -> None:
        from verdandi.gui.sourcetree import SourcePane

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            trace = source_trace(Path(tmp) / "trace")
            pane = SourcePane(root=root)
            self.assertEqual(pane.tree.topLevelItemCount(), 0)
            pane.show(trace.steps[0], trace)
            top = pane.tree.topLevelItem(0)
            assert top is not None
            self.assertTrue(top.isExpanded())
            docs = item_by_path(top, "docs")
            assert docs is not None
            self.assertEqual(docs.childCount(), 0)
            self.assertNotIn(".git", child_texts(top))

    def test_zoom_expands_to_the_file_and_highlights_it(self) -> None:
        from PySide6.QtCore import Qt

        from verdandi.gui.sourcetree import SourcePane

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            trace = source_trace(Path(tmp) / "trace")
            pane = SourcePane(root=root)
            pane.show(trace.steps[0], trace)
            top = pane.tree.topLevelItem(0)
            assert top is not None
            file_item = item_by_path(top, "src/passes/proc/proc.c")
            assert file_item is not None
            self.assertTrue(file_item.isExpanded())
            self.assertIsNotNone(file_item.data(0, Qt.ItemDataRole.BackgroundRole))
            names = child_texts(file_item)
        self.assertEqual(names, ["helper", "proc_pass"])

    def test_no_source_tree(self) -> None:
        from unittest import mock

        from verdandi.gui.sourcetree import SourcePane

        with tempfile.TemporaryDirectory() as tmp:
            trace = source_trace(Path(tmp) / "trace")
            with mock.patch.dict(os.environ, {"ODIN3_ROOT": ""}):
                pane = SourcePane(root=None)
                pane.show(trace.steps[0], trace)
        self.assertFalse(pane.note.isHidden())
        self.assertIn("no source tree", pane.note.text())
        self.assertEqual(pane.tree.topLevelItemCount(), 0)

    def test_zoom_uses_the_first_code_record(self) -> None:
        """D9 zooms to the step's first record, not the first one that names a function."""
        from PySide6.QtCore import Qt

        from verdandi.gui.sourcetree import SourcePane

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            step = Step(
                id="s0001",
                parent=None,
                level=1,
                title="opt",
                anchor="pass:opt",
                code=[
                    CodeRef(file="src/other.c", line=1, end_line=1, function=None),
                    CodeRef(
                        file="src/passes/proc/proc.c", line=5, end_line=7, function="proc_pass"
                    ),
                ],
            )
            trace = Trace(Path(tmp) / "trace", make_manifest(), [step])
            pane = SourcePane(root=root)
            pane.show(step, trace)
            top = pane.tree.topLevelItem(0)
            assert top is not None
            other = item_by_path(top, "src/other.c")
            assert other is not None
            self.assertIsNotNone(other.data(0, Qt.ItemDataRole.BackgroundRole))
            self.assertIsNone(item_by_path(top, "src/passes/proc/proc.c"))

    def test_click_opens_the_file_in_the_code_pane(self) -> None:
        from PySide6.QtWidgets import QApplication, QPlainTextEdit

        from verdandi.gui.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            window = MainWindow(source_trace(Path(tmp) / "trace"), code_root=root)
            self.addCleanup(window.close)
            window.show()
            QApplication.processEvents()
            top = window.source_pane.tree.topLevelItem(0)
            assert top is not None
            file_item = item_by_path(top, "src/other.c")
            assert file_item is not None
            click_item(window, file_item)
            self.assertEqual(window.code_pane.tabs.count(), 2)
            self.assertEqual(window.code_pane.tabs.tabText(1), "other.c")
            widget = window.code_pane.tabs.widget(1)
            assert isinstance(widget, QPlainTextEdit)
            self.assertIn("int other(void)", widget.toPlainText())

    def test_duplicate_click_selects_the_existing_tab(self) -> None:
        """A second click on the same file selects its tab instead of opening another."""
        from PySide6.QtWidgets import QApplication

        from verdandi.gui.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            window = MainWindow(source_trace(Path(tmp) / "trace"), code_root=root)
            self.addCleanup(window.close)
            window.show()
            QApplication.processEvents()
            top = window.source_pane.tree.topLevelItem(0)
            assert top is not None
            file_item = item_by_path(top, "src/other.c")
            assert file_item is not None
            click_item(window, file_item)
            opened = window.code_pane.tabs.widget(1)
            click_item(window, file_item)
            self.assertEqual(window.code_pane.tabs.count(), 2)
            self.assertIs(window.code_pane.tabs.widget(1), opened)
            self.assertIs(window.code_pane.tabs.currentWidget(), opened)

    def test_function_item_click_opens_the_file(self) -> None:
        """A click on one of a file's function items opens that file in the Code pane."""
        from PySide6.QtWidgets import QApplication, QPlainTextEdit

        from verdandi.gui.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            source_tree(root)
            window = MainWindow(source_trace(Path(tmp) / "trace"), code_root=root)
            self.addCleanup(window.close)
            window.show()
            QApplication.processEvents()
            top = window.source_pane.tree.topLevelItem(0)
            assert top is not None
            file_item = item_by_path(top, "src/other.c")
            assert file_item is not None
            file_item.setExpanded(True)
            QApplication.processEvents()
            function_item = next(
                child
                for row in range(file_item.childCount())
                if (child := file_item.child(row)) is not None and child.text(0) == "other"
            )
            click_item(window, function_item)
            self.assertEqual(window.code_pane.tabs.count(), 2)
            self.assertEqual(window.code_pane.tabs.tabText(1), "other.c")
            widget = window.code_pane.tabs.widget(1)
            assert isinstance(widget, QPlainTextEdit)
            self.assertIn("int other(void)", widget.toPlainText())


if __name__ == "__main__":
    unittest.main()
