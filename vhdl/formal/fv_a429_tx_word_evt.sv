// Formal doğrulama: a429_tx_word_evt (k-indüksiyon: kesin 1-clk kenar darbeleri + karşılıklı dışlama)
`default_nettype none
module fv_a429_tx_word_evt (
    input wire clk,
    input wire rst_n,
    input wire soft_rst,
    input wire tx_busy
);
    wire tx_word_start;
    wire tx_word_done;

    a429_tx_word_evt dut (
        .clk           (clk),
        .rst_n         (rst_n),
        .soft_rst      (soft_rst),
        .tx_busy       (tx_busy),
        .tx_word_start (tx_word_start),
        .tx_word_done  (tx_word_done)
    );

    reg f_past_valid = 1'b0;
    reg p_rst_n, p_soft_rst, p_tx_busy, p_ws, p_wd;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_tx_busy    <= tx_busy;
        p_ws         <= tx_word_start;
        p_wd         <= tx_word_done;

        if (!f_past_valid)
            assume(!rst_n);

        // P1: start ve done asla aynı clock'ta 1 olamaz
        assert(!(tx_word_start && tx_word_done));

        if (f_past_valid && rst_n && p_rst_n && !p_soft_rst) begin
            // P2: Yükselen ve düşen kenar tam eşitliği
            assert(tx_word_start == (tx_busy && !p_tx_busy));
            assert(tx_word_done  == (!tx_busy && p_tx_busy));
            // P3: Ardışık 2 clock'ta start veya done tekrarlanamaz (strict 1-clk darbe)
            assert(!(tx_word_start && p_ws));
            assert(!(tx_word_done  && p_wd));
        end
    end
endmodule
