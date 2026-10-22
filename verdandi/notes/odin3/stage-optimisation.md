anchor: stage:Optimisation

`opt` runs Yosys's `opt` family to a fixed point: a prologue (`opt_expr`,
`opt_merge -nomux`), then a loop of `opt_muxtree`, `opt_reduce`, `opt_merge`, `opt_share`
(with `-full` only), `opt_dff`, `opt_clean` and `opt_expr`, repeated until nothing changes.

Each sub-pass is one rewrite of the cell graph: `opt_expr` folds constants, `opt_merge`
merges equal cells, `opt_clean` deletes what no output reaches, `opt_dff` drops unused
flip-flop features, `opt_share` merges operators that feed the same mux. The pass never
renumbers IDs, so a step's diff compares like with like.

Why a loop: one rewrite exposes the next. Merging two cells makes their readers equal,
folding a constant makes a mux constant, and `opt_clean` then removes the tail. The
playthrough shows each iteration as a group step with its sub-passes as children, and each
sub-pass logs what it did (`opt_merge: removed N cells`).
