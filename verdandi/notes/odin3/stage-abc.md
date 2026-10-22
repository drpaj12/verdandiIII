anchor: stage:ABC: logic optimisation and K-LUT mapping

The soft logic goes to ABC, one run per module per clock domain. Hard cells, black boxes,
instances, level latches and another domain's flip-flops are cut points, so each run sees
only the combinational logic between them.

Today the netlist crosses as BLIF text. ABC's script optimises the AIG and maps it to
K-input LUTs; the result comes back as `$lut` cells (a truth table of 2^WIDTH bits) and the
provenance follows ABC's correspondence between input and output nodes.

The L2 children are ABC's own commands, replayed on the same BLIF with the standalone
binary, so each is a graph transformation you can look at. The pass compacts after, so IDs
are renumbered: the diff across this step matches objects by name and says so.

What to look for: `nd` (network nodes) and `lev` (depth) in each child's `print_stats`, and
the `-> N LUTs ... depth D` line of the run in the pass log.
