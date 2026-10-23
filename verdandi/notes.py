"""Anchored notes: short markdown explanations kept beside the recorder (spec 3, D10).

A note is one file under a notes directory. Its first line is ``anchor: <anchor>``, then one
blank line, then at most 15 lines of markdown. The anchor names what the note explains: a stage
of the stage map (``stage:<title>``), a pass (``pass:<name>``), a source function
(``func:<name>``), a logged rewrite (``rule:<pass>:<rule>``) or one command of the ABC script
(``abc:<command>``). ``load_notes`` reads a directory; ``stale`` lists the anchors no current
source backs, so a pass rename or a changed ABC script turns a note stale instead of silently
wrong. A note is advice, never a claim the recorder depends on.
"""

from __future__ import annotations

from pathlib import Path

from verdandi.odin3.abcsteps import abc_script
from verdandi.odin3.events import rule_tokens
from verdandi.odin3.locator import Locator

# The note file format (spec 3; plan Task 9): an anchor line, a blank line, at most this many
# lines of markdown.
MAX_BODY_LINES = 15

_ANCHOR_PREFIX = "anchor: "

# The anchor kinds the format allows (spec 3; plan Task 9).
_KINDS = ("stage", "pass", "func", "rule", "abc")


def shipped_dir() -> Path:
    """The Odin III notes shipped with the package (spec 3: ``verdandi/notes/odin3``)."""
    return Path(__file__).with_name("notes") / "odin3"


def load_notes(directory: Path) -> dict[str, str]:
    """The notes of ``directory`` as anchor -> markdown body, the files in name order.

    Each ``*.md`` file must hold the format above; a file without the anchor line, without the
    blank line after it, with more than ``MAX_BODY_LINES`` lines, or with an anchor another file
    already used raises ``ValueError`` naming the file. A missing directory raises too, and so
    does one with no ``*.md`` file: an empty list of notes is never what a user meant to check.
    """
    if not directory.is_dir():
        raise ValueError(f"{directory}: not a notes directory")
    paths = sorted(directory.glob("*.md"))
    if not paths:
        raise ValueError(f"{directory}: no note files (*.md) in the notes directory")
    notes: dict[str, str] = {}
    for path in paths:
        anchor, body = _parse_note(path)
        if anchor in notes:
            raise ValueError(f"{path}: the anchor {anchor!r} is already used by another note")
        notes[anchor] = body
    return notes


def stale(
    notes: dict[str, str],
    passes: set[str],
    locator: Locator,
    stage_titles: set[str],
) -> list[str]:
    """The anchors no current source backs, in name order (spec 8: ``check-notes``).

    ``pass:`` is checked against the build's pass names, ``stage:`` against the stage map,
    ``abc:`` against the command words of the current ABC script, ``rule:`` against the
    rule-name literals of its pass's source and the fixed rule tokens of its event patterns,
    and ``func:`` against the C function definitions of the pass and front-end roots. Without a
    source tree the function and rule anchors cannot be checked and are left alone; the shipped
    notes carry none, so a tree-less check still means something. An anchor of no known kind is
    stale.
    """
    words = _abc_words(locator)
    anchors: list[str] = []
    for anchor in notes:
        kind, _, rest = anchor.partition(":")
        if kind == "stage" and rest in stage_titles:
            continue
        if kind == "pass" and rest in passes:
            continue
        if kind == "abc" and rest in words:
            continue
        if kind == "func" and _function_exists(rest, locator):
            continue
        if kind == "rule" and _rule_exists(rest, locator):
            continue
        anchors.append(anchor)
    return sorted(anchors)


def _parse_note(path: Path) -> tuple[str, str]:
    """The note file's anchor and markdown body; a malformed file raises ValueError."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith(_ANCHOR_PREFIX):
        raise ValueError(f"{path}: the first line must be 'anchor: <anchor>'")
    anchor = lines[0][len(_ANCHOR_PREFIX) :].strip()
    if not anchor:
        raise ValueError(f"{path}: the anchor is empty")
    if len(lines) < 2 or lines[1].strip():
        raise ValueError(f"{path}: a blank line must follow the anchor line")
    body_lines = lines[2:]
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if len(body_lines) > MAX_BODY_LINES:
        raise ValueError(
            f"{path}: {len(body_lines)} lines of note text (at most {MAX_BODY_LINES})"
        )
    return anchor, "\n".join(body_lines)


def _abc_words(locator: Locator) -> set[str]:
    """The command words of the ABC script the recorder reads (the fallback without a tree)."""
    return {command.split()[0] for command in abc_script(locator.root, 6) if command.split()}


def _function_exists(name: str, locator: Locator) -> bool:
    """True when a source function backs a ``func:`` anchor.

    Without a source tree there is nothing to scan against, so a named anchor is not reported as
    stale (it cannot be checked either way); an empty name is malformed and always is.
    """
    if not name:
        return False
    if locator.root is None:
        return True
    return locator.has_function(name)


def _rule_exists(rest: str, locator: Locator) -> bool:
    """True when a pass's source or event patterns back a ``rule:<pass>:<rule>`` anchor.

    A rule name the pass logs is a runtime value in its DEBUG format, so the format text does
    not hold it; the pass's rule-name table does, as one C string literal per rule. A rule token
    the event patterns name themselves (the format's fixed rule, such as ``lowered``) is backed
    by ``events.rule_tokens``.
    """
    pass_name, _, rule = rest.partition(":")
    if not pass_name or not rule:
        return False
    if locator.root is None:
        return True
    if rule in rule_tokens(pass_name):
        return True
    return locator.has_literal(locator.pass_files(pass_name), rule)
