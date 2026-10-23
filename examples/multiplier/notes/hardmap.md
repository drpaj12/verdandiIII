anchor: pass:hardmap

`hardmap` (the script name of `partial_map`) looks for arithmetic cells the target can hold as
a hard block. On the k6 architecture a 4x4 unsigned `$mul` fits the multiply block, so the
step replaces the `$mul` cell with the block's cells and the log says
`hardmap: '$mul' cell '<cell>' mapped to a multiply`.

Without `--arch`, the LPM library supplies only simple blocks, so the flow omits `hardmap`
entirely: the multiply stays soft and `lower` and ABC handle it. Both recordings are valid;
compare where the multiply disappears.
