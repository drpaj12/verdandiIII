# The register example

`register.v` is a 4-bit register with an if/else: when `en` is high it loads `a & b`, otherwise
it keeps `q`:

    always @(posedge clk) begin
      if (en) q <= a & b;
      else q <= q;
    end

Record it from the repository root with the k6 architecture:

    verdandi record examples/register/register.v --top ifelse_reg \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o examples/register/trace

Without a VTR checkout, use the LPM tech library instead (`hardmap` is then omitted):

    verdandi record examples/register/register.v --top ifelse_reg \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o examples/register/trace

`verdandi play examples/register/trace` walks it. What to look for: `proc` makes the load-enable
a `$mux` in front of the `$dff`; `opt_dff` turns that shape into an enable on the flip-flop;
`opt_clean` removes the multiplexers the if/else left unused; `lower` splits the four-bit
register into bit cells; ABC maps the `a & b` logic to 4 LUTs. The notes beside this file
explain those steps; the other examples are listed in `examples/counter/README.md`.
