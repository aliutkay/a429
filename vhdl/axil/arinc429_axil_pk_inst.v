// Instantiation template for arinc429_axil_pk
arinc429_axil_pk u_arinc429_axil_pk (
    .S_AXI_ACLK          (),  // input
    .S_AXI_ARESETN       (),  // input
    .o_soft_reset_rst_all(),  // output
    .o_soft_reset_tx     (),  // output
    .o_soft_reset_txbit  (),  // output
    .o_soft_reset_rx0    (),  // output
    .o_global_freeze     (),  // output
    .o_ts_ctrl_enable    (),  // output
    .o_ts_ctrl_clear     (),  // output
    .i_ts_lsb            (),  // input [31:0]
    .o_ts_lsb_rd         (),  // output
    .i_ts_msb            (),  // input [31:0]
    .o_tx_ctrl_transmitter_en(),  // output
    .o_tx_ctrl_msg_sched_en(),  // output
    .o_tx_ctrl_builder_en(),  // output
    .o_tx_ctrl_sched_en  (),  // output
    .o_tx_word_label_val (),  // output [7:0]
    .o_tx_word_sdi       (),  // output [1:0]
    .o_tx_word_data      (),  // output [18:0]
    .o_tx_word_ssm       (),  // output [1:0]
    .o_tx_word_parity_type(),  // output
    .o_tx_send_cmd_send  (),  // output
    .o_tx_ext_data       (),  // output [31:0]
    .o_tx_ext_line_high  (),  // output
    .o_tx_ext_line_low   (),  // output
    .o_tx_initial_delay  (),  // output [31:0]
    .o_tx_inter_word_gap (),  // output [31:0]
    .o_tx_sched_count    (),  // output [31:0]
    .o_tx_cfg_sel        (),  // output [1:0]
    .o_tx_cfg_apply      (),  // output
    .o_tx_cust_timing_pulse_dur(),  // output [15:0]
    .o_tx_cust_timing_null_dur(),  // output [15:0]
    .o_tx_cust_gap_dur   (),  // output [31:0]
    .o_tx_cust_slp       (),  // output
    .i_tx_act_timing_pulse_dur(),  // input [15:0]
    .i_tx_act_timing_null_dur(),  // input [15:0]
    .i_tx_act_gap_dur    (),  // input [31:0]
    .i_tx_act_slp        (),  // input
    .i_tx_status_busy    (),  // input
    .i_tx_status_sched_active(),  // input
    .i_tx_status_act_cfg (),  // input [1:0]
    .i_tx_status_sched_done(),  // input
    .i_tx_word_cnt       (),  // input [31:0]
    .o_tb_ctrl_enable    (),  // output
    .o_tb_ctrl_freeze    (),  // output
    .o_tb_ctrl_clear     (),  // output
    .i_tb_status_frozen  (),  // input
    .i_tb_status_word_wrap(),  // input
    .i_tb_status_err_wrap(),  // input
    .i_tb_status_act_cfg (),  // input [1:0]
    .i_tb_status_line_high(),  // input
    .i_tb_status_line_low(),  // input
    .i_tb_status_sync_wait(),  // input
    .o_tb_cfg_sel        (),  // output [1:0]
    .o_tb_cfg_apply      (),  // output
    .o_tb_cust_pulse_min (),  // output [15:0]
    .o_tb_cust_pulse_max (),  // output [15:0]
    .o_tb_cust_bit_min   (),  // output [15:0]
    .o_tb_cust_bit_max   (),  // output [15:0]
    .o_tb_cust_noise_pulse_err(),  // output [15:0]
    .o_tb_cust_noise_null_err(),  // output [15:0]
    .o_tb_cust_filter_glitch_size(),  // output [15:0]
    .o_tb_cust_filter_gap_err(),  // output [15:0]
    .o_tb_cust_parity    (),  // output [1:0]
    .i_tb_act_pulse_min  (),  // input [15:0]
    .i_tb_act_pulse_max  (),  // input [15:0]
    .i_tb_act_bit_min    (),  // input [15:0]
    .i_tb_act_bit_max    (),  // input [15:0]
    .i_tb_act_noise_pulse_err(),  // input [15:0]
    .i_tb_act_noise_null_err(),  // input [15:0]
    .i_tb_act_filter_glitch_size(),  // input [15:0]
    .i_tb_act_filter_gap_err(),  // input [15:0]
    .i_tb_act_parity     (),  // input [1:0]
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
    .i_tb_err_rd_info_code(),  // input [15:0]
    .i_tb_err_rd_info_addr(),  // input [15:0]
    .i_tb_err_rd_data    (),  // input [31:0]
    .o_tb_err_rd_data_rd (),  // output
    .o_tb_bit_raddr_bit_idx(),  // output [4:0]
    .o_tb_bit_raddr_word_idx(),  // output [2:0]
    .o_tb_bit_raddr_wr   (),  // output
    .i_tb_bit_rd_pulse_dur(),  // input [15:0]
    .i_tb_bit_rd_pulse_err(),  // input [15:0]
    .i_tb_bit_rd_null_dur(),  // input [15:0]
    .i_tb_bit_rd_null_err(),  // input [15:0]
    .o_tb_bit_rd_null_rd (),  // output
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
    .i_rx0_status_line_high(),  // input
    .i_rx0_status_line_low(),  // input
    .i_rx0_status_sync_wait(),  // input
    .o_rx0_cfg_sel       (),  // output [1:0]
    .o_rx0_cfg_apply     (),  // output
    .o_rx0_cust_pulse_min(),  // output [15:0]
    .o_rx0_cust_pulse_max(),  // output [15:0]
    .o_rx0_cust_bit_min  (),  // output [15:0]
    .o_rx0_cust_bit_max  (),  // output [15:0]
    .o_rx0_cust_noise_pulse_err(),  // output [15:0]
    .o_rx0_cust_noise_null_err(),  // output [15:0]
    .o_rx0_cust_filter_glitch_size(),  // output [15:0]
    .o_rx0_cust_filter_gap_err(),  // output [15:0]
    .o_rx0_cust_parity   (),  // output [1:0]
    .i_rx0_act_pulse_min (),  // input [15:0]
    .i_rx0_act_pulse_max (),  // input [15:0]
    .i_rx0_act_bit_min   (),  // input [15:0]
    .i_rx0_act_bit_max   (),  // input [15:0]
    .i_rx0_act_noise_pulse_err(),  // input [15:0]
    .i_rx0_act_noise_null_err(),  // input [15:0]
    .i_rx0_act_filter_glitch_size(),  // input [15:0]
    .i_rx0_act_filter_gap_err(),  // input [15:0]
    .i_rx0_act_parity    (),  // input [1:0]
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
    .i_rx0_err_rd_info_code(),  // input [15:0]
    .i_rx0_err_rd_info_addr(),  // input [15:0]
    .i_rx0_err_rd_data   (),  // input [31:0]
    .o_rx0_err_rd_data_rd(),  // output
    .o_rx0_bit_raddr_bit_idx(),  // output [4:0]
    .o_rx0_bit_raddr_word_idx(),  // output [2:0]
    .o_rx0_bit_raddr_wr  (),  // output
    .i_rx0_bit_rd_pulse_dur(),  // input [15:0]
    .i_rx0_bit_rd_pulse_err(),  // input [15:0]
    .i_rx0_bit_rd_null_dur(),  // input [15:0]
    .i_rx0_bit_rd_null_err(),  // input [15:0]
    .o_rx0_bit_rd_null_rd(),  // output
    .SLAVE_AXI_REQ       (),  // input [110:0]
    .SLAVE_AXI_RSP       ()   // output [40:0]
);
