# Verdandi III

Verdandi III is the Micro through the Macro: it records a small Verilog design through the Odin
III pass sequence, one step at a time, and replays the recording as an interactive walk through
the code, the data and the Verilog source. It is part of the Yggdrasil III suite; the other
manuals are linked in the sidebar.

A recording is a **trace**: a directory holding the source, one snapshot of the design after
every step, the diff from the step before, the provenance spans of the objects that changed, the
source code location of the pass, and its log lines. The notes that explain the steps ship with
Verdandi (`verdandi/notes/odin3`), not with the trace, and the player looks one up by the step's
anchor. The player reads only the trace and those notes, so it never runs Odin III itself; only
the Code pane reads the Odin III source tree.

This page walks the shipped example: record it, play it, and see what every level and every key
shows. The one-page commands are also in `examples/playthrough/README.md`.

## Install

Verdandi needs Python 3.11 or newer and the `odin3` Python binding. The player needs PySide6
(extra `gui`); a standalone ABC binary and Graphviz `dot` are optional.

    python3 -m venv .venv
    .venv/bin/pip install -e ".[gui]"

To record against a local Odin III source tree, point the binding at it and keep the source tree
handy for the code locator (the Code pane and `check-notes` read it):

    export ODIN3_ROOT=/path/to/odin3
    export ODIN3_LIB=$ODIN3_ROOT/build/release/libodin3.so
    export PYTHONPATH=$ODIN3_ROOT/plugins/python

A standalone ABC binary (`$ODIN3_ABC`, else `$ODIN3_ROOT/build/*/third_party/abc/abc`) opens up
the ABC stage into its script commands; without one the ABC stage shows its single pass step and
the recorder warns once. Graphviz `dot` draws the data slice of each step; without it the Data
pane shows the tables only.

## Record the playthrough

The example is `examples/playthrough/playthrough.v`: a 2-bit counter, a register with an if/else,
a 4x4 multiplier and the top that joins them. Record it with the k6 architecture:

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o trace

`--top` names the top module and `-o` the trace directory (an existing trace is replaced). The
default script is the production flow:

    read_arch ARCH; read_verilog --nolatches --vtr-compat FILE; hierarchy --top playthrough;
    proc; fsm; opt; flatten; opt -full; wreduce; hardmap; lower; abc --lut 6; write_blif OUT

`--k K` changes the LUT size (default 6) and `--script FILE` replaces the whole script. Without a
VTR checkout, record with the LPM tech library instead; the first command is then
`read_techlib LIB` and `hardmap` is omitted:

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o trace

Five examples ship under `examples/`: `counter`, `register`, `multiplier` and `instantiation`
(each records its module alone, with its own README and notes) and `playthrough`, the existing
top that joins the counter, register and multiplier. The instantiation example shows a module
used inside another: a parameterised counter instantiated twice at different widths plus a leaf
gate module. `examples/record-all.sh` checks every example's notes with `verdandi check-notes`
and records all five into `examples/<name>/trace`, smallest design first.

With Odin III v1.0.0 and the k6 architecture the recording has 83 steps: 13 stages, 13 passes, 42
sub-steps and 15 logged events. It exits 0. A pass that fails ends the recording with that step
marked failed and its log kept, and exits 1; a usage or environment error exits 2.

