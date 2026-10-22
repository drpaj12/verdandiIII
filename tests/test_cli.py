"""CLI surface tests: subcommands, usage errors and the placeholder exit code."""

from __future__ import annotations

import contextlib
import io
import unittest

from verdandi.cli import main


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
        unwired = ("play", "check-notes")
        for name in unwired:
            with self.subTest(name=name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main([name])
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue().strip(),
                                 f"verdandi {name}: not implemented yet")


if __name__ == "__main__":
    unittest.main()
