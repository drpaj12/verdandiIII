anchor: pass:flatten

`flatten` inlines every module instance into the module that holds it, so a hierarchical
design becomes one flat top. It expands the instance tree from a top-down worklist, copying
each instance's body into its parent.

The nets joined at a port become one net with IR-2 aliases, so a port leaves no copy of its
net behind. Copied objects get dotted instance-path names, and a DERIVED provenance record
stores the path, so the hierarchy is still recoverable after flattening; black boxes and
library cells stay untouched.

A pre-flight runs before the IR changes: it builds the instance graph, reports recursive
instantiation, and checks the flat-size caps. With nothing to inline (the counter micro) the
log says `0 instances to expand`; the playthrough expands 3.

Why: after flattening the live design is one module, so the later stages read one flat
netlist, and the record keeps the answer to "where did this gate come from?".
