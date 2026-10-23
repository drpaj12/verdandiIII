"""The shipped playthrough example: it records, reaches every stage, and its notes are fresh.

Skipped without the odin3 binding. Recording uses the k6 VTR architecture when a VTR checkout
is around (with the opened-up ABC sub-steps when a standalone ABC binary is too), else the LPM
tech library, exactly as the manual's fallback describes.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import HAVE_ABC, HAVE_ODIN3, ODIN3_ROOT, vtr_arch
from verdandi.cli import main
from verdandi.trace import load

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "playthrough" / "playthrough.v"
STAGES_FILE = ROOT / "verdandi" / "odin3" / "stages.json"

# The stage map's title for the ABC pass, whose opened-up L2 steps the arch recording carries.
ABC_STAGE = "ABC: logic optimisation and K-LUT mapping"


def techlib() -> Path | None:
    """The LPM tech library the production flow reads first, when the Odin III tree is around."""
    if ODIN3_ROOT is None:
        return None
    path = ODIN3_ROOT / "lib" / "lpm.o3lib"
    return path if path.is_file() else None


def stages() -> dict[str, str]:
    """Pass name -> stage title, from the shipped stage map."""
    data = json.loads(STAGES_FILE.read_text(encoding="utf-8"))
    return {
        name: str(stage["title"]) for stage in data["stages"] for name in stage["passes"]
    }


def run_main(argv: list[str]) -> tuple[int, str]:
    """Run the CLI in-process and return its exit code and stdout."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    return code, out.getvalue()


@unittest.skipUnless(HAVE_ODIN3, "needs odin3")
class PlaythroughTest(unittest.TestCase):
    def test_playthrough_records(self) -> None:
        arch = vtr_arch()
        library = techlib()
        if arch is None and library is None:
            self.skipTest("neither the VTR k6 arch nor ODIN3_ROOT/lib/lpm.o3lib is available")
        self.assertTrue(EXAMPLE.is_file(), f"{EXAMPLE} is missing")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trace"
            argv = ["record", str(EXAMPLE), "--top", "playthrough", "-o", str(out)]
            if arch is not None:
                argv.extend(["--arch", str(arch)])
            else:
                assert library is not None
                argv.extend(["--techlib", str(library)])
            code, _ = run_main(argv)
            self.assertEqual(code, 0, "the playthrough did not record")
            trace = load(out)
            self.assertGreater(len(trace.steps), 30, "the trace has 30 steps or fewer")
            titles = stages()
            reached = {
                titles.get(step.anchor.removeprefix("pass:"), step.anchor.removeprefix("pass:"))
                for step in trace.steps
                if step.level == 1 and step.anchor is not None
            }
            self.assertIn("Read architecture", reached)
            for root in trace.children(None):
                self.assertEqual(root.level, 0, root.title)
                if root.title in reached:
                    passes = [
                        step
                        for step in trace.children(root.id)
                        if step.level == 1
                    ]
                    self.assertTrue(passes, f"stage {root.title!r} has no L1 step")
            roots = {step.title for step in trace.children(None)}
            missing = sorted(reached - roots)
            self.assertEqual(missing, [], f"no L0 stage step for {missing}")
            if arch is not None and HAVE_ABC:
                abc = [
                    step
                    for step in trace.steps
                    if step.anchor == "pass:abc" and step.level == 1
                ]
                self.assertEqual(len(abc), 1)
                substeps = trace.children(abc[0].id)
                self.assertTrue(substeps, "the ABC step has no opened-up L2 children")
                self.assertIn("abc:if", [step.anchor for step in substeps])
            code, stdout = run_main(["info", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("steps: ", stdout)
            steps_line = next(line for line in stdout.splitlines() if line.startswith("steps: "))
            self.assertGreater(int(steps_line.split(": ", 1)[1]), 30)
        code, _ = run_main(["check-notes"])
        self.assertEqual(code, 0, "the shipped notes are stale")


if __name__ == "__main__":
    unittest.main()