The trace directory is portable: the player needs no Odin III to read it, and only the Code pane
needs the Odin III source, at the recorded commit. The directory holds:

    trace/manifest.json   format version, Odin III version and source commit, files, top, arch, script
    trace/steps.json      the step tree: id, parent, level, title, anchor, snapshot, diff, code, log
    trace/snap/*.json     the design after each step (IR modules, nodes, nets, wires, or an AST)
    trace/src/            the recorded Verilog, so a later edit to your file does not change the walk
    trace/pic/*.dot       the graph picture of each opened-up ABC step

## Play it

    verdandi play trace

The window has a stage map, a step tree and four panes. The stage map is the paper's flow figure:
one box per recorded stage, the current one lit; click a box to jump. The step tree shows the
steps at every level. The panes follow the selected step:

- **Verilog** shows the recorded source with the provenance spans of the touched objects
  highlighted.
- **Code** shows the Odin III source file that registers the pass, at the function that runs it
  (root from the `codeRoot` app setting, else `$ODIN3_ROOT`). A click on a data-pane object opens
  the trace's copy of the example source at that object's line in its own tab, beside the step's
  source tabs.
- **Data** shows the snapshot's tables, filtered to the touched objects by default, an AST tree
  for the Parse and Elaborate steps, a symbol table, and a graph picture of the touched slice when
  `dot` is installed. Every node and table row carries its source line as a small grey provenance
  badge (the "show all provenance" checkbox hides them), and a click on a graph node, a table row
  or cell, or an AST node opens the example source at that loc's line in the Code pane.
- **Explanation** shows the note for the step, else a generated summary of its diff.
- The **Diff** strip counts what the step added (green), removed (red) and changed (amber).

`verdandi info trace` prints the step counts per level and the size of the snapshots without
opening a window.

### Keys

| Key | Action |
|---|---|
| `N` or `Space` | next step (the next sibling, else the parent's next sibling) |
| `I`, `Enter` or `Return` | step in (the first child, else stay) |
| `O` or `Backspace` | step out (the parent, else stay) |
| `B` | back (the previous position; the trace is recorded, so back is free) |
| `1` to `9` | jump to that stage (the stage map's first nine boxes) |
| `Ctrl+F` | focus the follow box (Enter follows it); press again for the next match |

Follow matches every step whose diff names the object (a node, a net or a wire), in recorded
order. `Ctrl+F` focuses the follow box and selects its text; type a name and press `Enter` to
follow it, or press `Ctrl+F` again to cycle to the next match.

### The levels

A playthrough is a tree of four levels (the player's step tree shows all of them):

- **L0 stage**: a box of the flow figure, e.g. Read architecture, Parse and elaborate, Processes,
  State machines, Optimisation, Flatten, Width reduction, Hard-block mapping, Lower, ABC, Write
  BLIF. A script command the stage map does not list (Odin III's `hierarchy`) gets a stage of its
  own, titled by the pass name, and `opt` appears twice when the script runs `opt` and later
  `opt -full`.
- **L1 pass**: one command of the script, titled by the command, e.g. `proc` or `opt -full`.
- **L2 sub-step**: a pass's documented parts, run one by one on a copy of the design: `proc`
  stops after each of its clean, rmdead, prune and arst phases and then the real `proc`; `opt`
  shows its parts in source order (`opt_expr`, `opt_merge -nomux`, then each iteration's
  `opt_muxtree`, `opt_reduce`, `opt_merge`, `opt_share` with `-full`, `opt_dff`, `opt_clean`,
  `opt_expr`); `fsm_detect` then `fsm`;
  Parse and Elaborate from the PARSED and ELABORATED ASTs; and one step per ABC command (below).
  A copy whose result differs from the real pass marks the step "illustration".
- **L3 event**: one logged action inside a step, parsed from the pass's DEBUG log lines, e.g.
  `opt_clean: removing unused $mux '$c8'` or `lower: $sdff '$c15' -> 4 bit cells`. A pass whose
  log lines match no pattern simply has no L3 children.

Walking the example with `N` from the top: Read architecture, Parse and elaborate, hierarchy, the
counter's always block is turned into processes (five `proc` sub-steps), the state machine pass
finds none, the first `opt` runs two iterations (`opt_clean` removes two unused multiplexers),
`flatten` inlines the three child modules into the top, `opt -full` runs once more with sharing,
`wreduce` narrows the data paths, `hardmap` maps the multiplies and adders to hard blocks,
`lower` splits the wide cells into bit cells, ABC maps the soft logic, and `write_blif` writes the
network.

## The ABC steps

Odin III's `abc` pass hands each module's soft logic to ABC with the script
`lib/abc/vtr.abc`. Verdandi opens that step without changing Odin III: on a copy of the design it
runs `abc --lut K --via-blif DIR` to obtain the exact BLIF exchanged with ABC, then replays the
script on that BLIF with the standalone ABC binary, one command at a time. After each command
ABC's own `print_stats`, `write_dot` and `write_blif` give the step's numbers, its graph picture
and its network. The commands, as L2 steps under the ABC stage:

- `strash`: the logic becomes an AIG of two-input ANDs with inverted edges, structurally hashed
  so that equal subgraphs are shared. The example's first module arrives with 18 AIG nodes at
  level 3.
- `ifraig -v`: nodes proven combinationally equivalent are merged (the example: none to merge,
  still 18 nodes).
- `scorr -v`: sequentially equivalent registers are merged across clock cycles (still 18).
- `dc2 -v`: local rewriting and balancing of the AIG (still 18).
- `dch -f`: rewriting with choices, keeping several equivalent structures for the mapper to pick
  from (the choice nodes lift the count from 18 to 32 until mapping picks one cover).
- `if -K 6 -v`: the K-LUT technology mapping. Every AIG node gets its K-feasible cuts, the mapper
  picks a cover of the AIG by cuts, and each chosen cut becomes one 6-input LUT whose truth table
  is the cut's function. The example's first module ends with 6 LUTs at depth 1 (its network
  reports 12 nodes because the six outputs each add a buffer); the whole design maps to 12 LUTs
  (counter 2, register 4, playthrough 6) plus its flip-flops.
- `mfs2 -v`: each LUT is simplified using don't-cares from its window (resubstitution); in the
  example no node is removed, but the fields are recomputed (12 nodes, 16 cubes).

If the standalone replay's network node count differs from the linked run's, the L2 steps are
marked "illustration": the shapes are ABC's, the numbers are the replay's.

## Notes and check-notes

The shipped notes (`verdandi/notes/odin3/*.md`) are short explanations, one per stage, per key
pass (`proc`, some `opt` parts, `hardmap`, `lower`, `flatten`, `wreduce`) and per ABC command.
Each file starts with an anchor line naming where it belongs:

    anchor: stage:Optimisation
    anchor: pass:opt_expr
    anchor: abc:if

The player looks up the step's own anchor first, then its pass, then its stage, and falls back to
a generated summary of the diff. `verdandi check-notes` checks every anchor against the current
Odin III source: pass names against the registered passes, function and rule anchors against the
source tree. It exits 0 when all anchors still exist and 1 listing the stale ones, so a rename in
Odin III is caught before the manual or the player is published:

    verdandi check-notes --odin3-root "$ODIN3_ROOT"

## Following a code change

A trace records the result of a code change; it does not follow the code as it changes. After
changing Odin III or the design, record again (the same `verdandi record` command, with the same
`-o trace`), and replay the new trace. The Code pane then opens the current source at the
recorded locations, and `check-notes` says whether any note anchor moved. The manifest keeps the
source commit of each recording, so two traces can be compared side by side.
