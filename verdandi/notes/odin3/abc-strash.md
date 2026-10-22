anchor: abc:strash

`strash` is ABC's structural hashing: the network read from BLIF is rebuilt as an
and-inverter graph (AIG), two-input ANDs with inversion carried on the edges. Identical
subgraphs become one node, which is what "structural hashing" means.

This is the starting point of every later command: the AIG is what `ifraig`, `dc2`, `dch`
and the mapper rewrite.

What to look for: the step's `print_stats` line. For the counter it is
`i/o = 1/2  lat = 2  and = 5  lev = 3`: two registers, five AND nodes, depth 3. Watch `and`
and `lev` move from here.
