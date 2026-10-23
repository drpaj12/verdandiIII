// The register with an if/else: the enable holds the old value.
module ifelse_reg(input clk, input en, input [3:0] a, input [3:0] b, output reg [3:0] q);
  always @(posedge clk) begin
    if (en) q <= a & b;
    else q <= q;
  end
endmodule
