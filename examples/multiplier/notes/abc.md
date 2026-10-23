anchor: abc:if

On the k6 architecture the multiplier never reaches ABC as a multiply: `hardmap` already bound
it to the hard block, and this one-module design has no other soft logic, so the ABC step's
log says `nothing to map` and the replay has no LUT steps to open up.

In the LPM fallback the multiply is still a word cell when `lower` runs; the lower diff shows
the multiply's gates, and ABC then maps those gates into LUTs. The LUT count is the price of
doing the multiply in soft logic instead of a hard block.
