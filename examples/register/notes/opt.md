anchor: pass:opt

The first `opt` runs its parts as L2 steps (`opt_expr`, `opt_merge -nomux`, then each
iteration's `opt_muxtree`, `opt_reduce`, `opt_merge`, `opt_dff`, `opt_clean`, `opt_expr`).

Two things happen to this register: `opt_clean` removes the multiplexers the if/else left
unused (the log says `removing unused $mux`), and `opt_dff` turns the load-enable mux into an
enable on the `$dff` (the log says `adding EN on $dff`). The second `opt` (`opt -full`) adds
sharing to the loop; it has nothing to share in one register.
