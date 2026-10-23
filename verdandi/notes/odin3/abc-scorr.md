anchor: abc:scorr

`scorr` is sequential sweeping: it finds registers and nodes that always match, proves it by
K-step induction across time frames, and merges the proven classes. It is the one command in
the script that reasons across the registers; the others stop at them.

Its log names what it compared: `NBeg`/`NEnd` (nodes before and after) and `RBeg`/`REnd`
(registers before and after), with the gain in percent.

What to look for: for the counter the counts stay at 5 nodes and 2 registers; a design with
redundant state registers shows `and` and `lat` fall.
