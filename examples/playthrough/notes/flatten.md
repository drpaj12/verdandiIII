anchor: pass:flatten

The playthrough top is the join: it instantiates the counter, the if/else register and the
multiplier, so `flatten` has three instances to expand, exactly as the log says. Each body is
copied into `playthrough` with a dotted name (`counter.count`, `regs.q`, `multiplier.y`), and
the three child modules are named as no longer instantiated.

This is the step that makes the live design flat: the top is now the only module the design
reaches. The child modules remain in the IR, and the later passes still visit them: `lower`
logs `playthrough`, `counter2` and `ifelse_reg`, and ABC runs on all four (`mul4` has nothing
left to map; it was hard-mapped before flatten).
