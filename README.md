# verdandi

Verdandi III: the Micro through the Macro. Record a micro Verilog design through the current
Odin III pass by pass into a trace, then replay it as an interactive playthrough that shows the
code, the data and the Verilog provenance of every step. Python 3.11+, `odin3` (cffi binding) for
the recorder, PySide6 (extra `gui`) for the player. Verdandi III is part of **Yggdrasil III**, the
suite of Odin III (<https://github.com/drpaj12/odin3>), Wyrd III
(<https://github.com/drpaj12/wyrd>), Loki III (<https://github.com/drpaj12/loki>) and Midgard III
(the Verilog Town game).

## Quick start

    verdandi record examples/playthrough/playthrough.v --top playthrough \
      --arch "$VTR_ROOT/vtr_flow/arch/timing/k6_frac_N10_frac_chain_mem32K_40nm.xml" -o trace
    verdandi play trace

Without a VTR checkout, record with `--techlib "$ODIN3_ROOT/lib/lpm.o3lib"` instead (the manual
has both). `N` walks the steps, `I` steps in, `O` steps out; the full walk is in the manual.

Five examples ship under `examples/`: `counter`, `register`, `multiplier`, `instantiation` and
`playthrough` (the existing top that joins the first three). `examples/record-all.sh` checks
each example's notes and records all five into `examples/<name>/trace`, smallest design first.

## Documentation

Start at the Yggdrasil III hub; every manual links to the others.

- [Yggdrasil III hub](https://drpaj12.github.io/YggdrasilIII/): the suite, how the pieces connect, getting started.
- [Odin III manual](https://drpaj12.github.io/odin3/).
- [Wyrd III manual](https://drpaj12.github.io/wyrd/), with
  [simulation (Bifrost III)](https://drpaj12.github.io/wyrd/simulation.html) and
  [Midgard III (Verilog Town)](https://drpaj12.github.io/wyrd/midgard.html).
- Tutorials (PDF): [command line](https://drpaj12.github.io/wyrd/wyrd-tutorial.pdf) and
  [GUI](https://drpaj12.github.io/wyrd/wyrd-gui-tutorial.pdf).
- [Loki III manual](https://drpaj12.github.io/loki/).
- [Verdandi III manual](https://drpaj12.github.io/verdandiIII/): this tool, with the shipped
  [playthrough example](examples/playthrough/README.md).
