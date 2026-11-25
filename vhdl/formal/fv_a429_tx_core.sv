// Formal doğrulama: a429_tx_core (3 MUX güvenlik ve izolasyon ispatı)
`default_nettype none
module fv_a429_tx_core (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire [15:0] pulse_dur,
    input wire [15:0] null_dur,
    input wire [31:0] gap_dur,
    input wire        slp,
    input wire        transmitter_en,
    input wire        msg_sched_en,
    input wire        builder_en,
    input wire [7:0]  label_val,
    input wire [1:0]  sdi,
    input wire [18:0] data,
    input wire [1:0]  ssm,
    input wire        parity_type,
    input wire        sched_en,
    input wire [31:0] initial_delay,
    input wire [31:0] inter_word_gap,
    input wire        send_cmd,
    input wire [31:0] ext_data,
    input wire        ext_high,
    input wire        ext_low
);
    wire        tx_high, tx_low, tx_slp, tx_busy, tx_sched_act;
    wire [31:0] tx_word_tx;

    a429_tx_core dut (
        .clk                 (clk),
        .rst_n               (rst_n),
        .soft_rst            (soft_rst),
        .\act_cfg[pulse_dur] (pulse_dur),
        .\act_cfg[null_dur]  (null_dur),
        .\act_cfg[gap_dur]   (gap_dur),
        .\act_cfg[slp]       (slp),
        .transmitter_en      (transmitter_en),
        .msg_sched_en        (msg_sched_en),
        .builder_en          (builder_en),
        .label_val           (label_val),
        .sdi                 (sdi),
        .data                (data),
        .ssm                 (ssm),
        .parity_type         (parity_type),
        .sched_en            (sched_en),
        .initial_delay       (initial_delay),
        .inter_word_gap      (inter_word_gap),
        .send_cmd            (send_cmd),
        .ext_data            (ext_data),
        .ext_high            (ext_high),
        .ext_low             (ext_low),
        .tx_high             (tx_high),
        .tx_low              (tx_low),
        .tx_slp              (tx_slp),
        .tx_busy             (tx_busy),
        .tx_sched_act        (tx_sched_act),
        .tx_word_tx          (tx_word_tx)
    );

    reg f_past_valid = 1'b0;
    reg p_rst_n, p_soft_rst, p_tx_en, p_ext_h, p_ext_l, p_busy;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_tx_en      <= transmitter_en;
        p_ext_h      <= ext_high;
        p_ext_l      <= ext_low;
        p_busy       <= tx_busy;

        if (!f_past_valid)
            assume(!rst_n);

        // P1: tx_slp her zaman aktif config'ten sürülür
        assert(tx_slp == slp);

        if (f_past_valid && rst_n && p_rst_n && !p_soft_rst) begin
            if (p_tx_en) begin
                // P2: Normal TX modunda hat ASLA "11" (Bus Fault) olmaz
                assert(!(tx_high && tx_low));
            end else begin
                // P3: Override modunda çıkış tam olarak ext_high/ext_low'dur ("11" HIGH-Z dahil)
                assert(tx_high == p_ext_h && tx_low == p_ext_l);
                // P4: Override modunda yeni Word başlamaz ve Scheduler pasiftir
                if (!p_busy)
                    assert(!tx_busy);
                assert(!tx_sched_act);
            end
        end
    end
endmodule
