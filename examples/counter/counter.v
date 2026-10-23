// The 2-bit counter alone: the smallest of the five examples.
module counter2(input clk, input rst, output reg [1:0] count);
  always @(posedge clk) begin
    if (rst) count <= 2'b00;
    else count <= count + 2'b01;
  end
endmodule
