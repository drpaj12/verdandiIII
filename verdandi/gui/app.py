"""Entry point of ``verdandi-gui`` and of ``verdandi play``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog

from verdandi.gui.mainwindow import MainWindow
from verdandi.trace import Trace, load


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verdandi-gui", description="Verdandi III player")
    parser.add_argument("trace", nargs="?", help="trace directory written by verdandi record")
    return parser


def player(trace: Trace) -> int:
    """Show the player for a loaded trace; reuse a QApplication when one exists."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    window = MainWindow(trace)
    window.show()
    return app.exec()


def _choose(settings: QSettings) -> Path | None:
    last = settings.value("lastTrace")
    if isinstance(last, str) and (Path(last) / "manifest.json").is_file():
        return Path(last)
    chosen = QFileDialog.getExistingDirectory(None, "Open trace")
    return Path(chosen) if chosen else None


def _load(directory: Path) -> Trace | None:
    try:
        return load(directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"verdandi-gui: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    settings = QSettings("verdandi", "verdandi-gui")
    directory = Path(args.trace) if args.trace else _choose(settings)
    if directory is None:
        return 0
    trace = _load(directory)
    if trace is None:
        return 2
    settings.setValue("lastTrace", str(trace.directory))
    window = MainWindow(trace)
    window.show()
    return app.exec()
