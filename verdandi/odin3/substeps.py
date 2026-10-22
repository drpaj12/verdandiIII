"""Sub-steps (L2): a pass's documented parts, run one by one on copies (spec 4, plan Task 8).

``proc`` runs its cumulative stop points, each from a fresh copy of the design before the pass;
``fsm`` runs ``fsm_detect`` and ``fsm`` in sequence on one copy; ``opt`` runs the driver's
prologue and then its loop, repeating until the IR stops changing (at most ten iterations), and
each iteration is a group "Iteration n" whose children are the loop's sub-passes. A recording
marks the sub-steps "illustration" when the last one does not ``match`` the real pass's result:
the decomposition then shows something other than what the pass did.

The ``expand`` entries are flat: an iteration group's title starts with ``ITERATION_PREFIX`` and
its snapshot is the iteration's end state, which is also its last child's snapshot; the recorder
nests the entries that follow it under it. ``matches`` compares the shape of two IR snapshots:
the multiset of node types per module and the net count.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from verdandi.odin3.snapshot import ir_snapshot

if TYPE_CHECKING:
    import odin3

# One expanded sub-step: its title, the snapshot after it and the log it wrote.
Entry = tuple[str, dict[str, Any], list[str]]

# The passes whose documented parts are opened up (spec 4, L2).
SUBSTEPS: dict[str, list[str]] = {
    "proc": [
        "proc --stop-after clean",
        "proc --stop-after rmdead",
        "proc --stop-after prune",
        "proc --stop-after arst",
        "proc",
    ],
    "fsm": ["fsm_detect", "fsm"],
}

# The opt driver's prologue, then its loop body in the source's order (Yosys 0.55 opt.cc);
# opt_share runs only with -full, right after opt_merge.
OPT_PROLOGUE: list[str] = ["opt_expr", "opt_merge -nomux"]
OPT_LOOP: list[str] = [
    "opt_muxtree",
    "opt_reduce",
    "opt_merge",
    "opt_share",
    "opt_dff",
    "opt_clean",
    "opt_expr",
]

# The driver's own cap (ODIN3_OPT_MAX_ITERATIONS): a loop that does not settle stops here.
OPT_MAX_ITERATIONS = 10

# An iteration group's title prefix; its entries carry the iteration's end snapshot.
ITERATION_PREFIX = "Iteration "

# A proc stop point starts from the design before the pass; the other sequences share one copy.
_FRESH_SUBSTEPS = frozenset({"proc"})


def opt_loop(full: bool) -> list[str]:
    """The loop body ``opt`` runs: ``opt_share`` joins it only for ``opt -full``."""
    return [command for command in OPT_LOOP if full or command != "opt_share"]


def expand(before: odin3.Design, command: str) -> list[Entry]:
    """The pass command's sub-steps, in order; an empty list when it has none.

    ``before`` is left open and unchanged: every sub-step runs on a copy of it.
    """
    name, arguments = _split(command)
    if name in SUBSTEPS:
        return _expand_sequence(before, SUBSTEPS[name], fresh=name in _FRESH_SUBSTEPS)
    if name == "opt":
        return _expand_opt(before, arguments)
    return []


def matches(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when the two IR snapshots have the same shape.

    The shape is the multiset of node types per module and the net count: IDs and names may
    differ, as they do between a copy's run and the pass's own.
    """
    return _profile(a) == _profile(b)


def _profile(snapshot: dict[str, Any]) -> list[tuple[Any, list[tuple[Any, int]], int]]:
    """One (module name, sorted node-type counts, net count) row per module, rows sorted."""
    rows = [
        (
            module.get("name"),
            sorted(Counter(node.get("type") for node in module.get("nodes", [])).items()),
            len(module.get("nets", [])),
        )
        for module in snapshot.get("modules", [])
    ]
    rows.sort()
    return rows


def _split(command: str) -> tuple[str, str]:
    """The command's pass name and its arguments (empty for a bare command)."""
    parts = command.split(maxsplit=1)
    return parts[0], parts[1].strip() if len(parts) > 1 else ""


def _run(design: odin3.Design, command: str) -> tuple[dict[str, Any], list[str]]:
    """Run one command on ``design`` at DEBUG level; its snapshot and its log lines."""
    name, arguments = _split(command)
    with design.odin3.capture_log() as records:
        # capture_log restores the level when the block ends.
        design.odin3.call("odin3_log_set_level", design.odin3.lib.ODIN3_LOG_DEBUG)
        design.run_pass(name, arguments)
    return ir_snapshot(design), [record.message for record in records]


def _entry(design: odin3.Design, command: str) -> Entry:
    """One sub-step entry: the command is its title."""
    snapshot, log = _run(design, command)
    return command, snapshot, log


def _expand_sequence(before: odin3.Design, commands: list[str], *, fresh: bool) -> list[Entry]:
    """A fixed sequence of sub-passes: each on a fresh copy, or all on one copy in sequence."""
    if not fresh:
        copy = before.copy()
        try:
            return [_entry(copy, command) for command in commands]
        finally:
            copy.close()
    entries: list[Entry] = []
    for command in commands:
        copy = before.copy()
        try:
            entries.append(_entry(copy, command))
        finally:
            copy.close()
    return entries


def _expand_opt(before: odin3.Design, arguments: str) -> list[Entry]:
    """The opt driver's prologue and iterations, each iteration a group plus its sub-passes.

    The loop repeats while an iteration's end snapshot differs from the one before it (the
    prologue's end for the first), and stops at OPT_MAX_ITERATIONS either way.
    """
    loop = opt_loop("-full" in arguments.split())
    copy = before.copy()
    entries: list[Entry] = []
    try:
        for command in OPT_PROLOGUE:
            entries.append(_entry(copy, command))
        previous = ir_snapshot(copy)
        for number in range(1, OPT_MAX_ITERATIONS + 1):
            iteration = [_entry(copy, command) for command in loop]
            end = iteration[-1][1]
            entries.append((f"{ITERATION_PREFIX}{number}", end, []))
            entries.extend(iteration)
            if end == previous:
                break
            previous = end
    finally:
        copy.close()
    return entries
