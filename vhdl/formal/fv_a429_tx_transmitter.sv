// Formal doğrulama: a429_tx_transmitter (Bus Fault yok, IDLE=NULL, word_tx sabitliği)
`default_nettype none
module fv_a429_tx_transmitter (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire [15:0] pulse_dur,
    input wire [15:0] null_dur,
    input wire [31:0] gap_dur,
    input wire        slp,
    input wire        start_trig,
    input wire [31:0] word_in
);
    wire        line_high, line_low, tx_busy;
    wire [31:0] word_tx;

    a429_tx_transmitter dut (
        .clk                 (clk),
        .rst_n               (rst_n),
        .soft_rst            (soft_rst),
        .\act_cfg[pulse_dur] (pulse_dur),
        .\act_cfg[null_dur]  (null_dur),
        .\act_cfg[gap_dur]   (gap_dur),
        .\act_cfg[slp]       (slp),
        .start_trig          (start_trig),
        .word_in             (word_in),
        .line_high           (line_high),
        .line_low            (line_low),
        .tx_busy             (tx_busy),
        .word_tx             (word_tx)
    );

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_busy, p_start;
    reg [31:0] p_word_in, p_word_tx;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_busy       <= tx_busy;
        p_start      <= start_trig;
        p_word_in    <= word_in;
        p_word_tx    <= word_tx;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid) begin
            // P1: Word Transmitter ASLA "11" (Bus Fault) sürmez!
            assert(!(line_high && line_low));

            // P2: IDLE (tx_busy == 0) iken hat kesinlikle NULL ("00")
            if (!tx_busy)
                assert(!line_high && !line_low);

            if (rst_n && (!p_rst_n || p_soft_rst)) begin
                // P3: Reset / soft_rst sonrası IDLE ve NULL
                assert(!tx_busy && !line_high && !line_low);
            end else if (rst_n && p_rst_n && !p_soft_rst) begin
                // P4: Gönderim sürerken word_tx asla değişmez (word_in/start_trig değişse bile)
                if (p_busy)
                    assert(word_tx == p_word_tx);
                // P5: IDLE'da start_trig gelince busy=1 ve word_tx=p_word_in olur
                if (!p_busy && p_start)
                    assert(tx_busy && word_tx == p_word_in);
            end
        end
    end
endmodule
