"""The call graph behind a step's code refs, for the Code pane's depth control (D8).

Depth 0 is the step's own code records. Depth > 0 adds the bodies of their callees, one ring
per level. Two sources, in order:

1. The code-review-graph database of the Odin III checkout
   (``ODIN3_ROOT/.code-review-graph/graph.db``), opened read-only. Its ``nodes`` table holds one
   row per function with ``file_path``, ``line_start`` and ``line_end``; its ``edges`` table
   holds ``CALLS`` rows from the caller's qualified name to the callee's. A callee edge whose
   target is a bare name (the graph's unresolved form) is resolved by function name, the same
   file first, else only when the name is unique in the tree.
2. A static scan of the step's file: the section-6 C function-definition scan (``Locator``)
   finds the function spans, and a call-site scan of the body (an identifier followed by ``(``)
   names the callees, which are resolved against the same file's definitions only.

A record that names no function but covers whole functions (a pass's whole-file record) seeds
every function of its file, and the expansion says so: the database note reads "file scope".
An unreadable file is never named as scanned.

The expansion names the source it used so the pane can say so. The database is opened
read-only, so ``graph.db`` and its ``-wal`` are never written; SQLite may create or touch the
``graph.db-shm`` shared-memory file beside it as read-side bookkeeping.
"""

from __future__ import annotations

import re
import sqlite3
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from verdandi.odin3.locator import Locator, _skip_comment, _skip_literal
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
    """The spans the pane shows and where the call graph came from.

    ``file_scope`` is True when a record covered no single function and the expansion seeded
    every function of its file, which the pane's source note repeats.
    """

    spans: tuple[Span, ...]
    source: str
    scanned: tuple[str, ...] = ()
    file_scope: bool = False


def expand(root: Path | None, refs: list[CodeRef], depth: int) -> Expansion:
    """The step's refs at depth 0 plus callee bodies to ``depth``, with the source used."""
    seeds = _seed_spans(root, refs)
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
            spans, file_scope = extra
            return Expansion(seeds + tuple(spans), SOURCE_GRAPH, file_scope=file_scope)
    extra_spans, scanned = _scan_callees(root, refs, depth)
    return Expansion(seeds + tuple(extra_spans), SOURCE_SCAN, tuple(scanned))


def _seed_spans(root: Path | None, refs: list[CodeRef]) -> tuple[Span, ...]:
    """The refs' spans; a record naming a function takes that function's located body.

    A rule event's record names its function but spans the one line of the log call; depth 0
    shows the function body D8 describes, so the record is widened to the definition the
    section-6 scan locates. Without a source tree, or without a located definition, the
    record's own span stays.
    """
    locator = Locator(root) if root is not None else None
    definitions: dict[str, list[CodeRef]] = {}
    spans: list[Span] = []
    for ref in refs:
        span = Span(ref.file, ref.line, ref.end_line, ref.function, 0)
        if locator is not None and ref.function is not None:
            if ref.file not in definitions:
                definitions[ref.file] = locator.functions(Path(ref.file))
            found = next(
                (item for item in definitions[ref.file] if item.function == ref.function), None
            )
            if found is not None:
                span = Span(ref.file, found.line, found.end_line, ref.function, 0)
        spans.append(span)
    return tuple(spans)


def _connect(database: Path) -> sqlite3.Connection:
    """A read-only connection; SQLite may still touch graph.db-shm for WAL bookkeeping."""
    return sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=2.0)


def _graph_callees(
    root: Path, database: Path, refs: list[CodeRef], depth: int
) -> tuple[list[Span], bool] | None:
    """The callee spans the database gives and whether a file scope seeded them.

    None when the database is not readable as a graph.
    """
    with closing(_connect(database)) as connection:
        connection.execute("SELECT 1 FROM nodes LIMIT 1").fetchall()
        seeds, file_scope = _seed_rows(connection, root, refs)
        queue = deque(seeds)
        seen = set(queue)
        spans: list[Span] = []
        for level in range(1, depth + 1):
            for _ in range(len(queue)):
                qualified = queue.popleft()
                for target, span in _callee_rows(connection, qualified, root):
                    if target in seen:
                        continue
                    seen.add(target)
                    queue.append(target)
                    spans.append(
                        Span(span.file, span.line, span.end_line, span.function, level)
                    )
    return spans, file_scope


