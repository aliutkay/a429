// Formal doğrulama: a429_timestamp (k-indüksiyon + 32-bit taşma sınırında atomik latch ispatı)
`default_nettype none
module fv_a429_timestamp (
    input wire clk,
    input wire rst_n,
    input wire soft_rst,
    input wire ts_en,
    input wire ts_clr,
    input wire ts_lsb_rd
);
    wire [63:0] ts_now;
    wire [31:0] ts_lsb;
    wire [31:0] ts_msb;

    a429_timestamp dut (
        .clk       (clk),
        .rst_n     (rst_n),
        .soft_rst  (soft_rst),
        .ts_en     (ts_en),
        .ts_clr    (ts_clr),
        .ts_lsb_rd (ts_lsb_rd),
        .ts_now    (ts_now),
        .ts_lsb    (ts_lsb),
        .ts_msb    (ts_msb)
    );

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_ts_en, p_ts_clr, p_ts_lsb_rd;
    reg [63:0] p_ts_now;
    reg [31:0] p_ts_msb_out;
    reg        f_past2_valid = 1'b0;
    reg [31:0] p2_ts_msb_in;
    reg        p2_rst_ok;

    always @(posedge clk) begin
        f_past_valid  <= 1'b1;
        f_past2_valid <= f_past_valid;
        p_rst_n       <= rst_n;
        p_soft_rst    <= soft_rst;
        p_ts_en       <= ts_en;
        p_ts_clr      <= ts_clr;
        p_ts_lsb_rd   <= ts_lsb_rd;
        p_ts_now      <= ts_now;
        p_ts_msb_out  <= ts_msb;
        p2_ts_msb_in  <= p_ts_now[63:32];
        p2_rst_ok     <= p_rst_n && !p_soft_rst && !p_ts_clr;

        // İlk adımda asenkron reset aktif olsun
        if (!f_past_valid)
            assume(!rst_n);

        // P0: ts_lsb her zaman ts_now'un alt 32 bitidir
        assert(ts_lsb == ts_now[31:0]);

        if (f_past_valid && rst_n) begin
            if (!p_rst_n || p_soft_rst || p_ts_clr) begin
                // P1: Reset veya clear sonrası sayaç ve latch 0
                assert(ts_now == 64'd0);
                assert(ts_msb == 32'd0);
            end else begin
                // P2: Sayma ve duraklatma kesinliği
                if (p_ts_en)
                    assert(ts_now == p_ts_now + 64'd1);
                else
                    assert(ts_now == p_ts_now);

                // P3: Atomik 64-bit MSB latch (32-bit LSB->MSB taşması dahil!)
                if (f_past2_valid && p_ts_lsb_rd && p2_rst_ok)
                    assert(ts_msb == p2_ts_msb_in);
                else if (!p_ts_lsb_rd)
                    assert(ts_msb == p_ts_msb_out);
            end
        end
    end
endmodule
