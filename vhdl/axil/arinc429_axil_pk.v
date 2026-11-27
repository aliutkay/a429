////////////////////////////////////////////////////////////////////////////////
// Module: arinc429_axil_pk
//
// HDL Designer block: arinc429_axil with packed AXI4-Lite ports (one request and one
// response vector per interface). The plain module is instantiated unchanged inside.
// All other ports are passed through unchanged.
//
// No parameters (no generics for a VHDL top, where 32-bit values would overflow an
// integer). The parameter values of the module are fixed here (regenerate with
// axilgen --pack FILE --set NAME=VALUE, or the AXIL Studio dialog, to change them):
//   C_AXI_ADDR_WIDTH = 32
//   C_AXI_DATA_WIDTH = 32
//   OPT_SKIDBUFFER = 1'h0
//   OPT_LOWPOWER = 1'h0
//
//   SLAVE_AXI_REQ / SLAVE_AXI_RSP : slave interface (S_AXI_*), 32-bit
//
// Packed layout:
//   REQ [110:0] = AWADDR[110:79] AWPROT[78:76] AWVALID[75] WDATA[74:43] WSTRB[42:39] WVALID[38]
//                 BREADY[37] ARADDR[36:5] ARPROT[4:2] ARVALID[1] RREADY[0]
//   RSP [40:0] = AWREADY[40] WREADY[39] BRESP[38:37] BVALID[36] ARREADY[35] RDATA[34:3]
//                RRESP[2:1] RVALID[0]
////////////////////////////////////////////////////////////////////////////////

