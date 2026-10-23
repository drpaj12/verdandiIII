"""Call-graph tests (D8): the code-review-graph database first, a static scan otherwise."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from verdandi.callgraph import (
    MAX_DEPTH,
    SOURCE_GRAPH,
    SOURCE_NO_TREE,
    SOURCE_NONE,
    SOURCE_SCAN,
    expand,
)
from verdandi.trace import CodeRef

SOURCE = """int leaf(int x) {
    return x + 1;
}

int mid(int y) {
    return leaf(y);
}

int top(int y) {
    int a = mid(y);
    printf("a=%d\\n", a);
    return a;
}
"""

TOP = CodeRef(file="src/a.c", line=9, end_line=13, function="top")
MID = CodeRef(file="src/a.c", line=5, end_line=7, function="mid")
LEAF = CodeRef(file="src/a.c", line=1, end_line=3, function="leaf")


def write_source(root: Path, text: str = SOURCE) -> None:
    path = root / "src" / "a.c"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


def make_graph_db(
    root: Path,
    nodes: list[tuple[str, str, str, str, int, int]],
    edges: list[tuple[str, str, str]],
) -> Path:
    """A minimal database with the columns the graph reader uses."""
    db = root / ".code-review-graph" / "graph.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE nodes (kind TEXT, name TEXT, qualified_name TEXT,"
            " file_path TEXT, line_start INTEGER, line_end INTEGER)"
        )
        con.execute(
            "CREATE TABLE edges (kind TEXT, source_qualified TEXT, target_qualified TEXT)"
        )
        con.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?)", nodes)
        con.executemany("INSERT INTO edges VALUES (?, ?, ?)", edges)
    return db


def graph_nodes(root: Path) -> list[tuple[str, str, str, str, int, int]]:
    path = str(root / "src" / "a.c")
    return [
        ("Function", "top", f"{path}::top", path, 9, 13),
        ("Function", "mid", f"{path}::mid", path, 5, 7),
        ("Function", "leaf", f"{path}::leaf", path, 1, 3),
    ]


def expanded(refs: list[CodeRef], depth: int) -> list[tuple[str | None, int]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_source(root)
        result = expand(root, refs, depth)
    return [(span.function, span.depth) for span in result.spans]


class StaticScanTest(unittest.TestCase):
    def test_depth_zero_is_the_step_functions_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root)
            result = expand(root, [TOP], 0)
        self.assertEqual(result.source, SOURCE_NONE)
        self.assertEqual(
            [(span.function, span.depth) for span in result.spans], [("top", 0)]
        )

    def test_depth_one_adds_a_direct_callee(self) -> None:
        self.assertEqual(
            expanded([TOP], 1), [("top", 0), ("mid", 1)]
        )

    def test_depth_two_adds_the_next_ring(self) -> None:
        self.assertEqual(
            expanded([TOP], 2), [("top", 0), ("mid", 1), ("leaf", 2)]
        )

    def test_undefined_calls_are_skipped(self) -> None:
        """printf has no definition in the file, so the scan does not follow it."""
        functions = [name for name, _depth in expanded([TOP], 2)]
        self.assertNotIn("printf", functions)

    def test_scan_note_names_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root)
            result = expand(root, [TOP], 1)
        self.assertEqual(result.source, SOURCE_SCAN)
        self.assertEqual(result.scanned, ("src/a.c",))

    def test_depth_is_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root)
            result = expand(root, [TOP], MAX_DEPTH + 5)
        self.assertEqual([span.depth for span in result.spans], [0, 1, 2])

    def test_no_source_tree(self) -> None:
        result = expand(None, [TOP], 2)
        self.assertEqual(result.source, SOURCE_NO_TREE)
        self.assertEqual([(span.function, span.depth) for span in result.spans], [("top", 0)])

    def test_ref_without_a_function_resolves_by_line(self) -> None:
        """A log-line ref names its line only; the scan still finds the enclosing body."""
        ref = CodeRef(file="src/a.c", line=10, end_line=10, function=None)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root)
            result = expand(root, [ref], 1)
        self.assertEqual(
            [(span.function, span.depth) for span in result.spans],
            [(None, 0), ("mid", 1)],
        )


class GraphDatabaseTest(unittest.TestCase):
    def test_graph_database_is_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            make_graph_db(
                root,
                graph_nodes(root),
                [
                    ("CALLS", f"{path}::top", f"{path}::mid"),
                    ("CALLS", f"{path}::mid", "leaf"),
                ],
            )
            result = expand(root, [TOP], 2)
        self.assertEqual(result.source, SOURCE_GRAPH)
        self.assertEqual(
            [(span.function, span.depth) for span in result.spans],
            [("top", 0), ("mid", 1), ("leaf", 2)],
        )

    def test_graph_cycle_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            make_graph_db(
                root,
                graph_nodes(root),
                [
                    ("CALLS", f"{path}::top", f"{path}::mid"),
                    ("CALLS", f"{path}::mid", f"{path}::leaf"),
                    ("CALLS", f"{path}::leaf", f"{path}::top"),
                ],
            )
            result = expand(root, [TOP], MAX_DEPTH)
        self.assertEqual(
            [span.function for span in result.spans], ["top", "mid", "leaf"]
        )

    def test_ambiguous_bare_name_is_skipped(self) -> None:
        """Two files define ``leaf``; a caller in a third file has no single answer."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            other = str(root / "src" / "b.c")
            third = str(root / "src" / "c.c")
            nodes = [
                ("Function", "top", f"{path}::top", path, 9, 13),
                ("Function", "mid", f"{path}::mid", path, 5, 7),
                ("Function", "leaf", f"{other}::leaf", other, 20, 22),
                ("Function", "leaf", f"{third}::leaf", third, 20, 22),
            ]
            make_graph_db(
                root,
                nodes,
                [("CALLS", f"{path}::top", "leaf")],
            )
            result = expand(root, [TOP], 1)
        self.assertEqual([span.function for span in result.spans], ["top"])

    def test_bare_name_prefers_the_caller_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            other = str(root / "src" / "b.c")
            nodes = [
                *graph_nodes(root),
                ("Function", "shared", f"{other}::shared", other, 20, 22),
                ("Function", "shared", f"{path}::shared", path, 20, 22),
            ]
            make_graph_db(
                root,
                nodes,
                [("CALLS", f"{path}::top", "shared")],
            )
            result = expand(root, [TOP], 1)
        self.assertEqual(
            [(span.function, span.file) for span in result.spans[1:]],
            [("shared", "src/a.c")],
        )

    def test_seed_like_pattern_does_not_wildcard_an_underscore(self) -> None:
        """src/axb.c must not resolve to the database's src/a_b.c through LIKE's wildcards."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a_b.c")
            make_graph_db(
                root,
                [
                    ("Function", "top", f"{path}::top", path, 1, 3),
                    ("Function", "mid", f"{path}::mid", path, 5, 7),
                ],
                [("CALLS", f"{path}::top", f"{path}::mid")],
            )
            ref = CodeRef(file="src/axb.c", line=1, end_line=3, function="top")
            result = expand(root, [ref], 1)
        self.assertEqual(result.source, SOURCE_GRAPH)
        self.assertEqual([span.function for span in result.spans], ["top"])

    def test_graph_callee_outside_the_tree_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            nodes = [
                *graph_nodes(root),
                ("Function", "shared", "/elsewhere/lib.c::shared", "/elsewhere/lib.c", 1, 2),
            ]
            make_graph_db(
                root,
                nodes,
                [
                    ("CALLS", f"{path}::top", f"{path}::mid"),
                    ("CALLS", f"{path}::top", "/elsewhere/lib.c::shared"),
                ],
            )
            result = expand(root, [TOP], 1)
        self.assertEqual([span.function for span in result.spans], ["top", "mid"])

    def test_unreadable_database_falls_back_to_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root)
            db = root / ".code-review-graph" / "graph.db"
            db.parent.mkdir(parents=True)
            db.write_bytes(b"not a database\n")
            result = expand(root, [TOP], 1)
        self.assertEqual(result.source, SOURCE_SCAN)
        self.assertEqual(
            [(span.function, span.depth) for span in result.spans],
            [("top", 0), ("mid", 1)],
        )

    def test_graph_resolves_a_ref_by_its_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_source(root, "")
            path = str(root / "src" / "a.c")
            make_graph_db(
                root,
                graph_nodes(root),
                [("CALLS", f"{path}::top", f"{path}::mid")],
            )
            ref = CodeRef(file="src/a.c", line=10, end_line=10, function=None)
            result = expand(root, [ref], 1)
        self.assertEqual(
            [(span.function, span.depth) for span in result.spans],
            [(None, 0), ("mid", 1)],
        )


if __name__ == "__main__":
    unittest.main()
