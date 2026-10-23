"""The five shipped examples: layout, a recording of each, fresh notes, and the instantiation.

Each example directory holds its design, a README and anchored notes. Every example records
through the production flow (the k6 VTR architecture when a VTR checkout is around, else the
LPM tech library); the instantiation example's trace shows the two counter instances, the leaf
gate and their expansion. Recording tests skip without the odin3 binding, or without either the
k6 arch or the LPM library, as the recorder tests do.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.helpers import HAVE_ODIN3, ODIN3_ROOT, vtr_arch
from verdandi.cli import main
from verdandi.trace import Trace, load

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

# Directory name, source file, top module; smallest design first, as record-all.sh records them.
EXAMPLE_SET = (
    ("counter", "counter.v", "counter2"),
    ("register", "register.v", "ifelse_reg"),
    ("multiplier", "multiplier.v", "mul4"),
    ("instantiation", "instantiation.v", "instantiation_top"),
    ("playthrough", "playthrough.v", "playthrough"),
)


def techlib() -> Path | None:
    """The LPM tech library the production flow reads first, when the Odin III tree is around."""
    if ODIN3_ROOT is None:
        return None
    path = ODIN3_ROOT / "lib" / "lpm.o3lib"
    return path if path.is_file() else None


def record_args() -> list[str] | None:
    """The recording source arguments: the k6 arch when VTR is around, else the LPM library."""
    arch = vtr_arch()
    if arch is not None:
        return ["--arch", str(arch)]
    library = techlib()
    if library is not None:
        return ["--techlib", str(library)]
    return None


def run_main(argv: list[str]) -> tuple[int, str]:
    """Run the CLI in-process and return its exit code and captured output."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue() + err.getvalue()


def ast_instances(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    """The snapshot's (module type, instance name) pairs, from its INSTANTIATION nodes."""
    pairs: list[tuple[str, str]] = []
    stack: list[dict[str, Any]] = list(snapshot.get("roots", []))
    while stack:
        node = stack.pop()
        if node.get("kind") == "INSTANTIATION":
            pairs.extend(
                (str(node["name"]), str(child["name"]))
                for child in node.get("children", [])
                if child.get("kind") == "INSTANCE"
            )
        stack.extend(node.get("children", []))
    return pairs


class ExampleLayoutTest(unittest.TestCase):
    def test_each_example_has_source_readme_and_notes(self) -> None:
        for name, source, _top in EXAMPLE_SET:
            with self.subTest(example=name):
                directory = EXAMPLES / name
                self.assertTrue((directory / source).is_file(), f"{directory / source} is missing")
                self.assertTrue(
                    (directory / "README.md").is_file(), f"{directory}/README.md is missing"
                )
                self.assertTrue(
                    sorted((directory / "notes").glob("*.md")),
                    f"{directory}/notes has no note files",
                )

    def test_record_all_lists_every_example_smallest_first(self) -> None:
        script = EXAMPLES / "record-all.sh"
        self.assertTrue(script.is_file(), f"{script} is missing")
        text = script.read_text(encoding="utf-8")
        entries = self.array_entries(text)
        self.assertEqual(
            entries,
            [(name, top, f"{name}/{source}") for name, source, top in EXAMPLE_SET],
            "record-all.sh does not list every example once, smallest first, uncommented",
        )
        self.assertIn("--arch", text, "record-all.sh never uses the k6 arch")
        self.assertIn("--techlib", text, "record-all.sh has no LPM fallback")
        self.assertIn("check-notes", text, "record-all.sh does not check the example notes")

    def array_entries(self, text: str) -> list[tuple[str, str, str]]:
        """The (name, top, source) entries of the script's `examples=(...)` array, comments out."""
        lines = text.splitlines()
        start = next(
            (index for index, line in enumerate(lines) if line.strip() == "examples=("), None
        )
        self.assertIsNotNone(start, "record-all.sh has no examples array")
        assert start is not None
        entries: list[tuple[str, str, str]] = []
        for line in lines[start + 1 :]:
            stripped = line.strip()
            if stripped == ")":
                return entries
            if not stripped or stripped.startswith("#"):
                continue
            name, top, source = stripped.strip('"').split()
            entries.append((name, top, source))
        self.fail("record-all.sh's examples array is not closed")


@unittest.skipUnless(HAVE_ODIN3, "needs odin3")
class ExampleNotesTest(unittest.TestCase):
    def test_example_notes_not_stale(self) -> None:
        for name, _source, _top in EXAMPLE_SET:
            with self.subTest(example=name):
                notes = EXAMPLES / name / "notes"
                code, output = run_main(["check-notes", "--notes", str(notes)])
                self.assertEqual(code, 0, f"{name}: check-notes failed\n{output}")


@unittest.skipUnless(HAVE_ODIN3, "needs odin3")
class ExampleRecordTest(unittest.TestCase):
    def test_every_example_records(self) -> None:
        args = record_args()
        if args is None:
            self.skipTest("neither the VTR k6 arch nor ODIN3_ROOT/lib/lpm.o3lib is available")
        for name, source, top in EXAMPLE_SET:
            with self.subTest(example=name):
                example = EXAMPLES / name / source
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / "trace"
                    code, output = run_main(
                        ["record", str(example), "--top", top, *args, "-o", str(out)]
                    )
                    self.assertEqual(code, 0, f"{name} did not record\n{output}")
                    trace = load(out)
                    self.assertEqual(trace.manifest.top, top)
                    self.assertEqual(trace.manifest.files, [str(example)])
                    self.assertGreaterEqual(len(trace.steps), 20, f"{name} has too few steps")
                    if name == "instantiation":
                        self.check_instantiation(trace)

    def check_instantiation(self, trace: Trace) -> None:
        """The trace shows the two counter instances, the leaf gate and their expansion."""
        elaborate = [step for step in trace.steps if step.title == "Elaborate"]
        self.assertEqual(len(elaborate), 1, "the trace has no single Elaborate step")
        snapshot = trace.snapshot(elaborate[0])
        self.assertIsNotNone(snapshot, "the Elaborate step has no AST snapshot")
        assert snapshot is not None
        self.assertEqual(snapshot.get("kind"), "ast")
        instances = ast_instances(snapshot)
        self.assertEqual(
            {instance for _module, instance in instances}, {"two", "four", "gate"}
        )
        counter_types = {
            (module, instance) for module, instance in instances if instance in ("two", "four")
        }
        self.assertEqual(
            counter_types,
            {("counter", "two"), ("counter$WIDTH=4", "four")},
            "the counter instances do not map to their expected widths",
        )
        self.assertEqual(
            [module for module, instance in instances if instance == "gate"], ["and_gate"]
        )
        hierarchy = next(step for step in trace.steps if step.anchor == "pass:hierarchy")
        self.assertIn(
            "hierarchy: top instantiation_top", "\n".join(hierarchy.log)
        )
        flatten = next(step for step in trace.steps if step.anchor == "pass:flatten")
        log = "\n".join(flatten.log)
        self.assertIn("3 instances to expand", log, "flatten expanded another number of instances")
        self.assertIn("counter$WIDTH=4", log, "the width override is not an instance module")
        self.assertIn("and_gate", log, "the leaf gate is not an instance module")


if __name__ == "__main__":
    unittest.main()