`default_nettype none

module arinc429_axil_pk (
    input  wire S_AXI_ACLK,
    input  wire S_AXI_ARESETN,
    output wire o_soft_reset_rst_all,
    output wire o_soft_reset_tx,
    output wire o_soft_reset_txbit,
    output wire o_soft_reset_rx0,
    output wire o_global_freeze,
    output wire o_ts_ctrl_enable,
    output wire o_ts_ctrl_clear,
    input  wire [31:0] i_ts_lsb,
    output wire o_ts_lsb_rd,
    input  wire [31:0] i_ts_msb,
    output wire o_tx_ctrl_transmitter_en,
    output wire o_tx_ctrl_msg_sched_en,
    output wire o_tx_ctrl_builder_en,
    output wire o_tx_ctrl_sched_en,
    output wire [7:0] o_tx_word_label_val,
    output wire [1:0] o_tx_word_sdi,
    output wire [18:0] o_tx_word_data,
    output wire [1:0] o_tx_word_ssm,
    output wire o_tx_word_parity_type,
    output wire o_tx_send_cmd_send,
    output wire [31:0] o_tx_ext_data,
    output wire o_tx_ext_line_high,
    output wire o_tx_ext_line_low,
    output wire [31:0] o_tx_initial_delay,
    output wire [31:0] o_tx_inter_word_gap,
    output wire [31:0] o_tx_sched_count,
    output wire [1:0] o_tx_cfg_sel,
    output wire o_tx_cfg_apply,
    output wire [15:0] o_tx_cust_timing_pulse_dur,
    output wire [15:0] o_tx_cust_timing_null_dur,
    output wire [31:0] o_tx_cust_gap_dur,
    output wire o_tx_cust_slp,
    input  wire [15:0] i_tx_act_timing_pulse_dur,
    input  wire [15:0] i_tx_act_timing_null_dur,
    input  wire [31:0] i_tx_act_gap_dur,
    input  wire i_tx_act_slp,
    input  wire i_tx_status_busy,
    input  wire i_tx_status_sched_active,
    input  wire [1:0] i_tx_status_act_cfg,
    input  wire i_tx_status_sched_done,
    input  wire [31:0] i_tx_word_cnt,
    output wire o_tb_ctrl_enable,
    output wire o_tb_ctrl_freeze,
    output wire o_tb_ctrl_clear,
    input  wire i_tb_status_frozen,
    input  wire i_tb_status_word_wrap,
    input  wire i_tb_status_err_wrap,
    input  wire [1:0] i_tb_status_act_cfg,
    input  wire i_tb_status_line_high,
    input  wire i_tb_status_line_low,
    input  wire i_tb_status_sync_wait,
    output wire [1:0] o_tb_cfg_sel,
    output wire o_tb_cfg_apply,
    output wire [15:0] o_tb_cust_pulse_min,
    output wire [15:0] o_tb_cust_pulse_max,
    output wire [15:0] o_tb_cust_bit_min,
    output wire [15:0] o_tb_cust_bit_max,
    output wire [15:0] o_tb_cust_noise_pulse_err,
    output wire [15:0] o_tb_cust_noise_null_err,
    output wire [15:0] o_tb_cust_filter_glitch_size,
    output wire [15:0] o_tb_cust_filter_gap_err,
    output wire [1:0] o_tb_cust_parity,
    input  wire [15:0] i_tb_act_pulse_min,
    input  wire [15:0] i_tb_act_pulse_max,
    input  wire [15:0] i_tb_act_bit_min,
    input  wire [15:0] i_tb_act_bit_max,
    input  wire [15:0] i_tb_act_noise_pulse_err,
    input  wire [15:0] i_tb_act_noise_null_err,
    input  wire [15:0] i_tb_act_filter_glitch_size,
    input  wire [15:0] i_tb_act_filter_gap_err,
    input  wire [1:0] i_tb_act_parity,
    input  wire [31:0] i_tb_word_cnt,
    input  wire [31:0] i_tb_err_cnt,
    input  wire [31:0] i_tb_drop_cnt,
    input  wire [31:0] i_tb_last_word,
    output wire [7:0] o_tb_word_raddr,
    output wire o_tb_word_raddr_wr,
    input  wire [31:0] i_tb_word_rd_ts_msb,
    input  wire [31:0] i_tb_word_rd_ts_lsb,
    input  wire [31:0] i_tb_word_rd_data,
    input  wire [31:0] i_tb_word_rd_gap,
    input  wire [15:0] i_tb_word_rd_gap_err,
    output wire o_tb_word_rd_gap_err_rd,
    output wire [7:0] o_tb_err_raddr,
    output wire o_tb_err_raddr_wr,
    input  wire [31:0] i_tb_err_rd_ts_msb,
    input  wire [31:0] i_tb_err_rd_ts_lsb,
    input  wire [15:0] i_tb_err_rd_info_code,
    input  wire [15:0] i_tb_err_rd_info_addr,
    input  wire [31:0] i_tb_err_rd_data,
    output wire o_tb_err_rd_data_rd,
    output wire [4:0] o_tb_bit_raddr_bit_idx,
    output wire [2:0] o_tb_bit_raddr_word_idx,
    output wire o_tb_bit_raddr_wr,
    input  wire [15:0] i_tb_bit_rd_pulse_dur,
    input  wire [15:0] i_tb_bit_rd_pulse_err,
    input  wire [15:0] i_tb_bit_rd_null_dur,
    input  wire [15:0] i_tb_bit_rd_null_err,
    output wire o_tb_bit_rd_null_rd,
    output wire o_tb_chk_ctrl_enable,
    output wire o_tb_chk_ctrl_clear,
    output wire [31:0] o_tb_chk_timeout,
    input  wire [31:0] i_tb_chk_ok_cnt,
    input  wire [31:0] i_tb_chk_err_cnt,
    input  wire [3:0] i_tb_chk_status_fifo_level,
    input  wire i_tb_chk_status_fifo_ovf,
    output wire o_rx0_ctrl_enable,
    output wire o_rx0_ctrl_freeze,
    output wire o_rx0_ctrl_clear,
    input  wire i_rx0_status_frozen,
    input  wire i_rx0_status_word_wrap,
    input  wire i_rx0_status_err_wrap,
    input  wire [1:0] i_rx0_status_act_cfg,
    input  wire i_rx0_status_line_high,
    input  wire i_rx0_status_line_low,
    input  wire i_rx0_status_sync_wait,
    output wire [1:0] o_rx0_cfg_sel,
    output wire o_rx0_cfg_apply,
    output wire [15:0] o_rx0_cust_pulse_min,
    output wire [15:0] o_rx0_cust_pulse_max,
    output wire [15:0] o_rx0_cust_bit_min,
    output wire [15:0] o_rx0_cust_bit_max,
    output wire [15:0] o_rx0_cust_noise_pulse_err,
    output wire [15:0] o_rx0_cust_noise_null_err,
    output wire [15:0] o_rx0_cust_filter_glitch_size,
    output wire [15:0] o_rx0_cust_filter_gap_err,
    output wire [1:0] o_rx0_cust_parity,
    input  wire [15:0] i_rx0_act_pulse_min,
    input  wire [15:0] i_rx0_act_pulse_max,
    input  wire [15:0] i_rx0_act_bit_min,
    input  wire [15:0] i_rx0_act_bit_max,
    input  wire [15:0] i_rx0_act_noise_pulse_err,
    input  wire [15:0] i_rx0_act_noise_null_err,
    input  wire [15:0] i_rx0_act_filter_glitch_size,
    input  wire [15:0] i_rx0_act_filter_gap_err,
    input  wire [1:0] i_rx0_act_parity,
    input  wire [31:0] i_rx0_word_cnt,
    input  wire [31:0] i_rx0_err_cnt,
    input  wire [31:0] i_rx0_drop_cnt,
    input  wire [31:0] i_rx0_last_word,
    output wire [7:0] o_rx0_word_raddr,
    output wire o_rx0_word_raddr_wr,
    input  wire [31:0] i_rx0_word_rd_ts_msb,
    input  wire [31:0] i_rx0_word_rd_ts_lsb,
    input  wire [31:0] i_rx0_word_rd_data,
    input  wire [31:0] i_rx0_word_rd_gap,
    input  wire [15:0] i_rx0_word_rd_gap_err,
    output wire o_rx0_word_rd_gap_err_rd,
    output wire [7:0] o_rx0_err_raddr,
    output wire o_rx0_err_raddr_wr,
    input  wire [31:0] i_rx0_err_rd_ts_msb,
    input  wire [31:0] i_rx0_err_rd_ts_lsb,
    input  wire [15:0] i_rx0_err_rd_info_code,
    input  wire [15:0] i_rx0_err_rd_info_addr,
    input  wire [31:0] i_rx0_err_rd_data,
    output wire o_rx0_err_rd_data_rd,
    output wire [4:0] o_rx0_bit_raddr_bit_idx,
    output wire [2:0] o_rx0_bit_raddr_word_idx,
    output wire o_rx0_bit_raddr_wr,
    input  wire [15:0] i_rx0_bit_rd_pulse_dur,
    input  wire [15:0] i_rx0_bit_rd_pulse_err,
    input  wire [15:0] i_rx0_bit_rd_null_dur,
    input  wire [15:0] i_rx0_bit_rd_null_err,
    output wire o_rx0_bit_rd_null_rd,
    input  wire [110:0] SLAVE_AXI_REQ,
    output wire [40:0] SLAVE_AXI_RSP
);

    // SLAVE_AXI: packed <-> core S_AXI_*
    wire [31:0] s_awaddr;
    wire [2:0] s_awprot;
    wire s_awvalid;
    wire [31:0] s_wdata;
    wire [3:0] s_wstrb;
    wire s_wvalid;
    wire s_bready;
    wire [31:0] s_araddr;
    wire [2:0] s_arprot;
    wire s_arvalid;
    wire s_rready;
    wire s_awready;
    wire s_wready;
    wire [1:0] s_bresp;
    wire s_bvalid;
    wire s_arready;
    wire [31:0] s_rdata;
    wire [1:0] s_rresp;
    wire s_rvalid;
    assign {s_awaddr, s_awprot, s_awvalid, s_wdata, s_wstrb, s_wvalid, s_bready, s_araddr, s_arprot, s_arvalid, s_rready} = SLAVE_AXI_REQ;
    assign SLAVE_AXI_RSP = {s_awready, s_wready, s_bresp, s_bvalid, s_arready, s_rdata, s_rresp, s_rvalid};
    wire [31:0] S_AXI_AWADDR;
    assign S_AXI_AWADDR = s_awaddr;
    wire [2:0] S_AXI_AWPROT;
    assign S_AXI_AWPROT = s_awprot;
    wire S_AXI_AWVALID;
    assign S_AXI_AWVALID = s_awvalid;
    wire [31:0] S_AXI_WDATA;
    assign S_AXI_WDATA = s_wdata;
    wire [3:0] S_AXI_WSTRB;
    assign S_AXI_WSTRB = s_wstrb;
    wire S_AXI_WVALID;
    assign S_AXI_WVALID = s_wvalid;
    wire S_AXI_BREADY;
    assign S_AXI_BREADY = s_bready;
    wire [31:0] S_AXI_ARADDR;
    assign S_AXI_ARADDR = s_araddr;
    wire [2:0] S_AXI_ARPROT;
    assign S_AXI_ARPROT = s_arprot;
    wire S_AXI_ARVALID;
    assign S_AXI_ARVALID = s_arvalid;
    wire S_AXI_RREADY;
    assign S_AXI_RREADY = s_rready;
    wire S_AXI_AWREADY;
    assign s_awready = S_AXI_AWREADY;
    wire S_AXI_WREADY;
    assign s_wready = S_AXI_WREADY;
    wire [1:0] S_AXI_BRESP;
    assign s_bresp = S_AXI_BRESP;
    wire S_AXI_BVALID;
    assign s_bvalid = S_AXI_BVALID;
    wire S_AXI_ARREADY;
    assign s_arready = S_AXI_ARREADY;
    wire [31:0] S_AXI_RDATA;
    assign s_rdata = S_AXI_RDATA;
    wire [1:0] S_AXI_RRESP;
    assign s_rresp = S_AXI_RRESP;
    wire S_AXI_RVALID;
    assign s_rvalid = S_AXI_RVALID;

    arinc429_axil #(
        .C_AXI_ADDR_WIDTH(32),
        .C_AXI_DATA_WIDTH(32),
        .OPT_SKIDBUFFER(1'h0),
        .OPT_LOWPOWER(1'h0)
    ) u_core (
        .S_AXI_ACLK(S_AXI_ACLK),
        .S_AXI_ARESETN(S_AXI_ARESETN),
        .S_AXI_AWVALID(S_AXI_AWVALID),
        .S_AXI_AWREADY(S_AXI_AWREADY),
        .S_AXI_AWADDR(S_AXI_AWADDR),
        .S_AXI_AWPROT(S_AXI_AWPROT),
        .S_AXI_WVALID(S_AXI_WVALID),
        .S_AXI_WREADY(S_AXI_WREADY),
        .S_AXI_WDATA(S_AXI_WDATA),
        .S_AXI_WSTRB(S_AXI_WSTRB),
        .S_AXI_BVALID(S_AXI_BVALID),
        .S_AXI_BREADY(S_AXI_BREADY),
        .S_AXI_BRESP(S_AXI_BRESP),
        .S_AXI_ARVALID(S_AXI_ARVALID),
        .S_AXI_ARREADY(S_AXI_ARREADY),
        .S_AXI_ARADDR(S_AXI_ARADDR),
        .S_AXI_ARPROT(S_AXI_ARPROT),
        .S_AXI_RVALID(S_AXI_RVALID),
        .S_AXI_RREADY(S_AXI_RREADY),
        .S_AXI_RDATA(S_AXI_RDATA),
        .S_AXI_RRESP(S_AXI_RRESP),
        .o_soft_reset_rst_all(o_soft_reset_rst_all),
        .o_soft_reset_tx(o_soft_reset_tx),
        .o_soft_reset_txbit(o_soft_reset_txbit),
        .o_soft_reset_rx0(o_soft_reset_rx0),
        .o_global_freeze(o_global_freeze),
        .o_ts_ctrl_enable(o_ts_ctrl_enable),
        .o_ts_ctrl_clear(o_ts_ctrl_clear),
        .i_ts_lsb(i_ts_lsb),
        .o_ts_lsb_rd(o_ts_lsb_rd),
        .i_ts_msb(i_ts_msb),
        .o_tx_ctrl_transmitter_en(o_tx_ctrl_transmitter_en),
        .o_tx_ctrl_msg_sched_en(o_tx_ctrl_msg_sched_en),
        .o_tx_ctrl_builder_en(o_tx_ctrl_builder_en),
        .o_tx_ctrl_sched_en(o_tx_ctrl_sched_en),
        .o_tx_word_label_val(o_tx_word_label_val),
        .o_tx_word_sdi(o_tx_word_sdi),
        .o_tx_word_data(o_tx_word_data),
        .o_tx_word_ssm(o_tx_word_ssm),
        .o_tx_word_parity_type(o_tx_word_parity_type),
        .o_tx_send_cmd_send(o_tx_send_cmd_send),
        .o_tx_ext_data(o_tx_ext_data),
        .o_tx_ext_line_high(o_tx_ext_line_high),
        .o_tx_ext_line_low(o_tx_ext_line_low),
        .o_tx_initial_delay(o_tx_initial_delay),
        .o_tx_inter_word_gap(o_tx_inter_word_gap),
        .o_tx_sched_count(o_tx_sched_count),
        .o_tx_cfg_sel(o_tx_cfg_sel),
        .o_tx_cfg_apply(o_tx_cfg_apply),
        .o_tx_cust_timing_pulse_dur(o_tx_cust_timing_pulse_dur),
        .o_tx_cust_timing_null_dur(o_tx_cust_timing_null_dur),
        .o_tx_cust_gap_dur(o_tx_cust_gap_dur),
        .o_tx_cust_slp(o_tx_cust_slp),
        .i_tx_act_timing_pulse_dur(i_tx_act_timing_pulse_dur),
        .i_tx_act_timing_null_dur(i_tx_act_timing_null_dur),
        .i_tx_act_gap_dur(i_tx_act_gap_dur),
        .i_tx_act_slp(i_tx_act_slp),
        .i_tx_status_busy(i_tx_status_busy),
        .i_tx_status_sched_active(i_tx_status_sched_active),
        .i_tx_status_act_cfg(i_tx_status_act_cfg),
        .i_tx_status_sched_done(i_tx_status_sched_done),
        .i_tx_word_cnt(i_tx_word_cnt),
        .o_tb_ctrl_enable(o_tb_ctrl_enable),
        .o_tb_ctrl_freeze(o_tb_ctrl_freeze),
        .o_tb_ctrl_clear(o_tb_ctrl_clear),
        .i_tb_status_frozen(i_tb_status_frozen),
        .i_tb_status_word_wrap(i_tb_status_word_wrap),
        .i_tb_status_err_wrap(i_tb_status_err_wrap),
        .i_tb_status_act_cfg(i_tb_status_act_cfg),
        .i_tb_status_line_high(i_tb_status_line_high),
        .i_tb_status_line_low(i_tb_status_line_low),
        .i_tb_status_sync_wait(i_tb_status_sync_wait),
        .o_tb_cfg_sel(o_tb_cfg_sel),
        .o_tb_cfg_apply(o_tb_cfg_apply),
        .o_tb_cust_pulse_min(o_tb_cust_pulse_min),
        .o_tb_cust_pulse_max(o_tb_cust_pulse_max),
        .o_tb_cust_bit_min(o_tb_cust_bit_min),
        .o_tb_cust_bit_max(o_tb_cust_bit_max),
        .o_tb_cust_noise_pulse_err(o_tb_cust_noise_pulse_err),
        .o_tb_cust_noise_null_err(o_tb_cust_noise_null_err),
        .o_tb_cust_filter_glitch_size(o_tb_cust_filter_glitch_size),
        .o_tb_cust_filter_gap_err(o_tb_cust_filter_gap_err),
        .o_tb_cust_parity(o_tb_cust_parity),
        .i_tb_act_pulse_min(i_tb_act_pulse_min),
        .i_tb_act_pulse_max(i_tb_act_pulse_max),
        .i_tb_act_bit_min(i_tb_act_bit_min),
        .i_tb_act_bit_max(i_tb_act_bit_max),
        .i_tb_act_noise_pulse_err(i_tb_act_noise_pulse_err),
        .i_tb_act_noise_null_err(i_tb_act_noise_null_err),
        .i_tb_act_filter_glitch_size(i_tb_act_filter_glitch_size),
        .i_tb_act_filter_gap_err(i_tb_act_filter_gap_err),
        .i_tb_act_parity(i_tb_act_parity),
        .i_tb_word_cnt(i_tb_word_cnt),
        .i_tb_err_cnt(i_tb_err_cnt),
        .i_tb_drop_cnt(i_tb_drop_cnt),
        .i_tb_last_word(i_tb_last_word),
        .o_tb_word_raddr(o_tb_word_raddr),
        .o_tb_word_raddr_wr(o_tb_word_raddr_wr),
        .i_tb_word_rd_ts_msb(i_tb_word_rd_ts_msb),
        .i_tb_word_rd_ts_lsb(i_tb_word_rd_ts_lsb),
        .i_tb_word_rd_data(i_tb_word_rd_data),
        .i_tb_word_rd_gap(i_tb_word_rd_gap),
        .i_tb_word_rd_gap_err(i_tb_word_rd_gap_err),
        .o_tb_word_rd_gap_err_rd(o_tb_word_rd_gap_err_rd),
        .o_tb_err_raddr(o_tb_err_raddr),
        .o_tb_err_raddr_wr(o_tb_err_raddr_wr),
        .i_tb_err_rd_ts_msb(i_tb_err_rd_ts_msb),
        .i_tb_err_rd_ts_lsb(i_tb_err_rd_ts_lsb),
        .i_tb_err_rd_info_code(i_tb_err_rd_info_code),
        .i_tb_err_rd_info_addr(i_tb_err_rd_info_addr),
        .i_tb_err_rd_data(i_tb_err_rd_data),
        .o_tb_err_rd_data_rd(o_tb_err_rd_data_rd),
        .o_tb_bit_raddr_bit_idx(o_tb_bit_raddr_bit_idx),
        .o_tb_bit_raddr_word_idx(o_tb_bit_raddr_word_idx),
        .o_tb_bit_raddr_wr(o_tb_bit_raddr_wr),
        .i_tb_bit_rd_pulse_dur(i_tb_bit_rd_pulse_dur),
        .i_tb_bit_rd_pulse_err(i_tb_bit_rd_pulse_err),
        .i_tb_bit_rd_null_dur(i_tb_bit_rd_null_dur),
        .i_tb_bit_rd_null_err(i_tb_bit_rd_null_err),
        .o_tb_bit_rd_null_rd(o_tb_bit_rd_null_rd),
        .o_tb_chk_ctrl_enable(o_tb_chk_ctrl_enable),
        .o_tb_chk_ctrl_clear(o_tb_chk_ctrl_clear),
        .o_tb_chk_timeout(o_tb_chk_timeout),
        .i_tb_chk_ok_cnt(i_tb_chk_ok_cnt),
        .i_tb_chk_err_cnt(i_tb_chk_err_cnt),
        .i_tb_chk_status_fifo_level(i_tb_chk_status_fifo_level),
        .i_tb_chk_status_fifo_ovf(i_tb_chk_status_fifo_ovf),
        .o_rx0_ctrl_enable(o_rx0_ctrl_enable),
        .o_rx0_ctrl_freeze(o_rx0_ctrl_freeze),
        .o_rx0_ctrl_clear(o_rx0_ctrl_clear),
        .i_rx0_status_frozen(i_rx0_status_frozen),
        .i_rx0_status_word_wrap(i_rx0_status_word_wrap),
        .i_rx0_status_err_wrap(i_rx0_status_err_wrap),
        .i_rx0_status_act_cfg(i_rx0_status_act_cfg),
        .i_rx0_status_line_high(i_rx0_status_line_high),
        .i_rx0_status_line_low(i_rx0_status_line_low),
        .i_rx0_status_sync_wait(i_rx0_status_sync_wait),
        .o_rx0_cfg_sel(o_rx0_cfg_sel),
        .o_rx0_cfg_apply(o_rx0_cfg_apply),
        .o_rx0_cust_pulse_min(o_rx0_cust_pulse_min),
        .o_rx0_cust_pulse_max(o_rx0_cust_pulse_max),
        .o_rx0_cust_bit_min(o_rx0_cust_bit_min),
        .o_rx0_cust_bit_max(o_rx0_cust_bit_max),
        .o_rx0_cust_noise_pulse_err(o_rx0_cust_noise_pulse_err),
        .o_rx0_cust_noise_null_err(o_rx0_cust_noise_null_err),
        .o_rx0_cust_filter_glitch_size(o_rx0_cust_filter_glitch_size),
        .o_rx0_cust_filter_gap_err(o_rx0_cust_filter_gap_err),
        .o_rx0_cust_parity(o_rx0_cust_parity),
        .i_rx0_act_pulse_min(i_rx0_act_pulse_min),
        .i_rx0_act_pulse_max(i_rx0_act_pulse_max),
        .i_rx0_act_bit_min(i_rx0_act_bit_min),
        .i_rx0_act_bit_max(i_rx0_act_bit_max),
        .i_rx0_act_noise_pulse_err(i_rx0_act_noise_pulse_err),
        .i_rx0_act_noise_null_err(i_rx0_act_noise_null_err),
        .i_rx0_act_filter_glitch_size(i_rx0_act_filter_glitch_size),
        .i_rx0_act_filter_gap_err(i_rx0_act_filter_gap_err),
        .i_rx0_act_parity(i_rx0_act_parity),
        .i_rx0_word_cnt(i_rx0_word_cnt),
        .i_rx0_err_cnt(i_rx0_err_cnt),
        .i_rx0_drop_cnt(i_rx0_drop_cnt),
        .i_rx0_last_word(i_rx0_last_word),
        .o_rx0_word_raddr(o_rx0_word_raddr),
        .o_rx0_word_raddr_wr(o_rx0_word_raddr_wr),
        .i_rx0_word_rd_ts_msb(i_rx0_word_rd_ts_msb),
        .i_rx0_word_rd_ts_lsb(i_rx0_word_rd_ts_lsb),
        .i_rx0_word_rd_data(i_rx0_word_rd_data),
        .i_rx0_word_rd_gap(i_rx0_word_rd_gap),
        .i_rx0_word_rd_gap_err(i_rx0_word_rd_gap_err),
        .o_rx0_word_rd_gap_err_rd(o_rx0_word_rd_gap_err_rd),
        .o_rx0_err_raddr(o_rx0_err_raddr),
        .o_rx0_err_raddr_wr(o_rx0_err_raddr_wr),
        .i_rx0_err_rd_ts_msb(i_rx0_err_rd_ts_msb),
        .i_rx0_err_rd_ts_lsb(i_rx0_err_rd_ts_lsb),
        .i_rx0_err_rd_info_code(i_rx0_err_rd_info_code),
        .i_rx0_err_rd_info_addr(i_rx0_err_rd_info_addr),
        .i_rx0_err_rd_data(i_rx0_err_rd_data),
        .o_rx0_err_rd_data_rd(o_rx0_err_rd_data_rd),
        .o_rx0_bit_raddr_bit_idx(o_rx0_bit_raddr_bit_idx),
        .o_rx0_bit_raddr_word_idx(o_rx0_bit_raddr_word_idx),
        .o_rx0_bit_raddr_wr(o_rx0_bit_raddr_wr),
        .i_rx0_bit_rd_pulse_dur(i_rx0_bit_rd_pulse_dur),
        .i_rx0_bit_rd_pulse_err(i_rx0_bit_rd_pulse_err),
        .i_rx0_bit_rd_null_dur(i_rx0_bit_rd_null_dur),
        .i_rx0_bit_rd_null_err(i_rx0_bit_rd_null_err),
        .o_rx0_bit_rd_null_rd(o_rx0_bit_rd_null_rd)
    );

endmodule

`default_nettype wire
