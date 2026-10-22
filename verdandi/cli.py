"""verdandi command line: record, play, check-notes and info."""

from __future__ import annotations

import argparse

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
    for name, help_text in SUBCOMMANDS.items():
        subparsers.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"verdandi {args.command}: not implemented yet")
    return 2
