// Instantiation template for arinc429_axil_pk
arinc429_axil_pk u_arinc429_axil_pk (
    .S_AXI_ACLK          (),  // input
    .S_AXI_ARESETN       (),  // input
    .o_soft_reset_rst_all(),  // output
    .o_soft_reset_tx     (),  // output
    .o_soft_reset_txbit  (),  // output
    .o_soft_reset_rx0    (),  // output
    .o_soft_reset_rx1    (),  // output
    .o_global_freeze     (),  // output
    .o_ts_ctrl_enable    (),  // output
    .o_ts_ctrl_clear     (),  // output
    .i_ts_lsb            (),  // input [31:0]
    .o_ts_lsb_rd         (),  // output
    .i_ts_msb            (),  // input [31:0]
    .o_tx_transmitter_en (),  // output
    .o_tx_msg_sched_en   (),  // output
    .o_tx_builder_en     (),  // output
    .o_tx_label          (),  // output [7:0]
    .o_tx_sdi            (),  // output [1:0]
    .o_tx_data           (),  // output [18:0]
    .o_tx_ssm            (),  // output [1:0]
    .o_tx_parity_type    (),  // output
    .o_tx_sched_en       (),  // output
    .o_tx_initial_delay  (),  // output [31:0]
    .o_tx_inter_word_gap (),  // output [31:0]
    .o_tx_send_cmd_send  (),  // output
    .o_tx_ext_data       (),  // output [31:0]
    .o_tx_ext_high       (),  // output
    .o_tx_ext_low        (),  // output
    .o_tx_cfg_sel        (),  // output [1:0]
    .o_tx_cfg_apply_apply(),  // output
    .o_tx_cust_pulse_dur (),  // output [15:0]
    .o_tx_cust_null_dur  (),  // output [15:0]
    .o_tx_cust_gap_dur   (),  // output [31:0]
    .o_tx_cust_slp       (),  // output
    .i_tx_act_pulse_dur  (),  // input [15:0]
    .i_tx_act_null_dur   (),  // input [15:0]
    .i_tx_act_gap_dur    (),  // input [31:0]
    .i_tx_act_slp        (),  // input
    .i_tx_status_busy    (),  // input
    .i_tx_status_sched_active(),  // input
    .i_tx_status_act_cfg (),  // input [1:0]
    .i_tx_word_cnt       (),  // input [31:0]
    .o_tb_ctrl_enable    (),  // output
    .o_tb_ctrl_freeze    (),  // output
    .o_tb_ctrl_clear     (),  // output
    .i_tb_status_frozen  (),  // input
    .i_tb_status_word_wrap(),  // input
    .i_tb_status_err_wrap(),  // input
    .i_tb_status_act_cfg (),  // input [1:0]
    .o_tb_cfg_sel        (),  // output [1:0]
    .o_tb_cfg_apply_apply(),  // output
    .o_tb_cust_glitch_filter_size(),  // output [15:0]
    .o_tb_cust_min_pulse (),  // output [15:0]
    .o_tb_cust_max_pulse (),  // output [15:0]
    .o_tb_cust_min_bit   (),  // output [15:0]
    .o_tb_cust_max_bit   (),  // output [15:0]
    .o_tb_cust_max_pulse_err(),  // output [15:0]
    .o_tb_cust_max_null_err(),  // output [15:0]
    .o_tb_cust_max_gap_err(),  // output [15:0]
    .o_tb_cust_parity_mode(),  // output [1:0]
    .i_tb_act_glitch_filter_size(),  // input [15:0]
    .i_tb_act_min_pulse  (),  // input [15:0]
    .i_tb_act_max_pulse  (),  // input [15:0]
    .i_tb_act_min_bit    (),  // input [15:0]
    .i_tb_act_max_bit    (),  // input [15:0]
    .i_tb_act_max_pulse_err(),  // input [15:0]
    .i_tb_act_max_null_err(),  // input [15:0]
    .i_tb_act_max_gap_err(),  // input [15:0]
    .i_tb_act_parity_mode(),  // input [1:0]
    .i_tb_word_cnt       (),  // input [31:0]
    .i_tb_err_cnt        (),  // input [31:0]
    .i_tb_drop_cnt       (),  // input [31:0]
    .i_tb_last_word      (),  // input [31:0]
    .o_tb_word_raddr     (),  // output [7:0]
    .o_tb_word_raddr_wr  (),  // output
    .i_tb_word_rd_ts_msb (),  // input [31:0]
    .i_tb_word_rd_ts_lsb (),  // input [31:0]
    .i_tb_word_rd_data   (),  // input [31:0]
    .i_tb_word_rd_gap    (),  // input [31:0]
    .i_tb_word_rd_gap_err(),  // input [15:0]
    .o_tb_word_rd_gap_err_rd(),  // output
    .o_tb_err_raddr      (),  // output [7:0]
    .o_tb_err_raddr_wr   (),  // output
    .i_tb_err_rd_ts_msb  (),  // input [31:0]
    .i_tb_err_rd_ts_lsb  (),  // input [31:0]
    .i_tb_err_rd_code    (),  // input [15:0]
    .i_tb_err_rd_addr    (),  // input [15:0]
    .i_tb_err_rd_data    (),  // input [31:0]
    .o_tb_err_rd_data_rd (),  // output
    .o_tb_bit_raddr_bit_idx(),  // output [4:0]
    .o_tb_bit_raddr_word_idx(),  // output [2:0]
    .o_tb_bit_raddr_wr   (),  // output
    .i_tb_bit_rd_pulse   (),  // input [15:0]
    .i_tb_bit_rd_pulse_err(),  // input [15:0]
    .i_tb_bit_rd_null    (),  // input [15:0]
    .i_tb_bit_rd_null_err(),  // input [15:0]
    .o_tb_bit_rd_null_err_rd(),  // output
    .o_tb_chk_ctrl_enable(),  // output
    .o_tb_chk_ctrl_clear (),  // output
    .o_tb_chk_timeout    (),  // output [31:0]
    .i_tb_chk_ok_cnt     (),  // input [31:0]
    .i_tb_chk_err_cnt    (),  // input [31:0]
    .i_tb_chk_status_fifo_level(),  // input [3:0]
    .i_tb_chk_status_fifo_ovf(),  // input
    .o_rx0_ctrl_enable   (),  // output
    .o_rx0_ctrl_freeze   (),  // output
    .o_rx0_ctrl_clear    (),  // output
    .i_rx0_status_frozen (),  // input
    .i_rx0_status_word_wrap(),  // input
    .i_rx0_status_err_wrap(),  // input
    .i_rx0_status_act_cfg(),  // input [1:0]
    .o_rx0_cfg_sel       (),  // output [1:0]
    .o_rx0_cfg_apply_apply(),  // output
    .o_rx0_cust_glitch_filter_size(),  // output [15:0]
    .o_rx0_cust_min_pulse(),  // output [15:0]
    .o_rx0_cust_max_pulse(),  // output [15:0]
    .o_rx0_cust_min_bit  (),  // output [15:0]
    .o_rx0_cust_max_bit  (),  // output [15:0]
    .o_rx0_cust_max_pulse_err(),  // output [15:0]
    .o_rx0_cust_max_null_err(),  // output [15:0]
    .o_rx0_cust_max_gap_err(),  // output [15:0]
    .o_rx0_cust_parity_mode(),  // output [1:0]
    .i_rx0_act_glitch_filter_size(),  // input [15:0]
    .i_rx0_act_min_pulse (),  // input [15:0]
    .i_rx0_act_max_pulse (),  // input [15:0]
    .i_rx0_act_min_bit   (),  // input [15:0]
    .i_rx0_act_max_bit   (),  // input [15:0]
    .i_rx0_act_max_pulse_err(),  // input [15:0]
    .i_rx0_act_max_null_err(),  // input [15:0]
    .i_rx0_act_max_gap_err(),  // input [15:0]
    .i_rx0_act_parity_mode(),  // input [1:0]
    .i_rx0_word_cnt      (),  // input [31:0]
    .i_rx0_err_cnt       (),  // input [31:0]
    .i_rx0_drop_cnt      (),  // input [31:0]
    .i_rx0_last_word     (),  // input [31:0]
    .o_rx0_word_raddr    (),  // output [7:0]
    .o_rx0_word_raddr_wr (),  // output
    .i_rx0_word_rd_ts_msb(),  // input [31:0]
    .i_rx0_word_rd_ts_lsb(),  // input [31:0]
    .i_rx0_word_rd_data  (),  // input [31:0]
    .i_rx0_word_rd_gap   (),  // input [31:0]
    .i_rx0_word_rd_gap_err(),  // input [15:0]
    .o_rx0_word_rd_gap_err_rd(),  // output
    .o_rx0_err_raddr     (),  // output [7:0]
    .o_rx0_err_raddr_wr  (),  // output
    .i_rx0_err_rd_ts_msb (),  // input [31:0]
    .i_rx0_err_rd_ts_lsb (),  // input [31:0]
    .i_rx0_err_rd_code   (),  // input [15:0]
    .i_rx0_err_rd_addr   (),  // input [15:0]
    .i_rx0_err_rd_data   (),  // input [31:0]
    .o_rx0_err_rd_data_rd(),  // output
    .o_rx0_bit_raddr_bit_idx(),  // output [4:0]
    .o_rx0_bit_raddr_word_idx(),  // output [2:0]
    .o_rx0_bit_raddr_wr  (),  // output
    .i_rx0_bit_rd_pulse  (),  // input [15:0]
    .i_rx0_bit_rd_pulse_err(),  // input [15:0]
    .i_rx0_bit_rd_null   (),  // input [15:0]
    .i_rx0_bit_rd_null_err(),  // input [15:0]
    .o_rx0_bit_rd_null_err_rd(),  // output
    .o_rx1_ctrl_enable   (),  // output
    .o_rx1_ctrl_freeze   (),  // output
    .o_rx1_ctrl_clear    (),  // output
    .i_rx1_status_frozen (),  // input
    .i_rx1_status_word_wrap(),  // input
    .i_rx1_status_err_wrap(),  // input
    .i_rx1_status_act_cfg(),  // input [1:0]
    .o_rx1_cfg_sel       (),  // output [1:0]
    .o_rx1_cfg_apply_apply(),  // output
    .o_rx1_cust_glitch_filter_size(),  // output [15:0]
    .o_rx1_cust_min_pulse(),  // output [15:0]
    .o_rx1_cust_max_pulse(),  // output [15:0]
    .o_rx1_cust_min_bit  (),  // output [15:0]
    .o_rx1_cust_max_bit  (),  // output [15:0]
    .o_rx1_cust_max_pulse_err(),  // output [15:0]
    .o_rx1_cust_max_null_err(),  // output [15:0]
    .o_rx1_cust_max_gap_err(),  // output [15:0]
    .o_rx1_cust_parity_mode(),  // output [1:0]
    .i_rx1_act_glitch_filter_size(),  // input [15:0]
    .i_rx1_act_min_pulse (),  // input [15:0]
    .i_rx1_act_max_pulse (),  // input [15:0]
    .i_rx1_act_min_bit   (),  // input [15:0]
    .i_rx1_act_max_bit   (),  // input [15:0]
    .i_rx1_act_max_pulse_err(),  // input [15:0]
    .i_rx1_act_max_null_err(),  // input [15:0]
    .i_rx1_act_max_gap_err(),  // input [15:0]
    .i_rx1_act_parity_mode(),  // input [1:0]
    .i_rx1_word_cnt      (),  // input [31:0]
    .i_rx1_err_cnt       (),  // input [31:0]
    .i_rx1_drop_cnt      (),  // input [31:0]
    .i_rx1_last_word     (),  // input [31:0]
    .o_rx1_word_raddr    (),  // output [7:0]
    .o_rx1_word_raddr_wr (),  // output
    .i_rx1_word_rd_ts_msb(),  // input [31:0]
    .i_rx1_word_rd_ts_lsb(),  // input [31:0]
    .i_rx1_word_rd_data  (),  // input [31:0]
    .i_rx1_word_rd_gap   (),  // input [31:0]
    .i_rx1_word_rd_gap_err(),  // input [15:0]
    .o_rx1_word_rd_gap_err_rd(),  // output
    .o_rx1_err_raddr     (),  // output [7:0]
    .o_rx1_err_raddr_wr  (),  // output
    .i_rx1_err_rd_ts_msb (),  // input [31:0]
    .i_rx1_err_rd_ts_lsb (),  // input [31:0]
    .i_rx1_err_rd_code   (),  // input [15:0]
    .i_rx1_err_rd_addr   (),  // input [15:0]
    .i_rx1_err_rd_data   (),  // input [31:0]
    .o_rx1_err_rd_data_rd(),  // output
    .o_rx1_bit_raddr_bit_idx(),  // output [4:0]
    .o_rx1_bit_raddr_word_idx(),  // output [2:0]
    .o_rx1_bit_raddr_wr  (),  // output
    .i_rx1_bit_rd_pulse  (),  // input [15:0]
    .i_rx1_bit_rd_pulse_err(),  // input [15:0]
    .i_rx1_bit_rd_null   (),  // input [15:0]
    .i_rx1_bit_rd_null_err(),  // input [15:0]
    .o_rx1_bit_rd_null_err_rd(),  // output
    .SLAVE_AXI_REQ       (),  // input [110:0]
    .SLAVE_AXI_RSP       ()   // output [40:0]
);
