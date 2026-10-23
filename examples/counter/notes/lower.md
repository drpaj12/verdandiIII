anchor: pass:lower

`lower` turns the counter's word cells into bit cells: the 2-bit `$dff` becomes two `$_DFF_P_`
(plus its reset logic), and the 2-bit `$add` becomes gates on one-bit nets.

The log names each word cell and how many bit cells it became, then a summary such as
`lowered N word cells to M bit cells`. The bit cells keep the word cell as their parent, so
`Ctrl+F` on `count` in the player follows the split through the rest of the trace.
