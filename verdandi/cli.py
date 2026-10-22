"""verdandi command line: record, play, check-notes and info."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from verdandi.odin3.record import record
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "record":
        return _record(args)
    if args.command == "info":
        return _info(args)
    print(f"verdandi {args.command}: not implemented yet")
    return 2
