// tb_arinc429_ip_loopback.v: arinc429_ip (HDL Designer paketli top) TX -> RX0 loopback entegrasyon testi.
// Gruplanmış register haritası (IP 2.0.0) ile uçtan uca:
//   A) RX0_CTRL.ENABLE=0  : Word gelse de WORD_CNT / ERR_CNT artmaz (logger kapalı)
//   B) ENABLE=1           : 3 Word alınır, LAST_WORD, Word RAM ve BIT_RD_PULSE/NULL (DUR|ERR) doğru
//   C) Ters hat (boşta 11): STATUS.LINE_HIGH=LINE_LOW=1, SYNC_WAIT=1; geçiş 1 kez BUS_FAULT,
//                           sonrasında Word de yeni hata da yok (yalnızca SYNC_WAIT gösterir)
//   D) Hat düzelince      : SYNC_WAIT=0, alım devam eder
// arinc429_ip.vhd önce ghdl --synth --out=verilog ile Verilog netlist'e çevrilir (bkz. vhdl/scripts/run_tests.sh).
`timescale 1ns/1ps
module tb_arinc429_ip_loopback;
  localparam TX_CTRL = 32'h0400, TX_WORD = 32'h0404, TX_SEND = 32'h0408, TX_WORD_CNT = 32'h0484;
  localparam RX_CTRL = 32'h4000, RX_STATUS = 32'h4004, RX_WORD_CNT = 32'h40E0, RX_ERR_CNT = 32'h40E4,
             RX_LAST = 32'h40EC, RX_WRADDR = 32'h4100, RX_WDATA = 32'h410C, RX_GAPERR = 32'h4114,
             RX_BRADDR = 32'h4140, RX_BPULSE = 32'h4144, RX_BNULL = 32'h4148;
  localparam [31:0] W_EXP = (32'h12345 << 10) | 32'hA5;   // parity biti (bit 31) Odd için 0

  reg clk = 0, rstn = 0; always #10 clk = ~clk;              // 50 MHz
  reg [31:0] awaddr = 0, wdata = 0, araddr = 0; reg awvalid = 0, wvalid = 0, arvalid = 0;
  wire [110:0] req = {awaddr, 3'b0, awvalid, wdata, 4'hF, wvalid, 1'b1, araddr, 3'b0, arvalid, 1'b1};
  wire [40:0] rsp; wire [31:0] rdata = rsp[34:3];
  wire txh, txl, slp; reg inv = 0;
  wire rh = inv ? ~txh : txh, rl = inv ? ~txl : txl;      // inv: aktif-düşük alıcı çıkışı (boşta 11)

  arinc429_ip dut(.S_AXI_ACLK(clk), .S_AXI_ARESETN(rstn), .SLAVE_AXI_REQ(req), .SLAVE_AXI_RSP(rsp),
    .tx_high(txh), .tx_low(txl), .tx_slp(slp), .txbit_rx_high(1'b0), .txbit_rx_low(1'b0),
    .rx_high(rh), .rx_low(rl));

  integer errs = 0;
  task rd(input [31:0] a, output [31:0] d); begin
    @(negedge clk) araddr = a; arvalid = 1; @(posedge clk); while (!rsp[35]) @(posedge clk);
    @(negedge clk) arvalid = 0; while (!rsp[0]) @(posedge clk); d = rdata; @(negedge clk); end endtask
  task wr(input [31:0] a, input [31:0] d); begin
    @(negedge clk) awaddr = a; wdata = d; awvalid = 1; wvalid = 1; @(posedge clk);
    while (!(rsp[40] && rsp[39])) @(posedge clk);
    @(negedge clk) awvalid = 0; wvalid = 0; while (!rsp[36]) @(posedge clk); @(negedge clk); end endtask
  task chk(input cond, input [8*64-1:0] msg); begin
    if (cond) $display("OK   : %0s", msg); else begin $display("HATA : %0s", msg); errs = errs + 1; end end endtask
  task send_words(input integer n); integer k; begin
    for (k = 0; k < n; k = k + 1) begin wr(TX_SEND, 1); repeat (25000) @(posedge clk); end end endtask  // ~500 us/Word

  reg [31:0] d, w, e, st, p, nl;
  initial begin
    repeat (5) @(posedge clk); rstn = 1;
    repeat (5000) @(posedge clk);                       // 100 us: decoder hat senkronunu alsın
    wr(TX_CTRL, 32'h5);                                 // TRANSMITTER_EN=1, BUILDER_EN=1
    wr(TX_WORD, (32'h1 << 31) | (32'h12345 << 10) | 32'hA5);   // Odd parity, Data, Label
    rd(TX_WORD, d); chk(d == ((32'h1 << 31) | (32'h12345 << 10) | 32'hA5), "TX_WORD alanlari tek register'da geri okundu");

    // A) Logger kapalı
    send_words(1);
    rd(TX_WORD_CNT, d); rd(RX_WORD_CNT, w); rd(RX_ERR_CNT, e); rd(RX_STATUS, st);
    chk(d == 1, "A: TX 1 Word gonderdi");
    chk(w == 0 && e == 0, "A: RX0_CTRL.ENABLE=0 iken Word/hata kaydedilmedi");
    chk(st[14] == 0 && st[13:12] == 2'b00, "A: STATUS SYNC_WAIT=0, hat bosta 00");

    // B) Logger açık
    wr(RX_CTRL, 32'h1);
    send_words(3);
    rd(RX_WORD_CNT, w); rd(RX_ERR_CNT, e); rd(RX_LAST, d);
    chk(w == 3 && e == 0, "B: ENABLE=1 ile 3 Word, 0 hata");
    chk(d == W_EXP, "B: LAST_WORD dogru");
    wr(RX_WRADDR, 0); rd(RX_WDATA, d); rd(RX_GAPERR, e);
    chk(d == W_EXP, "B: Word RAM[0] verisi dogru");
    wr(RX_BRADDR, 0); rd(RX_BPULSE, p); rd(RX_BNULL, nl);
    chk(p[15:0] >= 16'd240 && p[15:0] <= 16'd260, "B: BIT_RD_PULSE.DUR ~250 clk (HS)");
    chk(nl[15:0] >= 16'd240 && nl[15:0] <= 16'd260, "B: BIT_RD_NULL.DUR ~250 clk (HS)");
    rd(RX_BPULSE, d);
    chk(d != p || d[15:0] != 0, "B: BIT_RD_NULL okununca pointer bit1'e ilerledi");

    // C) Ters hat: boşta 11
    inv = 1; repeat (5000) @(posedge clk);
    rd(RX_STATUS, st);
    chk(st[13:12] == 2'b11, "C: STATUS.LINE_HIGH=LINE_LOW=1 (hat bosta 11)");
    chk(st[14] == 1, "C: STATUS.SYNC_WAIT=1 (decoder senkron bekliyor)");
    rd(RX_ERR_CNT, e);
    chk(e == 1, "C: 00->11 gecisi bir kez BUS_FAULT olarak raporlandi");
    send_words(1);
    rd(RX_WORD_CNT, w); rd(RX_ERR_CNT, e);
    chk(w == 3 && e == 1, "C: sonrasinda Word ve yeni hata yok (yalnizca SYNC_WAIT gosterir)");

    // D) Hat düzeldi
    inv = 0; repeat (5000) @(posedge clk);
    rd(RX_STATUS, st);
    chk(st[14] == 0, "D: hat duzelince SYNC_WAIT=0");
    send_words(1);
    rd(RX_WORD_CNT, w);
    chk(w == 4, "D: alim devam ediyor (4 Word)");

    if (errs == 0) $display("PASS: tb_arinc429_ip_loopback"); else $display("FAIL: tb_arinc429_ip_loopback errs=%0d", errs);
    $finish;
  end
endmodule
