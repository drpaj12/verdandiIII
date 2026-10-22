anchor: pass:wreduce

`wreduce` narrows word cells to the widths their inputs and readers need: a `$mux`, a
flip-flop, a latch and every operator lose operand bits that cannot affect the result, such
as a constant's top zero bits or an operand whose readers only use the low bits.

The pre-step handles the easy cases first: a one-bit result, `$div`/`$mod`/`$pow` operands,
and `$mem` address bits (unless `-memx`). Then rounds visit the cells with a pin on a net the
last round changed and rebuild them narrower. A rebuilt node keeps its predecessor's rank,
so an operand is visited before its consumer, as in Yosys.

Widths decide hard-block counts (an adder chain has one `adder` cell per operand bit), so
this pass changes the netlist structure for a reason unrelated to function. A module with
`$proc` nodes is skipped.

What to look for: `removed top 1 bits (of 2) from port B of $add '<cell>'` and the summary
`N cells narrowed, M bits removed`.
