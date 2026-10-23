anchor: stage:Flatten

`flatten` turns a design whose top instantiates other modules into one flat top. It walks
the instance tree top-down from a worklist and copies each instance's body into the module
that holds it.

Two nets joined at a port become one net with IR-2 aliases, so no port net is duplicated.
Every copied object gets a dotted instance-path name (`u1.x`), and a DERIVED provenance
record keeps the path (`hier`), so the hierarchy can be recovered after flattening. Black
boxes and library cells stay untouched.

Why here: after flattening, the live design is one module, so the later stages map, lower and
optimise a single flat netlist (the playthrough expands 3 instances). The log also names the
modules no longer instantiated; the IR cannot remove them, so they remain.
