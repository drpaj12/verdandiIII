anchor: abc:ifraig

`ifraig` is fraiging: it builds candidate equivalence classes by simulation, proves each
candidate with SAT sweeping, and merges the proven-equal nodes. It works combinationally: it
does not look across registers.

The result is a smaller AIG with the same function: fewer AND nodes, often shallower.

What to look for: `and` and `lev` fall. In the 4x4 multiply the AIG goes from 107 ANDs at
depth 16 to 101 at depth 15; for the counter it stays at 5 ANDs, depth 3, because a two-bit
counter has no equal subgraphs to merge.
