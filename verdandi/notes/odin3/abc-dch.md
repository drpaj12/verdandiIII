anchor: abc:dch

`dch` computes structural choices: for nodes that have several equivalent implementations
it keeps them all, linked as choice nodes, so the mapper can pick whichever costs less. The
script's `-f` selects its faster synthesis mode.

A choice node's alternatives are extra AND nodes, so `and` rises; the `(choice = N)` count
says how many of them are choices, and `lev` stays because a choice is one more way to build
the same node, not another level.

What to look for: in the 4x4 multiply `and` rises from 83 to 94 but the line carries
`(choice = 7)`; the counter shows no choices to make.
