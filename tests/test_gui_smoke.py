"""Offscreen Qt smoke test: the player window opens and its keys move the walk."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_navigator import make_trace

HAVE_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class GuiSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        existing = QApplication.instance()
        self.app = existing if isinstance(existing, QApplication) else QApplication([])

    def test_gui_smoke(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from verdandi.gui.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            trace = make_trace(Path(tmp) / "trace")
            window = MainWindow(trace)
            self.addCleanup(window.close)
            window.show()
            self.assertEqual(len(window.stage_buttons), 3)
            self.assertEqual(window.model.rowCount(), 3)
            self.assertEqual(
                set(window.docks), {"Verilog", "Code", "Data", "Explanation", "Diff"}
            )
            titles = [window.title_label.text()]
            keys = (Qt.Key.Key_N, Qt.Key.Key_I, Qt.Key.Key_O, Qt.Key.Key_B, Qt.Key.Key_3)
            for key in keys:
                QTest.keyClick(window, key)
                titles.append(window.title_label.text())
        self.assertEqual(
            titles,
            [
                "Read architecture",
                "Processes",
                "proc",
                "Processes",
                "proc",
                "ABC: logic optimisation and K-LUT mapping",
            ],
        )
        self.assertEqual(window.navigator.current().id, "s0008")


if __name__ == "__main__":
    unittest.main()
