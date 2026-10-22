anchor: abc:mfs2

`mfs2` is don't-care-based optimisation of the LUT network: each LUT's function is
re-synthesised inside a window of its fanout cone, using the don't-cares the surrounding
logic allows, so a LUT can lose an input or change its table without changing the design.

The lines after `if` and `mfs2` also report `aig` and `cube` (AIG nodes, and the SOP cubes of
the LUT tables); the numbers to compare are `nd` and `lev`. For the counter both stay at
nd 4, depth 1; for the 4x4 multiply nd stays 21 at depth 3.

What to look for: unchanged `nd` and `lev` mean the mapping was already good. `cube` is the
total number of SOP cubes over the LUT tables, so a lower count means simpler tables.
