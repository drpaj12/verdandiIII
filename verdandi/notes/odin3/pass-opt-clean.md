anchor: pass:opt_clean

`opt_clean` removes what nothing reads: cells and wires that reach no module output, and
the nets they leave behind. It is dead-code removal, and it is why the diff after an `opt`
step often shows more removed objects than the pass before it changed.

Order per module: buffers become plain wiring; a mark-and-sweep liveness pass deletes the
dead nodes (a dead flip-flop's init goes with it); then wires that are no longer used, and
the nets they leave; init cleanup last, so a wire kept only for its init loses it in the same
call and goes in the next iteration. It skips a module that still holds processes.

Why it matters to a reader: a name you were following can disappear here. The object is gone
from the design, not renamed; the trace's diff lists it under removed, and a name search
stops at that step.

What to look for: `removed N unused cells, M unused nets and K unused wires`; `-purge` also
drops names kept for public aliased or constant-driven wires.
