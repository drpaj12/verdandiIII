// The instantiation example: a parameterised counter used twice at different widths, a leaf
// gate module, and the top that instantiates all three.
module counter #(parameter WIDTH = 2) (
  input clk, input rst, output reg [WIDTH-1:0] count
);
  always @(posedge clk) begin
    if (rst) count <= 0;
    else count <= count + 1'b1;
  end
endmodule

module and_gate(input a, input b, output y);
  assign y = a & b;
endmodule

module instantiation_top(
  input clk, input rst, input a, input b,
  output [1:0] count2, output [3:0] count4, output y
);
  counter #(.WIDTH(2)) two(.clk(clk), .rst(rst), .count(count2));
  counter #(.WIDTH(4)) four(.clk(clk), .rst(rst), .count(count4));
  and_gate gate(.a(a), .b(b), .y(y));
endmodule
