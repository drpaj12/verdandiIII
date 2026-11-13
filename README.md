# verdandi

Verdandi III: the Micro through the Macro. Record a micro Verilog design through the current
Odin III pass by pass into a trace, then replay it as an interactive playthrough that shows the
code, the data and the Verilog provenance of every step. Python 3.11+, `odin3` (cffi binding) for
the recorder, PySide6 (extra `gui`) for the player. Verdandi III is part of **Yggdrasil III**, the suite of Odin III (<https://github.com/drpaj12/odin3>, the trunk), Wyrd III (<https://github.com/drpaj12/wyrd>, the canopy, with Bifrost III and Midgard III) and Heimdall III (<https://github.com/drpaj12/heimdallIII>, the canopy viewer), Loki III (<https://github.com/drpaj12/loki>), The Norns III (<https://github.com/drpaj12/nornsIII>), Verdandi III (<https://github.com/drpaj12/verdandiIII>) and Leman Russ III (<https://github.com/drpaj12/lemanrussIII>) on side branches, and Mímir III (<https://github.com/drpaj12/mimirIII>, the fruit). Verdandi III is a side branch, a tool and experiment: the Micro through the Macro. Version 0.1.0 (`pyproject.toml`; in the Yggdrasil III hub snapshot [v1.6.0](https://github.com/drpaj12/YggdrasilIII/blob/v1.6.0/docs/versions.md); Odin III 1.6.0). The hub is <https://github.com/drpaj12/YggdrasilIII> (documentation: <https://drpaj12.github.io/YggdrasilIII/>, versions of every piece: <https://drpaj12.github.io/YggdrasilIII/versions.html>) and its picture of the tree is <https://github.com/drpaj12/YggdrasilIII/blob/main/images/yggdrasil-tree.png>.

In short: a **recorder** (`verdandi record`) writes a trace with a snapshot after every step of four levels (stage, pass,
sub-step, event), including the ABC stage opened into its commands; a **player** (`verdandi play`, extra `gui`) replays it with
the Verilog provenance of each step, a Data pane, a Code pane and shipped notes that explain the stages. It is a teaching and
inspection tool, not an experiment: it has no paper and no measured result. Manual: <https://drpaj12.github.io/verdandiIII/>.
Hub: <https://github.com/drpaj12/YggdrasilIII>.

## Install

Python 3.11+, the `odin3` Python binding of Odin III 1.6.0 (C ABI 7; checked against this version) and, for the
player, PySide6. `odin3` is not on PyPI: install its release wheel, or `pip install cffi PySide6-Essentials`,
`pip install --no-deps -e .` and set `ODIN3_ROOT`, `ODIN3_LIB` and `PYTHONPATH` as in the
[manual](docs/user/index.md). Tools outside the suite and their versions: the hub's
[tools page](https://github.com/drpaj12/YggdrasilIII/blob/main/docs/tools.md).

## Quick start

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" -o trace
    verdandi play trace

Without a VTR checkout, record with `--techlib "$ODIN3_ROOT/lib/lpm.o3lib"` instead (the manual
has both). `N` walks the steps, `I` steps in, `O` steps out; the full walk is in the manual.

Five examples ship under `examples/`: `counter`, `register`, `multiplier`, `instantiation` and
`playthrough` (the existing top that joins the first three). `examples/record-all.sh` checks
each example's notes and records all five into `examples/<name>/trace`, smallest design first.

## Features

Status: **works** = on `main` with tests; **optional** = needs PySide6 (extra `gui`), Graphviz `dot` or a standalone ABC binary.

| Feature | Status | Where |
|---|---|---|
| Recorder: runs a micro Verilog design through the Odin III pass sequence and writes a trace (source, a snapshot after every step, the diff, provenance spans, the code location of the pass, log lines); exit codes 0, 1 (a pass failed, trace kept up to it), 2 | works | `verdandi record`; [manual](docs/user/index.md) |
| Four-level step tree: stage, pass, sub-step (for example the parts of `proc`, `opt` and `fsm`, and the Parse and Elaborate ASTs) and event (parsed from the pass's DEBUG log) | works | `verdandi record`; manual, "The levels" |
| ABC stage opened into its commands (`strash`, `ifraig`, `scorr`, `dc2`, `dch`, `if`, `mfs2`) with node counts and graph pictures, replayed with a standalone ABC binary | optional (ABC binary; without it one pass step) | manual, "The ABC steps" |
| Interactive player: stage map, step tree, Verilog, Code, Data and Explanation panes and a Diff strip; keys N, I, O, B, 1 to 9, Ctrl+F follow | optional (`gui`) | `verdandi play`; manual, "Play it" |
| Provenance in the player: spans of touched objects highlighted in the Verilog pane, a source-line badge on every node and table row, click to open the source at that line | optional (`gui`) | manual, "Play it" |
| Data pane: tables filtered to the touched objects, AST tree, symbol table, graph picture of the touched slice with net labels, structure badges and a colour diff | optional (`gui`; the picture needs Graphviz `dot`) | manual, "Play it" |
| Code pane: the Odin III source file and function that runs the pass, with call depth and a directory zoom | optional (`gui`; needs an Odin III source tree) | manual, "Play it" |
| Shipped notes explaining the stages, key passes and ABC commands, found by anchor | works | `verdandi/notes/odin3/` |
| `check-notes`: checks every note anchor against the current Odin III source, exit 1 and a list when stale | works | `verdandi check-notes --odin3-root` |
| `info`: step counts per level and snapshot sizes without a window | works | `verdandi info TRACE` |
| Five examples (`counter`, `register`, `multiplier`, `instantiation`, `playthrough`) and a script that checks their notes and records all five | works | `examples/`, `examples/record-all.sh` |
| Size guard (`--max-nodes`, default 5000) and deterministic snapshots; a trace is portable and read by the player without Odin III | works | manual, "Install" |

## Documentation

Start at the Yggdrasil III hub; every manual links to the others.

- [Yggdrasil III hub](https://drpaj12.github.io/YggdrasilIII/): the suite, how the pieces connect, getting started.
- [Odin III manual](https://drpaj12.github.io/odin3/).
- [Wyrd III manual](https://drpaj12.github.io/wyrd/), with
  [simulation (Bifrost III)](https://drpaj12.github.io/wyrd/simulation.html) and
  [Midgard III (Verilog Town)](https://drpaj12.github.io/wyrd/midgard.html).
- Tutorials (PDF): [command line](https://drpaj12.github.io/wyrd/wyrd-tutorial.pdf) and
  [GUI](https://drpaj12.github.io/wyrd/wyrd-gui-tutorial.pdf).
- [Loki III manual](https://drpaj12.github.io/loki/).
- [Verdandi III manual](https://drpaj12.github.io/verdandiIII/): this tool, with the shipped
  [playthrough example](examples/playthrough/README.md).
- [The Norns III](https://github.com/drpaj12/nornsIII) (repository; plan under `docs/`; its paper is kept locally by the author).
- [Set up the whole suite](https://drpaj12.github.io/YggdrasilIII/getting-started.html) on a clean Linux or
  Windows machine, and [drive it with Claude Code](https://drpaj12.github.io/YggdrasilIII/ai-agent.html).

Design: [spec](docs/specs/2026-10-22-verdandi-design.md) and [plan](docs/plans/2026-10-22-verdandi-plan.md).
