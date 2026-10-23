anchor: stage:Read architecture

Before Odin III can map anything it has to know what parts exist. `read_arch` reads a VPR
architecture file: its `<models>` become hard cell types (`multiply`, `adder`,
`single_port_ram`, `dual_port_ram` when their ports match the templates in `lib/vtr.o3lib`,
every other model a black box), and its pb_type tree becomes the architecture record that
carries the LUT size K and the pack patterns. `read_techlib` is the smaller door: an
`.o3lib` library (`lib/lpm.o3lib`) whose cells each become a cell type.

Why first: hard-block mapping can only bind a multiplier, adder or RAM the target has. With
a techlib there are no architecture models, so the recorder's default script leaves out
`hardmap` and the arithmetic stays soft for ABC.

What to look for: the `read_arch: <lib>: N models (R registered), L leaves, K=<k>` line
names what was registered and the LUT size; a model whose ports do not match a template is
a black box, not registered.
