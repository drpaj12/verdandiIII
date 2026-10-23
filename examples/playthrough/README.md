# The playthrough example (the top of the five)

`playthrough.v` is the design the Verdandi III manual walks through. Four small modules in one
top: a 2-bit counter, a register with an if/else, a 4x4 multiplier, and the top that joins them.
It is the same text as `tests/micros.py`'s `PLAYTHROUGH`.

It is also the **top** example of the five: `counter`, `register`, `multiplier` and
`instantiation` each record their module alone, and this one records the top that joins the
first three. Each directory holds its own `.v`, README, notes and (after
`examples/record-all.sh`) trace.

Record it from the repository root with the k6 architecture (one command):

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" \
      -o examples/playthrough/trace

Without a VTR checkout, record with the LPM tech library instead (`hardmap` is then omitted
from the flow):

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --techlib "$ODIN3_ROOT/lib/lpm.o3lib" -o examples/playthrough/trace

Play it (one command):

    verdandi play examples/playthrough/trace

`N` walks the steps, `I` steps in, `O` steps out, `B` goes back, `1`-`9` jump to a stage, and
`Ctrl+F` follows an object name. The full walk, the ABC steps and the notes are in
[docs/user/index.md](../../docs/user/index.md) (published at
<https://drpaj12.github.io/verdandiIII/>).
