--------------------------------------------------------------------------------
-- Dosya       : arinc429_ip.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   AXIL Studio'nun ürettiği arinc429_axil.v (AXI4-Lite slave, ZipCPU easyaxil)
--   ile saf VHDL arinc429_core çekirdeğini tek üst modülde birleştirir.
--
-- Gereksinimler:
--   REQ-1 : Dış bus arayüzü standart 32-bit AXI4-Lite Slave (S_AXI_*) olup
--           tek saat domain'inde (S_AXI_ACLK, S_AXI_ARESETN) çalışır.
--   REQ-2 : Tüm o_* / i_* register portları ve RAM wr_strobe / rd_strobe
--           sinyalleri arinc429_core record portlarına 1-1 bağlanır.
--   REQ-3 : Bu dosya vhdl/scripts/gen_axil_spec.py ile otomatik üretilir;
--           farklı RX kanal sayılarında tek komutla yenilenebilir.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;

entity arinc429_ip is
    generic (
        C_AXI_ADDR_WIDTH     : positive := 32;
        G_SYNC_STAGES        : positive := 4;
        G_CHK_FIFO_DEPTH     : positive := 4
    );
    port (
        -- AXI4-Lite Slave (AXIL Studio / easyaxil)
        S_AXI_ACLK    : in  std_logic;
        S_AXI_ARESETN : in  std_logic;
        S_AXI_AWVALID : in  std_logic;
        S_AXI_AWREADY : out std_logic;
        S_AXI_AWADDR  : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);
        S_AXI_AWPROT  : in  std_logic_vector(2 downto 0);
        S_AXI_WVALID  : in  std_logic;
        S_AXI_WREADY  : out std_logic;
        S_AXI_WDATA   : in  std_logic_vector(31 downto 0);
        S_AXI_WSTRB   : in  std_logic_vector(3 downto 0);
        S_AXI_BVALID  : out std_logic;
        S_AXI_BREADY  : in  std_logic;
        S_AXI_BRESP   : out std_logic_vector(1 downto 0);
        S_AXI_ARVALID : in  std_logic;
        S_AXI_ARREADY : out std_logic;
        S_AXI_ARADDR  : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);
        S_AXI_ARPROT  : in  std_logic_vector(2 downto 0);
        S_AXI_RVALID  : out std_logic;
        S_AXI_RREADY  : in  std_logic;
        S_AXI_RDATA   : out std_logic_vector(31 downto 0);
        S_AXI_RRESP   : out std_logic_vector(1 downto 0);

        -- Fiziksel ARINC 429 pinleri
        tx_high       : out std_logic;
        tx_low        : out std_logic;
        tx_slp        : out std_logic;
        txbit_rx_high : in  std_logic := '0';
        txbit_rx_low  : in  std_logic := '0';
        rx_high       : in  std_logic_vector(1 downto 0) := (others => '0');
        rx_low        : in  std_logic_vector(1 downto 0) := (others => '0')
    );
end entity arinc429_ip;

