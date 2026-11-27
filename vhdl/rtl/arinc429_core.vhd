--------------------------------------------------------------------------------
-- Dosya       : arinc429_core.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Bus-bağımsız, generic, saf VHDL ARINC 429 IP çekirdeği. Tek saat domain'i
--   içinde reset senkronizasyonu, ortak 64-bit zaman damgası, opsiyonel TX
--   kanalı, opsiyonel TX BIT (checker'lı) kanalı ve G_NUM_RX adet RX kanalını
--   birleştirir.
--
-- Gereksinimler:
--   REQ-1 : G_TX_EN = false iken TX bloğu sentezlenmez, çıkışlar '0' kalır;
--           G_TXBIT_EN yalnızca G_TX_EN = true iken aktiftir.
--   REQ-2 : Tüm RX ve TX BIT kanalları tek a429_timestamp sayacından (ts_now)
--           ve tek global_freeze sinyalinden beslenir.
--   REQ-3 : SOFT_RESET.RST_ALL tüm alt blokları; TX, TXBIT ve RX(n) darbeleri
--           yalnızca kendi kanalını senkron olarak sıfırlar.
--   REQ-4 : Register portları AXIL Studio'nun ürettiği arinc429_axil.v
--           AXI4-Lite slave'i ile arinc429_ip.vhd üzerinden 1-1 bağlanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;

entity arinc429_core is
    generic (
        G_NUM_RX             : natural  := 2;
        G_TX_EN              : boolean  := true;
        G_TXBIT_EN           : boolean  := true;
        G_SYNC_STAGES        : positive := 4;
        G_WORD_DEPTH_LOG2    : positive := 8;
        G_ERR_DEPTH_LOG2     : positive := 8;
        G_BITDIAG_WORDS_LOG2 : positive := 3;
        G_BITDIAG_EN         : boolean  := true;
        G_CHK_FIFO_DEPTH     : positive := 4
    );
    port (
        clk           : in  std_logic;
        rst_n         : in  std_logic;

        -- Global register sinyalleri
        rst_all       : in  std_logic;
        rst_tx        : in  std_logic;
        rst_txbit     : in  std_logic;
        rst_rx        : in  std_logic_vector(max_nat(G_NUM_RX, 1) - 1 downto 0);
        global_freeze : in  std_logic;
        ts_en         : in  std_logic;
        ts_clr        : in  std_logic;
        ts_lsb_rd     : in  std_logic;
        ts_lsb        : out std_logic_vector(31 downto 0);
        ts_msb        : out std_logic_vector(31 downto 0);

        -- TX register arayüzü
        tx_reg_in     : in  t_tx_reg_in := C_TX_REG_IN_ZERO;
        tx_reg_out    : out t_tx_reg_out;

        -- TX BIT (TB) register arayüzü
        tb_reg_in     : in  t_rx_reg_in := C_RX_REG_IN_ZERO;
        tb_reg_out    : out t_rx_reg_out;

        -- RX0..RX(N-1) register arayüzü
        rx_reg_in     : in  t_rx_reg_in_arr(0 to max_nat(G_NUM_RX, 1) - 1);
        rx_reg_out    : out t_rx_reg_out_arr(0 to max_nat(G_NUM_RX, 1) - 1);

        -- Fiziksel ARINC 429 pinleri
        tx_high       : out std_logic;
        tx_low        : out std_logic;
        tx_slp        : out std_logic;
        txbit_rx_high : in  std_logic := '0';
        txbit_rx_low  : in  std_logic := '0';
        rx_high       : in  std_logic_vector(max_nat(G_NUM_RX, 1) - 1 downto 0) := (others => '0');
        rx_low        : in  std_logic_vector(max_nat(G_NUM_RX, 1) - 1 downto 0) := (others => '0')
    );
end entity arinc429_core;

architecture rtl of arinc429_core is
    signal rst_n_sync    : std_logic;
    signal ts_now        : std_logic_vector(63 downto 0);

    signal tx_word_start : std_logic := '0';
    signal tx_word_done  : std_logic := '0';
    signal tx_word_tx    : std_logic_vector(31 downto 0) := (others => '0');

    signal soft_rst_tx   : std_logic;
    signal soft_rst_tb   : std_logic;
begin

    u_rst : entity work.a429_rst_sync
        port map (
            clk        => clk,
            rst_n      => rst_n,
            rst_n_sync => rst_n_sync
        );

    u_ts : entity work.a429_timestamp
        port map (
            clk       => clk,
            rst_n     => rst_n_sync,
            soft_rst  => rst_all,
            ts_en     => ts_en,
            ts_clr    => ts_clr,
            ts_lsb_rd => ts_lsb_rd,
            ts_now    => ts_now,
            ts_lsb    => ts_lsb,
            ts_msb    => ts_msb
        );

    soft_rst_tx <= rst_all or rst_tx;
    soft_rst_tb <= rst_all or rst_txbit;

    -- TX kanalı
    gen_tx : if G_TX_EN generate
        u_tx : entity work.a429_tx_channel
            port map (
                clk           => clk,
                rst_n         => rst_n_sync,
                soft_rst      => soft_rst_tx,
                reg_in        => tx_reg_in,
                reg_out       => tx_reg_out,
                tx_high       => tx_high,
                tx_low        => tx_low,
                tx_slp        => tx_slp,
                tx_word_start => tx_word_start,
                tx_word_done  => tx_word_done,
                tx_word_tx    => tx_word_tx
            );
    end generate;

    gen_no_tx : if not G_TX_EN generate
        tx_high <= '0';
        tx_low  <= '0';
        tx_slp  <= '0';
        tx_reg_out <= (
            act          => C_TX_CFG_ZERO,
            busy         => '0',
            sched_active => '0',
            sched_done   => '0',
            act_cfg      => C_CFG_HS,
            word_cnt     => (others => '0')
        );
    end generate;

    -- TX BIT kanalı (checker'lı RX kanalı)
    gen_tb : if G_TX_EN and G_TXBIT_EN generate
        u_tb : entity work.a429_rx_channel
            generic map (
                G_SYNC_STAGES        => G_SYNC_STAGES,
                G_WORD_DEPTH_LOG2    => G_WORD_DEPTH_LOG2,
                G_ERR_DEPTH_LOG2     => G_ERR_DEPTH_LOG2,
                G_BITDIAG_WORDS_LOG2 => G_BITDIAG_WORDS_LOG2,
                G_BITDIAG_EN         => G_BITDIAG_EN,
                G_HAS_CHECKER        => true,
                G_CHK_FIFO_DEPTH     => G_CHK_FIFO_DEPTH
            )
            port map (
                clk           => clk,
                rst_n         => rst_n_sync,
                soft_rst      => soft_rst_tb,
                pin_high      => txbit_rx_high,
                pin_low       => txbit_rx_low,
                ts_now        => ts_now,
                global_freeze => global_freeze,
                tx_word_start => tx_word_start,
                tx_word_tx    => tx_word_tx,
                reg_in        => tb_reg_in,
                reg_out       => tb_reg_out
            );
    end generate;

    gen_no_tb : if not (G_TX_EN and G_TXBIT_EN) generate
        tb_reg_out <= (
            status_frozen    => '0',
            status_word_wrap => '0',
            status_err_wrap  => '0',
            status_act_cfg   => C_CFG_HS,
            status_line_high => '0',
            status_line_low  => '0',
            status_sync_wait => '0',
            act              => C_RX_CFG_ZERO,
            word_cnt         => (others => '0'),
            err_cnt          => (others => '0'),
            drop_cnt         => (others => '0'),
            last_word        => (others => '0'),
            word_rd_ts_msb   => (others => '0'),
            word_rd_ts_lsb   => (others => '0'),
            word_rd_data     => (others => '0'),
            word_rd_gap      => (others => '0'),
            word_rd_gap_err  => (others => '0'),
            err_rd_ts_msb    => (others => '0'),
            err_rd_ts_lsb    => (others => '0'),
            err_rd_code      => (others => '0'),
            err_rd_addr      => (others => '0'),
            err_rd_data      => (others => '0'),
            bit_rd_pulse     => (others => '0'),
            bit_rd_pulse_err => (others => '0'),
            bit_rd_null      => (others => '0'),
            bit_rd_null_err  => (others => '0'),
            chk_ok_cnt       => (others => '0'),
            chk_err_cnt      => (others => '0'),
            chk_fifo_level   => (others => '0'),
            chk_fifo_ovf     => '0'
        );
    end generate;

    -- RX0..RX(N-1) kanalları
    gen_rx : for n in 0 to G_NUM_RX - 1 generate
        signal soft_rst_n : std_logic;
    begin
        soft_rst_n <= rst_all or rst_rx(n);

        u_rx : entity work.a429_rx_channel
            generic map (
                G_SYNC_STAGES        => G_SYNC_STAGES,
                G_WORD_DEPTH_LOG2    => G_WORD_DEPTH_LOG2,
                G_ERR_DEPTH_LOG2     => G_ERR_DEPTH_LOG2,
                G_BITDIAG_WORDS_LOG2 => G_BITDIAG_WORDS_LOG2,
                G_BITDIAG_EN         => G_BITDIAG_EN,
                G_HAS_CHECKER        => false,
                G_CHK_FIFO_DEPTH     => G_CHK_FIFO_DEPTH
            )
            port map (
                clk           => clk,
                rst_n         => rst_n_sync,
                soft_rst      => soft_rst_n,
                pin_high      => rx_high(n),
                pin_low       => rx_low(n),
                ts_now        => ts_now,
                global_freeze => global_freeze,
                tx_word_start => '0',
                tx_word_tx    => (others => '0'),
                reg_in        => rx_reg_in(n),
                reg_out       => rx_reg_out(n)
            );
    end generate;

end architecture rtl;
