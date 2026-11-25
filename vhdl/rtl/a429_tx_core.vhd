--------------------------------------------------------------------------------
-- Dosya       : a429_tx_core.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   ARINC 429 verici çekirdeği. Üç bağımsız alt bloğu (a429_tx_word_builder,
--   a429_tx_scheduler, a429_tx_transmitter) DESIGN.md §6.3'teki 3 MUX mimarisi
--   ile birleştirir:
--
--     [Label/SDI/Data/SSM/Parity] -> u_builder ─┐
--                                               ├─► MUX 1 (builder_en) ──► mux1_word
--     [EXT_DATA] ───────────────────────────────┘                              │
--                                                                              ▼
--     [INITIAL_DELAY/GAP/SCHED_EN]-> u_sched ───┐                        u_transmitter
--                                               ├─► MUX 2 (msg_sched_en) ─►    │
--     [SEND_CMD] ───────────────────────────────┘                              ▼
--                                                                         wt_high/low
--     [EXT_HIGH / EXT_LOW] ────────────────────────────────────────────────────┤
--                                                                              ▼
--                                                                   MUX 3 (transmitter_en)
--                                                                      (kayıtlı çıkış)
--                                                                              │
--                                                                       tx_high, tx_low
--
-- Gereksinimler:
--   REQ-1 : MUX 1 (builder_en): '1' -> a429_tx_word_builder çıkışı, '0' -> ext_data.
--   REQ-2 : MUX 2 (msg_sched_en): '1' -> a429_tx_scheduler tetiği, '0' -> send_cmd.
--           transmitter_en = '0' (override) iken u_transmitter tetiklenmez.
--   REQ-3 : MUX 3 (transmitter_en): '1' -> u_transmitter (wt_high/wt_low),
--           '0' -> hat override (ext_high/ext_low; "11" = HIGH-Z). Çıkışlar
--           glitch önlemek için kayıtlıdır (1 clk).
--   REQ-4 : tx_slp doğrudan aktif TX config'ten (act_cfg.slp) sürülür.
--   REQ-5 : soft_rst = '1' veya rst_n = '0' durumunda tüm alt bloklar ve
--           tx_high/tx_low çıkışları sıfırlanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;

entity a429_tx_core is
    port (
        clk            : in  std_logic;
        rst_n          : in  std_logic;
        soft_rst       : in  std_logic;

        -- Aktif TX config
        act_cfg        : in  t_tx_cfg;

        -- TX register girişleri
        transmitter_en : in  std_logic;
        msg_sched_en   : in  std_logic;
        builder_en     : in  std_logic;
        label_val      : in  std_logic_vector(7 downto 0);
        sdi            : in  std_logic_vector(1 downto 0);
        data           : in  std_logic_vector(18 downto 0);
        ssm            : in  std_logic_vector(1 downto 0);
        parity_type    : in  std_logic;   -- '1': Odd, '0': Even
        sched_en       : in  std_logic;
        initial_delay  : in  std_logic_vector(31 downto 0);
        inter_word_gap : in  std_logic_vector(31 downto 0);
        send_cmd       : in  std_logic;
        ext_data       : in  std_logic_vector(31 downto 0);
        ext_high       : in  std_logic;
        ext_low        : in  std_logic;

        -- Çıkışlar
        tx_high        : out std_logic;
        tx_low         : out std_logic;
        tx_slp         : out std_logic;
        tx_busy        : out std_logic;
        tx_sched_act   : out std_logic;
        tx_word_tx     : out std_logic_vector(31 downto 0)
    );
end entity a429_tx_core;

architecture rtl of a429_tx_core is
    signal built_word : std_logic_vector(31 downto 0);
    signal mux1_word  : std_logic_vector(31 downto 0);

    signal sched_enable : std_logic;
    signal sched_trig   : std_logic;
    signal mux2_trig    : std_logic;
    signal wt_start     : std_logic;

    signal wt_high    : std_logic;
    signal wt_low     : std_logic;
    signal busy_i     : std_logic;
begin

    -- Alt blok 1: Word Builder
    u_builder : entity work.a429_tx_word_builder
        port map (
            label_val   => label_val,
            sdi         => sdi,
            data        => data,
            ssm         => ssm,
            parity_type => parity_type,
            word_out    => built_word
        );

    -- MUX 1: Word kaynağı seçimi (Word Builder vs EXT_DATA)
    mux1_word <= built_word when builder_en = '1' else ext_data;

    -- Alt blok 2: Message Scheduler
    sched_enable <= transmitter_en and msg_sched_en and sched_en;

    u_scheduler : entity work.a429_tx_scheduler
        port map (
            clk            => clk,
            rst_n          => rst_n,
            soft_rst       => soft_rst,
            enable         => sched_enable,
            tx_busy        => busy_i,
            initial_delay  => initial_delay,
            inter_word_gap => inter_word_gap,
            sched_trig     => sched_trig,
            sched_active   => tx_sched_act
        );

    -- MUX 2: Gönderim tetik seçimi (Message Scheduler vs SEND_CMD)
    mux2_trig <= sched_trig when msg_sched_en = '1' else send_cmd;
    wt_start  <= mux2_trig and transmitter_en;

    -- Alt blok 3: Word Transmitter
    u_transmitter : entity work.a429_tx_transmitter
        port map (
            clk        => clk,
            rst_n      => rst_n,
            soft_rst   => soft_rst,
            act_cfg    => act_cfg,
            start_trig => wt_start,
            word_in    => mux1_word,
            line_high  => wt_high,
            line_low   => wt_low,
            tx_busy    => busy_i,
            word_tx    => tx_word_tx
        );

    -- MUX 3: Hat çıkış seçimi (Word Transmitter vs EXT_HIGH/EXT_LOW override, kayıtlı)
    process (clk, rst_n)
    begin
        if rst_n = '0' then
            tx_high <= '0';
            tx_low  <= '0';
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                tx_high <= '0';
                tx_low  <= '0';
            elsif transmitter_en = '1' then
                tx_high <= wt_high;
                tx_low  <= wt_low;
            else
                tx_high <= ext_high;
                tx_low  <= ext_low;
            end if;
        end if;
    end process;

    tx_slp  <= act_cfg.slp;
    tx_busy <= busy_i;

end architecture rtl;
