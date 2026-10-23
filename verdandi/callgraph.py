"""The call graph behind a step's code refs, for the Code pane's depth control (D8).

Depth 0 is the step's own code records. Depth > 0 adds the bodies of their callees, one ring
per level. Two sources, in order:

1. The code-review-graph database of the Odin III checkout
   (``ODIN3_ROOT/.code-review-graph/graph.db``), opened read-only. Its ``nodes`` table holds one
   row per function with ``file_path``, ``line_start`` and ``line_end``; its ``edges`` table
   holds ``CALLS`` rows from the caller's qualified name to the callee's. A callee edge whose
   target is a bare name (the graph's unresolved form) is resolved by function name, the same
   file first.
2. A static scan of the step's file: the section-6 C function-definition scan (``Locator``)
   finds the function spans, and a call-site scan of the body (an identifier followed by ``(``)
   names the callees, which are resolved against the same file's definitions only.

The expansion names the source it used so the pane can say so; nothing here writes the
checkout.
"""

from __future__ import annotations

import re
import sqlite3
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from verdandi.odin3.locator import Locator
from verdandi.trace import CodeRef

MAX_DEPTH = 5

GRAPH_DB = Path(".code-review-graph") / "graph.db"

SOURCE_NONE = "none"
SOURCE_GRAPH = "code-review-graph"
SOURCE_SCAN = "static scan"
SOURCE_NO_TREE = "no source tree"

# An identifier followed by ``(`` in a function body; a member call ``x.y(`` is not a C call.
_CALL = re.compile(r"(?<![\w.>])([A-Za-z_]\w*)\s*\(")

