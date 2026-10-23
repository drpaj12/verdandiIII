# The multiplier example

`multiplier.v` is a 4x4 unsigned multiplier: one continuous assignment, no clock.

    assign y = a * b;

Record it from the repository root with the k6 architecture:

    verdandi record examples/multiplier/multiplier.v --top mul4 \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o examples/multiplier/trace

Without a VTR checkout, use the LPM tech library instead (`hardmap` is then omitted and the
multiply stays soft for ABC):

    verdandi record examples/multiplier/multiplier.v --top mul4 \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o examples/multiplier/trace

`verdandi play examples/multiplier/trace` walks it. What to look for: `hardmap` binds the
`$mul` cell to the k6 multiply block (the log names the cell and the rule); `lower` splits the
remaining wide cells; ABC maps only what stays soft. Without the arch, the same multiply is
lowered and mapped by ABC instead, so the two recordings differ at the hard-block stage. The
notes beside this file explain those steps; the other examples are listed in
`examples/counter/README.md`.
