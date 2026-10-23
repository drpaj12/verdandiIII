"""The Explanation pane: a note for the step, else a generated summary.

Lookup order (plan Task 11): the step's own anchor, then its pass (``pass:<name>``, taken from a
``pass:``, ``rule:`` or ``sub:`` anchor), then its stage (``stage:<title>`` of the root step).
Without a note the pane generates ``"<title>: N added, M removed, K changed"`` and appends up to
five event titles, the step's children in recording order.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from verdandi.notes import load_notes, shipped_dir
from verdandi.trace import Step, Trace

MAX_EVENT_TITLES = 5


def pass_name(anchor: str) -> str | None:
    """The pass an anchor belongs to; None for a stage, function or ABC command anchor."""
    kind, _, rest = anchor.partition(":")
    if kind == "pass":
        return rest or None
    if kind in ("rule", "sub"):
        name = rest.partition(":")[0]
        return name or None
    return None


def root_step(trace: Trace, step: Step) -> Step:
    """The stage (root) step the given step sits under."""
    while step.parent is not None:
        step = trace.step(step.parent)
    return step


def find_note(step: Step, trace: Trace, notes: dict[str, str]) -> str | None:
    """The first note by the plan's order: anchor, pass, stage; None when none matches."""
    note = notes.get(step.anchor)
    if note is not None:
        return note
    name = pass_name(step.anchor)
    if name is not None:
        note = notes.get(f"pass:{name}")
        if note is not None:
            return note
    return notes.get(f"stage:{root_step(trace, step).title}")


def generated(step: Step, trace: Trace) -> str:
    """The summary of a step without a note: diff counts and up to five event titles."""
    diff = step.diff
    added = len(diff.added) if diff is not None else 0
    removed = len(diff.removed) if diff is not None else 0
    changed = len(diff.changed) if diff is not None else 0
    lines = [f"{step.title}: {added} added, {removed} removed, {changed} changed"]
    lines.extend(child.title for child in trace.children(step.id)[:MAX_EVENT_TITLES])
    return "\n".join(lines)


class ExplainPane:
    """The step's note (markdown) or generated text in a read-only browser."""

    def __init__(self, notes: dict[str, str] | None = None) -> None:
        self._notes = notes
        self.widget = QWidget()
        self.browser = QTextBrowser()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)

    def notes(self) -> dict[str, str]:
        """The pane's notes: the ones given, else the shipped Odin III notes (once)."""
        if self._notes is None:
            try:
                self._notes = load_notes(shipped_dir())
            except (OSError, ValueError):
                self._notes = {}
        return self._notes

    def show(self, step: Step, trace: Trace) -> None:
        note = find_note(step, trace, self.notes())
        if note is not None:
            self.browser.setMarkdown(note)
        else:
            self.browser.setPlainText(generated(step, trace))
