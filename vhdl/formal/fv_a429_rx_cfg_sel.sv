// Formal doğrulama: a429_rx_cfg_sel (shadow izolasyonu, geçersiz mod yok, soft_rst)
`default_nettype none
module fv_a429_rx_cfg_sel (
    input wire         clk,
    input wire         rst_n,
    input wire         soft_rst,
    input wire [1:0]   cfg_sel,
    input wire         cfg_apply,
    input wire [129:0] cust_cfg
);
    wire [15:0] act_gf, act_minp, act_maxp, act_minb, act_maxb, act_pe, act_ne, act_ge;
    wire [1:0]  act_pm;
    wire [129:0] act_cfg = {act_gf, act_minp, act_maxp, act_minb, act_maxb, act_pe, act_ne, act_ge, act_pm};
    wire [1:0]   act_mode;

    a429_rx_cfg_sel dut (
        .clk                            (clk),
        .rst_n                          (rst_n),
        .soft_rst                       (soft_rst),
        .cfg_sel                        (cfg_sel),
        .cfg_apply                      (cfg_apply),
        .\cust_cfg[glitch_filter_size]  (cust_cfg[129:114]),
        .\cust_cfg[min_pulse]           (cust_cfg[113:98]),
        .\cust_cfg[max_pulse]           (cust_cfg[97:82]),
        .\cust_cfg[min_bit]             (cust_cfg[81:66]),
        .\cust_cfg[max_bit]             (cust_cfg[65:50]),
        .\cust_cfg[max_pulse_err]       (cust_cfg[49:34]),
        .\cust_cfg[max_null_err]        (cust_cfg[33:18]),
        .\cust_cfg[max_gap_err]         (cust_cfg[17:2]),
        .\cust_cfg[parity_mode]         (cust_cfg[1:0]),
        .\act_cfg[glitch_filter_size]   (act_gf),
        .\act_cfg[min_pulse]            (act_minp),
        .\act_cfg[max_pulse]            (act_maxp),
        .\act_cfg[min_bit]              (act_minb),
        .\act_cfg[max_bit]              (act_maxb),
        .\act_cfg[max_pulse_err]        (act_pe),
        .\act_cfg[max_null_err]         (act_ne),
        .\act_cfg[max_gap_err]          (act_ge),
        .\act_cfg[parity_mode]          (act_pm),
        .act_mode                       (act_mode)
    );

    reg         f_past_valid = 1'b0;
    reg         p_rst_n, p_soft_rst, p_apply;
    reg [1:0]   p_sel, p_mode;
    reg [129:0] p_cust, p_act;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_apply      <= cfg_apply;
        p_sel        <= cfg_sel;
        p_cust       <= cust_cfg;
        p_mode       <= act_mode;
        p_act        <= act_cfg;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: Geçersiz mode ("11") ulaşılamaz
            assert(act_mode != 2'b11);

            if (!p_rst_n || p_soft_rst) begin
                // P2: Reset / soft_rst sonrası HS Preset
                assert(act_mode == 2'b00);
            end else if (!p_apply) begin
                // P3: Shadow izolasyonu: cfg_apply olmadan aktif değer değişmez
                assert(act_mode == p_mode);
                assert(act_cfg  == p_act);
            end else if (p_sel == 2'b10) begin
                // P4: Custom apply -> tam eşleşme
                assert(act_mode == 2'b10 && act_cfg == p_cust);
            end else if (p_sel == 2'b01) begin
                assert(act_mode == 2'b01);
            end else begin
                assert(act_mode == 2'b00);
            end
        end
    end
endmodule
