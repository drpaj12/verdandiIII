anchor: pass:opt_expr

`opt_expr` folds constants and simplifies arithmetic and logic whose inputs are constant or
repeated: `a & 0` becomes `0`, `a | 0` becomes `a`, a `$mux` with a constant select becomes
one of its inputs.

It runs twice per iteration (the prologue and the loop's last call) because the other
sub-passes keep creating constant and repeated inputs for it to fold. One round folds
flip-flop polarities first, then visits the evaluable nodes in topological order and applies
to each the first rule of its type that fires. `-keepdc` keeps don't-care values, which is
why `proc`'s trailing call passes it.

What to look for: each fired rule is a DEBUG line, so the step's L3 children read
`opt_expr: module '<m>': <rule> on <type> '<cell>'` and the Code pane opens the rule's source
line. The summary counts the cells rewritten and folded.
