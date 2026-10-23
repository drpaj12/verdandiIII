anchor: pass:hardmap

On the k6 architecture `hardmap` binds the arithmetic the target holds: the recording's two
`$mul` cells become multiply blocks and its two `$add` cells become adder chains. The L3
event steps name each cell and its rule (`mapped to a multiply`, `mapped to an adder chain`).

The register's logic and the reset multiplexers stay soft for ABC. Watch which cells the diff
adds at this step, then compare with the Lower stage: what hardmap took is already blocks,
what it left is still word cells waiting to be lowered.
