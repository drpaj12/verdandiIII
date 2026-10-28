# verdandi

Verdandi III: the Micro through the Macro. Record a micro Verilog design through the current
Odin III pass by pass into a trace, then replay it as an interactive playthrough that shows the
code, the data and the Verilog provenance of every step. Python 3.11+, `odin3` (cffi binding) for
the recorder, PySide6 (extra `gui`) for the player. Verdandi III is part of **Yggdrasil III**, the suite of Odin III (<https://github.com/drpaj12/odin3>, the trunk), Wyrd III (<https://github.com/drpaj12/wyrd>, the canopy, with Bifrost III and Midgard III), Loki III (<https://github.com/drpaj12/loki>), The Norns III (<https://github.com/drpaj12/nornsIII>) and Verdandi III (<https://github.com/drpaj12/verdandiIII>) on side branches, and Mímir III (<https://github.com/drpaj12/mimirIII>, the fruit). Verdandi III is a side branch, a tool and experiment: the Micro through the Macro. Version 0.1.0 (`pyproject.toml`). The hub is <https://github.com/drpaj12/YggdrasilIII> (documentation: <https://drpaj12.github.io/YggdrasilIII/>, versions of every piece: <https://drpaj12.github.io/YggdrasilIII/versions.html>) and its picture of the tree is <https://github.com/drpaj12/YggdrasilIII/blob/main/images/yggdrasil-tree.png>.

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
- [The Norns III](https://github.com/drpaj12/nornsIII) (repository; plan and paper under `docs/`).
- [Set up the whole suite](https://drpaj12.github.io/YggdrasilIII/getting-started.html) on a clean Linux or
  Windows machine, and [drive it with Claude Code](https://drpaj12.github.io/YggdrasilIII/ai-agent.html).

Design: [spec](docs/specs/2026-10-22-verdandi-design.md) and [plan](docs/plans/2026-10-22-verdandi-plan.md).
