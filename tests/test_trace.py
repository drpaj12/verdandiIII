"""Trace model and file format tests: round trip, version guard, ordering, copies."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from verdandi.trace import (
    FORMAT_VERSION,
    CodeRef,
    Diff,
    Manifest,
    ObjRef,
    Step,
    load,
    save,
)


def make_manifest(version: int = FORMAT_VERSION) -> Manifest:
    return Manifest(
        version=version,
        program="odin3",
        program_version="1.0.0",
        abi=1,
        source_commit="0123456789abcdef",
        files=["counter.v"],
        top="counter",
        arch=None,
        script="read_verilog counter.v; proc",
        stage_map_version=1,
        recorded="2026-10-22T12:00:00Z",
    )


def make_steps() -> list[Step]:
    node = ObjRef(module="counter", kind="node", id=1, name="$dff")
    net = ObjRef(module="counter", kind="net", id=2, name="q")
    return [
        Step(
            id="s0001",
            parent=None,
            level=0,
            title="Read architecture",
            anchor="stage:Read architecture",
            snapshot="s0001.json",
        ),
        Step(
            id="s0002",
            parent="s0001",
            level=1,
            title="read_verilog --nolatches --vtr-compat counter.v",
            anchor="pass:read_verilog",
            snapshot="s0002.json",
            diff=Diff(added=[node], removed=[], changed=[net], by_name=False),
            code=[CodeRef(file="src/frontends/verilog/verilog_frontend.c", line=10,
                          end_line=20, function="parse_verilog")],
            log=["line one", "line two"],
        ),
        Step(
            id="s0003",
            parent="s0002",
            level=2,
            title="Parse",
            anchor="ast:parsed",
            snapshot="s0003.json",
            illustration=True,
        ),
        Step(
            id="s0004",
            parent=None,
            level=0,
            title="ABC: logic optimisation and K-LUT mapping",
            anchor="stage:ABC",
            picture="s0004.dot",
            failed=True,
        ),
        Step(
            id="s0005",
            parent="s0002",
            level=2,
            title="Elaborate",
            anchor="ast:elaborated",
        ),
    ]


def make_snapshots() -> dict[str, dict[str, Any]]:
    return {
        "s0001.json": {"kind": "ir", "modules": []},
        "s0002.json": {
            "kind": "ir",
            "modules": [
                {
                    "name": "counter",
                    "nodes": [
                        {"id": 1, "name": "$dff", "type": "$dff", "params": {},
                         "pins": [{"port": "Q", "bit": 0, "net": 2}], "sources": []}
                    ],
                    "nets": [{"id": 2, "name": "q", "drivers": [1], "sinks": [],
                              "sources": []}],
                    "wires": [],
                }
            ],
        },
        "s0003.json": {"kind": "ast", "form": "PARSED", "roots": []},
    }


class TraceFileTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        manifest = make_manifest()
        steps = make_steps()
        snapshots = make_snapshots()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            save(Path(first), manifest, steps, snapshots, [])
            trace = load(Path(first))
            self.assertEqual(trace.manifest, manifest)
            self.assertEqual(trace.steps, steps)
            save(Path(second), trace.manifest, trace.steps, snapshots, [])
            first_bytes = (Path(first) / "steps.json").read_bytes()
            second_bytes = (Path(second) / "steps.json").read_bytes()
            self.assertEqual(first_bytes, second_bytes)

    def test_refuses_newer_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save(Path(directory), make_manifest(version=FORMAT_VERSION + 1), [], {}, [])
            with self.assertRaises(ValueError) as caught:
                load(Path(directory))
            self.assertIn("newer", str(caught.exception))

    def test_children_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save(Path(directory), make_manifest(), make_steps(), {}, [])
            trace = load(Path(directory))
        roots = trace.children(None)
        self.assertEqual([step.id for step in roots], ["s0001", "s0004"])
        first_children = trace.children("s0001")
        self.assertEqual([step.id for step in first_children], ["s0002"])
        second_children = trace.children("s0002")
        self.assertEqual([step.id for step in second_children], ["s0003", "s0005"])
        self.assertEqual(trace.children("s0003"), [])
        self.assertEqual(trace.step("s0003").title, "Parse")

    def test_sources_copied(self) -> None:
        data = b"module counter;\r\n\treg q;\r\nendmodule\r\n"
        with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as directory:
            source = Path(work) / "counter.v"
            source.write_bytes(data)
            save(Path(directory), make_manifest(), [], {}, [source])
            copied = Path(directory) / "src" / "counter.v"
            self.assertEqual(copied.read_bytes(), data)

    def test_snapshot_cached(self) -> None:
        snapshots = make_snapshots()
        with tempfile.TemporaryDirectory() as directory:
            save(Path(directory), make_manifest(), make_steps(), snapshots, [])
            trace = load(Path(directory))
            step = trace.step("s0002")
            first = trace.snapshot(step)
            second = trace.snapshot(step)
            self.assertIs(first, second)
            self.assertEqual(first, snapshots["s0002.json"])
            self.assertIsNone(trace.snapshot(trace.step("s0004")))

    def test_pictures_copied(self) -> None:
        data = b"digraph G {\n}\n"
        with tempfile.TemporaryDirectory() as work, tempfile.TemporaryDirectory() as directory:
            picture = Path(work) / "strash.dot"
            picture.write_bytes(data)
            steps = make_steps()
            save(Path(directory), make_manifest(), steps, {},
                 [], pictures={"s0004.dot": picture})
            copied = Path(directory) / "pic" / "s0004.dot"
            self.assertEqual(copied.read_bytes(), data)


class TraceSafetyTest(unittest.TestCase):
    def test_snapshot_names_cannot_escape(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            trace_dir = Path(work) / "trace"
            escaped = Path(work) / "escaped.json"
            for name in ("../../escaped.json", str(escaped)):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        save(trace_dir, make_manifest(), [], {name: {"kind": "ir"}}, [])
                    self.assertFalse(escaped.exists())
                    self.assertFalse(trace_dir.exists())

    def test_picture_names_cannot_escape(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / "strash.dot"
            source.write_bytes(b"digraph G {\n}\n")
            trace_dir = Path(work) / "trace"
            escaped = Path(work) / "escaped.dot"
            for name in ("../../escaped.dot", str(escaped)):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        save(trace_dir, make_manifest(), [], {}, [],
                             pictures={name: source})
                    self.assertFalse(escaped.exists())
                    self.assertFalse(trace_dir.exists())

    def test_loaded_snapshot_name_cannot_escape(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work) / "trace"
            save(directory, make_manifest(), make_steps(), make_snapshots(), [])
            outside = Path(work) / "secret.json"
            outside.write_text('{"kind": "ir", "modules": []}\n', encoding="utf-8")
            steps_path = directory / "steps.json"
            data = json.loads(steps_path.read_text(encoding="utf-8"))
            data[0]["snapshot"] = "../../secret.json"
            steps_path.write_text(json.dumps(data), encoding="utf-8")
            trace = load(directory)
            with self.assertRaises(ValueError):
                trace.snapshot(trace.step("s0001"))

    def test_duplicate_source_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            first = Path(work) / "a" / "counter.v"
            first.parent.mkdir()
            first.write_text("module counter;\nendmodule\n", encoding="utf-8")
            second = Path(work) / "b" / "counter.v"
            second.parent.mkdir()
            second.write_text("module other;\nendmodule\n", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                save(Path(work) / "trace", make_manifest(), [], {}, [first, second])
            self.assertIn("counter.v", str(caught.exception))

    def test_names_colliding_ignoring_case_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / "strash.dot"
            source.write_bytes(b"digraph G {\n}\n")
            trace_dir = Path(work) / "trace"
            with self.subTest(kind="snapshot"), self.assertRaises(ValueError):
                save(trace_dir, make_manifest(), [],
                     {"s0001.json": {"kind": "ir"}, "S0001.json": {"kind": "ir"}}, [])
            with self.subTest(kind="picture"), self.assertRaises(ValueError):
                save(trace_dir, make_manifest(), [], {}, [],
                     pictures={"a.dot": source, "A.dot": source})


if __name__ == "__main__":
    unittest.main()
