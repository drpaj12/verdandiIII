"""Pure player state: where the walk is and how to move it (no Qt)."""

from __future__ import annotations

from verdandi.trace import Step, Trace


class Navigator:
    """The walk position over a trace's step tree.

    Moves follow ``parent`` and the children in recording order, never the level number.
    Every move that changes the position pushes the old one onto a history stack, which
    :meth:`back` pops; a move that cannot change anything leaves both untouched.
    """

    def __init__(self, trace: Trace) -> None:
        self.trace = trace
        roots = trace.children(None)
        if not roots:
            raise ValueError("the trace has no steps")
        self._current = roots[0]
        self._history: list[Step] = []

    def current(self) -> Step:
        return self._current

    def next(self) -> Step:
        """The next sibling; with none, the parent's next sibling, climbing to a root."""
        step = self._current
        while True:
            siblings = self.trace.children(step.parent)
            index = siblings.index(step)
            if index + 1 < len(siblings):
                return self._move(siblings[index + 1])
            if step.parent is None:
                return step
            step = self.trace.step(step.parent)

    def step_in(self) -> Step:
        """The first child; unchanged at a step without children."""
        children = self.trace.children(self._current.id)
        return self._move(children[0]) if children else self._current

    def step_out(self) -> Step:
        """The parent; unchanged at a root."""
        if self._current.parent is None:
            return self._current
        return self._move(self.trace.step(self._current.parent))

    def back(self) -> Step:
        """The previous position in the history; unchanged when it is empty."""
        if not self._history:
            return self._current
        self._current = self._history.pop()
        return self._current

    def jump_stage(self, index: int) -> Step:
        """The root at ``index`` (0-based); IndexError outside the stage count."""
        roots = self.trace.children(None)
        if not 0 <= index < len(roots):
            raise IndexError(f"no stage {index}: the trace has {len(roots)}")
        return self._move(roots[index])

    def move_to(self, step_id: str) -> Step:
        """The step with ``step_id`` (a follow match, say); an unknown id raises KeyError."""
        return self._move(self.trace.step(step_id))

    def follow(self, name: str) -> list[Step]:
        """Every step whose diff names an object ``name``, in recording order.

        The first match becomes the current step, so Ctrl+F jumps as it lists.
        """
        matches = [step for step in self.trace.steps if _touches(step, name)]
        if matches:
            self._move(matches[0])
        return matches

    def _move(self, step: Step) -> Step:
        if step is not self._current:
            self._history.append(self._current)
            self._current = step
        return self._current


def _touches(step: Step, name: str) -> bool:
    if step.diff is None:
        return False
    refs = [*step.diff.added, *step.diff.removed, *step.diff.changed]
    return any(ref.name == name for ref in refs)
