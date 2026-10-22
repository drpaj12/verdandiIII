anchor: stage:Write BLIF

`write_blif` turns the netlist into BLIF, the exchange format with VTR. The recorder's run
writes the plain dialect: the top first, then the other modules, with constants as `gnd`,
`vcc` and `unconn`, each generator once per module.

`--vtr` writes the top alone in the dialect VPR reads, and its preflight refuses before any
byte is written what VPR would reject or misread: a hierarchical top, a falling-edge latch,
a tri-state, a multi-driver net. In either dialect a `$lut` becomes a `.names` cover, the
shorter of the on-set and off-set irredundant sum of products.

Why the playthrough ends here: this file is the netlist handed to VTR (decision D8); the
VPR stages, if added later, start from it. `--name-style provenance` names the nets
`hier/path/name@file:line` (top ports and generators excepted), so a net traces to its
source line without Odin III loaded.
