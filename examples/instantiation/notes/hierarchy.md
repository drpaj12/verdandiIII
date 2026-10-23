anchor: pass:hierarchy

The top is not named on the command line to the reader here: `hierarchy --top
instantiation_top` keeps that module and drops the ones nothing reaches. The log names the
chosen top, `hierarchy: top instantiation_top`.

At this point the IR holds four modules: the top, `counter`, `counter$WIDTH=4` and
`and_gate`. Each instance is still an instance; its body is not copied yet. That copy is
`flatten`'s job, which is why the design is a hierarchy until the Flatten stage.
