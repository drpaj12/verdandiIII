anchor: pass:lower

`lower` turns every word cell into bit cells so the netlist view holds: an `$add` becomes
gates, a `$mux` an AND/OR tree, a `$dff` a `$_DFF_P_` plus its enable and reset logic.

Each word cell is one transaction: the new bit nodes are created on fresh nets, one DERIVED
record links them to the word cell, and only then is the word cell deleted. A failure while
building rolls the cell back, so a word cell is lowered completely or not at all.

The bit nodes are named after their word cell and the record keeps it as parent, so a gate
can be read back to the operator it came from. Asynchronous resets are made synchronous, as
Parmys's `adff2dff` does; a falling-edge flip-flop is inverted by default.

What to look for: `lower: module '<m>': $add '<cell>' -> N bit cells` for each word cell,
then the summary `lowered N word cells to M bit cells`. In the playthrough, 5 to 192.