architecture rtl of arinc429_ip is

    component arinc429_axil is
        generic (
            C_AXI_ADDR_WIDTH : integer := 32
        );
        port (
            S_AXI_ACLK                     : in  std_logic;
            S_AXI_ARESETN                  : in  std_logic;
            S_AXI_AWVALID                  : in  std_logic;
            S_AXI_AWREADY                  : out std_logic;
            S_AXI_AWADDR                   : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);
            S_AXI_AWPROT                   : in  std_logic_vector(2 downto 0);
            S_AXI_WVALID                   : in  std_logic;
            S_AXI_WREADY                   : out std_logic;
            S_AXI_WDATA                    : in  std_logic_vector(31 downto 0);
            S_AXI_WSTRB                    : in  std_logic_vector(3 downto 0);
            S_AXI_BVALID                   : out std_logic;
            S_AXI_BREADY                   : in  std_logic;
            S_AXI_BRESP                    : out std_logic_vector(1 downto 0);
            S_AXI_ARVALID                  : in  std_logic;
            S_AXI_ARREADY                  : out std_logic;
            S_AXI_ARADDR                   : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);
            S_AXI_ARPROT                   : in  std_logic_vector(2 downto 0);
            S_AXI_RVALID                   : out std_logic;
            S_AXI_RREADY                   : in  std_logic;
            S_AXI_RDATA                    : out std_logic_vector(31 downto 0);
            S_AXI_RRESP                    : out std_logic_vector(1 downto 0);
            o_soft_reset_rst_all           : out std_logic;
            o_soft_reset_tx                : out std_logic;
            o_soft_reset_txbit             : out std_logic;
            o_soft_reset_rx0               : out std_logic;
            o_soft_reset_rx1               : out std_logic;
            o_global_freeze                : out std_logic;
            o_ts_ctrl_enable               : out std_logic;
            o_ts_ctrl_clear                : out std_logic;
            i_ts_lsb                       : in  std_logic_vector(31 downto 0);
            o_ts_lsb_rd                    : out std_logic;
            i_ts_msb                       : in  std_logic_vector(31 downto 0);
            o_tx_transmitter_en            : out std_logic;
            o_tx_msg_sched_en              : out std_logic;
            o_tx_builder_en                : out std_logic;
            o_tx_label                     : out std_logic_vector(7 downto 0);
            o_tx_sdi                       : out std_logic_vector(1 downto 0);
            o_tx_data                      : out std_logic_vector(18 downto 0);
            o_tx_ssm                       : out std_logic_vector(1 downto 0);
            o_tx_parity_type               : out std_logic;
            o_tx_sched_en                  : out std_logic;
            o_tx_initial_delay             : out std_logic_vector(31 downto 0);
            o_tx_inter_word_gap            : out std_logic_vector(31 downto 0);
            o_tx_send_cmd_send             : out std_logic;
            o_tx_ext_data                  : out std_logic_vector(31 downto 0);
            o_tx_ext_high                  : out std_logic;
            o_tx_ext_low                   : out std_logic;
            o_tx_cfg_sel                   : out std_logic_vector(1 downto 0);
            o_tx_cfg_apply_apply           : out std_logic;
            o_tx_cust_pulse_dur            : out std_logic_vector(15 downto 0);
            o_tx_cust_null_dur             : out std_logic_vector(15 downto 0);
            o_tx_cust_gap_dur              : out std_logic_vector(31 downto 0);
            o_tx_cust_slp                  : out std_logic;
            i_tx_act_pulse_dur             : in  std_logic_vector(15 downto 0);
            i_tx_act_null_dur              : in  std_logic_vector(15 downto 0);
            i_tx_act_gap_dur               : in  std_logic_vector(31 downto 0);
            i_tx_act_slp                   : in  std_logic;
            i_tx_status_busy               : in  std_logic;
            i_tx_status_sched_active       : in  std_logic;
            i_tx_status_act_cfg            : in  std_logic_vector(1 downto 0);
            i_tx_word_cnt                  : in  std_logic_vector(31 downto 0);
            o_tb_ctrl_enable               : out std_logic;
            o_tb_ctrl_freeze               : out std_logic;
            o_tb_ctrl_clear                : out std_logic;
            i_tb_status_frozen             : in  std_logic;
            i_tb_status_word_wrap          : in  std_logic;
            i_tb_status_err_wrap           : in  std_logic;
            i_tb_status_act_cfg            : in  std_logic_vector(1 downto 0);
            o_tb_cfg_sel                   : out std_logic_vector(1 downto 0);
            o_tb_cfg_apply_apply           : out std_logic;
            o_tb_cust_glitch_filter_size   : out std_logic_vector(15 downto 0);
            o_tb_cust_min_pulse            : out std_logic_vector(15 downto 0);
            o_tb_cust_max_pulse            : out std_logic_vector(15 downto 0);
            o_tb_cust_min_bit              : out std_logic_vector(15 downto 0);
            o_tb_cust_max_bit              : out std_logic_vector(15 downto 0);
            o_tb_cust_max_pulse_err        : out std_logic_vector(15 downto 0);
            o_tb_cust_max_null_err         : out std_logic_vector(15 downto 0);
            o_tb_cust_max_gap_err          : out std_logic_vector(15 downto 0);
            o_tb_cust_parity_mode          : out std_logic_vector(1 downto 0);
            i_tb_act_glitch_filter_size    : in  std_logic_vector(15 downto 0);
            i_tb_act_min_pulse             : in  std_logic_vector(15 downto 0);
            i_tb_act_max_pulse             : in  std_logic_vector(15 downto 0);
            i_tb_act_min_bit               : in  std_logic_vector(15 downto 0);
            i_tb_act_max_bit               : in  std_logic_vector(15 downto 0);
            i_tb_act_max_pulse_err         : in  std_logic_vector(15 downto 0);
            i_tb_act_max_null_err          : in  std_logic_vector(15 downto 0);
            i_tb_act_max_gap_err           : in  std_logic_vector(15 downto 0);
            i_tb_act_parity_mode           : in  std_logic_vector(1 downto 0);
            i_tb_word_cnt                  : in  std_logic_vector(31 downto 0);
            i_tb_err_cnt                   : in  std_logic_vector(31 downto 0);
            i_tb_drop_cnt                  : in  std_logic_vector(31 downto 0);
            i_tb_last_word                 : in  std_logic_vector(31 downto 0);
            o_tb_word_raddr                : out std_logic_vector(7 downto 0);
            o_tb_word_raddr_wr             : out std_logic;
            i_tb_word_rd_ts_msb            : in  std_logic_vector(31 downto 0);
            i_tb_word_rd_ts_lsb            : in  std_logic_vector(31 downto 0);
            i_tb_word_rd_data              : in  std_logic_vector(31 downto 0);
            i_tb_word_rd_gap               : in  std_logic_vector(31 downto 0);
            i_tb_word_rd_gap_err           : in  std_logic_vector(15 downto 0);
            o_tb_word_rd_gap_err_rd        : out std_logic;
            o_tb_err_raddr                 : out std_logic_vector(7 downto 0);
            o_tb_err_raddr_wr              : out std_logic;
            i_tb_err_rd_ts_msb             : in  std_logic_vector(31 downto 0);
            i_tb_err_rd_ts_lsb             : in  std_logic_vector(31 downto 0);
            i_tb_err_rd_code               : in  std_logic_vector(15 downto 0);
            i_tb_err_rd_addr               : in  std_logic_vector(15 downto 0);
            i_tb_err_rd_data               : in  std_logic_vector(31 downto 0);
            o_tb_err_rd_data_rd            : out std_logic;
            o_tb_bit_raddr_bit_idx         : out std_logic_vector(4 downto 0);
            o_tb_bit_raddr_word_idx        : out std_logic_vector(2 downto 0);
            o_tb_bit_raddr_wr              : out std_logic;
            i_tb_bit_rd_pulse              : in  std_logic_vector(15 downto 0);
            i_tb_bit_rd_pulse_err          : in  std_logic_vector(15 downto 0);
            i_tb_bit_rd_null               : in  std_logic_vector(15 downto 0);
            i_tb_bit_rd_null_err           : in  std_logic_vector(15 downto 0);
            o_tb_bit_rd_null_err_rd        : out std_logic;
            o_tb_chk_ctrl_enable           : out std_logic;
            o_tb_chk_ctrl_clear            : out std_logic;
            o_tb_chk_timeout               : out std_logic_vector(31 downto 0);
            i_tb_chk_ok_cnt                : in  std_logic_vector(31 downto 0);
            i_tb_chk_err_cnt               : in  std_logic_vector(31 downto 0);
            i_tb_chk_status_fifo_level     : in  std_logic_vector(3 downto 0);
            i_tb_chk_status_fifo_ovf       : in  std_logic;
            o_rx0_ctrl_enable              : out std_logic;
            o_rx0_ctrl_freeze              : out std_logic;
            o_rx0_ctrl_clear               : out std_logic;
            i_rx0_status_frozen            : in  std_logic;
            i_rx0_status_word_wrap         : in  std_logic;
            i_rx0_status_err_wrap          : in  std_logic;
            i_rx0_status_act_cfg           : in  std_logic_vector(1 downto 0);
            o_rx0_cfg_sel                  : out std_logic_vector(1 downto 0);
            o_rx0_cfg_apply_apply          : out std_logic;
            o_rx0_cust_glitch_filter_size  : out std_logic_vector(15 downto 0);
            o_rx0_cust_min_pulse           : out std_logic_vector(15 downto 0);
            o_rx0_cust_max_pulse           : out std_logic_vector(15 downto 0);
            o_rx0_cust_min_bit             : out std_logic_vector(15 downto 0);
            o_rx0_cust_max_bit             : out std_logic_vector(15 downto 0);
            o_rx0_cust_max_pulse_err       : out std_logic_vector(15 downto 0);
            o_rx0_cust_max_null_err        : out std_logic_vector(15 downto 0);
            o_rx0_cust_max_gap_err         : out std_logic_vector(15 downto 0);
            o_rx0_cust_parity_mode         : out std_logic_vector(1 downto 0);
            i_rx0_act_glitch_filter_size   : in  std_logic_vector(15 downto 0);
            i_rx0_act_min_pulse            : in  std_logic_vector(15 downto 0);
            i_rx0_act_max_pulse            : in  std_logic_vector(15 downto 0);
            i_rx0_act_min_bit              : in  std_logic_vector(15 downto 0);
            i_rx0_act_max_bit              : in  std_logic_vector(15 downto 0);
            i_rx0_act_max_pulse_err        : in  std_logic_vector(15 downto 0);
            i_rx0_act_max_null_err         : in  std_logic_vector(15 downto 0);
            i_rx0_act_max_gap_err          : in  std_logic_vector(15 downto 0);
            i_rx0_act_parity_mode          : in  std_logic_vector(1 downto 0);
            i_rx0_word_cnt                 : in  std_logic_vector(31 downto 0);
            i_rx0_err_cnt                  : in  std_logic_vector(31 downto 0);
            i_rx0_drop_cnt                 : in  std_logic_vector(31 downto 0);
            i_rx0_last_word                : in  std_logic_vector(31 downto 0);
            o_rx0_word_raddr               : out std_logic_vector(7 downto 0);
            o_rx0_word_raddr_wr            : out std_logic;
            i_rx0_word_rd_ts_msb           : in  std_logic_vector(31 downto 0);
            i_rx0_word_rd_ts_lsb           : in  std_logic_vector(31 downto 0);
            i_rx0_word_rd_data             : in  std_logic_vector(31 downto 0);
            i_rx0_word_rd_gap              : in  std_logic_vector(31 downto 0);
            i_rx0_word_rd_gap_err          : in  std_logic_vector(15 downto 0);
            o_rx0_word_rd_gap_err_rd       : out std_logic;
            o_rx0_err_raddr                : out std_logic_vector(7 downto 0);
            o_rx0_err_raddr_wr             : out std_logic;
            i_rx0_err_rd_ts_msb            : in  std_logic_vector(31 downto 0);
            i_rx0_err_rd_ts_lsb            : in  std_logic_vector(31 downto 0);
            i_rx0_err_rd_code              : in  std_logic_vector(15 downto 0);
            i_rx0_err_rd_addr              : in  std_logic_vector(15 downto 0);
            i_rx0_err_rd_data              : in  std_logic_vector(31 downto 0);
            o_rx0_err_rd_data_rd           : out std_logic;
            o_rx0_bit_raddr_bit_idx        : out std_logic_vector(4 downto 0);
            o_rx0_bit_raddr_word_idx       : out std_logic_vector(2 downto 0);
            o_rx0_bit_raddr_wr             : out std_logic;
            i_rx0_bit_rd_pulse             : in  std_logic_vector(15 downto 0);
            i_rx0_bit_rd_pulse_err         : in  std_logic_vector(15 downto 0);
            i_rx0_bit_rd_null              : in  std_logic_vector(15 downto 0);
            i_rx0_bit_rd_null_err          : in  std_logic_vector(15 downto 0);
            o_rx0_bit_rd_null_err_rd       : out std_logic;
            o_rx1_ctrl_enable              : out std_logic;
            o_rx1_ctrl_freeze              : out std_logic;
            o_rx1_ctrl_clear               : out std_logic;
            i_rx1_status_frozen            : in  std_logic;
            i_rx1_status_word_wrap         : in  std_logic;
            i_rx1_status_err_wrap          : in  std_logic;
            i_rx1_status_act_cfg           : in  std_logic_vector(1 downto 0);
            o_rx1_cfg_sel                  : out std_logic_vector(1 downto 0);
            o_rx1_cfg_apply_apply          : out std_logic;
            o_rx1_cust_glitch_filter_size  : out std_logic_vector(15 downto 0);
            o_rx1_cust_min_pulse           : out std_logic_vector(15 downto 0);
            o_rx1_cust_max_pulse           : out std_logic_vector(15 downto 0);
            o_rx1_cust_min_bit             : out std_logic_vector(15 downto 0);
            o_rx1_cust_max_bit             : out std_logic_vector(15 downto 0);
            o_rx1_cust_max_pulse_err       : out std_logic_vector(15 downto 0);
            o_rx1_cust_max_null_err        : out std_logic_vector(15 downto 0);
            o_rx1_cust_max_gap_err         : out std_logic_vector(15 downto 0);
            o_rx1_cust_parity_mode         : out std_logic_vector(1 downto 0);
            i_rx1_act_glitch_filter_size   : in  std_logic_vector(15 downto 0);
            i_rx1_act_min_pulse            : in  std_logic_vector(15 downto 0);
            i_rx1_act_max_pulse            : in  std_logic_vector(15 downto 0);
            i_rx1_act_min_bit              : in  std_logic_vector(15 downto 0);
            i_rx1_act_max_bit              : in  std_logic_vector(15 downto 0);
            i_rx1_act_max_pulse_err        : in  std_logic_vector(15 downto 0);
            i_rx1_act_max_null_err         : in  std_logic_vector(15 downto 0);
            i_rx1_act_max_gap_err          : in  std_logic_vector(15 downto 0);
            i_rx1_act_parity_mode          : in  std_logic_vector(1 downto 0);
            i_rx1_word_cnt                 : in  std_logic_vector(31 downto 0);
            i_rx1_err_cnt                  : in  std_logic_vector(31 downto 0);
            i_rx1_drop_cnt                 : in  std_logic_vector(31 downto 0);
            i_rx1_last_word                : in  std_logic_vector(31 downto 0);
            o_rx1_word_raddr               : out std_logic_vector(7 downto 0);
            o_rx1_word_raddr_wr            : out std_logic;
            i_rx1_word_rd_ts_msb           : in  std_logic_vector(31 downto 0);
            i_rx1_word_rd_ts_lsb           : in  std_logic_vector(31 downto 0);
            i_rx1_word_rd_data             : in  std_logic_vector(31 downto 0);
            i_rx1_word_rd_gap              : in  std_logic_vector(31 downto 0);
            i_rx1_word_rd_gap_err          : in  std_logic_vector(15 downto 0);
            o_rx1_word_rd_gap_err_rd       : out std_logic;
            o_rx1_err_raddr                : out std_logic_vector(7 downto 0);
            o_rx1_err_raddr_wr             : out std_logic;
            i_rx1_err_rd_ts_msb            : in  std_logic_vector(31 downto 0);
            i_rx1_err_rd_ts_lsb            : in  std_logic_vector(31 downto 0);
            i_rx1_err_rd_code              : in  std_logic_vector(15 downto 0);
            i_rx1_err_rd_addr              : in  std_logic_vector(15 downto 0);
            i_rx1_err_rd_data              : in  std_logic_vector(31 downto 0);
            o_rx1_err_rd_data_rd           : out std_logic;
            o_rx1_bit_raddr_bit_idx        : out std_logic_vector(4 downto 0);
            o_rx1_bit_raddr_word_idx       : out std_logic_vector(2 downto 0);
            o_rx1_bit_raddr_wr             : out std_logic;
            i_rx1_bit_rd_pulse             : in  std_logic_vector(15 downto 0);
            i_rx1_bit_rd_pulse_err         : in  std_logic_vector(15 downto 0);
            i_rx1_bit_rd_null              : in  std_logic_vector(15 downto 0);
            i_rx1_bit_rd_null_err          : in  std_logic_vector(15 downto 0);
            o_rx1_bit_rd_null_err_rd       : out std_logic
        );
    end component;

    signal rst_all       : std_logic;
    signal rst_tx        : std_logic;
    signal rst_txbit     : std_logic;
    signal rst_rx        : std_logic_vector(1 downto 0) := (others => '0');
    signal global_freeze : std_logic;
    signal ts_en         : std_logic;
    signal ts_clr        : std_logic;
    signal ts_lsb_rd     : std_logic;
    signal ts_lsb        : std_logic_vector(31 downto 0);
    signal ts_msb        : std_logic_vector(31 downto 0);

    signal tx_reg_in     : t_tx_reg_in  := C_TX_REG_IN_ZERO;
    signal tx_reg_out    : t_tx_reg_out;
    signal tb_reg_in     : t_rx_reg_in  := C_RX_REG_IN_ZERO;
    signal tb_reg_out    : t_rx_reg_out;
    signal rx_reg_in     : t_rx_reg_in_arr(0 to 1) := (others => C_RX_REG_IN_ZERO);
    signal rx_reg_out    : t_rx_reg_out_arr(0 to 1);
    signal s_tb_word_raddr : std_logic_vector(7 downto 0);
    signal s_tb_err_raddr  : std_logic_vector(7 downto 0);
    signal s_tb_bit_widx   : std_logic_vector(2 downto 0);
    signal s_rx0_word_raddr : std_logic_vector(7 downto 0);
    signal s_rx0_err_raddr  : std_logic_vector(7 downto 0);
    signal s_rx0_bit_widx   : std_logic_vector(2 downto 0);
    signal s_rx1_word_raddr : std_logic_vector(7 downto 0);
    signal s_rx1_err_raddr  : std_logic_vector(7 downto 0);
    signal s_rx1_bit_widx   : std_logic_vector(2 downto 0);

