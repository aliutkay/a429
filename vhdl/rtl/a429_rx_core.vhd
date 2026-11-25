--------------------------------------------------------------------------------
-- a429_rx_core
--
-- RX ön ucu: a429_cdc_sync (G_SYNC_STAGES) → a429_glitch_filter → a429_rx_decoder
--
--   pin_high/pin_low (alıcı entegresi ROUTA/ROUTB, asenkron)
--        │
--   a429_cdc_sync      : G_SYNC_STAGES FF (varsayılan 4)
--        │
--   a429_glitch_filter : 2 bitlik hat durumu tek sembol olarak filtrelenir
--        │ rx_high_f, rx_low_f, glitch_win_cnt
--   a429_rx_decoder    : bit / Word ölçümü ve hata tespiti
--
-- Toplam gecikme (pin → decoder girişi): G_SYNC_STAGES + glitch_size + 1 clk (sabit).
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_rx_core is
    generic (
        G_SYNC_STAGES : positive := 4;
        G_SIZE_W      : positive := 16;   -- glitch_size genişliği
        G_DUR_W       : positive := 16;
        G_GAP_W       : positive := 32;
        G_CNT_W       : positive := 16
    );
    port (
        clk                 : in  std_logic;
        rst_n               : in  std_logic;

        pin_high            : in  std_logic;
        pin_low             : in  std_logic;

        -- Config
        cfg_glitch_size     : in  std_logic_vector(G_SIZE_W - 1 downto 0);
        cfg_min_pulse       : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_pulse       : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_min_bit         : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_bit         : in  std_logic_vector(G_DUR_W - 1 downto 0);
        cfg_max_pulse_err   : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_max_null_err    : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_max_gap_err     : in  std_logic_vector(G_CNT_W - 1 downto 0);
        cfg_parity_mode     : in  std_logic_vector(1 downto 0);

        -- Word
        word_start          : out std_logic;
        word_data           : out std_logic_vector(31 downto 0);
        word_gap_dur        : out std_logic_vector(G_GAP_W - 1 downto 0);
        word_gap_err_cnt    : out std_logic_vector(G_CNT_W - 1 downto 0);
        word_valid          : out std_logic;

        -- Bit diagnostic
        bit_idx             : out std_logic_vector(4 downto 0);
        bit_pulse_dur       : out std_logic_vector(G_DUR_W - 1 downto 0);
        bit_null_dur        : out std_logic_vector(G_DUR_W - 1 downto 0);
        bit_pulse_err_cnt   : out std_logic_vector(G_CNT_W - 1 downto 0);
        bit_null_err_cnt    : out std_logic_vector(G_CNT_W - 1 downto 0);
        bit_valid           : out std_logic;

        -- Hatalar
        err_bus_fault       : out std_logic;
        err_noise_violation : out std_logic;
        err_gap_violation   : out std_logic;
        err_bit_early       : out std_logic;
        err_pulse_glitch    : out std_logic;
        err_pulse_stuck     : out std_logic;
        err_bit_timeout     : out std_logic;
        err_parity          : out std_logic;
        err_addr            : out std_logic_vector(15 downto 0);
        err_data            : out std_logic_vector(31 downto 0);

        -- Glitch istatistiği
        glitch_tick         : out std_logic;
        glitch_total_cnt    : out std_logic_vector(G_CNT_W - 1 downto 0)
    );
end entity a429_rx_core;

architecture rtl of a429_rx_core is

    signal pin_vec        : std_logic_vector(1 downto 0);
    signal sync_vec       : std_logic_vector(1 downto 0);
    signal rx_high_f      : std_logic;
    signal rx_low_f       : std_logic;
    signal glitch_win_cnt : std_logic_vector(G_CNT_W - 1 downto 0);

begin

    pin_vec <= pin_high & pin_low;

    u_cdc : entity work.a429_cdc_sync
        generic map (G_STAGES => G_SYNC_STAGES, G_WIDTH => 2, G_RST_VALUE => '0')
        port map (clk => clk, rst_n => rst_n, async_in => pin_vec, sync_out => sync_vec);

    u_filter : entity work.a429_glitch_filter
        generic map (G_SIZE_W => G_SIZE_W, G_CNT_W => G_CNT_W)
        port map (
            clk              => clk,
            rst_n            => rst_n,
            glitch_size      => cfg_glitch_size,
            rx_high_in       => sync_vec(1),
            rx_low_in        => sync_vec(0),
            rx_high_out      => rx_high_f,
            rx_low_out       => rx_low_f,
            glitch_tick      => glitch_tick,
            glitch_total_cnt => glitch_total_cnt,
            glitch_win_cnt   => glitch_win_cnt
        );

    u_decoder : entity work.a429_rx_decoder
        generic map (G_DUR_W => G_DUR_W, G_GAP_W => G_GAP_W, G_CNT_W => G_CNT_W)
        port map (
            clk                 => clk,
            rst_n               => rst_n,
            cfg_min_pulse       => cfg_min_pulse,
            cfg_max_pulse       => cfg_max_pulse,
            cfg_min_bit         => cfg_min_bit,
            cfg_max_bit         => cfg_max_bit,
            cfg_max_pulse_err   => cfg_max_pulse_err,
            cfg_max_null_err    => cfg_max_null_err,
            cfg_max_gap_err     => cfg_max_gap_err,
            cfg_parity_mode     => cfg_parity_mode,
            rx_high             => rx_high_f,
            rx_low              => rx_low_f,
            glitch_cnt          => glitch_win_cnt,
            word_start          => word_start,
            word_data           => word_data,
            word_gap_dur        => word_gap_dur,
            word_gap_err_cnt    => word_gap_err_cnt,
            word_valid          => word_valid,
            bit_idx             => bit_idx,
            bit_pulse_dur       => bit_pulse_dur,
            bit_null_dur        => bit_null_dur,
            bit_pulse_err_cnt   => bit_pulse_err_cnt,
            bit_null_err_cnt    => bit_null_err_cnt,
            bit_valid           => bit_valid,
            err_bus_fault       => err_bus_fault,
            err_noise_violation => err_noise_violation,
            err_gap_violation   => err_gap_violation,
            err_bit_early       => err_bit_early,
            err_pulse_glitch    => err_pulse_glitch,
            err_pulse_stuck     => err_pulse_stuck,
            err_bit_timeout     => err_bit_timeout,
            err_parity          => err_parity,
            err_addr            => err_addr,
            err_data            => err_data
        );

end architecture rtl;
