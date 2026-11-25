// Formal doğrulama: a429_tx_scheduler (k-indüksiyon: enable=0 kapısı, meşgulken tetik yok, 1-clk darbe)
`default_nettype none
module fv_a429_tx_scheduler (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire        enable,
    input wire        tx_busy,
    input wire [31:0] initial_delay,
    input wire [31:0] inter_word_gap
);
    wire sched_trig;
    wire sched_active;

    a429_tx_scheduler dut (
        .clk            (clk),
        .rst_n          (rst_n),
        .soft_rst       (soft_rst),
        .enable         (enable),
        .tx_busy        (tx_busy),
        .initial_delay  (initial_delay),
        .inter_word_gap (inter_word_gap),
        .sched_trig     (sched_trig),
        .sched_active   (sched_active)
    );

    reg f_past_valid = 1'b0;
    reg p_rst_n, p_soft_rst, p_en, p_busy, p_trig;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_en         <= enable;
        p_busy       <= tx_busy;
        p_trig       <= sched_trig;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: Reset, soft_rst veya enable=0 ertesi clk pasif ve tetiksiz
            if (!p_rst_n || p_soft_rst || !p_en) begin
                assert(!sched_active);
                assert(!sched_trig);
            end
            // P2: Verici meşgulken (tx_busy=1) ASLA yeni tetik üretilmez
            if (p_busy)
                assert(!sched_trig);
            // P3: Ardışık 2 clock'ta tetik üretilemez (strict 1-clk darbe)
            if (p_trig)
                assert(!sched_trig);
        end
    end
endmodule
