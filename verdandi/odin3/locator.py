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

# The call whose DEBUG format logs an event, and the level token that call must name.
_LOG_CALL = "odin3_log"
_DEBUG_LEVEL = "ODIN3_LOG_DEBUG"


def _literals(line: str) -> list[str]:
    """The contents of the line's C string literals, in order."""
    return _LITERAL.findall(line)


def _skip_literal(text: str, start: int) -> int:
    """The index after the C string or character literal that starts at ``start``."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote or char == "\n":
            return index + 1
        index += 1
    return index


def _skip_comment(text: str, start: int) -> int:
    """The index after the C comment at ``start``; a line comment ends at its newline."""
    if text.startswith("/*", start):
        end = text.find("*/", start + 2)
        return len(text) if end < 0 else end + 2
    end = text.find("\n", start + 2)
    return len(text) if end < 0 else end


def _call_end(text: str, open_at: int) -> int:
    """The index after the ``)`` that closes the call whose ``(`` is at ``open_at``."""
    depth = 0
    index = open_at
    while index < len(text):
        char = text[index]
        if char == "/" and text.startswith(("/*", "//"), index):
            index = _skip_comment(text, index)
        elif char in "\"'":
            index = _skip_literal(text, index)
        else:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index + 1
            index += 1
    return len(text)


def _is_token(text: str, index: int, token: str) -> bool:
    """True when ``token`` starts at ``index`` as a whole C identifier."""
    if not text.startswith(token, index):
        return False
    before = text[index - 1] if index > 0 else ""
    after = text[index + len(token)] if index + len(token) < len(text) else ""
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _debug_call_lines(text: str) -> dict[int, int]:
    """Line numbers inside an ``odin3_log(ODIN3_LOG_DEBUG, ...)`` call -> the call's first line.

    A call's span is measured with comments and literals skipped, so a format's parentheses do
    not end it early. A line outside every DEBUG call is absent from the mapping.
    """
    lines: dict[int, int] = {}
    index = 0
    while index < len(text):
        char = text[index]
        if char == "/" and text.startswith(("/*", "//"), index):
            index = _skip_comment(text, index)
        elif char in "\"'":
            index = _skip_literal(text, index)
        elif _is_token(text, index, _LOG_CALL):
            open_at = index + len(_LOG_CALL)
            while open_at < len(text) and text[open_at].isspace():
                open_at += 1
            if open_at >= len(text) or text[open_at] != "(":
                index += len(_LOG_CALL)
                continue
            end = _call_end(text, open_at)
            if text[open_at + 1 : end].lstrip().startswith(_DEBUG_LEVEL):
                first = text.count("\n", 0, index) + 1
                last = text.count("\n", 0, end) + 1
                for number in range(first, last + 1):
                    lines.setdefault(number, first)
            index = end
        else:
            index += 1
    return lines


class Locator:
    """Code locations in the Odin III source tree rooted at ``root`` (None: no tree)."""

    def __init__(self, root: Path | None) -> None:
        self._root = root.resolve() if root is not None else None

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

    def find_log_text(self, files: list[Path], text: str) -> list[CodeRef]:
        """Every DEBUG log call of ``files`` whose format holds ``text``.

        The ref is the call's first line, the line that names ``ODIN3_LOG_DEBUG`` and the
        format; a comment, an INFO line, or a call whose message merely shares the prefix does
        not log an event and is left out. A format that spans lines still gives one ref: the
        line that opens its call.
        """
        refs: list[CodeRef] = []
        for path in files:
            content = self._text(path)
            if content is None:
                continue
            starts = _debug_call_lines(content)
            if not starts:
                continue
            lines = content.splitlines()
            spans = self.functions(path)
            seen: set[int] = set()
            for number, line in enumerate(lines, start=1):
                if text not in line or number not in starts:
                    continue
                first = starts[number]
                if first in seen:
                    continue
                seen.add(first)
                function = next(
                    (span.function for span in spans if span.line <= first <= span.end_line),
                    None,
                )
                refs.append(
                    CodeRef(
                        file=str(self._relative(path)),
                        line=first,
                        end_line=first,
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

    def _text(self, path: Path) -> str | None:
        """The file's text, or None without a root or when the file cannot be read."""
        if self._root is None:
            return None
        try:
            return (self._root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _lines(self, path: Path) -> list[str] | None:
        """The file's lines, or None without a root or when the file cannot be read."""
        text = self._text(path)
        return None if text is None else text.splitlines()

    def _relative(self, path: Path) -> Path:
        """``path`` relative to the root (a no-op for paths already below it)."""
        assert self._root is not None
        return path.relative_to(self._root) if path.is_absolute() else path
