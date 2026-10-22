anchor: stage:Processes

`proc` removes the `$proc` cells: each process becomes ordinary cells. It does what Yosys's
`proc -norom` does, in the same phases.

First comes analysis, which changes nothing: decode the decision tree, then `clean`,
`rmdead`, `prune` and `arst`, plus the clock pre-check. Only if every process of a module
passes does the module change: mux trees, then latches, then flip-flops, and finally an
`opt_expr -keepdc`. A module with one error keeps all its `$proc` nodes, so a module is
lowered completely or not at all.

Why the separate phases: the playthrough shows them as the L2 sub-steps (`--stop-after
clean|rmdead|prune|arst`, each from the same starting design), so you can watch a process
go from a decision tree to muxes and a register before the whole pass runs.
