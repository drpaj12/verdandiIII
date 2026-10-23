# The instantiation example

`instantiation.v` shows how one module uses another. `instantiation_top` instantiates the
parameterised `counter` twice, at different widths (2 and 4 bits), and the leaf gate module
`and_gate` once:

    counter #(.WIDTH(2)) two(.clk(clk), .rst(rst), .count(count2));
    counter #(.WIDTH(4)) four(.clk(clk), .rst(rst), .count(count4));
    and_gate gate(.a(a), .b(b), .y(y));

An **instantiation** is a module used inside another module. The used module is the module
type, each use is an **instance** with its own name (`two`, `four`, `gate`), and the
connections map the instance's ports to the parent's nets. A `#(...)` overrides the module's
parameters: `WIDTH(2)` leaves the default module `counter`, `WIDTH(4)` makes a specialised
module whose ports are four bits wide (`counter$WIDTH=4` in the trace). A **leaf** module is
one that instantiates nothing itself, like `and_gate`.

Record it from the repository root with the k6 architecture:

    verdandi record examples/instantiation/instantiation.v --top instantiation_top \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o examples/instantiation/trace

Without a VTR checkout, use the LPM tech library instead (`hardmap` is then omitted):

    verdandi record examples/instantiation/instantiation.v --top instantiation_top \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o examples/instantiation/trace

`verdandi play examples/instantiation/trace` walks it. The trace shows the instantiations at
three points: the Parse and Elaborate steps (each use is an `INSTANTIATION` node with its
`INSTANCE` and `CONNECTION` children; at Parse both counter uses are named `counter`, and
Elaborate resolves the second to `counter$WIDTH=4`), the `hierarchy` step log (the top
is the one module no other module instantiates), and the `flatten` step log (three instances
expanded, `counter`, `counter$WIDTH=4` and `and_gate` now uninstantiated). The notes beside
this file explain those steps; the other examples are listed in `examples/counter/README.md`.
