// Formal doğrulama: a429_rx_decoder (en fazla 1 hata bayrağı, hatalı Word yok, soft_rst temizliği)
`default_nettype none
module fv_a429_rx_decoder (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire [15:0] cfg_min_pulse,
    input wire [15:0] cfg_max_pulse,
    input wire [15:0] cfg_min_bit,
    input wire [15:0] cfg_max_bit,
    input wire [15:0] cfg_max_pulse_err,
    input wire [15:0] cfg_max_null_err,
    input wire [15:0] cfg_max_gap_err,
    input wire [1:0]  cfg_parity_mode,
    input wire        rx_high,
    input wire        rx_low,
    input wire [15:0] glitch_cnt
);
    wire        word_start, word_valid, bit_valid;
    wire [31:0] word_data, word_gap_dur, err_data;
    wire [15:0] word_gap_err_cnt, bit_pulse_dur, bit_null_dur, bit_pulse_err_cnt, bit_null_err_cnt, err_addr;
    wire [4:0]  bit_idx;
    wire        e_bus, e_noise, e_gap, e_early, e_pg, e_stuck, e_to, e_par;

    a429_rx_decoder dut (
        .clk                 (clk),
        .rst_n               (rst_n),
        .soft_rst            (soft_rst),
        .cfg_min_pulse       (cfg_min_pulse),
        .cfg_max_pulse       (cfg_max_pulse),
        .cfg_min_bit         (cfg_min_bit),
        .cfg_max_bit         (cfg_max_bit),
        .cfg_max_pulse_err   (cfg_max_pulse_err),
        .cfg_max_null_err    (cfg_max_null_err),
        .cfg_max_gap_err     (cfg_max_gap_err),
        .cfg_parity_mode     (cfg_parity_mode),
        .rx_high             (rx_high),
        .rx_low              (rx_low),
        .glitch_cnt          (glitch_cnt),
        .word_start          (word_start),
        .word_data           (word_data),
        .word_gap_dur        (word_gap_dur),
        .word_gap_err_cnt    (word_gap_err_cnt),
        .word_valid          (word_valid),
        .bit_idx             (bit_idx),
        .bit_pulse_dur       (bit_pulse_dur),
        .bit_null_dur        (bit_null_dur),
        .bit_pulse_err_cnt   (bit_pulse_err_cnt),
        .bit_null_err_cnt    (bit_null_err_cnt),
        .bit_valid           (bit_valid),
        .err_bus_fault       (e_bus),
        .err_noise_violation (e_noise),
        .err_gap_violation   (e_gap),
        .err_bit_early       (e_early),
        .err_pulse_glitch    (e_pg),
        .err_pulse_stuck     (e_stuck),
        .err_bit_timeout     (e_to),
        .err_parity          (e_par),
        .err_addr            (err_addr),
        .err_data            (err_data)
    );

    wire [7:0] err_vec = {e_par, e_to, e_stuck, e_pg, e_early, e_gap, e_noise, e_bus};
    wire [3:0] err_pop = e_bus + e_noise + e_gap + e_early + e_pg + e_stuck + e_to + e_par;

    reg f_past_valid = 1'b0;
    reg p_rst_n, p_soft_rst;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: Bir clock'ta en fazla BİR hata bayrağı yükselebilir (one-hot/zero)
            assert(err_pop <= 4'd1);

            // P2: word_valid ile herhangi bir hata bayrağı asla aynı anda '1' olamaz
            assert(!(word_valid && (err_vec != 8'd0)));

            // P3: word_start ile word_valid asla aynı anda '1' olamaz
            assert(!(word_start && word_valid));

            // P4: Reset veya soft_rst ertesi clk tüm 1-clk çıkışlar sıfır
            if (!p_rst_n || p_soft_rst) begin
                assert(!word_start && !word_valid && !bit_valid);
                assert(err_vec == 8'd0);
            end
        end
    end
endmodule
