anchor: pass:opt_merge

`opt_merge` does common-subexpression elimination: two cells of one type with the same
parameters and the same input operands become one, and every reader is pointed at the
survivor.

The key is the cell's type, parameters, input operands (a net ID, or a constant value when
the net carries one) and, for a flip-flop, the init of Q. The lower ID survives, so a merge
is deterministic; the survivor gets one DERIVED record naming the merged cells, so
provenance still shows where the logic came from.

The prologue of `opt` calls it with `-nomux`, so muxes are left to `opt_muxtree`;
`opt_share` is the separate pass that merges operators feeding the same mux. `-ffbits` (off
by default, not in the production script) also merges identical bits of word flip-flops.

What to look for: `opt_merge: removed N cells` and the diff's removed objects.
