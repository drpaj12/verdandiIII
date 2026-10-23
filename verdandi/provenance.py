"""Provenance locations: the trace's source-line records as small badges (D5, D6).

An IR snapshot object carries ``sources``: a list of source rows
``[file, line, col, end_line, end_col]`` (1-based, the recorder's convention). An AST node and
a symbol table row carry a ``loc`` string ``file:line:col``. Both become a ``Loc``: the file as
the trace names it, the start line and the end line. The badge is small: the file's basename and
the line (a range when ``end_line`` is past ``line``); the reference keeps the trace's path for
a tooltip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _basename(file: str) -> str:
    """The file name after the last slash, whichever slash an example source uses."""
    return file.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Loc:
    """One source location: the file the trace names, start line and end line."""

    file: str
    line: int
    end_line: int

    @property
    def badge(self) -> str:
        """The small provenance badge: basename and line, or basename and line range."""
        name = _basename(self.file)
        if self.end_line > self.line:
            return f"{name}:{self.line}-{self.end_line}"
        return f"{name}:{self.line}"

    @property
    def reference(self) -> str:
        """The full reference, trace path included, for a tooltip."""
        if self.end_line > self.line:
            return f"{self.file}:{self.line}-{self.end_line}"
        return f"{self.file}:{self.line}"


def _positive_int(value: Any) -> int | None:
    """An integer line number of at least 1; None for anything else."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def loc_from_source_row(row: Any) -> Loc | None:
    """One IR ``sources`` row as a Loc; None when it names no line.

    A row with no usable end line (0, or before its start line) runs to its start line.
    """
    if not isinstance(row, (list, tuple)) or len(row) < 4:
        return None
    file = str(row[0])
    line = _positive_int(row[1])
    if not file or line is None:
        return None
    end_line = _positive_int(row[3])
    if end_line is None or end_line < line:
        end_line = line
    return Loc(file=file, line=line, end_line=end_line)


def loc_from_text(text: Any) -> Loc | None:
    """An AST or symbol-table ``file:line:col`` loc string as a Loc; None when malformed."""
    if not isinstance(text, str):
        return None
    parts = text.rsplit(":", 2)
    if len(parts) != 3:
        return None
    file, line_text, _column = parts
    line = _positive_int(line_text)
    if not file or line is None:
        return None
    return Loc(file=file, line=line, end_line=line)


def object_loc(item: dict[str, Any]) -> Loc | None:
    """An IR node or net's first usable source row; None when it reports no loc."""
    sources = item.get("sources")
    if not isinstance(sources, list):
        return None
    return first_loc(sources)


def first_loc(rows: Any) -> Loc | None:
    """The first row of a source-row list that names a line; None when there is none."""
    if not isinstance(rows, (list, tuple)):
        return None
    for row in rows:
        loc = loc_from_source_row(row)
        if loc is not None:
            return loc
    return None
