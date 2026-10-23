"""Pane tests: Verilog highlight columns, code fallback, data filter, explanation order, no dot."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_navigator import make_manifest
from verdandi.trace import CodeRef, Diff, ObjRef, Step, Trace, load, save

HAVE_QT = importlib.util.find_spec("PySide6") is not None


def ir_snapshot(modules: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "ir", "modules": modules}


def write_sources(directory: Path) -> list[Path]:
    """A CRLF source (a plain identifier) and a tab-indented source beside the trace."""
    crlf = directory / "crlf.v"
    crlf.write_bytes(b"module crlf;\r\n  wire alpha;\r\nendmodule\r\n")
    tab = directory / "tab.v"
    tab.write_bytes(b"module tab;\n\twire beta;\nendmodule\n")
    return [crlf, tab]


def highlight_trace(directory: Path, span_paths: bool = False) -> Trace:
    """A one-net-per-source trace; with ``span_paths`` the rows carry the read paths."""
    sources = write_sources(directory.parent)
    crlf = str(directory.parent / "crlf.v") if span_paths else "crlf.v"
    tab = str(directory.parent / "tab.v") if span_paths else "tab.v"
    snapshot = ir_snapshot(
        [
            {
                "name": "m",
                "nodes": [],
                "nets": [
                    {
                        "id": 10,
                        "name": "alpha",
                        "drivers": [],
                        "sinks": [],
                        "sources": [[crlf, 2, 8, 2, 13]],
                    },
                    {
                        "id": 11,
                        "name": "beta",
                        "drivers": [],
                        "sinks": [],
                        "sources": [[tab, 2, 7, 2, 11]],
                    },
                ],
                "wires": [],
            }
        ]
    )
    diff = Diff(
        added=[ObjRef("m", "net", 10, "alpha"), ObjRef("m", "net", 11, "beta")],
        removed=[],
        changed=[],
        by_name=False,
    )
    steps = [
        Step(
            id="s0001",
            parent=None,
            level=0,
            title="Read",
            anchor="pass:read_verilog",
            snapshot="s0001.json",
            diff=diff,
        )
    ]
    save(directory, make_manifest(), steps, {"s0001.json": snapshot}, sources)
    return load(directory)


def data_trace(directory: Path) -> Trace:
    snapshot = ir_snapshot(
        [
            {
                "name": "counter2",
                "nodes": [
                    {"id": 1, "name": "a", "type": "$dff", "params": {}, "pins": [], "sources": []},
                    {"id": 2, "name": "b", "type": "$not", "params": {}, "pins": [], "sources": []},
                ],
                "nets": [
                    {"id": 20, "name": "q", "drivers": [1], "sinks": [2], "sources": []}
                ],
                "wires": [],
            }
        ]
    )
    diff = Diff(
        added=[],
        removed=[],
        changed=[ObjRef("counter2", "node", 1, "a")],
        by_name=False,
    )
    steps = [
        Step(
            id="s0001",
            parent=None,
            level=1,
            title="opt",
            anchor="pass:opt",
            snapshot="s0001.json",
            diff=diff,
        )
    ]
    save(directory, make_manifest(), steps, {"s0001.json": snapshot}, [])
    return load(directory)


def ast_trace(directory: Path, form: str = "ELABORATED") -> Trace:
    """One AST step: module m declares input clk and uses it on a line below."""
    snapshot = {
        "kind": "ast",
        "form": form,
        "roots": [
            {
                "kind": "UNIT",
                "sub": "",
                "name": "m.v",
                "loc": "m.v:1:1",
                "children": [
                    {
                        "kind": "MODULE",
                        "sub": "",
                        "name": "m",
                        "loc": "m.v:1:1",
                        "children": [
                            {
                                "kind": "LIST",
                                "sub": "",
                                "name": "",
                                "loc": "m.v:1:10",
                                "children": [
                                    {
                                        "kind": "PORT_DECL",
                                        "sub": "input",
                                        "name": "",
                                        "loc": "m.v:1:11",
                                        "children": [
                                            {
                                                "kind": "DECLARATOR",
                                                "sub": "",
                                                "name": "clk",
                                                "loc": "m.v:1:17",
                                                "children": [],
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "kind": "CONT_ASSIGN",
                                "sub": "",
                                "name": "",
                                "loc": "m.v:2:1",
                                "children": [
                                    {
                                        "kind": "IDENT",
                                        "sub": "",
                                        "name": "clk",
                                        "loc": "m.v:2:11",
                                        "children": [],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    steps = [
        Step(
            id="s0001",
            parent=None,
            level=2,
            title=form.title(),
            anchor="pass:read_verilog",
            snapshot="s0001.json",
            diff=Diff(added=[], removed=[], changed=[], by_name=False),
        )
    ]
    save(directory, make_manifest(), steps, {"s0001.json": snapshot}, [])
    return load(directory)


def picture_trace(directory: Path) -> Trace:
    """An ABC step: a picture and no snapshot."""
    dot = directory.parent / "abc.dot"
    dot.write_text("digraph G { a -> b; }\n", encoding="utf-8")
    steps = [
        Step(
            id="s0001",
            parent=None,
            level=2,
            title="balance",
            anchor="abc:balance",
            diff=Diff(added=[], removed=[], changed=[], by_name=False),
            picture="s0001.dot",
        )
    ]
    save(
        directory,
        make_manifest(),
        steps,
        {},
        [],
        pictures={"s0001.dot": dot},
    )
    return load(directory)


def removed_trace(directory: Path) -> Trace:
    """Two steps: the first holds a net the second's diff removes."""
    sources = write_sources(directory.parent)
    before = ir_snapshot(
        [
            {
                "name": "m",
                "nodes": [],
                "nets": [
                    {
                        "id": 10,
                        "name": "alpha",
                        "drivers": [],
                        "sinks": [],
                        "sources": [["crlf.v", 2, 8, 2, 13]],
                    }
                ],
                "wires": [],
            }
        ]
    )
    after = ir_snapshot([{"name": "m", "nodes": [], "nets": [], "wires": []}])
    steps = [
        Step(
            id="s0001",
            parent=None,
            level=1,
            title="read_verilog",
            anchor="pass:read_verilog",
            snapshot="s0001.json",
        ),
        Step(
            id="s0002",
            parent=None,
            level=1,
            title="opt",
            anchor="pass:opt",
            snapshot="s0002.json",
            diff=Diff(
                added=[],
                removed=[ObjRef("m", "net", 10, "alpha")],
                changed=[],
                by_name=False,
            ),
        ),
    ]
    save(
        directory,
        make_manifest(),
        steps,
        {"s0001.json": before, "s0002.json": after},
        sources,
    )
    return load(directory)


