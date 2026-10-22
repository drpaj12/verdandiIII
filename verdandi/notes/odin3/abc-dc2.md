anchor: abc:dc2

`dc2` runs ABC's `compress2` script on the AIG: rewrite, refactor and balance, repeated a few
times. A rewrite replaces a node's local function with a cheaper one; a refactor
re-synthesises a larger cone; a balance rebuilds the tree to reduce depth. It keeps no
choices.

What to look for: `and` falls, `lev` stays or falls. In the 4x4 multiply the AIG goes from
101 ANDs to 83 at depth 15; for the counter nothing changes (5 ANDs, depth 3), which is
normal: there is little to rewrite in a small network.
