anchor: pass:hardmap

`hardmap` is the script name of `partial_map`: the pass that binds arithmetic and memories
to the target's hard blocks and leaves everything else soft for ABC. The k6 defaults are
Parmys's rules; every improvement is a named option that is off by default.

It binds `$mul` first (a `multiply` of the architecture's width, operands on the low pins,
`unconn` padding; a 2x2 one stays soft with a warning, an unsigned wider one is split, a
signed one that fits is mapped sign-extended to Y_WIDTH; only a signed one wider than the
block, or with Y_WIDTH above it, stays soft for `lower`), then `$add`/`$sub` (`max(A,B)+2`
adder chains), then RAMs (`$mem` to one- or two-port slices after its flip-flops merge).

The result carries a `hardmap` attribute; nodes are named `<cell>.<role>`, so a mapped
block still names the operator it came from.

Why: the idea is Odin II's, as Parmys implements it: bind part of the word-level design to the
target's hard blocks and leave the rest soft, so ABC maps only the remaining logic.
