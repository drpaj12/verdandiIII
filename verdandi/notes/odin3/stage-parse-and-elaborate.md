anchor: stage:Parse and elaborate

`read_verilog` is two front ends behind one command. The parser is a reentrant Flex lexer
and a pure LALR(1) Bison grammar; it builds a parsed AST in which every node keeps the
source location of its first token. That AST is the L2 "Parse" step.

Elaboration then runs in two stages. Stage 1 is Verilog-only: it picks the top, applies
parameter overrides, and unrolls `generate` blocks and constant functions into an elaborated
AST. Stage 2 is shared by every front end: it binds through the symbol table, fixes widths
and signedness, creates word cells and drivers, and turns each `always` block into one
`$proc` cell whose I/O pins are the nets it reads and drives.

Why the seam: a second front end could emit the elaborated AST and reuse stage 2 instead of
writing another elaborator. The recorder shows both ASTs as children, so you see what the
parser read and what elaboration settled.
