"""CLI surface tests: subcommands, usage errors, info and the placeholder exit code."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from verdandi.cli import main
from verdandi.trace import FORMAT_VERSION, Manifest, Step, save


def make_manifest() -> Manifest:
    return Manifest(
        version=FORMAT_VERSION,
        program="odin3",
        program_version="1.0.0",
        abi=1,
        source_commit="0123456789abcdef",
        files=["counter2.v"],
        top="counter2",
        arch=None,
        script="read_verilog counter2.v",
        stage_map_version=1,
        recorded="2026-10-22T12:00:00Z",
    )


def make_step() -> Step:
    return Step(
        id="s0001",
        parent=None,
        level=0,
        title="Read architecture",
        anchor="stage:Read architecture",
        snapshot="s0001.json",
    )


def write_trace(directory: Path) -> None:
    snapshots = {"s0001.json": {"kind": "ir", "modules": []}}
    save(directory, make_manifest(), [make_step()], snapshots, [])


def drop_program(manifest: dict[str, Any]) -> None:
    del manifest["program"]


def wrong_files_type(manifest: dict[str, Any]) -> None:
    manifest["files"] = 5


class CliTest(unittest.TestCase):
    def test_help_lists_subcommands(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ex:
            main(["--help"])
        self.assertEqual(ex.exception.code, 0)
        for name in ("record", "play", "check-notes", "info"):
            self.assertIn(name, out.getvalue())

    def test_unknown_subcommand_is_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ex:
            main(["nope"])
        self.assertEqual(ex.exception.code, 2)

    def test_subcommands_not_implemented_yet(self) -> None:
        # Every subcommand is still unwired at Task 1; drop each name from this
        # loop in the task that wires it: Task 6 wires record and info, Task 9
        # wires check-notes, Task 10 wires play.
        unwired = ("play",)
        for name in unwired:
            with self.subTest(name=name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main([name])
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue().strip(),
                                 f"verdandi {name}: not implemented yet")


    def test_info_valid_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trace"
            write_trace(directory)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["info", str(directory)])
            self.assertEqual(code, 0)
            self.assertIn("steps: 1", out.getvalue())
            self.assertIn("snapshots: 1 files", out.getvalue())

    def test_info_corrupt_manifest_is_usage_error(self) -> None:
        cases = {"KeyError": drop_program, "TypeError": wrong_files_type}
        with tempfile.TemporaryDirectory() as tmp:
            for name, corrupt in cases.items():
                with self.subTest(name=name):
                    directory = Path(tmp) / name
                    write_trace(directory)
                    path = directory / "manifest.json"
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    corrupt(manifest)
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        code = main(["info", str(directory)])
                    self.assertEqual(code, 2, stderr.getvalue())
                    self.assertIn("verdandi info:", stderr.getvalue())

    def test_info_refuses_snapshot_traversal(self) -> None:
        cases = {
            "dotdot": ("..", "is not a file name"),
            "absolute": ("/etc/passwd", "escapes the trace directory"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, (snapshot, message) in cases.items():
                with self.subTest(name=name):
                    directory = Path(tmp) / name
                    write_trace(directory)
                    path = directory / "steps.json"
                    steps = json.loads(path.read_text(encoding="utf-8"))
                    steps[0]["snapshot"] = snapshot
                    path.write_text(json.dumps(steps), encoding="utf-8")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        code = main(["info", str(directory)])
                    self.assertEqual(code, 2, stderr.getvalue())
                    self.assertIn(message, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
