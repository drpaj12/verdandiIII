"""verdandi command line: record, play, check-notes and info."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from verdandi.notes import load_notes, shipped_dir, stale
from verdandi.odin3.locator import Locator
from verdandi.odin3.record import record, stage_map
from verdandi.trace import _checked_name, load

SUBCOMMANDS = {
    "record": "record a design through Odin III into a trace",
    "play": "replay a recorded trace in the player window",
    "check-notes": "check that every note anchor exists in the current sources",
    "info": "print a trace's step counts and sizes",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verdandi",
        description="Verdandi III: the Micro through the Macro.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    parsers = {
        name: subparsers.add_parser(name, help=help_text, description=help_text)
        for name, help_text in SUBCOMMANDS.items()
    }
    record_parser = parsers["record"]
    record_parser.add_argument("files", nargs="+", metavar="FILE")
    record_parser.add_argument("--top", required=True, metavar="T")
    source = record_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--arch", type=Path, metavar="ARCH.xml")
    source.add_argument("--techlib", type=Path, metavar="LIB")
    record_parser.add_argument("--k", type=int, default=6, metavar="K")
    record_parser.add_argument("--script", type=Path, metavar="FILE")
    record_parser.add_argument("--max-nodes", type=int, default=5000, metavar="N")
    record_parser.add_argument("-o", "--out", type=Path, required=True, metavar="TRACE")
    notes_parser = parsers["check-notes"]
    notes_parser.add_argument("--odin3-root", type=Path, metavar="DIR")
    notes_parser.add_argument("--notes", type=Path, metavar="DIR")
    parsers["play"].add_argument("trace", type=Path, metavar="TRACE")
    parsers["info"].add_argument("trace", type=Path, metavar="TRACE")
    return parser


def _record(args: argparse.Namespace) -> int:
    script = None
    if args.script is not None:
        try:
            script = Path(args.script).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"verdandi record: {exc}", file=sys.stderr)
            return 2
    return record(
        [Path(name) for name in args.files],
        args.top,
        args.out,
        arch=args.arch,
        techlib=args.techlib,
        k=args.k,
        script=script,
        max_nodes=args.max_nodes,
    )


def _snapshot_size(directory: Path, name: str) -> int:
    """The size of one snapshot file; a name that leaves snap/ is refused."""
    return (directory / "snap" / _checked_name(name, "snapshot")).stat().st_size


def _info(args: argparse.Namespace) -> int:
    try:
        trace = load(args.trace)
        names = {step.snapshot for step in trace.steps if step.snapshot is not None}
        total = sum(_snapshot_size(trace.directory, name) for name in names)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"verdandi info: {exc}", file=sys.stderr)
        return 2
    counts = Counter(step.level for step in trace.steps)
    print(f"trace: {trace.directory}")
    print(
        f"format {trace.manifest.version}: odin3 {trace.manifest.program_version}, "
        f"source {trace.manifest.source_commit}"
    )
    print(f"steps: {len(trace.steps)}")
    for level in range(4):
        print(f"level {level}: {counts.get(level, 0)}")
    print(f"snapshots: {len(names)} files, {total} bytes")
    return 0


def _odin3_root(argument: Path | None) -> Path | None:
    """The source tree to check against: ``--odin3-root``, else $ODIN3_ROOT when it is a dir.

    An explicit ``--odin3-root`` that is not a directory raises ValueError: falling back to no
    tree would silently leave every ``func:`` and ``rule:`` anchor unchecked.
    """
    if argument is not None:
        if not argument.is_dir():
            raise ValueError(f"{argument}: not a source tree")
        return argument
    value = os.environ.get("ODIN3_ROOT")
    if value:
        root = Path(value)
        if root.is_dir():
            return root
    return None


def _registered_passes() -> set[str]:
    """The pass names the build registers (spec 8: pass notes checked against Odin3.passes())."""
    try:
        import odin3

        names = odin3.default().passes()
    except Exception as exc:
        raise RuntimeError(f"the odin3 library is not available ({exc})") from exc
    return set(names)


def _check_notes(args: argparse.Namespace) -> int:
    directory = args.notes if args.notes is not None else shipped_dir()
    try:
        notes = load_notes(directory)
        root = _odin3_root(args.odin3_root)
        titles = set(stage_map()[1].values())
        passes = _registered_passes()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"verdandi check-notes: {exc}", file=sys.stderr)
        return 2
    locator = Locator(root)
    anchors = stale(notes, passes, locator, titles)
    for anchor in anchors:
        print(f"{anchor}: stale")
    if anchors:
        print(f"{len(anchors)} stale of {len(notes)} notes")
        return 1
    print(f"{len(notes)} notes, no stale anchors")
    return 0


def _play(args: argparse.Namespace) -> int:
    try:
        trace = load(args.trace)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"verdandi play: {exc}", file=sys.stderr)
        return 2
    try:
        from verdandi.gui.app import player
    except ImportError as exc:
        print(f"verdandi play: the player needs PySide6 ({exc})", file=sys.stderr)
        return 2
    return player(trace)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "record": _record,
        "play": _play,
        "check-notes": _check_notes,
        "info": _info,
    }
    return handlers[args.command](args)