# Control statements that look like calls but define no function.
_NOT_CALLS = frozenset(
    {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case", "defined"}
)


@dataclass(frozen=True)
class Span:
    """One function body to show: a trace code record (depth 0) or a callee (depth > 0)."""

    file: str
    line: int
    end_line: int
    function: str | None
    depth: int


@dataclass(frozen=True)
class Expansion:
    """The spans the pane shows and where the call graph came from."""

    spans: tuple[Span, ...]
    source: str
    scanned: tuple[str, ...] = ()


def expand(root: Path | None, refs: list[CodeRef], depth: int) -> Expansion:
    """The step's refs at depth 0 plus callee bodies to ``depth``, with the source used."""
    seeds = tuple(Span(ref.file, ref.line, ref.end_line, ref.function, 0) for ref in refs)
    if depth <= 0 or not seeds:
        return Expansion(seeds, SOURCE_NONE)
    if root is None or not root.is_dir():
        return Expansion(seeds, SOURCE_NO_TREE)
    depth = min(depth, MAX_DEPTH)
    database = root / GRAPH_DB
    if database.is_file():
        try:
            extra = _graph_callees(root, database, refs, depth)
        except (sqlite3.Error, OSError):
            extra = None
        if extra is not None:
            return Expansion(seeds + tuple(extra), SOURCE_GRAPH)
    extra, scanned = _scan_callees(root, refs, depth)
    return Expansion(seeds + tuple(extra), SOURCE_SCAN, tuple(scanned))


def _connect(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=2.0)


def _graph_callees(
    root: Path, database: Path, refs: list[CodeRef], depth: int
) -> list[Span] | None:
    """The callee spans the database gives; None when the database is not readable as a graph."""
    with closing(_connect(database)) as connection:
        connection.execute("SELECT 1 FROM nodes LIMIT 1").fetchall()
        queue = deque(_seed_rows(connection, root, refs))
        seen = set(queue)
        spans: list[Span] = []
        for level in range(1, depth + 1):
            for _ in range(len(queue)):
                qualified = queue.popleft()
                for row in _callee_rows(connection, qualified, root):
                    target, span = row
                    if target in seen:
                        continue
                    seen.add(target)
                    queue.append(target)
                    spans.append(
                        Span(span.file, span.line, span.end_line, span.function, level)
                    )
    return spans


def _seed_rows(connection: sqlite3.Connection, root: Path, refs: list[CodeRef]) -> list[str]:
    """The qualified names of the refs' functions, resolved by name or by line."""
    found: list[str] = []
    for ref in refs:
        path = str(root / ref.file)
        if ref.function is not None:
            row = connection.execute(
                "SELECT qualified_name FROM nodes WHERE kind = 'Function' AND name = ?"
                " AND (file_path = ? OR file_path LIKE ?)"
                " ORDER BY (file_path = ?) DESC, qualified_name LIMIT 1",
                (ref.function, path, "%/" + ref.file, path),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT qualified_name FROM nodes WHERE kind = 'Function'"
                " AND (file_path = ? OR file_path LIKE ?)"
                " AND line_start <= ? AND line_end >= ?"
                " ORDER BY (file_path = ?) DESC, line_start DESC LIMIT 1",
                (path, "%/" + ref.file, ref.line, ref.line, path),
            ).fetchone()
        if row is not None and row[0] not in found:
            found.append(str(row[0]))
    return found


def _callee_rows(
    connection: sqlite3.Connection, qualified: str, root: Path
) -> list[tuple[str, Span]]:
    """The function nodes the CALLS edges of ``qualified`` reach, inside the source tree."""
    targets = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT target_qualified FROM edges"
            " WHERE kind = 'CALLS' AND source_qualified = ?",
            (qualified,),
        )
    ]
    found: list[tuple[str, Span]] = []
    for target in targets:
        if "::" in target:
            rows = connection.execute(
                "SELECT qualified_name, name, file_path, line_start, line_end FROM nodes"
                " WHERE kind = 'Function' AND qualified_name = ?",
                (target,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT qualified_name, name, file_path, line_start, line_end FROM nodes"
                " WHERE kind = 'Function' AND name = ?"
                " ORDER BY (file_path = ?) DESC, file_path, line_start LIMIT 1",
                (target, str(root)),
            ).fetchall()
        for row in rows:
            relative = _relative(root, str(row[2]))
            if relative is None or row[3] is None or row[4] is None:
                continue
            found.append(
                (
                    str(row[0]),
                    Span(relative, int(row[3]), int(row[4]), str(row[1]), 0),
                )
            )
    return found


def _relative(root: Path, file_path: str) -> str | None:
    """``file_path`` relative to ``root``; None when it lies outside the tree."""
    try:
        return str(Path(file_path).relative_to(root))
    except ValueError:
        try:
            return str(Path(file_path).resolve().relative_to(root.resolve()))
        except (OSError, ValueError):
            return None


def _scan_callees(
    root: Path, refs: list[CodeRef], depth: int
) -> tuple[list[Span], list[str]]:
    """The callee spans a call-site scan of the refs' files gives, and the files scanned."""
    locator = Locator(root)
    definitions: dict[str, list[CodeRef]] = {}
    texts: dict[str, list[str] | None] = {}

    def spans_of(file: str) -> list[CodeRef]:
        if file not in definitions:
            definitions[file] = locator.functions(Path(file))
        return definitions[file]

    def lines_of(file: str) -> list[str] | None:
        if file not in texts:
            try:
                text = (root / file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                texts[file] = None
            else:
                texts[file] = text.splitlines()
        return texts[file]

    queue: deque[tuple[CodeRef, int]] = deque()
    seen: set[tuple[str, str, int]] = set()
    for ref in refs:
        definition = _definition_of(spans_of(ref.file), ref)
        seed = definition if definition is not None else ref
        key = (seed.file, seed.function or "", seed.line)
        if key not in seen:
            seen.add(key)
            queue.append((seed, 0))
    spans: list[Span] = []
    scanned: list[str] = []
    while queue:
        definition, level = queue.popleft()
        if level >= depth:
            continue
        if definition.file not in scanned:
            scanned.append(definition.file)
        lines = lines_of(definition.file)
        if lines is None:
            continue
        body = "\n".join(lines[definition.line - 1 : definition.end_line])
        for name in _CALL.findall(body):
            if name in _NOT_CALLS:
                continue
            target = next(
                (span for span in spans_of(definition.file) if span.function == name), None
            )
            if target is None:
                continue
            key = (target.file, target.function or "", target.line)
            if key in seen:
                continue
            seen.add(key)
            spans.append(
                Span(target.file, target.line, target.end_line, target.function, level + 1)
            )
            queue.append((target, level + 1))
    return spans, scanned


def _definition_of(spans: list[CodeRef], ref: CodeRef) -> CodeRef | None:
    """The definition a ref names, by function name first, else by the line it covers."""
    if ref.function is not None:
        return next((span for span in spans if span.function == ref.function), None)
    return next(
        (span for span in spans if span.line <= ref.line <= span.end_line), None
    )