begin

    tb_reg_in.word_raddr <= (15 downto 8 => '0') & s_tb_word_raddr;
    tb_reg_in.err_raddr  <= (15 downto 8 => '0') & s_tb_err_raddr;
    tb_reg_in.bit_raddr_word <= (7 downto 3 => '0') & s_tb_bit_widx;
    rx_reg_in(0).word_raddr <= (15 downto 8 => '0') & s_rx0_word_raddr;
    rx_reg_in(0).err_raddr  <= (15 downto 8 => '0') & s_rx0_err_raddr;
    rx_reg_in(0).bit_raddr_word <= (7 downto 3 => '0') & s_rx0_bit_widx;
    rx_reg_in(1).word_raddr <= (15 downto 8 => '0') & s_rx1_word_raddr;
    rx_reg_in(1).err_raddr  <= (15 downto 8 => '0') & s_rx1_err_raddr;
    rx_reg_in(1).bit_raddr_word <= (7 downto 3 => '0') & s_rx1_bit_widx;

    u_axil : arinc429_axil
        generic map (C_AXI_ADDR_WIDTH => C_AXI_ADDR_WIDTH)
        port map (
            S_AXI_ACLK                     => S_AXI_ACLK,
            S_AXI_ARESETN                  => S_AXI_ARESETN,
            S_AXI_AWVALID                  => S_AXI_AWVALID,
            S_AXI_AWREADY                  => S_AXI_AWREADY,
            S_AXI_AWADDR                   => S_AXI_AWADDR,
            S_AXI_AWPROT                   => S_AXI_AWPROT,
            S_AXI_WVALID                   => S_AXI_WVALID,
            S_AXI_WREADY                   => S_AXI_WREADY,
            S_AXI_WDATA                    => S_AXI_WDATA,
            S_AXI_WSTRB                    => S_AXI_WSTRB,
            S_AXI_BVALID                   => S_AXI_BVALID,
            S_AXI_BREADY                   => S_AXI_BREADY,
            S_AXI_BRESP                    => S_AXI_BRESP,
            S_AXI_ARVALID                  => S_AXI_ARVALID,
            S_AXI_ARREADY                  => S_AXI_ARREADY,
            S_AXI_ARADDR                   => S_AXI_ARADDR,
            S_AXI_ARPROT                   => S_AXI_ARPROT,
            S_AXI_RVALID                   => S_AXI_RVALID,
            S_AXI_RREADY                   => S_AXI_RREADY,
            S_AXI_RDATA                    => S_AXI_RDATA,
            S_AXI_RRESP                    => S_AXI_RRESP,
            o_soft_reset_rst_all           => rst_all,
            o_soft_reset_tx                => rst_tx,
            o_soft_reset_txbit             => rst_txbit,
            o_soft_reset_rx0               => rst_rx(0),
            o_soft_reset_rx1               => rst_rx(1),
            o_global_freeze                => global_freeze,
            o_ts_ctrl_enable               => ts_en,
            o_ts_ctrl_clear                => ts_clr,
            i_ts_lsb                       => ts_lsb,
            o_ts_lsb_rd                    => ts_lsb_rd,
            i_ts_msb                       => ts_msb,
            o_tx_transmitter_en            => tx_reg_in.transmitter_en,
            o_tx_msg_sched_en              => tx_reg_in.msg_sched_en,
            o_tx_builder_en                => tx_reg_in.builder_en,
            o_tx_label                     => tx_reg_in.label_val,
            o_tx_sdi                       => tx_reg_in.sdi,
            o_tx_data                      => tx_reg_in.data,
            o_tx_ssm                       => tx_reg_in.ssm,
            o_tx_parity_type               => tx_reg_in.parity_type,
            o_tx_sched_en                  => tx_reg_in.sched_en,
            o_tx_initial_delay             => tx_reg_in.initial_delay,
            o_tx_inter_word_gap            => tx_reg_in.inter_word_gap,
            o_tx_send_cmd_send             => tx_reg_in.send_cmd,
            o_tx_ext_data                  => tx_reg_in.ext_data,
            o_tx_ext_high                  => tx_reg_in.ext_high,
            o_tx_ext_low                   => tx_reg_in.ext_low,
            o_tx_cfg_sel                   => tx_reg_in.cfg_sel,
            o_tx_cfg_apply_apply           => tx_reg_in.cfg_apply,
            o_tx_cust_pulse_dur            => tx_reg_in.cust.pulse_dur,
            o_tx_cust_null_dur             => tx_reg_in.cust.null_dur,
            o_tx_cust_gap_dur              => tx_reg_in.cust.gap_dur,
            o_tx_cust_slp                  => tx_reg_in.cust.slp,
            i_tx_act_pulse_dur             => tx_reg_out.act.pulse_dur,
            i_tx_act_null_dur              => tx_reg_out.act.null_dur,
            i_tx_act_gap_dur               => tx_reg_out.act.gap_dur,
            i_tx_act_slp                   => tx_reg_out.act.slp,
            i_tx_status_busy               => tx_reg_out.busy,
            i_tx_status_sched_active       => tx_reg_out.sched_active,
            i_tx_status_act_cfg            => tx_reg_out.act_cfg,
            i_tx_word_cnt                  => tx_reg_out.word_cnt,
            o_tb_ctrl_enable               => tb_reg_in.ctrl_enable,
            o_tb_ctrl_freeze               => tb_reg_in.ctrl_freeze,
            o_tb_ctrl_clear                => tb_reg_in.ctrl_clear,
            i_tb_status_frozen             => tb_reg_out.status_frozen,
            i_tb_status_word_wrap          => tb_reg_out.status_word_wrap,
            i_tb_status_err_wrap           => tb_reg_out.status_err_wrap,
            i_tb_status_act_cfg            => tb_reg_out.status_act_cfg,
            o_tb_cfg_sel                   => tb_reg_in.cfg_sel,
            o_tb_cfg_apply_apply           => tb_reg_in.cfg_apply,
            o_tb_cust_glitch_filter_size   => tb_reg_in.cust.glitch_filter_size,
            o_tb_cust_min_pulse            => tb_reg_in.cust.min_pulse,
            o_tb_cust_max_pulse            => tb_reg_in.cust.max_pulse,
            o_tb_cust_min_bit              => tb_reg_in.cust.min_bit,
            o_tb_cust_max_bit              => tb_reg_in.cust.max_bit,
            o_tb_cust_max_pulse_err        => tb_reg_in.cust.max_pulse_err,
            o_tb_cust_max_null_err         => tb_reg_in.cust.max_null_err,
            o_tb_cust_max_gap_err          => tb_reg_in.cust.max_gap_err,
            o_tb_cust_parity_mode          => tb_reg_in.cust.parity_mode,
            i_tb_act_glitch_filter_size    => tb_reg_out.act.glitch_filter_size,
            i_tb_act_min_pulse             => tb_reg_out.act.min_pulse,
            i_tb_act_max_pulse             => tb_reg_out.act.max_pulse,
            i_tb_act_min_bit               => tb_reg_out.act.min_bit,
            i_tb_act_max_bit               => tb_reg_out.act.max_bit,
            i_tb_act_max_pulse_err         => tb_reg_out.act.max_pulse_err,
            i_tb_act_max_null_err          => tb_reg_out.act.max_null_err,
            i_tb_act_max_gap_err           => tb_reg_out.act.max_gap_err,
            i_tb_act_parity_mode           => tb_reg_out.act.parity_mode,
            i_tb_word_cnt                  => tb_reg_out.word_cnt,
            i_tb_err_cnt                   => tb_reg_out.err_cnt,
            i_tb_drop_cnt                  => tb_reg_out.drop_cnt,
            i_tb_last_word                 => tb_reg_out.last_word,
            o_tb_word_raddr                => s_tb_word_raddr,
            o_tb_word_raddr_wr             => tb_reg_in.word_raddr_wr,
            i_tb_word_rd_ts_msb            => tb_reg_out.word_rd_ts_msb,
            i_tb_word_rd_ts_lsb            => tb_reg_out.word_rd_ts_lsb,
            i_tb_word_rd_data              => tb_reg_out.word_rd_data,
            i_tb_word_rd_gap               => tb_reg_out.word_rd_gap,
            i_tb_word_rd_gap_err           => tb_reg_out.word_rd_gap_err,
            o_tb_word_rd_gap_err_rd        => tb_reg_in.word_rd_last,
            o_tb_err_raddr                 => s_tb_err_raddr,
            o_tb_err_raddr_wr              => tb_reg_in.err_raddr_wr,
            i_tb_err_rd_ts_msb             => tb_reg_out.err_rd_ts_msb,
            i_tb_err_rd_ts_lsb             => tb_reg_out.err_rd_ts_lsb,
            i_tb_err_rd_code               => tb_reg_out.err_rd_code,
            i_tb_err_rd_addr               => tb_reg_out.err_rd_addr,
            i_tb_err_rd_data               => tb_reg_out.err_rd_data,
            o_tb_err_rd_data_rd            => tb_reg_in.err_rd_last,
            o_tb_bit_raddr_bit_idx         => tb_reg_in.bit_raddr_bit,
            o_tb_bit_raddr_word_idx        => s_tb_bit_widx,
            o_tb_bit_raddr_wr              => tb_reg_in.bit_raddr_wr,
            i_tb_bit_rd_pulse              => tb_reg_out.bit_rd_pulse,
            i_tb_bit_rd_pulse_err          => tb_reg_out.bit_rd_pulse_err,
            i_tb_bit_rd_null               => tb_reg_out.bit_rd_null,
            i_tb_bit_rd_null_err           => tb_reg_out.bit_rd_null_err,
            o_tb_bit_rd_null_err_rd        => tb_reg_in.bit_rd_last,
            o_tb_chk_ctrl_enable           => tb_reg_in.chk_enable,
            o_tb_chk_ctrl_clear            => tb_reg_in.chk_clear,
            o_tb_chk_timeout               => tb_reg_in.chk_timeout,
            i_tb_chk_ok_cnt                => tb_reg_out.chk_ok_cnt,
            i_tb_chk_err_cnt               => tb_reg_out.chk_err_cnt,
            i_tb_chk_status_fifo_level     => tb_reg_out.chk_fifo_level,
            i_tb_chk_status_fifo_ovf       => tb_reg_out.chk_fifo_ovf,
            o_rx0_ctrl_enable              => rx_reg_in(0).ctrl_enable,
            o_rx0_ctrl_freeze              => rx_reg_in(0).ctrl_freeze,
            o_rx0_ctrl_clear               => rx_reg_in(0).ctrl_clear,
            i_rx0_status_frozen            => rx_reg_out(0).status_frozen,
            i_rx0_status_word_wrap         => rx_reg_out(0).status_word_wrap,
            i_rx0_status_err_wrap          => rx_reg_out(0).status_err_wrap,
            i_rx0_status_act_cfg           => rx_reg_out(0).status_act_cfg,
            o_rx0_cfg_sel                  => rx_reg_in(0).cfg_sel,
            o_rx0_cfg_apply_apply          => rx_reg_in(0).cfg_apply,
            o_rx0_cust_glitch_filter_size  => rx_reg_in(0).cust.glitch_filter_size,
            o_rx0_cust_min_pulse           => rx_reg_in(0).cust.min_pulse,
            o_rx0_cust_max_pulse           => rx_reg_in(0).cust.max_pulse,
            o_rx0_cust_min_bit             => rx_reg_in(0).cust.min_bit,
            o_rx0_cust_max_bit             => rx_reg_in(0).cust.max_bit,
            o_rx0_cust_max_pulse_err       => rx_reg_in(0).cust.max_pulse_err,
            o_rx0_cust_max_null_err        => rx_reg_in(0).cust.max_null_err,
            o_rx0_cust_max_gap_err         => rx_reg_in(0).cust.max_gap_err,
            o_rx0_cust_parity_mode         => rx_reg_in(0).cust.parity_mode,
            i_rx0_act_glitch_filter_size   => rx_reg_out(0).act.glitch_filter_size,
            i_rx0_act_min_pulse            => rx_reg_out(0).act.min_pulse,
            i_rx0_act_max_pulse            => rx_reg_out(0).act.max_pulse,
            i_rx0_act_min_bit              => rx_reg_out(0).act.min_bit,
            i_rx0_act_max_bit              => rx_reg_out(0).act.max_bit,
            i_rx0_act_max_pulse_err        => rx_reg_out(0).act.max_pulse_err,
            i_rx0_act_max_null_err         => rx_reg_out(0).act.max_null_err,
            i_rx0_act_max_gap_err          => rx_reg_out(0).act.max_gap_err,
            i_rx0_act_parity_mode          => rx_reg_out(0).act.parity_mode,
            i_rx0_word_cnt                 => rx_reg_out(0).word_cnt,
            i_rx0_err_cnt                  => rx_reg_out(0).err_cnt,
            i_rx0_drop_cnt                 => rx_reg_out(0).drop_cnt,
            i_rx0_last_word                => rx_reg_out(0).last_word,
            o_rx0_word_raddr               => s_rx0_word_raddr,
            o_rx0_word_raddr_wr            => rx_reg_in(0).word_raddr_wr,
            i_rx0_word_rd_ts_msb           => rx_reg_out(0).word_rd_ts_msb,
            i_rx0_word_rd_ts_lsb           => rx_reg_out(0).word_rd_ts_lsb,
            i_rx0_word_rd_data             => rx_reg_out(0).word_rd_data,
            i_rx0_word_rd_gap              => rx_reg_out(0).word_rd_gap,
            i_rx0_word_rd_gap_err          => rx_reg_out(0).word_rd_gap_err,
            o_rx0_word_rd_gap_err_rd       => rx_reg_in(0).word_rd_last,
            o_rx0_err_raddr                => s_rx0_err_raddr,
            o_rx0_err_raddr_wr             => rx_reg_in(0).err_raddr_wr,
            i_rx0_err_rd_ts_msb            => rx_reg_out(0).err_rd_ts_msb,
            i_rx0_err_rd_ts_lsb            => rx_reg_out(0).err_rd_ts_lsb,
            i_rx0_err_rd_code              => rx_reg_out(0).err_rd_code,
            i_rx0_err_rd_addr              => rx_reg_out(0).err_rd_addr,
            i_rx0_err_rd_data              => rx_reg_out(0).err_rd_data,
            o_rx0_err_rd_data_rd           => rx_reg_in(0).err_rd_last,
            o_rx0_bit_raddr_bit_idx        => rx_reg_in(0).bit_raddr_bit,
            o_rx0_bit_raddr_word_idx       => s_rx0_bit_widx,
            o_rx0_bit_raddr_wr             => rx_reg_in(0).bit_raddr_wr,
            i_rx0_bit_rd_pulse             => rx_reg_out(0).bit_rd_pulse,
            i_rx0_bit_rd_pulse_err         => rx_reg_out(0).bit_rd_pulse_err,
            i_rx0_bit_rd_null              => rx_reg_out(0).bit_rd_null,
            i_rx0_bit_rd_null_err          => rx_reg_out(0).bit_rd_null_err,
            o_rx0_bit_rd_null_err_rd       => rx_reg_in(0).bit_rd_last,
            o_rx1_ctrl_enable              => rx_reg_in(1).ctrl_enable,
            o_rx1_ctrl_freeze              => rx_reg_in(1).ctrl_freeze,
            o_rx1_ctrl_clear               => rx_reg_in(1).ctrl_clear,
            i_rx1_status_frozen            => rx_reg_out(1).status_frozen,
            i_rx1_status_word_wrap         => rx_reg_out(1).status_word_wrap,
            i_rx1_status_err_wrap          => rx_reg_out(1).status_err_wrap,
            i_rx1_status_act_cfg           => rx_reg_out(1).status_act_cfg,
            o_rx1_cfg_sel                  => rx_reg_in(1).cfg_sel,
            o_rx1_cfg_apply_apply          => rx_reg_in(1).cfg_apply,
            o_rx1_cust_glitch_filter_size  => rx_reg_in(1).cust.glitch_filter_size,
            o_rx1_cust_min_pulse           => rx_reg_in(1).cust.min_pulse,
            o_rx1_cust_max_pulse           => rx_reg_in(1).cust.max_pulse,
            o_rx1_cust_min_bit             => rx_reg_in(1).cust.min_bit,
            o_rx1_cust_max_bit             => rx_reg_in(1).cust.max_bit,
            o_rx1_cust_max_pulse_err       => rx_reg_in(1).cust.max_pulse_err,
            o_rx1_cust_max_null_err        => rx_reg_in(1).cust.max_null_err,
            o_rx1_cust_max_gap_err         => rx_reg_in(1).cust.max_gap_err,
            o_rx1_cust_parity_mode         => rx_reg_in(1).cust.parity_mode,
            i_rx1_act_glitch_filter_size   => rx_reg_out(1).act.glitch_filter_size,
            i_rx1_act_min_pulse            => rx_reg_out(1).act.min_pulse,
            i_rx1_act_max_pulse            => rx_reg_out(1).act.max_pulse,
            i_rx1_act_min_bit              => rx_reg_out(1).act.min_bit,
            i_rx1_act_max_bit              => rx_reg_out(1).act.max_bit,
            i_rx1_act_max_pulse_err        => rx_reg_out(1).act.max_pulse_err,
            i_rx1_act_max_null_err         => rx_reg_out(1).act.max_null_err,
            i_rx1_act_max_gap_err          => rx_reg_out(1).act.max_gap_err,
            i_rx1_act_parity_mode          => rx_reg_out(1).act.parity_mode,
            i_rx1_word_cnt                 => rx_reg_out(1).word_cnt,
            i_rx1_err_cnt                  => rx_reg_out(1).err_cnt,
            i_rx1_drop_cnt                 => rx_reg_out(1).drop_cnt,
            i_rx1_last_word                => rx_reg_out(1).last_word,
            o_rx1_word_raddr               => s_rx1_word_raddr,
            o_rx1_word_raddr_wr            => rx_reg_in(1).word_raddr_wr,
            i_rx1_word_rd_ts_msb           => rx_reg_out(1).word_rd_ts_msb,
            i_rx1_word_rd_ts_lsb           => rx_reg_out(1).word_rd_ts_lsb,
            i_rx1_word_rd_data             => rx_reg_out(1).word_rd_data,
            i_rx1_word_rd_gap              => rx_reg_out(1).word_rd_gap,
            i_rx1_word_rd_gap_err          => rx_reg_out(1).word_rd_gap_err,
            o_rx1_word_rd_gap_err_rd       => rx_reg_in(1).word_rd_last,
            o_rx1_err_raddr                => s_rx1_err_raddr,
            o_rx1_err_raddr_wr             => rx_reg_in(1).err_raddr_wr,
            i_rx1_err_rd_ts_msb            => rx_reg_out(1).err_rd_ts_msb,
            i_rx1_err_rd_ts_lsb            => rx_reg_out(1).err_rd_ts_lsb,
            i_rx1_err_rd_code              => rx_reg_out(1).err_rd_code,
            i_rx1_err_rd_addr              => rx_reg_out(1).err_rd_addr,
            i_rx1_err_rd_data              => rx_reg_out(1).err_rd_data,
            o_rx1_err_rd_data_rd           => rx_reg_in(1).err_rd_last,
            o_rx1_bit_raddr_bit_idx        => rx_reg_in(1).bit_raddr_bit,
            o_rx1_bit_raddr_word_idx       => s_rx1_bit_widx,
            o_rx1_bit_raddr_wr             => rx_reg_in(1).bit_raddr_wr,
            i_rx1_bit_rd_pulse             => rx_reg_out(1).bit_rd_pulse,
            i_rx1_bit_rd_pulse_err         => rx_reg_out(1).bit_rd_pulse_err,
            i_rx1_bit_rd_null              => rx_reg_out(1).bit_rd_null,
            i_rx1_bit_rd_null_err          => rx_reg_out(1).bit_rd_null_err,
            o_rx1_bit_rd_null_err_rd       => rx_reg_in(1).bit_rd_last
        );

    u_core : entity work.arinc429_core
        generic map (
            G_NUM_RX             => 2,
            G_TX_EN              => true,
            G_TXBIT_EN           => true,
            G_SYNC_STAGES        => G_SYNC_STAGES,
            G_WORD_DEPTH_LOG2    => 8,
            G_ERR_DEPTH_LOG2     => 8,
            G_BITDIAG_WORDS_LOG2 => 3,
            G_BITDIAG_EN         => true,
            G_CHK_FIFO_DEPTH     => G_CHK_FIFO_DEPTH
        )
        port map (
            clk           => S_AXI_ACLK,
            rst_n         => S_AXI_ARESETN,
            rst_all       => rst_all,
            rst_tx        => rst_tx,
            rst_txbit     => rst_txbit,
            rst_rx        => rst_rx,
            global_freeze => global_freeze,
            ts_en         => ts_en,
            ts_clr        => ts_clr,
            ts_lsb_rd     => ts_lsb_rd,
            ts_lsb        => ts_lsb,
            ts_msb        => ts_msb,
            tx_reg_in     => tx_reg_in,
            tx_reg_out    => tx_reg_out,
            tb_reg_in     => tb_reg_in,
            tb_reg_out    => tb_reg_out,
            rx_reg_in     => rx_reg_in,
            rx_reg_out    => rx_reg_out,
            tx_high       => tx_high,
            tx_low        => tx_low,
            tx_slp        => tx_slp,
            txbit_rx_high => txbit_rx_high,
            txbit_rx_low  => txbit_rx_low,
            rx_high       => rx_high,
            rx_low        => rx_low
        );

end architecture rtl;
