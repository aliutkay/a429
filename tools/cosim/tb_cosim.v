// tb_cosim.v: arinc429_ip RTL eş-simülasyonu (Python <-> iverilog, isimli FIFO üzerinden komut protokolü)
//   W <off_hex> <val_hex>  -> "K"           AXI4-Lite yazma
//   R <off_hex>            -> "D <hex>"     AXI4-Lite okuma
//   T <clk_dec>            -> "K"           saat ilerlet
//   M <rx_dec> <mod_dec>   -> "K"           RX hat bağlantısı: 0 loopback, 1 açık (00), 2 ters (11 boşta), 3 A/B ters
//   Q                      -> simülasyon biter
// Kullanım: tools/cosim/cosim.py (a429.cosim.CosimClient)
`timescale 1ns/1ps
module tb_cosim;
  parameter NRX = 1;
  reg clk = 0, rstn = 0; always #10 clk = ~clk;          // 50 MHz
  reg [31:0] awaddr = 0, wdata = 0, araddr = 0; reg awvalid = 0, wvalid = 0, arvalid = 0;
  wire [110:0] req = {awaddr, 3'b0, awvalid, wdata, 4'hF, wvalid, 1'b1, araddr, 3'b0, arvalid, 1'b1};
  wire [40:0] rsp; wire [31:0] rdata = rsp[34:3];
  wire txh, txl, slp;
  reg [1:0] mode [0:NRX-1];
  reg [NRX-1:0] rh, rl;
  integer k;
  always @* for (k = 0; k < NRX; k = k + 1) case (mode[k])
      2'd0: begin rh[k] = txh;  rl[k] = txl;  end
      2'd1: begin rh[k] = 1'b0; rl[k] = 1'b0; end
      2'd2: begin rh[k] = ~txh; rl[k] = ~txl; end
      default: begin rh[k] = txl; rl[k] = txh; end
    endcase

  arinc429_ip dut(.S_AXI_ACLK(clk), .S_AXI_ARESETN(rstn), .SLAVE_AXI_REQ(req), .SLAVE_AXI_RSP(rsp),
    .tx_high(txh), .tx_low(txl), .tx_slp(slp), .txbit_rx_high(txh), .txbit_rx_low(txl),
    .rx_high(rh), .rx_low(rl));

  task rd(input [31:0] a, output [31:0] d); begin
    @(negedge clk) araddr = a; arvalid = 1; @(posedge clk); while (!rsp[35]) @(posedge clk);
    @(negedge clk) arvalid = 0; while (!rsp[0]) @(posedge clk); d = rdata; @(negedge clk); end endtask
  task wr(input [31:0] a, input [31:0] d); begin
    @(negedge clk) awaddr = a; wdata = d; awvalid = 1; wvalid = 1; @(posedge clk);
    while (!(rsp[40] && rsp[39])) @(posedge clk);
    @(negedge clk) awvalid = 0; wvalid = 0; while (!rsp[36]) @(posedge clk); @(negedge clk); end endtask

  integer fc, fr, n, i; reg [8*4-1:0] cmd; reg [31:0] a, v; reg [8*512-1:0] cpath, rpath;
  initial begin
    for (i = 0; i < NRX; i = i + 1) mode[i] = 0;
    if (!$value$plusargs("CMD=%s", cpath)) cpath = "cmd.fifo";
    if (!$value$plusargs("RSP=%s", rpath)) rpath = "rsp.fifo";
    fr = $fopen(rpath, "w");
    fc = $fopen(cpath, "r");
    repeat (5) @(posedge clk); rstn = 1; repeat (5) @(posedge clk);
    $fdisplay(fr, "READY %0d", NRX); $fflush(fr);
    forever begin
      n = $fscanf(fc, "%s", cmd);
      if (n != 1) $finish;
      case (cmd[7:0])
        "W": begin n = $fscanf(fc, "%h %h", a, v); wr(a, v); $fdisplay(fr, "K"); end
        "R": begin n = $fscanf(fc, "%h", a); rd(a, v); $fdisplay(fr, "D %h", v); end
        "T": begin n = $fscanf(fc, "%d", v); repeat (v) @(posedge clk); $fdisplay(fr, "K"); end
        "M": begin n = $fscanf(fc, "%d %d", a, v); mode[a] = v[1:0]; @(posedge clk); $fdisplay(fr, "K"); end
        "Q": $finish;
        default: $fdisplay(fr, "E");
      endcase
      $fflush(fr);
    end
  end
endmodule
