anchor: abc:if

`if -K 6 -v`: ABC maps the counter's two bits of next-state logic to two 6-input LUTs. Each LUT
is one cut of the AIG, with the cut's function as its truth table.

The step after it, `mfs2`, rebuilds the LUTs from don't-cares. The whole counter is two LUTs
plus its two flip-flops; the counter example is the shortest walk to the mapped netlist.
