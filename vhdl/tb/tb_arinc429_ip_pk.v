// tb_arinc429_ip_pk.v: arinc429_ip (HDL Designer paketli top, icinde arinc429_axil_pk) entegrasyon testi.
// SLAVE_AXI_REQ / SLAVE_AXI_RSP uzerinden IP_ID, IP_VERSION, CAPS okunur; GLOBAL_FREEZE yazilip geri okunur.
// arinc429_ip.vhd once ghdl --synth --out=verilog ile Verilog netlist'e cevrilir (bkz. vhdl/scripts/run_tests.sh).
`timescale 1ns/1ps
module tb_ip_pk;
  reg clk=0, rstn=0; always #10 clk=~clk;
  reg [31:0] awaddr=0, wdata=0, araddr=0; reg [3:0] wstrb=0;
  reg awvalid=0, wvalid=0, bready=1, arvalid=0, rready=1;
  wire [110:0] req = {awaddr,3'b0,awvalid,wdata,wstrb,wvalid,bready,araddr,3'b0,arvalid,rready};
  wire [40:0] rsp;
  wire awready=rsp[40], wready=rsp[39], bvalid=rsp[36], arready=rsp[35], rvalid=rsp[0];
  wire [31:0] rdata=rsp[34:3]; wire [1:0] bresp=rsp[38:37], rresp=rsp[2:1];
  wire txh, txl, slp;
  arinc429_ip dut(.S_AXI_ACLK(clk), .S_AXI_ARESETN(rstn), .SLAVE_AXI_REQ(req), .SLAVE_AXI_RSP(rsp),
    .tx_high(txh), .tx_low(txl), .tx_slp(slp), .txbit_rx_high(1'b0), .txbit_rx_low(1'b0), .rx_high(1'b0), .rx_low(1'b0));
  integer errs=0;
  task rd(input [31:0] a, output [31:0] d); begin
    @(negedge clk) araddr=a; arvalid=1; @(posedge clk); while(!arready) @(posedge clk);
    @(negedge clk) arvalid=0; while(!rvalid) @(posedge clk); d=rdata; if(rresp!=0) errs=errs+1; @(negedge clk); end endtask
  task wr(input [31:0] a, input [31:0] d); begin
    @(negedge clk) awaddr=a; wdata=d; wstrb=4'hF; awvalid=1; wvalid=1; @(posedge clk); while(!(awready&&wready)) @(posedge clk);
    @(negedge clk) awvalid=0; wvalid=0; while(!bvalid) @(posedge clk); if(bresp!=0) errs=errs+1; @(negedge clk); end endtask
  reg [31:0] d;
  initial begin
    repeat(5) @(posedge clk); rstn=1; repeat(20) @(posedge clk);
    rd(32'h0, d); $display("IP_ID      = %h", d); if (d!==32'h41343239) errs=errs+1;
    rd(32'h4, d); $display("IP_VERSION = %h", d); if (d!==32'h00010000) errs=errs+1;
    rd(32'h8, d); $display("CAPS       = %h", d); if (d[4:0]!==5'd1) errs=errs+1;
    wr(32'h24, 32'h1); rd(32'h24, d); $display("GLOBAL_FREEZE = %h", d); if (d!==32'h1) errs=errs+1;
    if (dut.u_axil.o_global_freeze !== 1'b1) errs=errs+1;
    wr(32'h24, 32'h0); rd(32'h24, d); if (d!==32'h0) errs=errs+1;
    if (errs==0) $display("PASS: arinc429_ip (HDL Designer pk) AXI okuma/yazma"); else $display("FAIL errs=%0d", errs);
    $finish;
  end
  initial begin #2000000 $display("TIMEOUT"); $finish; end
endmodule
