anchor: pass:proc

`proc` is where this design stops being Verilog: elaboration left one `$proc` cell holding the
`always` block, and `proc` lowers it to a `$dff` for `count` plus a `$mux` that picks
`2'b00` or `count + 2'b01` from `rst`.

The five L2 sub-steps (`--stop-after clean`, `rmdead`, `prune`, `arst`, then the real pass)
show the decision tree shrinking before the muxes appear. Watch the diff on the real step:
the `$proc` node is gone, and the `$dff` and `$mux` are new.
