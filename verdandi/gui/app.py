"""Entry point of ``verdandi-gui`` and of ``verdandi play``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from verdandi.trace import Trace, load

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings

GUI_HINT = 'pip install "verdandi[gui]"'
SETTINGS_ORGANISATION = "verdandi"
SETTINGS_APPLICATION = "verdandi-gui"
CODE_ROOT_KEY = "codeRoot"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verdandi-gui", description="Verdandi III player")
    parser.add_argument("trace", nargs="?", help="trace directory written by verdandi record")
    return parser


def _settings() -> QSettings:
    from PySide6.QtCore import QSettings

    return QSettings(SETTINGS_ORGANISATION, SETTINGS_APPLICATION)


def code_root_setting(settings: QSettings) -> Path | None:
    """The app's code root setting when it names a directory, else None.

    The player's root choice: the ``codeRoot`` setting wins over ``ODIN3_ROOT``, which the Code
    pane still falls back to when the setting is unset or stale.
    """
    value = settings.value(CODE_ROOT_KEY)
    if isinstance(value, str) and value:
        path = Path(value)
        if path.is_dir():
            return path
    return None


def player(trace: Trace) -> int:
    """Show the player for a loaded trace; reuse a QApplication when one exists.

    Qt is imported here, not at module load, so ``verdandi play`` can report a missing
    gui extra with its own clean message.
    """
    from PySide6.QtWidgets import QApplication

    from verdandi.gui.mainwindow import MainWindow

    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    window = MainWindow(trace, code_root=code_root_setting(_settings()))
    window.show()
    return app.exec()


def _choose(settings: QSettings) -> Path | None:
    from PySide6.QtWidgets import QFileDialog

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
    try:
        from PySide6.QtWidgets import QApplication

        from verdandi.gui.mainwindow import MainWindow
    except ImportError as exc:
        print(
            f"verdandi-gui: the player needs PySide6 ({exc}); {GUI_HINT}",
            file=sys.stderr,
        )
        return 2
    app = QApplication(sys.argv[:1])
    settings = _settings()
    directory = Path(args.trace) if args.trace else _choose(settings)
    if directory is None:
        return 0
    trace = _load(directory)
    if trace is None:
        return 2
    settings.setValue("lastTrace", str(trace.directory))
    window = MainWindow(trace, code_root=code_root_setting(settings))
    window.show()
    return app.exec()
