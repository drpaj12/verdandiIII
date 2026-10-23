anchor: pass:flatten

`flatten` copies each instance's body into the module that holds it, following the instance
tree top-down. The flatten lines report the counts (`3 instances to expand`, `3 instances
expanded (0 kept) in 1 roots; 3 modules unused`), a cost line (bytes, provenance records,
added nodes, pins, nets and wires), and the uninstantiated modules. The copied objects are
dotted (`two.count`, `gate.y`) and keep a DERIVED provenance record, so the hierarchy can be
recovered after flattening.

The log names the modules no longer instantiated (`counter`, `counter$WIDTH=4`, `and_gate`).
The IR cannot remove modules, so they remain in the snapshot but nothing instantiates them:
the live design is the flat top from here on. The later passes still visit the dead modules:
`lower` logs all four modules, and ABC maps each of them (2, 4 and 1 LUTs in the three unused
modules, 7 in the top).
