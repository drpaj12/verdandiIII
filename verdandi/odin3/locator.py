"""Locate the Odin III C source of a pass in the source tree (spec 6).

The tree is read at record time, never changed. A pass is found by the string literal of its
``odin3_pass_def`` usage entry (the ``"<name>"`` literal followed within three lines by a
literal starting with ``"<name> "`` or ``"<name>:"``); when no file matches, a macro-registered
family is found by a second clause: a ``.c`` holding the token ``odin3_pass_def`` plus both the
``"<name>"`` literal and the usage literal anywhere in the file (``OPT_DEF`` in
``src/passes/opt/register.c``). Its files are that registering file's directory, minus the
per-file split when the directory is ``src/passes`` itself. Functions come from a C
function-definition scan of those files, and the line that logs an L3 event from a plain text
search. No compiler or external parser is involved: a scan that finds nothing gives the pass's
files only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from verdandi.trace import CodeRef

# Where a pass registers: processing passes, then reader frontends.
_SOURCE_ROOTS = ("src/passes", "src/frontends")

# One C string literal on a line; group 1 is the text between the quotes.
_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

# A function definition's first line: column 0, a name, a parameter list with no semicolon (a
# prototype ends in one, so its line is skipped), and a body. The name is group 1.
_FUNCTION = re.compile(r"^[A-Za-z_][\w \*]*\b(\w+)\s*\([^;]*$")


def _literals(line: str) -> list[str]:
    """The contents of the line's C string literals, in order."""
    return _LITERAL.findall(line)


class Locator:
    """Code locations in the Odin III source tree rooted at ``root`` (None: no tree)."""

    def __init__(self, root: Path | None) -> None:
        self._root = root

    def pass_files(self, name: str) -> list[Path]:
        """The pass's C files, relative to the root; empty when it registers nowhere."""
        registering = self._registering(name)
        if registering is None:
            return []
        directory = registering.parent
        if self._relative(directory) == Path("src/passes"):
            return [self._relative(registering)]
        return [self._relative(path) for path in sorted(directory.glob("*.c"))]

    def functions(self, path: Path) -> list[CodeRef]:
        """The C function definitions in ``path``, with their exact first and last lines."""
        lines = self._lines(path)
        if lines is None:
            return []
        refs: list[CodeRef] = []
        index = 0
        while index < len(lines):
            match = _FUNCTION.match(lines[index])
            if match is None:
                index += 1
                continue
            end = self._body_end(lines, index)
            if end is None:
                index += 1
                continue
            refs.append(
                CodeRef(
                    file=str(self._relative(path)),
                    line=index + 1,
                    end_line=end + 1,
                    function=match.group(1),
                )
            )
            index = end + 1
        return refs

    def find_text(self, files: list[Path], text: str) -> list[CodeRef]:
        """Every line of ``files`` containing ``text``, with its enclosing function's name."""
        refs: list[CodeRef] = []
        for path in files:
            lines = self._lines(path)
            if lines is None:
                continue
            spans = self.functions(path)
            for number, line in enumerate(lines, start=1):
                if text not in line:
                    continue
                function = next(
                    (span.function for span in spans if span.line <= number <= span.end_line),
                    None,
                )
                refs.append(
                    CodeRef(
                        file=str(self._relative(path)),
                        line=number,
                        end_line=number,
                        function=function,
                    )
                )
        return refs

    def commit(self) -> str:
        """The tree's ``git rev-parse HEAD``, or ``"unknown"`` without a git tree."""
        if self._root is None:
            return "unknown"
        try:
            done = subprocess.run(
                ["git", "-C", str(self._root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return "unknown"
        value = done.stdout.strip()
        return value if done.returncode == 0 and value else "unknown"

    def _registering(self, name: str) -> Path | None:
        """The .c file that registers ``name``: the 3-line rule, else the macro-registered rule."""
        if self._root is None:
            return None
        paths = [
            path
            for source_root in _SOURCE_ROOTS
            if (self._root / source_root).is_dir()
            for path in sorted((self._root / source_root).rglob("*.c"))
        ]
        for path in paths:
            lines = self._lines(path)
            if lines is not None and self._usage_follows(lines, name):
                return path
        for path in paths:
            lines = self._lines(path)
            if lines is not None and self._defines_pass(lines, name):
                return path
        return None

    @staticmethod
    def _defines_pass(lines: list[str], name: str) -> bool:
        """True when the file holds ``odin3_pass_def``, ``"<name>"`` and its usage."""
        if "odin3_pass_def" not in "\n".join(lines):
            return False
        exact = False
        usage = False
        for line in lines:
            for literal in _literals(line):
                exact = exact or literal == name
                usage = usage or (
                    literal == name
                    or literal.startswith(name + " ")
                    or literal.startswith(name + ":")
                )
        return exact and usage

    @staticmethod
    def _usage_follows(lines: list[str], name: str) -> bool:
        """True when a literal equal to ``name`` is followed within 3 lines by its usage."""
        for number, line in enumerate(lines):
            literals = _literals(line)
            for at, literal in enumerate(literals):
                if literal != name:
                    continue
                following = literals[at + 1 :]
                for row in lines[number + 1 : number + 4]:
                    following.extend(_literals(row))
                for candidate in following:
                    if (
                        candidate.startswith(name + " ")
                        or candidate.startswith(name + ":")
                        or candidate == name
                    ):
                        return True
        return False

    @staticmethod
    def _body_end(lines: list[str], start: int) -> int | None:
        """The line of the definition's closing brace at column 0, or None.

        The body must open with ``{`` on the signature's line or the next one; the brace
        depths are matched naively (string and comment contents are not masked), and the
        closing brace must sit at column 0.
        """
        opens = "{" in lines[start] or (start + 1 < len(lines) and "{" in lines[start + 1])
        if not opens:
            return None
        depth = 0
        opened = False
        for number in range(start, len(lines)):
            row = lines[number]
            for char in row:
                if char == "{":
                    depth += 1
                    opened = True
                elif char == "}":
                    depth -= 1
                    if opened and depth == 0:
                        return number if row.startswith("}") else None
            if opened and depth < 0:
                return None
        return None

    def _lines(self, path: Path) -> list[str] | None:
        """The file's lines, or None without a root or when the file cannot be read."""
        if self._root is None:
            return None
        try:
            text = (self._root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return text.splitlines()

    def _relative(self, path: Path) -> Path:
        """``path`` relative to the root (a no-op for paths already below it)."""
        assert self._root is not None
        return path.relative_to(self._root) if path.is_absolute() else path
