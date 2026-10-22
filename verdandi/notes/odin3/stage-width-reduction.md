anchor: stage:Width reduction

`wreduce` narrows word cells to the widths their inputs and readers actually need: an adder
whose result only feeds a 2-bit register becomes a 2-bit adder, and operands bounded by
constants lose their top bits.

Why it matters beyond size: widths decide hard-block counts. An adder chain has one `adder`
cell per operand bit, and the multiplier threshold reads operand widths, so narrowing before
hard-block mapping and `lower` changes the netlist for a reason that has nothing to do with
function.

It visits an operand before its consumer, as Yosys does, so a consumer sees the narrowed
operand in the same round. The production script runs it after `flatten` (Parmys runs it
before; that is a script order, not a different pass).

What to look for: `removed top 1 bits (of 2) from port B of $add '<cell>'` and the summary
`N cells narrowed, M bits removed`. The counter's increment constant loses its top bit.
