"""Micro Verilog designs used by the recorder tests: each a (top, text) pair."""

from __future__ import annotations

Micro = tuple[str, str]

COUNTER2: Micro = (
    "counter2",
    """\
module counter2(input clk, input rst, output reg [1:0] count);
  always @(posedge clk) begin
    if (rst) count <= 2'b00;
    else count <= count + 2'b01;
  end
endmodule
""",
)

IFELSE_REG: Micro = (
    "ifelse_reg",
    """\
module ifelse_reg(input clk, input en, input [3:0] a, input [3:0] b, output reg [3:0] q);
  always @(posedge clk) begin
    if (en) q <= a & b;
    else q <= q;
  end
endmodule
""",
)

MUL4: Micro = (
    "mul4",
    """\
module mul4(input [3:0] a, input [3:0] b, output [7:0] y);
  assign y = a * b;
endmodule
""",
)

AND_ZERO: Micro = (
    "and_zero",
    """\
module and_zero(input a, output y);
  assign y = a & 1'b0;
endmodule
""",
)

PLAYTHROUGH: Micro = (
    "playthrough",
    """\
module counter2(input clk, input rst, output reg [1:0] count);
  always @(posedge clk) begin
    if (rst) count <= 2'b00;
    else count <= count + 2'b01;
  end
endmodule

module ifelse_reg(input clk, input en, input [3:0] a, input [3:0] b, output reg [3:0] q);
  always @(posedge clk) begin
    if (en) q <= a & b;
    else q <= q;
  end
endmodule

module mul4(input [3:0] a, input [3:0] b, output [7:0] y);
  assign y = a * b;
endmodule

module playthrough(
  input clk, input rst, input en,
  input [3:0] a, input [3:0] b,
  output [1:0] count, output [3:0] q, output [7:0] product
);
  counter2 counter(.clk(clk), .rst(rst), .count(count));
  ifelse_reg regs(.clk(clk), .en(en), .a(a), .b(b), .q(q));
  mul4 multiplier(.a(a), .b(b), .y(product));
endmodule
""",
)
