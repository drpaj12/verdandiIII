anchor: stage:State machines

`fsm` is Yosys's `fsm` port: it detects a state register and its next-state logic, extracts
the state graph, optimises it, recodes the states, and maps the result back to logic.

Recoding changes the state encoding. `auto` uses one-hot below 32 states and binary from 32;
an `fsm_encoding` attribute on the register wins. The new state wire keeps the register's
name, and attributes (`onehot`, `odin3_fsm_states`, `odin3_fsm_encoding`) record the state
count and encoding.

It runs right after `proc`, where Parmys runs it, because the state graph is easiest to see
while the next-state logic is still word-level.

What to look for: `fsm: found state register '<name>'` and `fsm: recoding '<name>' using
'<encoding>' encoding`. The micros here have no state machine, so the step logs only its
time.
