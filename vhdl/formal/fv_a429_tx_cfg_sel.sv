// Formal doğrulama: a429_tx_cfg_sel (k-indüksiyon: Word ortasında config değişmeme garantisi)
`default_nettype none
module fv_a429_tx_cfg_sel (
    input wire        clk,
    input wire        rst_n,
    input wire        soft_rst,
    input wire        tx_busy,
    input wire [1:0]  cfg_sel,
    input wire        cfg_apply,
    input wire [15:0] cust_pulse,
    input wire [15:0] cust_null,
    input wire [31:0] cust_gap,
    input wire        cust_slp
);
    wire [15:0] act_pulse, act_null;
    wire [31:0] act_gap;
    wire        act_slp;
    wire [64:0] cust_rec = {cust_pulse, cust_null, cust_gap, cust_slp};
    wire [64:0] act_rec  = {act_pulse,  act_null,  act_gap,  act_slp};
    wire [1:0]  act_mode;

    a429_tx_cfg_sel dut (
        .clk                  (clk),
        .rst_n                (rst_n),
        .soft_rst             (soft_rst),
        .tx_busy              (tx_busy),
        .cfg_sel              (cfg_sel),
        .cfg_apply            (cfg_apply),
        .\cust_cfg[pulse_dur] (cust_pulse),
        .\cust_cfg[null_dur]  (cust_null),
        .\cust_cfg[gap_dur]   (cust_gap),
        .\cust_cfg[slp]       (cust_slp),
        .\act_cfg[pulse_dur]  (act_pulse),
        .\act_cfg[null_dur]   (act_null),
        .\act_cfg[gap_dur]    (act_gap),
        .\act_cfg[slp]        (act_slp),
        .act_mode             (act_mode)
    );

    localparam [64:0] C_TX_HS = {16'd250,  16'd250,  32'd2000,  1'b1};
    localparam [64:0] C_TX_LS = {16'd2000, 16'd2000, 32'd16000, 1'b0};

    reg        f_past_valid = 1'b0;
    reg        p_rst_n, p_soft_rst, p_tx_busy, p_apply;
    reg [1:0]  p_sel, p_mode;
    reg [64:0] p_cust, p_act;

    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        p_rst_n      <= rst_n;
        p_soft_rst   <= soft_rst;
        p_tx_busy    <= tx_busy;
        p_apply      <= cfg_apply;
        p_sel        <= cfg_sel;
        p_cust       <= cust_rec;
        p_mode       <= act_mode;
        p_act        <= act_rec;

        if (!f_past_valid)
            assume(!rst_n);

        if (f_past_valid && rst_n) begin
            // P1: Geçersiz mode ("11") asla üretilmez
            assert(act_mode != 2'b11);

            if (!p_rst_n || p_soft_rst) begin
                // P2: Reset / soft_rst sonrası kesinlikle High Speed Preset
                assert(act_mode == 2'b00);
                assert(act_rec  == C_TX_HS);
            end else begin
                // P3: Word ortasında (tx_busy == 1) aktif config ASLA değişmez!
                if (p_tx_busy) begin
                    assert(act_mode == p_mode);
                    assert(act_rec  == p_act);
                end
                // P4: Boştayken cfg_apply 1 clk'de kesinlikle uygulanır
                if (p_apply && !p_tx_busy) begin
                    if (p_sel == 2'b01) begin
                        assert(act_mode == 2'b01 && act_rec == C_TX_LS);
                    end else if (p_sel == 2'b10) begin
                        assert(act_mode == 2'b10 && act_rec == p_cust);
                    end else begin
                        assert(act_mode == 2'b00 && act_rec == C_TX_HS);
                    end
                end
            end
        end
    end
endmodule
