"""L3 events: one logged action per object-naming DEBUG line (spec 4, plan Task 8).

The recorder raises the library's log level to DEBUG while a pass runs; each pass format that
names a design object (a module, cell, net, name or state) has one pattern here, found from the
``ODIN3_LOG_DEBUG`` call sites under ``src/passes``. A matching line gives an event title (the
message with its pass prefix and module kept to the pass name) and an anchor
``rule:<pass>:<rule>``; a line no pattern matches gives no event (spec 10). The format text
before its first ``%`` is kept so the recorder can find the line that logs the event.

A pass name that logs under another name (``hardmap`` is the alias of ``partial_map``) reuses
that pass's rows: the log prefix is stripped, the title carries the step's pass name.
"""

from __future__ import annotations

import re

# One pattern row: the compiled pattern, the format's text before its first %, and the rule
# token used when the pattern has no "rule" named group.
_Row = tuple[re.Pattern[str], str, str]

_MODULE_PREFIX = re.compile(r"^module '[^']*': ")
_LOG_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*: ")

_ROWS: dict[str, list[_Row]] = {
    "abc": [
        (
            re.compile(r"^abc: module '(?P<module>[^']*)': nothing to map$"),
            "abc: module '",
            "nothing_to_map",
        ),
    ],
    "flatten": [
        (
            re.compile(r"^flatten: renamed '(?P<name>[^']*)' \(name taken\)$"),
            "flatten: renamed '",
            "renamed",
        ),
    ],
    "fsm": [
        (
            re.compile(
                r"^fsm: transition: (?P<from>\d+) (?P<in>\S*) -> (?P<to>\d+) (?P<out>\S*)"
                r"(?: (?P<what>.*))?$"
            ),
            "fsm: transition: ",
            "transition",
        ),
        (
            re.compile(r"^fsm: removing unreachable state (?P<state>\d+)$"),
            "fsm: removing unreachable state ",
            "unreachable_state",
        ),
        (
            re.compile(r"^fsm: removing unused output signal (?P<signal>\d+)$"),
            "fsm: removing unused output signal ",
            "unused_output",
        ),
        (
            re.compile(r"^fsm: input signals (?P<first>\d+) and (?P<second>\d+) are one signal$"),
            "fsm: input signals ",
            "one_signal",
        ),
        (
            re.compile(r"^fsm: signal is input (?P<signal>\d+) and output (?P<output>\d+)$"),
            "fsm: signal is input ",
            "inout",
        ),
        (
            re.compile(r"^fsm: removing unused input signal (?P<signal>\d+)$"),
            "fsm: removing unused input signal ",
            "unused_input",
        ),
        (
            re.compile(r"^fsm: state (?P<state>\d+) -> index (?P<index>\d+)$"),
            "fsm: state ",
            "state_index",
        ),
    ],
    "lower": [
        (
            re.compile(
                r"^lower: module '(?P<module>[^']*)': (?P<type>\S+) '(?P<cell>[^']*)' -> "
                r"(?P<bits>\d+) bit cells$"
            ),
            "lower: module '",
            "lowered",
        ),
    ],
    "lpmmap": [
        (
            re.compile(r"^lpmmap: cell '(?P<cell>[^']*)' mapped to an LPM block$"),
            "lpmmap: cell '",
            "mapped",
        ),
    ],
    "opt_clean": [
        (
            re.compile(
                r"^opt_clean: module '(?P<module>[^']*)': removing unused (?P<type>\S+) "
                r"'(?P<cell>[^']*)'$"
            ),
            "opt_clean: module '",
            "removing_unused",
        ),
    ],
    "opt_dff": [
        (
            re.compile(
                r"^opt_dff: module '(?P<module>[^']*)': (?P<action>.+?) on (?P<type>\S+) "
                r"'(?P<cell>[^']*)'$"
            ),
            "opt_dff: module '",
            "dff_action",
        ),
    ],
    "opt_expr": [
        # The rewrite line (plan Task 8). It also matches the "undriven on net '<net>'" line,
        # whose rule group then reads "undriven": one pattern, both formats.
        (
            re.compile(
                r"^opt_expr: module '(?P<module>[^']*)': (?P<rule>\S+) on (?P<type>\S+) "
                r"'(?P<cell>[^']*)'$"
            ),
            "opt_expr: module '",
            "rewrite",
        ),
    ],
    "opt_merge": [
        (
            re.compile(
                r"^opt_merge: -ffbits: '(?P<drop>[^']*)' bit (?P<drop_bit>\d+) is identical to "
                r"'(?P<keep>[^']*)' bit (?P<keep_bit>\d+)$"
            ),
            "opt_merge: -ffbits: '",
            "ffbits",
        ),
        (
            re.compile(
                r"^opt_merge: module '(?P<module>[^']*)': '(?P<drop>[^']*)' is identical to "
                r"'(?P<keep>[^']*)'$"
            ),
            "opt_merge: module '",
            "merged",
        ),
    ],
    "opt_muxtree": [
        (
            re.compile(
                r"^opt_muxtree: module '(?P<module>[^']*)': dead port (?P<port>\d+)/"
                r"(?P<ports>\d+) on (?P<type>\S+) '(?P<cell>[^']*)'$"
            ),
            "opt_muxtree: module '",
            "dead_port",
        ),
    ],
    "partial_map": [
        (
            re.compile(r"^partial_map: '\$mul' cell '(?P<cell>[^']*)' mapped to a multiply$"),
            "partial_map: '$mul' cell '",
            "mul",
        ),
        (
            re.compile(
                r"^partial_map: '\$mem' cell '(?P<cell>[^']*)' mapped to (?P<slices>\d+) slices$"
            ),
            "partial_map: '$mem' cell '",
            "mem_slices",
        ),
        (
            re.compile(
                r"^partial_map: '(?P<type>[^']*)' cell '(?P<cell>[^']*)' mapped to "
                r"(?P<slices>\d+) slices$"
            ),
            "partial_map: '",
            "ram_slices",
        ),
        (
            re.compile(
                r"^partial_map: '(?P<type>[^']*)' cell '(?P<cell>[^']*)' mapped to an adder "
                r"chain$"
            ),
            "partial_map: '",
            "adder_chain",
        ),
    ],
    "wreduce": [
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': removed top (?P<bits>\d+) address bits "
                r"\(of (?P<of>\d+)\) from memory '(?P<cell>[^']*)'$"
            ),
            "wreduce: module '",
            "memory_narrowed",
        ),
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': removed top (?P<bits>\d+) bits "
                r"\(of (?P<of>\d+)\) from mux cell (?P<type>\S+) '(?P<cell>[^']*)'$"
            ),
            "wreduce: module '",
            "mux_narrowed",
        ),
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': removed top (?P<bits>\d+) bits "
                r"\(of (?P<of>\d+)\) from FF cell (?P<type>\S+) '(?P<cell>[^']*)'$"
            ),
            "wreduce: module '",
            "ff_narrowed",
        ),
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': removed top (?P<bits>\d+) bits "
                r"\(of (?P<of>\d+)\) from (?P<what>\S+) (?P<type>\S+) '(?P<cell>[^']*)'$"
            ),
            "wreduce: module '",
            "removed_top_bits",
        ),
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': converting (?P<type>\S+) "
                r"'(?P<cell>[^']*)' from (?P<how>.+)$"
            ),
            "wreduce: module '",
            "converted",
        ),
        (
            re.compile(
                r"^wreduce: module '(?P<module>[^']*)': removed (?P<type>\S+) '(?P<cell>[^']*)'$"
            ),
            "wreduce: module '",
            "removed",
        ),
    ],
}

