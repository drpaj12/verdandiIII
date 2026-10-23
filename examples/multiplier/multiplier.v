// The 4x4 multiplier: one continuous assignment, and the hard-block example.
module mul4(input [3:0] a, input [3:0] b, output [7:0] y);
  assign y = a * b;
endmodule
