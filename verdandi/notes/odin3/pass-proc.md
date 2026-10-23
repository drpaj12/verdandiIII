anchor: pass:proc

`proc` is the first real transformation in the flow: it lowers the `$proc` cell that
elaboration made for an `always` block into mux trees, latches and flip-flops.

It mirrors Yosys 0.55's `proc -norom` sub-passes as phases of one pass, in Yosys's order:
`clean`, `rmdead`, `prune`, `arst` (decision-tree cleanup, run on every process of a module
before the IR changes), then `mux`, `latch`, `ff`, and an `opt_expr -keepdc` at the end. A
module with an error keeps its processes, and the analysis phases never change the IR.

Why the L2 sub-steps: `--stop-after clean|rmdead|prune|arst` re-encodes each process after
that phase, so the playthrough can show the decision tree shrinking before the muxes appear.
The diff shows each `$proc` node replaced by cells; anything the process leaves dead is
removed by the next `opt_clean`.
