--------------------------------------------------------------------------------
-- a429_tx_core
--
-- Sentezlenebilir ARINC 429 Verici (DESIGN.md §6.3):
--   * MUX1 (builder_en)    : Word Builder (Label/SDI/Data/SSM + Parity) veya EXT_DATA
--   * MUX2 (msg_sched_en)  : Message Scheduler (INITIAL_DELAY + INTER_WORD_GAP) veya SEND_CMD
--   * MUX3 (transmitter_en): Word Transmitter veya EXT_HIGH/EXT_LOW override (11 = HIGH-Z)
--
-- Bit sırası (ARINC 429 standardı & a429_rx_decoder uyumu):
--   word_tx[7:0]  = Label (hatta MSB -> LSB, önce bit 7 gönderilir)
--   word_tx[31:8] = SDI, Data, SSM, Parity (hatta LSB -> MSB, bit 8 -> 31)
--
-- Zamanlama (a429/txlive.py uyumu):
--   Word Transmitter : 32 * (pulse_dur + null_dur) + gap_dur boyunca tx_busy = '1'
--   Message Scheduler: tx_busy = '0' olduktan sonra max(1, inter_word_gap) clk bekler
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
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
        parity_type    : in  std_logic;   -- 1: Odd, 0: Even
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
    type t_wt_state is (WT_IDLE, WT_PULSE, WT_NULL, WT_GAP);
    type t_sc_state is (SC_IDLE, SC_INIT_DELAY, SC_WAIT_TX, SC_INTER_GAP);

    signal wt_state  : t_wt_state;
    signal sc_state  : t_sc_state;

    signal mux1_word : std_logic_vector(31 downto 0);
    signal lat_word  : std_logic_vector(31 downto 0);
    signal bit_idx   : natural range 0 to 31;
    signal dur_cnt   : unsigned(31 downto 0);

    signal r_pulse   : unsigned(15 downto 0);
    signal r_null    : unsigned(15 downto 0);
    signal r_gap     : unsigned(31 downto 0);

    signal sc_cnt    : unsigned(31 downto 0);
    signal sc_trig   : std_logic;

    signal wt_high   : std_logic;
    signal wt_low    : std_logic;
    signal busy_i    : std_logic;

    function calc_parity(w31 : std_logic_vector(30 downto 0); odd : std_logic) return std_logic is
        variable p : std_logic := '0';
    begin
        for i in 0 to 30 loop
            p := p xor w31(i);
        end loop;
        if odd = '1' then
            return not p;   -- Toplam 1 sayısı tek olsun
        else
            return p;       -- Toplam 1 sayısı çift olsun
        end if;
    end function;

    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then
            return w(7 - k);
        else
            return w(k);
        end if;
    end function;
