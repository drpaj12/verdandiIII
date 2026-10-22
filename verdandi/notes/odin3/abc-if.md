anchor: abc:if

`if` is the K-LUT technology mapping: every AIG node gets its K-feasible cuts (cones of at
most K inputs), the mapper picks a cover of the AIG by those cuts, and each chosen cut
becomes one K-input LUT whose truth table is the cut's function.

This is the step where the graph changes kind: nodes become LUTs, and `print_stats` reports
`nd` (network nodes) and `lev` (depth) where it reported `and`. ABC's `nd` is the network
node count, LUTs plus the buffer nodes Odin aliases on read-back; counter2 has 2 LUTs and
depth 1 with nd 4 (the two extra nodes are its output buffers, written as one-input `1 1`
covers that Odin III reads as a connection, not a LUT).

What to look for: `nd` falls towards the LUT count and `lev` is the depth; the pass log's
`-> N LUTs (at most K inputs, depth D)` gives both for the run the replay follows. In the
4x4 multiply: nd 21, lev 3.
