anchor: pass:flatten

The playthrough top is the join: it instantiates the counter, the if/else register and the
multiplier, so `flatten` has three instances to expand, exactly as the log says. Each body is
copied into `playthrough` with a dotted name (`counter.count`, `regs.q`, `multiplier.y`), and
the three child modules are named as no longer instantiated.

This is the step that turns four modules into the one flat netlist the rest of the flow maps.
Before it, the design is a hierarchy; after it, later passes see one module, and the child
modules remain in the IR but nothing reaches them.
