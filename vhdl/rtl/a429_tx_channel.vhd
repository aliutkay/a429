--------------------------------------------------------------------------------
-- Dosya       : a429_tx_channel.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   TX kanalının üst sarmalayıcısı: a429_tx_cfg_sel + a429_tx_core (3 alt blok
--   + 3 MUX) + a429_tx_word_evt + 32-bit TX_WORD_CNT sayacı.
--
-- Gereksinimler:
--   REQ-1 : Aktif TX config'i (ACT_PULSE/NULL/GAP/SLP ve TX_STATUS.ACT_CFG)
--           a429_tx_cfg_sel üzerinden yönetir ve AXIL arayüzüne sunar.
--   REQ-2 : Gönderilen her gerçek Word için tx_word_start darbesiyle
--           TX_WORD_CNT +1 artar (Scheduler Δ TX_WORD_CNT ölçümü ile uyumlu).
--   REQ-3 : tx_word_start, tx_word_done ve tx_word_tx sinyallerini TX BIT
--           Word Checker bloğuna iletir.
--   REQ-4 : soft_rst = '1' veya rst_n = '0' durumunda tüm alt bloklar ve
--           TX_WORD_CNT sıfırlanır, config High Speed Preset'e döner.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity a429_tx_channel is
    port (
        clk           : in  std_logic;
        rst_n         : in  std_logic;
        soft_rst      : in  std_logic;

        -- AXIL register arayüzü
        reg_in        : in  t_tx_reg_in;
        reg_out       : out t_tx_reg_out;

        -- Fiziksel çıkışlar (line driver TX1IN, TX0IN, SLP)
        tx_high       : out std_logic;
        tx_low        : out std_logic;
        tx_slp        : out std_logic;

        -- TX BIT Checker olayları
        tx_word_start : out std_logic;
        tx_word_done  : out std_logic;
        tx_word_tx    : out std_logic_vector(31 downto 0)
    );
end entity a429_tx_channel;

architecture rtl of a429_tx_channel is
    signal act_cfg       : t_tx_cfg;
    signal act_mode      : std_logic_vector(1 downto 0);
    signal busy_i        : std_logic;
    signal sched_act_i   : std_logic;
    signal word_start_i  : std_logic;
    signal word_done_i   : std_logic;
    signal word_tx_i     : std_logic_vector(31 downto 0);
    signal r_word_cnt    : unsigned(31 downto 0);
begin

    u_cfg : entity work.a429_tx_cfg_sel
        port map (
            clk       => clk,
            rst_n     => rst_n,
            soft_rst  => soft_rst,
            tx_busy   => busy_i,
            cfg_sel   => reg_in.cfg_sel,
            cfg_apply => reg_in.cfg_apply,
            cust_cfg  => reg_in.cust,
            act_cfg   => act_cfg,
            act_mode  => act_mode
        );

    u_core : entity work.a429_tx_core
        port map (
            clk            => clk,
            rst_n          => rst_n,
            soft_rst       => soft_rst,
            act_cfg        => act_cfg,
            transmitter_en => reg_in.transmitter_en,
            msg_sched_en   => reg_in.msg_sched_en,
            builder_en     => reg_in.builder_en,
            label_val      => reg_in.label_val,
            sdi            => reg_in.sdi,
            data           => reg_in.data,
            ssm            => reg_in.ssm,
            parity_type    => reg_in.parity_type,
            sched_en       => reg_in.sched_en,
            initial_delay  => reg_in.initial_delay,
            inter_word_gap => reg_in.inter_word_gap,
            send_cmd       => reg_in.send_cmd,
            ext_data       => reg_in.ext_data,
            ext_high       => reg_in.ext_high,
            ext_low        => reg_in.ext_low,
            tx_high        => tx_high,
            tx_low         => tx_low,
            tx_slp         => tx_slp,
            tx_busy        => busy_i,
            tx_sched_act   => sched_act_i,
            tx_word_tx     => word_tx_i
        );

    u_evt : entity work.a429_tx_word_evt
        port map (
            clk           => clk,
            rst_n         => rst_n,
            soft_rst      => soft_rst,
            tx_busy       => busy_i,
            tx_word_start => word_start_i,
            tx_word_done  => word_done_i
        );

    -- Gönderilen Word sayacı (word_start ile anında artar -> Scheduler Δ TX_WORD_CNT uyumlu)
    process (clk, rst_n)
    begin
        if rst_n = '0' then
            r_word_cnt <= (others => '0');
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                r_word_cnt <= (others => '0');
            elsif word_start_i = '1' then
                r_word_cnt <= r_word_cnt + 1;
            end if;
        end if;
    end process;

    tx_word_start        <= word_start_i;
    tx_word_done         <= word_done_i;
    tx_word_tx           <= word_tx_i;

    reg_out.act          <= act_cfg;
    reg_out.busy         <= busy_i;
    reg_out.sched_active <= sched_act_i;
    reg_out.act_cfg      <= act_mode;
    reg_out.word_cnt     <= std_logic_vector(r_word_cnt);

end architecture rtl;
