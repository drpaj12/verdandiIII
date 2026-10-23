anchor: abc:if

The trace maps 12 LUTs in all, but only 6 are live. The flat top's 6 LUTs are the copies of
the counter (2) and the register (4); the 2 and 4 LUTs in the `counter2` and `ifelse_reg`
module lines are the same logic again, in the modules the top no longer instantiates. So the
live design is 6 LUTs and 6 flip-flops, and the other 6 LUTs are dead copies.

The counter and register examples record their own module alone, so their ABC LUT counts are
the same 2 and 4. Mapping the top adds no new logic: the hard-mapped multiplier contributes
no LUTs (`mul4` has nothing to map). `if -K 6 -v` is the step that turns the AIG into
6-input LUTs.
