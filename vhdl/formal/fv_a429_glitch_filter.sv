// Formal doğrulama: a429_glitch_filter (doyum güvenliği, win = pencerede glitch clk toplamı, stable geçişte win=0, soft_rst)
`default_nettype none
module fv_a429_glitch_filter (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire [15:0] glitch_size,
    input wire        rx_high_in,
    input wire        rx_low_in
);
    wire        rx_high_out, rx_low_out, glitch_tick;
    wire [15:0] glitch_total_cnt, glitch_win_cnt;

    a429_glitch_filter dut (
        .clk              (clk),
        .rst_n            (rst_n),
        .soft_rst         (soft_rst),
        .glitch_size      (glitch_size),
        .rx_high_in       (rx_high_in),
        .rx_low_in        (rx_low_in),
        .rx_high_out      (rx_high_out),
        .rx_low_out       (rx_low_out),
        .glitch_tick      (glitch_tick),
        .glitch_total_cnt (glitch_total_cnt),
        .glitch_win_cnt   (glitch_win_cnt)
    );

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_hi_out, p_lo_out;
    reg [15:0] p_tot, p_win;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_hi_out     <= rx_high_out;
        p_lo_out     <= rx_low_out;
        p_tot        <= glitch_total_cnt;
        p_win        <= glitch_win_cnt;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: Pencerede glitch yoksa ve stable durum değişmediyse win_cnt sabit kalır;
            //     glitch bittiğinde win_cnt glitch süresi (>= 1 clk) kadar artar, doyumda 0'a sarmaz.
            //     (Reset / soft_rst ertesi clk P2 ile ayrıca kontrol edilir.)
            if (p_rst_n && !p_soft_rst && {rx_high_out, rx_low_out} == {p_hi_out, p_lo_out}) begin
                if (!glitch_tick)
                    assert(glitch_win_cnt == p_win);
                else
                    assert(glitch_win_cnt == 16'hFFFF || glitch_win_cnt > p_win);
            end

            if (!p_rst_n || p_soft_rst) begin
                // P2: Reset / soft_rst sonrası NULL çıkış ve sıfır sayaçlar
                assert(!rx_high_out && !rx_low_out);
                assert(glitch_total_cnt == 16'd0 && glitch_win_cnt == 16'd0);
                assert(!glitch_tick);
            end else begin
                // P3: Toplam sayaç monoton artar (doyumda 0'a sarmaz!)
                assert(glitch_total_cnt >= p_tot);
                // P4: Yeni stable durum kabul edildiğinde glitch_win_cnt kesinlikle 0 olur
                if ({rx_high_out, rx_low_out} != {p_hi_out, p_lo_out})
                    assert(glitch_win_cnt == 16'd0);
                // P5: glitch_tick sadece total_cnt maksimum değilse +1 artırır
                if (glitch_tick && p_tot != 16'hFFFF)
                    assert(glitch_total_cnt == p_tot + 16'd1);
                if (!glitch_tick)
                    assert(glitch_total_cnt == p_tot);
            end
        end
    end
endmodule
