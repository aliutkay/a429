// Formal doğrulama: a429_rx_logger (enable=0 kapısı, FREEZE RAM yazmama garantisi, sıfır hata kaybı)
`default_nettype none
module fv_a429_rx_logger (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire [63:0] ts_now,
    input wire        enable,
    input wire        freeze,
    input wire        global_freeze,
    input wire        clear,
    input wire        word_start,
    input wire [31:0] word_data,
    input wire [31:0] word_gap_dur,
    input wire [15:0] word_gap_err_cnt,
    input wire        word_valid,
    input wire [4:0]  bit_idx,
    input wire [15:0] bit_pulse_dur,
    input wire [15:0] bit_null_dur,
    input wire [15:0] bit_pulse_err_cnt,
    input wire [15:0] bit_null_err_cnt,
    input wire        bit_valid,
    input wire        e_bus, e_noise, e_gap, e_early, e_pg, e_stuck, e_to, e_par,
    input wire [15:0] err_addr,
    input wire [31:0] err_data,
    input wire        err_label_filtered,
    input wire        chk_mismatch,
    input wire        chk_no_echo,
    input wire        chk_unexpected,
    input wire [15:0] chk_addr,
    input wire [31:0] chk_data
);
    wire         word_we, err_we, bit_we, frozen, word_wrap, err_wrap, rx_err_any;
    wire [7:0]   word_waddr, err_waddr, bit_waddr;
    wire [143:0] word_wdata;
    wire [127:0] err_wdata;
    wire [63:0]  bit_wdata;
    wire [31:0]  word_cnt, err_cnt, drop_cnt, last_word;

    a429_rx_logger dut (
        .clk                 (clk),
        .rst_n               (rst_n),
        .soft_rst            (soft_rst),
        .ts_now              (ts_now),
        .enable              (enable),
        .freeze              (freeze),
        .global_freeze       (global_freeze),
        .clear               (clear),
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
        .err_data            (err_data),
        .err_label_filtered  (err_label_filtered),
        .chk_mismatch        (chk_mismatch),
        .chk_no_echo         (chk_no_echo),
        .chk_unexpected      (chk_unexpected),
        .chk_addr            (chk_addr),
        .chk_data            (chk_data),
        .word_we             (word_we),
        .word_waddr          (word_waddr),
        .word_wdata          (word_wdata),
        .err_we              (err_we),
        .err_waddr           (err_waddr),
        .err_wdata           (err_wdata),
        .bit_we              (bit_we),
        .bit_waddr           (bit_waddr),
        .bit_wdata           (bit_wdata),
        .frozen              (frozen),
        .word_wrap           (word_wrap),
        .err_wrap            (err_wrap),
        .word_cnt            (word_cnt),
        .err_cnt             (err_cnt),
        .drop_cnt            (drop_cnt),
        .last_word           (last_word),
        .rx_err_any          (rx_err_any)
    );

    wire [15:0] exp_code = {4'b0, err_label_filtered, chk_unexpected, chk_no_echo, chk_mismatch,
                            e_par, e_to, e_stuck, e_pg, e_early, e_gap, e_noise, e_bus};

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_clear, p_en, p_frz;
    reg [15:0] p_code;
    reg [31:0] p_wcnt, p_ecnt, p_dcnt;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_clear      <= clear;
        p_en         <= enable;
        p_frz        <= freeze || global_freeze;
        p_code       <= exp_code;
        p_wcnt       <= word_cnt;
        p_ecnt       <= err_cnt;
        p_dcnt       <= drop_cnt;

        if (!f_past_valid)
            assume(!rst_n);

        // P0: frozen kombinasyonel olarak freeze OR global_freeze
        assert(frozen == (freeze || global_freeze));

        if (f_past_valid && rst_n) begin
            if (!p_rst_n || p_soft_rst || p_clear) begin
                // P1: Reset / clear -> tüm sayaçlar, wrap ve RAM we sıfır
                assert(!word_we && !err_we && !bit_we);
                assert(word_cnt == 32'd0 && err_cnt == 32'd0 && drop_cnt == 32'd0);
                assert(!word_wrap && !err_wrap);
            end else begin
                // P2: enable=0 -> RAM yazması yok, hiçbir sayaç değişmez
                if (!p_en) begin
                    assert(!word_we && !err_we && !bit_we);
                    assert(word_cnt == p_wcnt && err_cnt == p_ecnt && drop_cnt == p_dcnt);
                end
                // P3: FREEZE aktifken RAM'e ASLA yazılmaz (okuma bütünlüğü garantisi!)
                if (p_frz) begin
                    assert(!word_we && !err_we && !bit_we);
                    assert(word_cnt == p_wcnt && err_cnt == p_ecnt);
                end
                // P4: Aktif ve donuk değilken hiçbir hata biti kaybolmaz (OR korunumu)
                if (p_en && !p_frz && (p_code != 16'd0)) begin
                    assert(err_we == 1'b1);
                    assert(err_wdata[63:48] == p_code);
                    assert(err_cnt == p_ecnt + 32'd1);
                end
            end
        end
    end
endmodule