def _seed_rows(
    connection: sqlite3.Connection, root: Path, refs: list[CodeRef]
) -> tuple[list[str], bool]:
    """The qualified names of the refs' functions, resolved by name or by record span.

    A record without a function seeds every function its span intersects, so a whole-file
    record reaches all of its file's functions. When the span meets no function, the whole
    file's functions seed the expansion instead, and the returned flag says so.
    """
    found: list[str] = []
    file_scope = False
    for ref in refs:
        path = str(root / ref.file)
        if ref.function is not None:
            row = connection.execute(
                "SELECT qualified_name FROM nodes WHERE kind = 'Function' AND name = ?"
                " AND (file_path = ? OR file_path LIKE ? ESCAPE '\\')"
                " ORDER BY (file_path = ?) DESC, qualified_name LIMIT 1",
                (ref.function, path, _like_suffix(ref.file), path),
            ).fetchone()
            if row is not None and row[0] not in found:
                found.append(str(row[0]))
            continue
        rows = connection.execute(
            "SELECT qualified_name FROM nodes WHERE kind = 'Function'"
            " AND (file_path = ? OR file_path LIKE ? ESCAPE '\\')"
            " AND line_start <= ? AND line_end >= ?"
            " ORDER BY (file_path = ?) DESC, line_start",
            (path, _like_suffix(ref.file), ref.end_line, ref.line, path),
        ).fetchall()
        if not rows:
            rows = connection.execute(
                "SELECT qualified_name FROM nodes WHERE kind = 'Function'"
                " AND (file_path = ? OR file_path LIKE ? ESCAPE '\\')"
                " ORDER BY (file_path = ?) DESC, line_start",
                (path, _like_suffix(ref.file), path),
            ).fetchall()
            if rows:
                file_scope = True
        elif len(rows) > 1:
            file_scope = True
        for row in rows:
            if row[0] not in found:
                found.append(str(row[0]))
    return found, file_scope


def _callee_rows(
    connection: sqlite3.Connection, qualified: str, root: Path
) -> list[tuple[str, Span]]:
    """The function nodes the CALLS edges of ``qualified`` reach, inside the source tree.

    A qualified target names one node. A bare target (the graph's unresolved form) is resolved
    by function name: the caller's own file wins, else the name must be unique in the tree, as
    a wrong body would be worse than no callee.
    """
    caller = connection.execute(
        "SELECT file_path FROM nodes WHERE qualified_name = ?", (qualified,)
    ).fetchone()
    caller_file = "" if caller is None else str(caller[0])
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
                " WHERE kind = 'Function' AND name = ?",
                (target,),
            ).fetchall()
            rows = _unambiguous(rows, caller_file, root)
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


def _unambiguous(
    rows: list[tuple[object, ...]], caller_file: str, root: Path
) -> list[tuple[object, ...]]:
    """Bare-name candidates: the caller's file's definition, else the only one in the tree."""
    in_tree = [row for row in rows if _relative(root, str(row[2])) is not None]
    same_file = [row for row in in_tree if str(row[2]) == caller_file]
    if same_file:
        return same_file[:1]
    return in_tree if len(in_tree) == 1 else []


def _like_suffix(file: str) -> str:
    """A ``LIKE`` pattern for the tail of a path, with the file's own wildcards escaped."""
    escaped = file.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%/" + escaped


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

    def push(definition: CodeRef) -> None:
        key = (definition.file, definition.function or "", definition.line)
        if key not in seen:
            seen.add(key)
            queue.append((definition, 0))

    for ref in refs:
        file_definitions = spans_of(ref.file)
        if ref.function is not None:
            push(_definition_of(file_definitions, ref) or ref)
            continue
        intersecting = [
            span
            for span in file_definitions
            if span.line <= ref.end_line and span.end_line >= ref.line
        ]
        if intersecting or file_definitions:
            for span in intersecting or file_definitions:
                push(span)
        else:
            push(ref)
    spans: list[Span] = []
    scanned: list[str] = []
    while queue:
        definition, level = queue.popleft()
        if level >= depth:
            continue
        lines = lines_of(definition.file)
        if lines is None:
            continue
        if definition.file not in scanned:
            scanned.append(definition.file)
        body = _code_only("\n".join(lines[definition.line - 1 : definition.end_line]))
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


def _code_only(text: str) -> str:
    """``text`` with C comments and string or character literals replaced by spaces.

    A call name in a comment or a format string is no call; the Locator's scanners define
    where a comment or a literal ends.
    """
    parts: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "/" and text.startswith(("/*", "//"), index):
            index = _skip_comment(text, index)
        elif char in "\"'":
            index = _skip_literal(text, index)
        else:
            parts.append(char)
            index += 1
            continue
        parts.append(" ")
    return "".join(parts)


def _definition_of(spans: list[CodeRef], ref: CodeRef) -> CodeRef | None:
    """The definition a ref names, by function name first, else by the line it covers."""
    if ref.function is not None:
        return next((span for span in spans if span.function == ref.function), None)
    return next(
        (span for span in spans if span.line <= ref.line <= span.end_line), None
    )
