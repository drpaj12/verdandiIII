"""The Verdandi III player window: stage map, title, step tree and pane docks."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from verdandi.navigator import Navigator
from verdandi.trace import Step, Trace

PANE_NAMES = ("Verilog", "Code", "Data", "Explanation", "Diff")
KEYS_HINT = "N next   I in   O out   B back   1-9 stage   Ctrl+F follow (again: next match)"


class MainWindow(QMainWindow):
    """One recorded walk: the stage map and step tree move the navigator, the panes follow.

    The panes themselves arrive in Task 11; this window keeps one empty dock per pane so
    the layout and the object names are stable.

    The window holds the keyboard focus: the stage buttons and the step tree are NoFocus, so a
    click never pulls the keys away, and the follow box only takes focus when clicked or on
    Ctrl+F. Space therefore always reaches the Next binding, whatever was clicked last.
    """

    def __init__(self, trace: Trace, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.trace = trace
        self.navigator = Navigator(trace)
        self.stage_buttons: list[QPushButton] = []
        self.title_label = QLabel()
        self.follow_edit = QLineEdit()
        self.tree = QTreeView()
        self.model = QStandardItemModel(self)
        self.items: dict[str, QStandardItem] = {}
        self.docks: dict[str, QDockWidget] = {}
        self.matches: list[Step] = []
        self.match_index = 0
        self.match_name = ""
        self._build()
        self._build_menus()
        self._refresh()
        self.setFocus()

    def _build(self) -> None:
        self.setWindowTitle(f"Verdandi III - {self.trace.manifest.top}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._stage_map())
        self.title_label.setObjectName("step-title")
        font = self.title_label.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        self.title_label.setFont(font)
        layout.addWidget(self.title_label)
        layout.addWidget(self._follow_row())
        self._build_tree()
        layout.addWidget(self.tree, 1)
        self.setCentralWidget(central)
        self._build_docks()
        self.statusBar().showMessage(KEYS_HINT)

    def _stage_map(self) -> QWidget:
        """A row of checkable buttons, one per root step: click to jump to the stage."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        for index, root in enumerate(self.trace.children(None)):
            button = QPushButton(f"{index + 1} {root.title}")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip(f"stage {index + 1}: {root.title}")
            button.clicked.connect(partial(self._jump_to_stage, index))
            layout.addWidget(button)
            self.stage_buttons.append(button)
        return row

    def _follow_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Follow:")
        self.follow_edit.setPlaceholderText("an object name, e.g. q[3]")
        self.follow_edit.setClearButtonEnabled(True)
        self.follow_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.follow_edit.returnPressed.connect(self._follow)
        layout.addWidget(label)
        layout.addWidget(self.follow_edit, 1)
        return row

    def _build_tree(self) -> None:
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._add_children(None, self.model.invisibleRootItem())

    def _add_children(self, parent_id: str | None, parent_item: QStandardItem) -> None:
        for step in self.trace.children(parent_id):
            item = QStandardItem(step.title)
            item.setData(step.id, Qt.ItemDataRole.UserRole)
            item.setEditable(False)
            parent_item.appendRow(item)
            self.items[step.id] = item
            self._add_children(step.id, item)

    def _build_docks(self) -> None:
        areas = {
            "Verilog": Qt.DockWidgetArea.RightDockWidgetArea,
            "Code": Qt.DockWidgetArea.RightDockWidgetArea,
            "Data": Qt.DockWidgetArea.RightDockWidgetArea,
            "Explanation": Qt.DockWidgetArea.BottomDockWidgetArea,
            "Diff": Qt.DockWidgetArea.BottomDockWidgetArea,
        }
        for name in PANE_NAMES:
            dock = QDockWidget(name, self)
            dock.setObjectName(f"dock-{name.lower()}")
            placeholder = QLabel(f"{name} pane (Task 11)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dock.setWidget(placeholder)
            self.addDockWidget(areas[name], dock)
            self.docks[name] = dock

    def _build_menus(self) -> None:
        view_menu = self.menuBar().addMenu("View")
        assert view_menu is not None
        for dock in self.docks.values():
            view_menu.addAction(dock.toggleViewAction())

    def _refresh(self) -> None:
        step = self.navigator.current()
        self.title_label.setText(step.title)
        self._sync_stage_map(step)
        self._sync_tree(step)

    def _sync_stage_map(self, step: Step) -> None:
        root = self._root_of(step)
        roots = self.trace.children(None)
        index = next(i for i, candidate in enumerate(roots) if candidate.id == root.id)
        for i, button in enumerate(self.stage_buttons):
            button.setChecked(i == index)

    def _sync_tree(self, step: Step) -> None:
        index = self.items[step.id].index()
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        if self.model.hasChildren(index):
            self.tree.expand(index)

    def _root_of(self, step: Step) -> Step:
        while step.parent is not None:
            step = self.trace.step(step.parent)
        return step

    def _jump_to_stage(self, index: int, _checked: bool = False) -> None:
        self.navigator.jump_stage(index)
        self._refresh()

    def _follow(self) -> None:
        name = self.follow_edit.text().strip()
        if not name:
            return
        self.matches = self.navigator.follow(name)
        self.match_name = name
        self.match_index = 0
        self.setFocus()
        self._refresh()
        if self.matches:
            self._show_match()
        else:
            self.statusBar().showMessage(f"no step touches {name}")

    def _show_match(self) -> None:
        self.statusBar().showMessage(
            f"match {self.match_index + 1} of {len(self.matches)}: {self.match_name}"
        )

    def _next_match(self) -> None:
        """Cycle to the next follow match, wrapping after the last one."""
        self.match_index = (self.match_index + 1) % len(self.matches)
        self.navigator.move_to(self.matches[self.match_index].id)
        self.setFocus()
        self._refresh()
        self._show_match()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()  # an int in PySide6, not a Qt.Key member
        control = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_F.value and control:
            name = self.follow_edit.text().strip()
            if name and name == self.match_name and self.matches:
                self._next_match()
            else:
                self.follow_edit.setFocus()
                self.follow_edit.selectAll()
            event.accept()
            return
        index = key - Qt.Key.Key_1.value
        if key in (Qt.Key.Key_N.value, Qt.Key.Key_Space.value):
            self.navigator.next()
        elif key in (Qt.Key.Key_I.value, Qt.Key.Key_Return.value, Qt.Key.Key_Enter.value):
            self.navigator.step_in()
        elif key in (Qt.Key.Key_O.value, Qt.Key.Key_Backspace.value):
            self.navigator.step_out()
        elif key == Qt.Key.Key_B.value:
            self.navigator.back()
        elif 0 <= index < len(self.stage_buttons):
            self.navigator.jump_stage(index)
        else:
            super().keyPressEvent(event)
            return
        self._refresh()
        event.accept()
