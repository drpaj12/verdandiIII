"""Shared test helpers: Odin III, ABC and Graphviz availability."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _odin3_root() -> Path | None:
    value = os.environ.get("ODIN3_ROOT")
    if value:
        root = Path(value)
        if root.is_dir():
            return root
    return None


ODIN3_ROOT: Path | None = _odin3_root()


def _odin3_available() -> bool:
    """True when the odin3 binding imports and its shared library loads."""
    try:
        import odin3

        odin3.default()
    except Exception:
        return False
    return True


def abc_binary() -> str | None:
    """The standalone ABC binary: $ODIN3_ABC, else build/*/third_party/abc/abc."""
    configured = os.environ.get("ODIN3_ABC")
    if configured:
        path = Path(configured)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    if ODIN3_ROOT is not None:
        for candidate in sorted(ODIN3_ROOT.glob("build/*/third_party/abc/abc")):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


HAVE_ODIN3: bool = _odin3_available()
HAVE_ABC: bool = abc_binary() is not None
HAVE_DOT: bool = shutil.which("dot") is not None
