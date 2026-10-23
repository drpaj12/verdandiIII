anchor: pass:proc

The if/else with a self-assignment (`q <= q`) makes the process a hold: `proc` lowers the
`$proc` cell to a `$dff` for `q` and a `$mux` that selects `a & b` or the old `q` on `en`.

The L2 sub-steps walk the process phases first (`clean`, `rmdead`, `prune`, `arst`); then the
real pass writes the cells. In the diff the `$proc` node is replaced by the `$dff`, the `$mux`
and the `$and` that computes `a & b`.
