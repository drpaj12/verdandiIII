anchor: abc:if

`if -K 6 -v` maps the register's four bits of `a & b` logic to four 6-input LUTs; the flip-flop
is not software logic, so ABC never sees it as a LUT.

Compare this with the counter: two bits of logic map to two LUTs, four bits to four. The
step's own log reports the network's node and LUT counts, and `mfs2` simplifies each LUT
afterwards.