begin

    -- MUX1: Word Builder vs EXT_DATA
    process (builder_en, label_val, sdi, data, ssm, parity_type, ext_data)
        variable w31 : std_logic_vector(30 downto 0);
    begin
        if builder_en = '1' then
            w31       := ssm & data & sdi & label_val;
            mux1_word <= calc_parity(w31, parity_type) & w31;
        else
            mux1_word <= ext_data;
        end if;
    end process;

    busy_i <= '0' when wt_state = WT_IDLE else '1';

    -- Message Scheduler (MUX2 kaynağı)
    process (clk, rst_n)
        variable v_gap : unsigned(31 downto 0);
    begin
        if rst_n = '0' then
            sc_state <= SC_IDLE;
            sc_cnt   <= (others => '0');
            sc_trig  <= '0';
        elsif rising_edge(clk) then
            sc_trig <= '0';
            if soft_rst = '1' or transmitter_en = '0' or msg_sched_en = '0' or sched_en = '0' then
                sc_state <= SC_IDLE;
                sc_cnt   <= (others => '0');
            else
                case sc_state is
                    when SC_IDLE =>
                        if unsigned(initial_delay) = 0 then
                            if busy_i = '0' then
                                sc_trig  <= '1';
                                sc_state <= SC_WAIT_TX;
                            end if;
                        else
                            sc_cnt   <= unsigned(initial_delay) - 1;
                            sc_state <= SC_INIT_DELAY;
                        end if;

                    when SC_INIT_DELAY =>
                        if sc_cnt = 0 then
                            if busy_i = '0' then
                                sc_trig  <= '1';
                                sc_state <= SC_WAIT_TX;
                            end if;
                        else
                            sc_cnt <= sc_cnt - 1;
                        end if;

                    when SC_WAIT_TX =>
                        -- sc_trig'den sonra Word Transmitter busy=1 yapar; busy=0 olunca gap say
                        if sc_trig = '0' and busy_i = '0' then
                            v_gap := unsigned(inter_word_gap);
                            if v_gap <= 1 then
                                sc_trig <= '1';   -- en az 1 clk busy=0 garantilendi
                            else
                                sc_cnt   <= v_gap - 2;
                                sc_state <= SC_INTER_GAP;
                            end if;
                        end if;

                    when SC_INTER_GAP =>
                        if sc_cnt = 0 then
                            if busy_i = '0' then
                                sc_trig  <= '1';
                                sc_state <= SC_WAIT_TX;
                            end if;
                        else
                            sc_cnt <= sc_cnt - 1;
                        end if;
                end case;
            end if;
        end if;
    end process;

    -- Word Transmitter FSM
    process (clk, rst_n)
        variable v_trig : std_logic;
        variable v_p    : unsigned(15 downto 0);
        variable v_n    : unsigned(15 downto 0);
        variable v_g    : unsigned(31 downto 0);
        variable v_b    : std_logic;
    begin
        if rst_n = '0' then
            wt_state <= WT_IDLE;
            lat_word <= (others => '0');
            bit_idx  <= 0;
            dur_cnt  <= (others => '0');
            r_pulse  <= to_unsigned(250, 16);
            r_null   <= to_unsigned(250, 16);
            r_gap    <= to_unsigned(2000, 32);
            wt_high  <= '0';
            wt_low   <= '0';
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                wt_state <= WT_IDLE;
                lat_word <= (others => '0');
                bit_idx  <= 0;
                dur_cnt  <= (others => '0');
                wt_high  <= '0';
                wt_low   <= '0';
            else
                if msg_sched_en = '1' then
                    v_trig := sc_trig;
                else
                    v_trig := send_cmd;
                end if;

                case wt_state is
                    when WT_IDLE =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if transmitter_en = '1' and v_trig = '1' then
                            v_p := unsigned(act_cfg.pulse_dur);
                            v_n := unsigned(act_cfg.null_dur);
                            v_g := unsigned(act_cfg.gap_dur);
                            if v_p = 0 then v_p := to_unsigned(1, 16); end if;
                            if v_n = 0 then v_n := to_unsigned(1, 16); end if;
                            if v_g = 0 then v_g := to_unsigned(1, 32); end if;

                            lat_word <= mux1_word;
                            r_pulse  <= v_p;
                            r_null   <= v_n;
                            r_gap    <= v_g;
                            bit_idx  <= 0;
                            dur_cnt  <= resize(v_p - 1, 32);
                            v_b      := wire_bit(mux1_word, 0);
                            wt_high  <= v_b;
                            wt_low   <= not v_b;
                            wt_state <= WT_PULSE;
                        end if;

                    when WT_PULSE =>
                        if dur_cnt = 0 then
                            wt_high  <= '0';
                            wt_low   <= '0';
                            dur_cnt  <= resize(r_null - 1, 32);
                            wt_state <= WT_NULL;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;

                    when WT_NULL =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if dur_cnt = 0 then
                            if bit_idx = 31 then
                                dur_cnt  <= r_gap - 1;
                                wt_state <= WT_GAP;
                            else
                                bit_idx  <= bit_idx + 1;
                                dur_cnt  <= resize(r_pulse - 1, 32);
                                v_b      := wire_bit(lat_word, bit_idx + 1);
                                wt_high  <= v_b;
                                wt_low   <= not v_b;
                                wt_state <= WT_PULSE;
                            end if;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;

                    when WT_GAP =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if dur_cnt = 0 then
                            wt_state <= WT_IDLE;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;
                end case;
            end if;
        end if;
    end process;

    -- MUX3: Word Transmitter vs EXT_HIGH/EXT_LOW override (glitch'siz kayıtlı çıkış)
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

    tx_slp       <= act_cfg.slp;
    tx_busy      <= busy_i;
    tx_sched_act <= '0' when sc_state = SC_IDLE else '1';
    tx_word_tx   <= lat_word;

end architecture rtl;
