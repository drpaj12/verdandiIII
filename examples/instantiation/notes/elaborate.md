anchor: stage:Parse and elaborate

The Parse step's AST is the file as written; the Elaborate step's AST is the same tree with
each module type resolved. Its `INSTANTIATION` nodes name the module types (`counter`,
`counter$WIDTH=4`, `and_gate`) and hold an `INSTANCE` per use (`two`, `four`, `gate`) with the
port `CONNECTION`s.

The width override is why two counters appear as two types: the default parameter set keeps
the name `counter`, and the changed one gets the `$WIDTH=4` suffix. Elaboration creates the
specialised module once; the `two` instance still uses `counter`, and only `four` uses
`counter$WIDTH=4`.
