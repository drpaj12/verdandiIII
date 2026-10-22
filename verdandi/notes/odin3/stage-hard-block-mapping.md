anchor: stage:Hard-block mapping

`partial_map` (the script name is `hardmap`) binds what the target architecture has and
leaves the rest soft for ABC. The rules follow Parmys, taken from the k6 architecture's
models: `multiply`, `adder`, `single_port_ram` and `dual_port_ram`.

On k6: a `$mul` becomes a `multiply` cell of width 36 with the operand bits on the low pins
and the rest `unconn`; a 2x2 multiplier stays soft with a warning, an unsigned one wider
than the block is split, a signed one is left to `lower`. A `$add` or `$sub` becomes a chain
of `max(A,B)+2` `adder` cells (a head, one stage per bit and a top stage); a `$mem` becomes
single- or dual-port RAM slices after its port flip-flops are merged.

Why: the idea is Odin II's, as Parmys implements it: bind some of the word-level design to
the target's hard blocks and leave the rest soft for ABC. Nodes are named `<cell>.<role>`
and carry a `hardmap` attribute, so a mapped cell still names the operator it came from.
With a techlib there is no architecture record, so the recorder's script omits this stage.
