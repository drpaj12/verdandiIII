"""Recorder tests: stage steps (L0), pass steps (L1), Parse and Elaborate (L2), exit codes.

Skipped without the odin3 binding and library. The recording tests also need the LPM tech
library the production flow reads first, ``ODIN3_ROOT/lib/lpm.o3lib`` (tools/flow/odin3_flow.py
reads it), and skip without it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import verdandi.odin3.record as record_module
from tests.helpers import HAVE_ODIN3, ODIN3_ROOT
from tests.micros import COUNTER2, Micro
from verdandi.diff import diff
from verdandi.odin3.record import _check_top, default_script, record
from verdandi.trace import Diff, load

STAGES_FILE = Path(__file__).resolve().parent.parent / "verdandi" / "odin3" / "stages.json"


def techlib() -> Path | None:
    """The LPM tech library the production flow reads first, when the Odin III tree is around."""
    if ODIN3_ROOT is None:
        return None
    path = ODIN3_ROOT / "lib" / "lpm.o3lib"
    return path if path.is_file() else None


def write_micro(micro: Micro, directory: Path) -> Path:
    """Write the micro's text to <directory>/<top>.v and return the path."""
    top, text = micro
    path = directory / f"{top}.v"
    path.write_text(text, encoding="utf-8")
    return path


def stage_map() -> dict[str, str]:
    """Pass name -> stage title, from the shipped stage map."""
    data = json.loads(STAGES_FILE.read_text(encoding="utf-8"))
    return {
        name: str(stage["title"]) for stage in data["stages"] for name in stage["passes"]
    }


class TopNameTest(unittest.TestCase):
    def test_top_rejects_non_identifiers(self) -> None:
        # A top names a path (<top>.blif) and a hierarchy option: only an identifier passes.
        for top in ("../escape", "a/b", "a\\b", "-top", "a b", 'a"b', "a;b", "..", ""):
            with self.subTest(top=top), self.assertRaises(ValueError):
                _check_top(top)

    def test_top_accepts_identifiers(self) -> None:
        for top in ("counter2", "_count2", "a$b", "A1"):
            with self.subTest(top=top):
                _check_top(top)
                script = default_script(
                    [Path("counter2.v")],
                    top,
                    arch=None,
                    techlib=Path("lpm.o3lib"),
                    k=6,
                    blif_out=Path("out.blif"),
                )
                self.assertIn('read_techlib "lpm.o3lib"', script)


