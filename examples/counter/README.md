# The counter example

`counter.v` is the smallest of the five examples: a 2-bit counter with a synchronous reset.

    always @(posedge clk) begin
      if (rst) count <= 2'b00;
      else count <= count + 2'b01;
    end

Record it from the repository root with the k6 architecture:

    verdandi record examples/counter/counter.v --top counter2 \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o examples/counter/trace

Without a VTR checkout, use the LPM tech library instead (`hardmap` is then omitted):

    verdandi record examples/counter/counter.v --top counter2 \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o examples/counter/trace

`verdandi play examples/counter/trace` walks it. What to look for: `proc` turns the `always`
block into a `$dff`, a `$mux` and a `$add` (five sub-steps), `opt_dff` folds the synchronous
reset into a `$sdff`, `hardmap` turns the add into an adder chain, `lower` splits the `$sdff`
into two flip-flops and two reset multiplexers, and ABC maps the two bits of next-state logic
to two 6-input LUTs. The notes beside this file
explain those steps; the full walk is in `docs/user/index.md`.

The other examples are `register`, `multiplier`, `instantiation` and `playthrough` (the top
that joins the counter, register and multiplier); `examples/record-all.sh` records all five.
