anchor: pass:lower

`lower` turns the counter's word cells into bit cells. After `opt_dff` the register is a 2-bit
`$sdff`, which becomes two `$_DFF_P_` flip-flops and two reset `$_MUX_` cells: four bit cells
from one word cell. The adder is already an adder chain from `hardmap`, so it is not lowered.

The log names the word cell and its bit-cell count, then `lowered 1 word cells to 4 bit
cells`. The bit cells keep the word cell as their parent, so `Ctrl+F` on `count` in the player
follows the split through the rest of the trace.