def code_trace(directory: Path, root: Path) -> Trace:
    """One step whose CodeRef names a file under ``root``."""
    source = root / "src" / "passes" / "opt" / "opt.c"
    source.parent.mkdir(parents=True)
    source.write_text("int one;\nint two;\n", encoding="utf-8")
    step = Step(
        id="s0001",
        parent=None,
        level=1,
        title="opt",
        anchor="pass:opt",
        code=[
            CodeRef(
                file="src/passes/opt/opt.c", line=2, end_line=2, function="opt"
            )
        ],
    )
    return Trace(directory, make_manifest(), [step])


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class PaneTest(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        existing = QApplication.instance()
        self.app = existing if isinstance(existing, QApplication) else QApplication([])

    def test_highlight_columns(self) -> None:
        from verdandi.gui.verilogpane import VerilogPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = highlight_trace(Path(tmp) / "trace")
            pane = VerilogPane()
            pane.show(trace.steps[0], trace)
            self.assertEqual(pane.highlighted_texts(), ["alpha", "beta"])

    def test_highlight_span_paths(self) -> None:
        """A real trace's span names the read_verilog path, not the tab's basename."""
        from verdandi.gui.verilogpane import VerilogPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = highlight_trace(Path(tmp) / "trace", span_paths=True)
            pane = VerilogPane()
            pane.show(trace.steps[0], trace)
            self.assertEqual(pane.highlighted_texts(), ["alpha", "beta"])

    def test_highlight_removed_span(self) -> None:
        """A removed object's spans come from the nearest earlier snapshot, in their own colour."""
        from verdandi.gui.verilogpane import REMOVED_HIGHLIGHT, VerilogPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = removed_trace(Path(tmp) / "trace")
            pane = VerilogPane()
            pane.show(trace.steps[1], trace)
            self.assertEqual(pane.highlighted_texts(), ["alpha"])
            colours = [
                selection.format.background().color().name()
                for selection in pane.editors["crlf.v"].extraSelections()
            ]
        self.assertEqual(colours, [REMOVED_HIGHLIGHT.name()])

    def test_code_missing_file(self) -> None:
        from PySide6.QtWidgets import QPlainTextEdit

        from verdandi.gui.codepane import CodePane

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = CodeRef(
                file="src/passes/nope/nope.c", line=3, end_line=5, function="nope"
            )
            step = Step(
                id="s0001",
                parent=None,
                level=1,
                title="nope",
                anchor="pass:nope",
                code=[ref],
            )
            trace = Trace(root / "trace", make_manifest(), [step])
            pane = CodePane(root=root)
            pane.show(step, trace)
            self.assertEqual(pane.tabs.count(), 1)
            widget = pane.tabs.widget(0)
            self.assertIsInstance(widget, QPlainTextEdit)
            assert isinstance(widget, QPlainTextEdit)
            self.assertIn(
                "source not available: src/passes/nope/nope.c", widget.toPlainText()
            )

    def test_code_line_past_eof(self) -> None:
        """A ref past the file's last line highlights nothing and logs no invalid cursor."""
        from PySide6.QtWidgets import QPlainTextEdit

        from verdandi.gui.codepane import CodePane

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            trace = code_trace(Path(tmp) / "trace", root)
            step = trace.steps[0]
            step.code[0].line = 99
            step.code[0].end_line = 99
            pane = CodePane(root=root)
            pane.show(step, trace)
            widget = pane.tabs.widget(0)
            self.assertIsInstance(widget, QPlainTextEdit)
            assert isinstance(widget, QPlainTextEdit)
            self.assertIn("int two;", widget.toPlainText())
            self.assertEqual(widget.extraSelections(), [])

    def test_data_filters_touched(self) -> None:
        from verdandi.gui.datapane import DataPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = data_trace(Path(tmp) / "trace")
            pane = DataPane()
            pane.show(trace.steps[0], trace)
            self.assertEqual(pane.node_table.rowCount(), 1)
            item = pane.node_table.item(0, 0)
            assert item is not None
            self.assertEqual(item.text(), "1")
            pane.all_box.setChecked(True)
            self.assertEqual(pane.node_table.rowCount(), 2)

    def test_net_name_toggle(self) -> None:
        """The graph labels every net; the net-names checkbox hides the labels."""
        from verdandi.gui import datapane

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
        dot_texts: list[str] = []

        def capture(text: str) -> bytes:
            dot_texts.append(text)
            return svg

        with tempfile.TemporaryDirectory() as tmp:
            trace = data_trace(Path(tmp) / "trace")
            with mock.patch.object(datapane, "render_dot", side_effect=capture):
                pane = datapane.DataPane()
                pane.show(trace.steps[0], trace)
                self.assertIn('label="q"', dot_texts[-1])
                pane.net_names_box.setChecked(False)
                self.assertNotIn('label="q"', dot_texts[-1])
        self.assertEqual(len(dot_texts), 2)

    def test_diff_strip_still_renders(self) -> None:
        """The +/- log stays, beside the graph's colour diff: counts and the touched list."""
        from verdandi.gui.diffstrip import DiffStrip

        step = Step(
            id="s0001",
            parent=None,
            level=1,
            title="opt",
            anchor="pass:opt",
            diff=Diff(
                added=[ObjRef("m", "node", 1, "a")],
                removed=[ObjRef("m", "net", 20, "q")],
                changed=[ObjRef("m", "node", 2, "b")],
                by_name=False,
            ),
        )
        trace = Trace(Path("/tmp/claude-1000/v2-diffstrip"), make_manifest(), [step])
        strip = DiffStrip()
        strip.show(step, trace)
        self.assertEqual(strip.labels["added"].text(), "+1 added")
        self.assertEqual(strip.labels["removed"].text(), "-1 removed")
        self.assertEqual(strip.labels["changed"].text(), "~1 changed")
        self.assertEqual(strip.refs.count(), 3)
        self.assertEqual(
            [strip.refs.item(row).text() for row in range(3)],
            ["+ node m.a", "- net m.q", "~ node m.b"],
        )

    def test_diff_colours_on_the_graph(self) -> None:
        """D4: the step diff is drawn on the graph, not only in the +/- log."""
        from verdandi.gui import datapane

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
        dot_texts: list[str] = []

        def capture(text: str) -> bytes:
            dot_texts.append(text)
            return svg

        with tempfile.TemporaryDirectory() as tmp:
            trace = data_trace(Path(tmp) / "trace")
            with mock.patch.object(datapane, "render_dot", side_effect=capture):
                pane = datapane.DataPane()
                pane.show(trace.steps[0], trace)
        self.assertIn('color="#9a6700"', dot_texts[-1])

    def test_structure_badge_per_step_kind(self) -> None:
        """D3: the badge names the structure the pane shows; the symbol tab says so."""
        from verdandi.gui.datapane import DataPane

        with tempfile.TemporaryDirectory() as tmp:
            ir_trace = data_trace(Path(tmp) / "ir")
            pane = DataPane()
            pane.show(ir_trace.steps[0], ir_trace)
            self.assertEqual(pane.badge.objectName(), "structure-badge")
            self.assertEqual(pane.badge.text(), "IR after opt (netlist)")
            parsed = ast_trace(Path(tmp) / "parsed", "PARSED")
            pane.show(parsed.steps[0], parsed)
            self.assertEqual(pane.badge.text(), "AST (parsed)")
            self.assertIs(pane.tabs.currentWidget(), pane.ast_tree)
            elaborated = ast_trace(Path(tmp) / "elaborated")
            pane.show(elaborated.steps[0], elaborated)
            self.assertEqual(pane.badge.text(), "AST (elaborated)")
            pane.tabs.setCurrentWidget(pane.symbol_table)
            self.assertEqual(pane.badge.text(), "symbol table")

    def test_structure_badge_picture(self) -> None:
        from verdandi.gui import datapane

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
        with tempfile.TemporaryDirectory() as tmp:
            trace = picture_trace(Path(tmp) / "trace")
            with mock.patch.object(datapane, "render_dot", return_value=svg):
                pane = datapane.DataPane()
                pane.show(trace.steps[0], trace)
        self.assertEqual(pane.badge.text(), "ABC network (picture)")

    def test_structure_badge_log_event(self) -> None:
        """An L3 event has no snapshot: the badge says so and no structure tab shows."""
        from verdandi.gui.datapane import DataPane

        event = Step(
            id="s0001",
            parent=None,
            level=3,
            title="opt_clean: removing unused $mux '$c8'",
            anchor="rule:opt_clean:removing_unused",
        )
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace(Path(tmp) / "trace", make_manifest(), [event])
            pane = DataPane()
            pane.show(event, trace)
        self.assertEqual(pane.badge.text(), "log event (no snapshot)")
        self.assertFalse(pane.tabs.isTabVisible(pane.tabs.indexOf(pane.node_table)))

    def test_symbol_table_view(self) -> None:
        """D3: the symbol table lists scope, name, declaration and uses of the AST."""
        from verdandi.gui.datapane import DataPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = ast_trace(Path(tmp) / "trace")
            pane = DataPane()
            pane.show(trace.steps[0], trace)
        self.assertTrue(pane.tabs.isTabVisible(pane.tabs.indexOf(pane.symbol_table)))
        self.assertEqual(pane.symbol_table.rowCount(), 1)
        values = []
        for column in range(4):
            item = pane.symbol_table.item(0, column)
            assert item is not None
            values.append(item.text())
        self.assertEqual(values, ["m", "clk", "m.v:1:17", "m.v:2:11"])

    def test_symbol_table_hidden_for_ir_step(self) -> None:
        from verdandi.gui.datapane import DataPane

        with tempfile.TemporaryDirectory() as tmp:
            trace = data_trace(Path(tmp) / "trace")
            pane = DataPane()
            pane.show(trace.steps[0], trace)
        self.assertFalse(pane.tabs.isTabVisible(pane.tabs.indexOf(pane.symbol_table)))

    def test_data_picture_only_step(self) -> None:
        """An ABC step has a picture and no snapshot; the picture must still render."""
        from verdandi.gui import datapane

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
        with tempfile.TemporaryDirectory() as tmp:
            trace = picture_trace(Path(tmp) / "trace")
            with mock.patch.object(datapane, "render_dot", return_value=svg):
                pane = datapane.DataPane()
                pane.show(trace.steps[0], trace)
        self.assertTrue(pane.has_graph())
        self.assertFalse(pane.tabs.isTabVisible(pane.tabs.indexOf(pane.node_table)))

    def test_code_root_setting(self) -> None:
        """The app setting is read from QSettings and only kept when it names a directory."""
        from PySide6.QtCore import QSettings

        from verdandi.gui.app import code_root_setting

        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(
                str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat
            )
            self.assertIsNone(code_root_setting(settings))
            root = Path(tmp) / "odin3"
            root.mkdir()
            settings.setValue("codeRoot", str(root))
            self.assertEqual(code_root_setting(settings), root)
            settings.setValue("codeRoot", str(Path(tmp) / "gone"))
            self.assertIsNone(code_root_setting(settings))

    def test_mainwindow_code_root(self) -> None:
        """The window passes the code root setting through to the Code pane."""
        from PySide6.QtWidgets import QPlainTextEdit

        from verdandi.gui.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "odin3"
            trace = code_trace(Path(tmp) / "trace", root)
            window = MainWindow(trace, code_root=root)
            self.addCleanup(window.close)
            code = window.panes["Code"]
            assert hasattr(code, "tabs")
            widget = code.tabs.widget(0)
            self.assertIsInstance(widget, QPlainTextEdit)
            assert isinstance(widget, QPlainTextEdit)
            self.assertIn("int two;", widget.toPlainText())

    def test_explain_fallback_order(self) -> None:
        from verdandi.gui.explainpane import ExplainPane

        with tempfile.TemporaryDirectory() as tmp:
            root = Step(
                id="s0001",
                parent=None,
                level=0,
                title="Optimisation",
                anchor="stage:Optimisation",
            )
            event = Step(
                id="s0002",
                parent="s0001",
                level=3,
                title="opt",
                anchor="rule:opt:merge",
                diff=Diff(
                    added=[ObjRef("m", "node", 1, "a")],
                    removed=[],
                    changed=[],
                    by_name=False,
                ),
            )
            child = Step(
                id="s0003",
                parent="s0002",
                level=3,
                title="merged cell _1_",
                anchor="rule:opt:merge",
            )
            trace = Trace(Path(tmp), make_manifest(), [root, event, child])
            full = {
                "rule:opt:merge": "anchor note",
                "pass:opt": "pass note",
                "stage:Optimisation": "stage note",
            }
            pane = ExplainPane(notes=full)
            pane.show(event, trace)
            self.assertEqual(pane.browser.toPlainText(), "anchor note")
            pane = ExplainPane(
                notes={"pass:opt": "pass note", "stage:Optimisation": "stage note"}
            )
            pane.show(event, trace)
            self.assertEqual(pane.browser.toPlainText(), "pass note")
            pane = ExplainPane(notes={"stage:Optimisation": "stage note"})
            pane.show(event, trace)
            self.assertEqual(pane.browser.toPlainText(), "stage note")
            pane = ExplainPane(notes={})
            pane.show(event, trace)
            text = pane.browser.toPlainText()
            self.assertIn("opt: 1 added, 0 removed, 0 changed", text)
            self.assertIn("merged cell _1_", text)

    def test_explain_unreadable_notes(self) -> None:
        """An unreadable note file leaves the pane with no notes instead of raising."""
        from verdandi.gui import explainpane

        with mock.patch.object(explainpane, "load_notes", side_effect=OSError("denied")):
            pane = explainpane.ExplainPane()
            self.assertEqual(pane.notes(), {})

    def test_graph_without_dot(self) -> None:
        from verdandi.gui import datapane

        with tempfile.TemporaryDirectory() as tmp:
            trace = data_trace(Path(tmp) / "trace")
            with mock.patch.object(datapane, "which", return_value=None):
                pane = datapane.DataPane()
                pane.show(trace.steps[0], trace)
        self.assertFalse(pane.has_graph())
        self.assertEqual(pane.node_table.rowCount(), 1)
        self.assertTrue(
            pane.tabs.isTabVisible(pane.tabs.indexOf(pane.node_table))
        )


if __name__ == "__main__":
    unittest.main()
