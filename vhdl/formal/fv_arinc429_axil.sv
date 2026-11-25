// Formal doğrulama: arinc429_axil (AXIL Studio üretimi AXI4-Lite slave protokol uyumu)
`default_nettype none
module fv_arinc429_axil (
    input wire        S_AXI_ACLK,
    input wire        S_AXI_ARESETN,
    input wire        S_AXI_AWVALID,
    input wire [31:0] S_AXI_AWADDR,
    input wire [2:0]  S_AXI_AWPROT,
    input wire        S_AXI_WVALID,
    input wire [31:0] S_AXI_WDATA,
    input wire [3:0]  S_AXI_WSTRB,
    input wire        S_AXI_BREADY,
    input wire        S_AXI_ARVALID,
    input wire [31:0] S_AXI_ARADDR,
    input wire [2:0]  S_AXI_ARPROT,
    input wire        S_AXI_RREADY
);
    wire        S_AXI_AWREADY, S_AXI_WREADY, S_AXI_BVALID;
    wire [1:0]  S_AXI_BRESP;
    wire        S_AXI_ARREADY, S_AXI_RVALID;
    wire [31:0] S_AXI_RDATA;
    wire [1:0]  S_AXI_RRESP;
    wire        o_soft_reset_rst_all;

    arinc429_axil dut (
        .S_AXI_ACLK           (S_AXI_ACLK),
        .S_AXI_ARESETN        (S_AXI_ARESETN),
        .S_AXI_AWVALID        (S_AXI_AWVALID),
        .S_AXI_AWREADY        (S_AXI_AWREADY),
        .S_AXI_AWADDR         (S_AXI_AWADDR),
        .S_AXI_AWPROT         (S_AXI_AWPROT),
        .S_AXI_WVALID         (S_AXI_WVALID),
        .S_AXI_WREADY         (S_AXI_WREADY),
        .S_AXI_WDATA          (S_AXI_WDATA),
        .S_AXI_WSTRB          (S_AXI_WSTRB),
        .S_AXI_BVALID         (S_AXI_BVALID),
        .S_AXI_BREADY         (S_AXI_BREADY),
        .S_AXI_BRESP          (S_AXI_BRESP),
        .S_AXI_ARVALID        (S_AXI_ARVALID),
        .S_AXI_ARREADY        (S_AXI_ARREADY),
        .S_AXI_ARADDR         (S_AXI_ARADDR),
        .S_AXI_ARPROT         (S_AXI_ARPROT),
        .S_AXI_RVALID         (S_AXI_RVALID),
        .S_AXI_RREADY         (S_AXI_RREADY),
        .S_AXI_RDATA          (S_AXI_RDATA),
        .S_AXI_RRESP          (S_AXI_RRESP),
        .o_soft_reset_rst_all (o_soft_reset_rst_all)
    );

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_bvalid, p_bready, p_rvalid, p_rready;
    reg [1:0]  p_bresp, p_rresp;
    reg [31:0] p_rdata;
    reg        p_ar_hs;
    reg [15:0] p_ar_off;

    always @(posedge S_AXI_ACLK) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= S_AXI_ARESETN;
        p_bvalid     <= S_AXI_BVALID;
        p_bready     <= S_AXI_BREADY;
        p_bresp      <= S_AXI_BRESP;
        p_rvalid     <= S_AXI_RVALID;
        p_rready     <= S_AXI_RREADY;
        p_rdata      <= S_AXI_RDATA;
        p_rresp      <= S_AXI_RRESP;
        p_ar_hs      <= S_AXI_ARVALID && S_AXI_ARREADY;
        p_ar_off     <= S_AXI_ARADDR[15:0];

        if (!f_past_valid)
            assume(!S_AXI_ARESETN);

        // P1: AXI4-Lite BRESP ve RRESP her zaman OKAY (2'b00)
        assert(S_AXI_BRESP == 2'b00);
        assert(S_AXI_RRESP == 2'b00);

        if (f_past_valid && !p_rst_n) begin
            // P2: Reset sonrası BVALID, RVALID ve PULSE çıkışları 0
            assert(!S_AXI_BVALID);
            assert(!S_AXI_RVALID);
            assert(!o_soft_reset_rst_all);
        end else if (f_past_valid && S_AXI_ARESETN && p_rst_n) begin
            // P3: AXI4-Lite BVALID kararlılık kuralı (BREADY=0 iken BVALID düşemez)
            if (p_bvalid && !p_bready) begin
                assert(S_AXI_BVALID);
                assert(S_AXI_BRESP == p_bresp);
            end
            // P4: AXI4-Lite RVALID/RDATA kararlılık kuralı (RREADY=0 iken düşemez/değişemez)
            if (p_rvalid && !p_rready) begin
                assert(S_AXI_RVALID);
                assert(S_AXI_RDATA == p_rdata);
                assert(S_AXI_RRESP == p_rresp);
            end
            // P5: IP_ID (0x0000) daima 0x41343239, SOFT_RESET (0x0020) daima 0x00000000 okunur
            if (p_ar_hs && p_ar_off[15:2] == 14'h0000)
                assert(S_AXI_RVALID && S_AXI_RDATA == 32'h41343239);
            if (p_ar_hs && p_ar_off[15:2] == 14'h0008)
                assert(S_AXI_RVALID && S_AXI_RDATA == 32'h00000000);
        end
    end
endmodule
