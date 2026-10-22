anchor: pass:hardmap

`hardmap` is the script name of `partial_map`: the pass that binds arithmetic and memories
to the target's hard blocks and leaves everything else soft for ABC. The k6 defaults are
Parmys's rules; every improvement is a named option that is off by default.

It binds `$mul` first (a `multiply` of the architecture's width, operands on the low pins,
`unconn` padding; a 2x2 multiplier stays soft with a warning, an unsigned wider one is
split, a signed one is left to `lower`), then `$add`/`$sub` (a chain of `max(A,B)+2` adder
cells), then RAMs (`$mem` to single- or dual-port slices after its port flip-flops merge).

The result carries a `hardmap` attribute; nodes are named `<cell>.<role>`, so a mapped
block still names the operator it came from.

Why: the idea is Odin II's, as Parmys implements it: bind part of the word-level design to the
target's hard blocks and leave the rest soft, so ABC maps only the remaining logic.
