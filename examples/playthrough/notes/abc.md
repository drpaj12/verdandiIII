anchor: abc:if

The whole playthrough maps to 12 LUTs plus its flip-flops: the counter takes 2, the register's
four bits 4, and the flat top's remaining soft logic 6. `if -K 6 -v` is the step that turns
the AIG into those 6-input LUTs.

The counter and register examples record their own module alone, so their ABC LUT counts are
the same 2 and 4. Mapping the top's leftover logic is what the combined example adds; the
hard-mapped multiplier contributes no LUTs at all.
