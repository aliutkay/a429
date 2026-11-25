// Formal doğrulama: a429_word_checker (FIFO sınır güvenliği, hata dışlaması, sayaç tutarlılığı)
`default_nettype none
module fv_a429_word_checker (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire        chk_en,
    input wire        chk_clear,
    input wire [31:0] chk_timeout,
    input wire        chk_route_ok,
    input wire [63:0] ts_now,
    input wire        tx_word_start,
    input wire [31:0] tx_word_tx,
    input wire [31:0] rx_word_data,
    input wire        rx_word_valid,
    input wire        rx_err_any
);
    wire        c_mm, c_ne, c_un, fovf;
    wire [15:0] c_addr;
    wire [31:0] c_data, ok_cnt, err_cnt;
    wire [3:0]  flev;

    a429_word_checker dut (
        .clk            (clk),
        .rst_n          (rst_n),
        .soft_rst       (soft_rst),
        .chk_en         (chk_en),
        .chk_clear      (chk_clear),
        .chk_timeout    (chk_timeout),
        .chk_route_ok   (chk_route_ok),
        .ts_now         (ts_now),
        .tx_word_start  (tx_word_start),
        .tx_word_tx     (tx_word_tx),
        .rx_word_data   (rx_word_data),
        .rx_word_valid  (rx_word_valid),
        .rx_err_any     (rx_err_any),
        .chk_mismatch   (c_mm),
        .chk_no_echo    (c_ne),
        .chk_unexpected (c_un),
        .chk_addr       (c_addr),
        .chk_data       (c_data),
        .chk_ok_cnt     (ok_cnt),
        .chk_err_cnt    (err_cnt),
        .chk_fifo_level (flev),
        .chk_fifo_ovf   (fovf)
    );

    wire [1:0] err_pop = c_mm + c_ne + c_un;

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_clr, p_act;
    reg [31:0] p_ok, p_err;
    reg [3:0]  p_flev;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_clr        <= chk_clear;
        p_act        <= chk_en && chk_route_ok;
        p_ok         <= ok_cnt;
        p_err        <= err_cnt;
        p_flev       <= flev;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: FIFO seviyesi asla G_FIFO_DEPTH (4) değerini aşamaz
            assert(flev <= 4'd4);

            // P2: Mismatch, NoEcho ve Unexpected karşılıklı dışlamalıdır
            assert(err_pop <= 2'd1);

            if (!p_rst_n || p_soft_rst) begin
                assert(flev == 4'd0 && !fovf && ok_cnt == 32'd0 && err_cnt == 32'd0);
            end else if (p_clr) begin
                // P3: chk_clear FIFO ve ovf'yi sıfırlar
                assert(flev == 4'd0 && !fovf);
            end else begin
                // P4: Pasifken hata üretilmez ve sayaçlar/FIFO değişmez
                if (!p_act) begin
                    assert(err_pop == 2'd0);
                    assert(ok_cnt == p_ok && err_cnt == p_err && flev == p_flev);
                end
                // P5: Hata sayacı tam olarak bir hata bayrağı çıktığında +1 artar
                if (err_pop == 2'd1)
                    assert(err_cnt == p_err + 32'd1);
                else
                    assert(err_cnt == p_err);
            end
        end
    end
endmodule