@unittest.skipUnless(HAVE_ODIN3, "the odin3 binding and library")
class RecorderTest(unittest.TestCase):
    def require_techlib(self) -> Path:
        library = techlib()
        if library is None:
            self.skipTest("ODIN3_ROOT/lib/lpm.o3lib is not available")
        assert library is not None
        return library

    def test_record_counter(self) -> None:
        library = self.require_techlib()
        top, text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
            self.assertEqual(code, 0)
            trace = load(out)
            titles = stage_map()
            roots = trace.children(None)
            self.assertTrue(roots, "no stage steps")
            passes = []
            for root in roots:
                self.assertEqual(root.level, 0, root.title)
                self.assertEqual(root.anchor, f"stage:{root.title}")
                passes.extend(trace.children(root.id))
            self.assertTrue(passes, "no pass steps")
            for step in passes:
                self.assertEqual(step.level, 1, step.title)
                self.assertIsNotNone(step.snapshot, f"{step.title}: no snapshot")
                self.assertTrue(step.anchor.startswith("pass:"), step.anchor)
                name = step.anchor.removeprefix("pass:")
                self.assertIsNotNone(step.parent, step.title)
                assert step.parent is not None
                parent = trace.step(step.parent)
                self.assertEqual(parent.level, 0, step.title)
                self.assertEqual(parent.title, titles.get(name, name), step.title)
            read_verilog = [step for step in passes if step.anchor == "pass:read_verilog"]
            self.assertEqual(len(read_verilog), 1)
            children = trace.children(read_verilog[0].id)
            self.assertEqual([child.title for child in children], ["Parse", "Elaborate"])
            for child, form in zip(children, ("PARSED", "ELABORATED"), strict=True):
                self.assertEqual(child.level, 2, child.title)
                self.assertEqual(child.parent, read_verilog[0].id)
                snapshot = trace.snapshot(child)
                self.assertIsNotNone(snapshot, child.title)
                assert snapshot is not None
                self.assertEqual(snapshot.get("kind"), "ast", child.title)
                self.assertEqual(snapshot.get("form"), form, child.title)
            self.assertEqual(
                (out / "src" / f"{top}.v").read_text(encoding="utf-8"), text
            )

    def test_record_counter_abc_diff_by_name(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
            self.assertEqual(code, 0)
            trace = load(out)
            steps = [step for step in trace.steps if step.anchor == "pass:abc"]
            self.assertEqual(len(steps), 1)
            step = steps[0]
            self.assertIsNotNone(step.diff, "the abc step has no diff")
            assert step.diff is not None
            # v1.0.0: abc compacts the IDs; by name only its two $lut cells are new, and the
            # cells and nets it removes are gone by name too (2 added, 24 removed, 11 changed).
            self.assertTrue(step.diff.by_name)
            self.assertEqual(len(step.diff.added), 2)
            self.assertEqual(len(step.diff.removed), 24)
            self.assertEqual(len(step.diff.changed), 11)
            after = trace.snapshot(step)
            assert after is not None
            nodes = {
                int(item["id"]): item
                for module in after["modules"]
                for item in module.get("nodes", [])
            }
            for ref in step.diff.added:
                self.assertEqual(ref.kind, "node")
                self.assertEqual(nodes[ref.id]["type"], "$lut")
            removed = [ref for ref in step.diff.removed if ref.name]
            self.assertNotIn("wire", {ref.kind for ref in removed})
            self.assertNotIn("count.dff_p1", {ref.name for ref in removed})
            self.assertNotIn("count.dff_p3", {ref.name for ref in removed})

    def test_record_compact_step_diff_by_name(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc; compact; proc"
            )
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, script=script)
            self.assertEqual(code, 0)
            trace = load(out)
            steps = [step for step in trace.steps if step.anchor == "pass:compact"]
            self.assertEqual(len(steps), 1)
            step = steps[0]
            self.assertIsNotNone(step.diff, "the compact step has no diff")
            assert step.diff is not None
            self.assertTrue(step.diff.by_name)
            self.assertEqual(step.diff.added, [])
            self.assertEqual(step.diff.removed, [])

    def test_record_without_root_warns_once(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            stderr = io.StringIO()
            with mock.patch.dict(os.environ):
                os.environ.pop("ODIN3_ROOT", None)
                with contextlib.redirect_stderr(stderr):
                    code = record([source], top, out, techlib=library, odin3_root=None)
            self.assertEqual(code, 0)
            # Task 7 adds its own warning (no standalone ABC binary) in this environment.
            warnings = [
                line
                for line in stderr.getvalue().splitlines()
                if "warning" in line and "no Odin III source tree" in line
            ]
            self.assertEqual(len(warnings), 1, stderr.getvalue())
            self.assertIn("ODIN3_ROOT", warnings[0])
            trace = load(out)
            self.assertEqual(trace.manifest.source_commit, "unknown")
            self.assertFalse(any(step.code for step in trace.steps), "code refs without a tree")

    def test_record_non_git_root_warns_once(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            root = Path(tmp) / "not-git"
            root.mkdir()
            out = Path(tmp) / "trace"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = record([source], top, out, techlib=library, odin3_root=root)
            self.assertEqual(code, 0)
            # Task 7 adds its own warning (no standalone ABC binary) in this environment.
            warnings = [
                line
                for line in stderr.getvalue().splitlines()
                if "warning" in line and "no Odin III source tree" in line
            ]
            self.assertEqual(len(warnings), 1, stderr.getvalue())
            self.assertIn("ODIN3_ROOT", warnings[0])
            trace = load(out)
            self.assertEqual(trace.manifest.source_commit, "unknown")
            self.assertFalse(any(step.code for step in trace.steps), "code refs without a tree")

    def test_record_save_errors_are_usage_errors(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        script = f'read_techlib "{library}"'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = write_micro(COUNTER2, base)
            other = base / "a" / "counter2.v"
            other.parent.mkdir()
            other.write_text("module other; endmodule\n", encoding="utf-8")
            (base / "occupied").write_text("x", encoding="utf-8")
            (base / "file").write_text("x", encoding="utf-8")
            cases: dict[str, tuple[list[Path], Path]] = {
                "occupied out": ([source], base / "occupied"),
                "unwritable out": ([source], base / "file" / "trace"),
                "duplicate source basenames": ([source, other], base / "trace"),
            }
            for name, (files, out) in cases.items():
                with self.subTest(name=name):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        code = record(files, top, out, techlib=library, script=script)
                    self.assertEqual(code, 2, stderr.getvalue())
                    self.assertTrue(stderr.getvalue().startswith("verdandi record: "))

    def test_record_stage_map_errors_are_usage_errors(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        script = f'read_techlib "{library}"'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = write_micro(COUNTER2, base)
            corrupt = base / "corrupt.json"
            corrupt.write_text("{", encoding="utf-8")
            cases = {"missing": base / "missing.json", "corrupt": corrupt}
            for name, path in cases.items():
                with self.subTest(name=name):
                    stderr = io.StringIO()
                    with (
                        mock.patch.object(record_module, "_STAGES_FILE", path),
                        contextlib.redirect_stderr(stderr),
                    ):
                        code = record(
                            [source], top, base / "trace", techlib=library, script=script
                        )
                    self.assertEqual(code, 2, stderr.getvalue())
                    self.assertTrue(stderr.getvalue().startswith("verdandi record: "))

    def test_record_rejects_unsafe_top(self) -> None:
        library = self.require_techlib()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "work"
            base.mkdir()
            source = write_micro(COUNTER2, base)
            out = base / "trace"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = record([source], "../escape", out, techlib=library)
            self.assertEqual(code, 2)
            self.assertIn("not a Verilog identifier", stderr.getvalue())
            self.assertFalse(out.exists())
            self.assertFalse((base.parent / "escape.blif").exists())

    def test_record_every_step_carries_a_diff(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
            self.assertEqual(code, 0)
            trace = load(out)
            for step in trace.steps:
                self.assertIsNotNone(step.diff, f"{step.title}: no diff")
            # An L0 stage diffs its own end snapshot against the step before it: the previous
            # stage's final IR snapshot (None before the first stage).
            previous: dict[str, Any] | None = None
            for root in trace.children(None):
                snapshot = trace.snapshot(root)
                self.assertIsNotNone(snapshot, f"{root.title}: no snapshot")
                assert snapshot is not None and root.diff is not None
                self.assertEqual(root.diff, diff(previous, snapshot, by_name=root.diff.by_name))
                if root.title.startswith("ABC"):
                    self.assertTrue(root.diff.by_name, "the ABC stage compacts the IDs")
                previous = snapshot
            read_verilog = next(
                step for step in trace.steps if step.anchor == "pass:read_verilog"
            )
            children = trace.children(read_verilog.id)
            self.assertEqual([child.title for child in children], ["Parse", "Elaborate"])
            for child in children:
                self.assertEqual(
                    child.diff, Diff(added=[], removed=[], changed=[], by_name=False)
                )

    def test_event_code_refs_are_debug_log_lines(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            assert ODIN3_ROOT is not None
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
            self.assertEqual(code, 0)
            trace = load(out)
            events = [step for step in trace.steps if step.level == 3]
            self.assertTrue(events, "no event steps")
            for event in events:
                self.assertTrue(event.code, event.title)
                for ref in event.code:
                    line = (ODIN3_ROOT / ref.file).read_text(encoding="utf-8").splitlines()[
                        ref.line - 1
                    ]
                    # An event's ref is the DEBUG log call that formats it: no comment, no
                    # INFO line, and no unrelated call that shares the prefix.
                    self.assertIn("odin3_log", line, (ref.file, ref.line))
                    self.assertIn("ODIN3_LOG_DEBUG", line, (ref.file, ref.line))

    def test_write_blif_log_keeps_info_only(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, odin3_root=ODIN3_ROOT)
            self.assertEqual(code, 0)
            trace = load(out)
            step = next(s for s in trace.steps if s.anchor == "pass:write_blif")
            # The writer's report is DEBUG and capture_log keeps INFO and above, so the step
            # log holds the timing line alone (agent default 6 said it kept the report).
            self.assertEqual(len(step.log), 1, step.log)
            self.assertTrue(step.log[0].startswith("pass write_blif:"), step.log)

    def test_record_failing_pass(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            script = (
                f'read_techlib "{library}"; '
                f'read_verilog --nolatches --vtr-compat "{source}"; '
                "proc --no-such-flag"
            )
            out = Path(tmp) / "trace"
            code = record([source], top, out, techlib=library, script=script)
            self.assertEqual(code, 1)
            trace = load(out)
            self.assertTrue(trace.steps, "the failed trace has no steps")
            last = trace.steps[-1]
            self.assertTrue(last.failed)
            self.assertEqual(last.level, 1)
            self.assertEqual(last.anchor, "pass:proc")
            self.assertTrue(last.log, "the failed step kept no log")

    def test_size_guard(self) -> None:
        library = self.require_techlib()
        top, _text = COUNTER2
        with tempfile.TemporaryDirectory() as tmp:
            source = write_micro(COUNTER2, Path(tmp))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = record(
                    [source], top, Path(tmp) / "trace", techlib=library, max_nodes=3
                )
            self.assertEqual(code, 2)
            self.assertIn("read_verilog", stderr.getvalue())

    def test_stage_map_passes_exist(self) -> None:
        import odin3

        passes = set(odin3.default().passes())
        for name in stage_map():
            self.assertIn(name, passes)


if __name__ == "__main__":
    unittest.main()