# hardmap is partial_map's alias: it logs under the partial_map prefix and reuses its rows.
_ROWS["hardmap"] = _ROWS["partial_map"]

# The pass-name key -> its patterns, in the order a line is tried (plan Task 8 PATTERNS).
PATTERNS: dict[str, list[re.Pattern[str]]] = {
    name: [pattern for pattern, _prefix, _rule in rows] for name, rows in _ROWS.items()
}


def match(pass_name: str, line: str) -> tuple[str, str, str] | None:
    """The line's event as (title, anchor, format prefix), or None when no pattern matches.

    The title is the line with its log prefix replaced by the pass name and its module part
    dropped (the plan's example: ``opt_expr: const_and on $and '$c12'``); the anchor is
    ``rule:<pass>:<rule>`` with the matched rule group, else the format's rule token.
    """
    for pattern, prefix, rule in _ROWS.get(pass_name, []):
        found = pattern.match(line)
        if found is None:
            continue
        rule_name = found.groupdict().get("rule") or rule
        text = _MODULE_PREFIX.sub("", _LOG_PREFIX.sub("", line)).rstrip()
        return f"{pass_name}: {text}", f"rule:{pass_name}:{rule_name}", prefix
    return None


def events(pass_name: str, log: list[str]) -> list[tuple[str, str]]:
    """The log's events as (title, anchor) pairs, in log order; a pass without patterns: none."""
    found: list[tuple[str, str]] = []
    for line in log:
        hit = match(pass_name, line)
        if hit is not None:
            found.append((hit[0], hit[1]))
    return found
