--------------------------------------------------------------------------------
-- Dosya       : a429_rx_channel.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Tek bir RX veya TX BIT (G_HAS_CHECKER = true) kanalını oluşturur:
--   a429_rx_cfg_sel -> a429_rx_core -> a429_rx_logger -> 3x a429_sdp_ram
--   (+ opsiyonel a429_word_checker) ve otomatik artan RAM okuma pointer'ları.
--
-- Gereksinimler:
--   REQ-1 : G_HAS_CHECKER = true iken TX BIT Word Checker sentezlenir; false
--           iken checker kaynak harcamaz ve ilgili çıkışlar '0' kalır.
--   REQ-2 : G_BITDIAG_EN = true iken 2^G_BITDIAG_WORDS_LOG2 x 32 satırlık
--           64-bit Bit Diagnostic RAM sentezlenir.
--   REQ-3 : Otomatik artan okuma pointer'ları (Seçenek 2 — wr_strobe + rd_strobe):
--             * *_RADDR yazıldığında (*_raddr_wr='1') pointer o adrese yüklenir.
--             * Kaydın son RD register'ı okunduğunda (*_rd_last='1') pointer
--               dairesel +1 artar (BIT'te bit 31 -> sonraki Word bit 0).
--             * next_*_ptr doğrudan BRAM raddr'a sürülerek 1 clk gecikme gizlenir.
--   REQ-4 : soft_rst veya ctrl_clear okuma pointer'larını da sıfırlar.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity a429_rx_channel is
    generic (
        G_SYNC_STAGES        : positive := 4;
        G_WORD_DEPTH_LOG2    : positive := 8;
        G_ERR_DEPTH_LOG2     : positive := 8;
        G_BITDIAG_WORDS_LOG2 : positive := 3;
        G_BITDIAG_EN         : boolean  := true;
        G_HAS_CHECKER        : boolean  := false;
        G_CHK_FIFO_DEPTH     : positive := 4
    );
    port (
        clk           : in  std_logic;
        rst_n         : in  std_logic;
        soft_rst      : in  std_logic;

        -- Fiziksel girişler (alıcı entegresi ROUTA / ROUTB)
        pin_high      : in  std_logic;
        pin_low       : in  std_logic;

        -- Global sinyaller
        ts_now        : in  std_logic_vector(63 downto 0);
        global_freeze : in  std_logic;

        -- Checker için TX olayları (G_HAS_CHECKER = true ise kullanılır)
        tx_word_start : in  std_logic := '0';
        tx_word_tx    : in  std_logic_vector(31 downto 0) := (others => '0');

        -- AXIL register arayüzü
        reg_in        : in  t_rx_reg_in;
        reg_out       : out t_rx_reg_out
    );
end entity a429_rx_channel;

architecture rtl of a429_rx_channel is
    signal act_cfg             : t_rx_cfg;
    signal act_mode            : std_logic_vector(1 downto 0);

    signal word_start          : std_logic;
    signal word_data           : std_logic_vector(31 downto 0);
    signal word_gap_dur        : std_logic_vector(31 downto 0);
    signal word_gap_err_cnt    : std_logic_vector(15 downto 0);
    signal word_valid          : std_logic;

    signal bit_idx             : std_logic_vector(4 downto 0);
    signal bit_pulse_dur       : std_logic_vector(15 downto 0);
    signal bit_null_dur        : std_logic_vector(15 downto 0);
    signal bit_pulse_err_cnt   : std_logic_vector(15 downto 0);
    signal bit_null_err_cnt    : std_logic_vector(15 downto 0);
    signal bit_valid           : std_logic;

    signal err_bus_fault       : std_logic;
    signal err_noise_violation : std_logic;
    signal err_gap_violation   : std_logic;
    signal err_bit_early       : std_logic;
    signal err_pulse_glitch    : std_logic;
    signal err_pulse_stuck     : std_logic;
    signal err_bit_timeout     : std_logic;
    signal err_parity          : std_logic;
    signal err_addr            : std_logic_vector(15 downto 0);
    signal err_data            : std_logic_vector(31 downto 0);
    signal rx_err_any          : std_logic;

    signal chk_mismatch        : std_logic := '0';
    signal chk_no_echo         : std_logic := '0';
    signal chk_unexpected      : std_logic := '0';
    signal chk_addr            : std_logic_vector(15 downto 0) := (others => '0');
    signal chk_data            : std_logic_vector(31 downto 0) := (others => '0');
    signal chk_ok_cnt          : std_logic_vector(31 downto 0) := (others => '0');
    signal chk_err_cnt         : std_logic_vector(31 downto 0) := (others => '0');
    signal chk_fifo_level      : std_logic_vector(3 downto 0)  := (others => '0');
    signal chk_fifo_ovf        : std_logic := '0';

    signal word_we             : std_logic;
    signal word_waddr          : std_logic_vector(G_WORD_DEPTH_LOG2 - 1 downto 0);
    signal word_wdata          : std_logic_vector(143 downto 0);
    signal word_rdata          : std_logic_vector(143 downto 0);
    signal r_word_ptr          : unsigned(G_WORD_DEPTH_LOG2 - 1 downto 0);
    signal next_word_ptr       : unsigned(G_WORD_DEPTH_LOG2 - 1 downto 0);

    signal err_we              : std_logic;
    signal err_waddr           : std_logic_vector(G_ERR_DEPTH_LOG2 - 1 downto 0);
    signal err_wdata           : std_logic_vector(127 downto 0);
    signal err_rdata           : std_logic_vector(127 downto 0);
    signal r_err_ptr           : unsigned(G_ERR_DEPTH_LOG2 - 1 downto 0);
    signal next_err_ptr        : unsigned(G_ERR_DEPTH_LOG2 - 1 downto 0);

    signal bit_we              : std_logic;
    signal bit_waddr           : std_logic_vector(G_BITDIAG_WORDS_LOG2 + 4 downto 0);
    signal bit_wdata           : std_logic_vector(63 downto 0);
    signal bit_rdata           : std_logic_vector(63 downto 0) := (others => '0');
    signal r_bit_ptr           : unsigned(G_BITDIAG_WORDS_LOG2 + 4 downto 0);
    signal next_bit_ptr        : unsigned(G_BITDIAG_WORDS_LOG2 + 4 downto 0);
begin

    u_cfg : entity work.a429_rx_cfg_sel
        port map (
            clk       => clk,
            rst_n     => rst_n,
            soft_rst  => soft_rst,
            cfg_sel   => reg_in.cfg_sel,
            cfg_apply => reg_in.cfg_apply,
            cust_cfg  => reg_in.cust,
            act_cfg   => act_cfg,
            act_mode  => act_mode
        );

    u_core : entity work.a429_rx_core
        generic map (
            G_SYNC_STAGES => G_SYNC_STAGES,
            G_SIZE_W      => 16,
            G_DUR_W       => 16,
            G_GAP_W       => 32,
            G_CNT_W       => 16
        )
        port map (
            clk                 => clk,
            rst_n               => rst_n,
            soft_rst            => soft_rst,
            pin_high            => pin_high,
            pin_low             => pin_low,
            cfg_glitch_size     => act_cfg.glitch_filter_size,
            cfg_min_pulse       => act_cfg.min_pulse,
            cfg_max_pulse       => act_cfg.max_pulse,
            cfg_min_bit         => act_cfg.min_bit,
            cfg_max_bit         => act_cfg.max_bit,
            cfg_max_pulse_err   => act_cfg.max_pulse_err,
            cfg_max_null_err    => act_cfg.max_null_err,
            cfg_max_gap_err     => act_cfg.max_gap_err,
            cfg_parity_mode     => act_cfg.parity_mode,
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
            err_data            => err_data,
            glitch_tick         => open,
            glitch_total_cnt    => open
        );

    gen_checker : if G_HAS_CHECKER generate
        u_chk : entity work.a429_word_checker
            generic map (G_FIFO_DEPTH => G_CHK_FIFO_DEPTH)
            port map (
                clk            => clk,
                rst_n          => rst_n,
                soft_rst       => soft_rst,
                chk_en         => reg_in.chk_enable,
                chk_clear      => reg_in.chk_clear,
                chk_timeout    => reg_in.chk_timeout,
                chk_route_ok   => '1',
                ts_now         => ts_now,
                tx_word_start  => tx_word_start,
                tx_word_tx     => tx_word_tx,
                rx_word_data   => word_data,
                rx_word_valid  => word_valid,
                rx_err_any     => rx_err_any,
                chk_mismatch   => chk_mismatch,
                chk_no_echo    => chk_no_echo,
                chk_unexpected => chk_unexpected,
                chk_addr       => chk_addr,
                chk_data       => chk_data,
                chk_ok_cnt     => chk_ok_cnt,
                chk_err_cnt    => chk_err_cnt,
                chk_fifo_level => chk_fifo_level,
                chk_fifo_ovf   => chk_fifo_ovf
            );
    end generate;

    u_logger : entity work.a429_rx_logger
        generic map (
            G_WORD_DEPTH_LOG2    => G_WORD_DEPTH_LOG2,
            G_ERR_DEPTH_LOG2     => G_ERR_DEPTH_LOG2,
            G_BITDIAG_WORDS_LOG2 => G_BITDIAG_WORDS_LOG2,
            G_BITDIAG_EN         => G_BITDIAG_EN
        )
        port map (
            clk                 => clk,
            rst_n               => rst_n,
            soft_rst            => soft_rst,
            ts_now              => ts_now,
            enable              => reg_in.ctrl_enable,
            freeze              => reg_in.ctrl_freeze,
            global_freeze       => global_freeze,
            clear               => reg_in.ctrl_clear,
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
            err_data            => err_data,
            err_label_filtered  => '0',
            chk_mismatch        => chk_mismatch,
            chk_no_echo         => chk_no_echo,
            chk_unexpected      => chk_unexpected,
            chk_addr            => chk_addr,
            chk_data            => chk_data,
            word_we             => word_we,
            word_waddr          => word_waddr,
            word_wdata          => word_wdata,
            err_we              => err_we,
            err_waddr           => err_waddr,
            err_wdata           => err_wdata,
            bit_we              => bit_we,
            bit_waddr           => bit_waddr,
            bit_wdata           => bit_wdata,
            frozen              => reg_out.status_frozen,
            word_wrap           => reg_out.status_word_wrap,
            err_wrap            => reg_out.status_err_wrap,
            word_cnt            => reg_out.word_cnt,
            err_cnt             => reg_out.err_cnt,
            drop_cnt            => reg_out.drop_cnt,
            last_word           => reg_out.last_word,
            rx_err_any          => rx_err_any
        );

    -- Otomatik artan okuma pointer'ları (RADDR yazımında yüklenir, son RD register okumasında +1 sarar)
    -- next_* kombinasyonel olarak BRAM raddr'a verilerek 1 clk gecikme gizlenir
    next_word_ptr <= unsigned(reg_in.word_raddr(G_WORD_DEPTH_LOG2 - 1 downto 0)) when reg_in.word_raddr_wr = '1' else
                     r_word_ptr + 1                                               when reg_in.word_rd_last = '1' else
                     r_word_ptr;

    next_err_ptr  <= unsigned(reg_in.err_raddr(G_ERR_DEPTH_LOG2 - 1 downto 0))   when reg_in.err_raddr_wr = '1' else
                     r_err_ptr + 1                                                when reg_in.err_rd_last = '1' else
                     r_err_ptr;

    next_bit_ptr  <= unsigned(reg_in.bit_raddr_word(G_BITDIAG_WORDS_LOG2 - 1 downto 0) & reg_in.bit_raddr_bit)
                                                                                  when reg_in.bit_raddr_wr = '1' else
                     r_bit_ptr + 1                                                when reg_in.bit_rd_last = '1' else
                     r_bit_ptr;

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            r_word_ptr <= (others => '0');
            r_err_ptr  <= (others => '0');
            r_bit_ptr  <= (others => '0');
        elsif rising_edge(clk) then
            if soft_rst = '1' or reg_in.ctrl_clear = '1' then
                r_word_ptr <= (others => '0');
                r_err_ptr  <= (others => '0');
                r_bit_ptr  <= (others => '0');
            else
                r_word_ptr <= next_word_ptr;
                r_err_ptr  <= next_err_ptr;
                r_bit_ptr  <= next_bit_ptr;
            end if;
        end if;
    end process;

    u_word_ram : entity work.a429_sdp_ram
        generic map (G_ADDR_W => G_WORD_DEPTH_LOG2, G_DATA_W => 144)
        port map (
            clk   => clk,
            we    => word_we,
            waddr => word_waddr,
            wdata => word_wdata,
            raddr => std_logic_vector(next_word_ptr),
            rdata => word_rdata
        );

    u_err_ram : entity work.a429_sdp_ram
        generic map (G_ADDR_W => G_ERR_DEPTH_LOG2, G_DATA_W => 128)
        port map (
            clk   => clk,
            we    => err_we,
            waddr => err_waddr,
            wdata => err_wdata,
            raddr => std_logic_vector(next_err_ptr),
            rdata => err_rdata
        );

    gen_bit_ram : if G_BITDIAG_EN generate
        u_bit_ram : entity work.a429_sdp_ram
            generic map (G_ADDR_W => G_BITDIAG_WORDS_LOG2 + 5, G_DATA_W => 64)
            port map (
                clk   => clk,
                we    => bit_we,
                waddr => bit_waddr,
                wdata => bit_wdata,
                raddr => std_logic_vector(next_bit_ptr),
                rdata => bit_rdata
            );
    end generate;

    -- Register okuma eşlemeleri
    reg_out.status_act_cfg   <= act_mode;
    reg_out.act              <= act_cfg;

    reg_out.word_rd_ts_msb   <= word_rdata(143 downto 112);
    reg_out.word_rd_ts_lsb   <= word_rdata(111 downto 80);
    reg_out.word_rd_data     <= word_rdata(79 downto 48);
    reg_out.word_rd_gap      <= word_rdata(47 downto 16);
    reg_out.word_rd_gap_err  <= word_rdata(15 downto 0);

    reg_out.err_rd_ts_msb    <= err_rdata(127 downto 96);
    reg_out.err_rd_ts_lsb    <= err_rdata(95 downto 64);
    reg_out.err_rd_code      <= err_rdata(63 downto 48);
    reg_out.err_rd_addr      <= err_rdata(47 downto 32);
    reg_out.err_rd_data      <= err_rdata(31 downto 0);

    reg_out.bit_rd_pulse     <= bit_rdata(63 downto 48);
    reg_out.bit_rd_pulse_err <= bit_rdata(47 downto 32);
    reg_out.bit_rd_null      <= bit_rdata(31 downto 16);
    reg_out.bit_rd_null_err  <= bit_rdata(15 downto 0);

    reg_out.chk_ok_cnt       <= chk_ok_cnt;
    reg_out.chk_err_cnt      <= chk_err_cnt;
    reg_out.chk_fifo_level   <= chk_fifo_level;
    reg_out.chk_fifo_ovf     <= chk_fifo_ovf;

end architecture rtl;
