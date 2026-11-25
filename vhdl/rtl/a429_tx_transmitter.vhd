--------------------------------------------------------------------------------
-- Dosya       : a429_tx_transmitter.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   32-bit ARINC 429 Word'ünü RZ (Return-to-Zero) bipolar formatında (HIGH/LOW)
--   seri olarak hatta süren Word Transmitter FSM'i.
--   a429_tx_core içindeki MUX 3'ün (transmitter_en = '1') veri kaynağıdır.
--
-- Gereksinimler:
--   REQ-1 : Yalnızca WT_IDLE durumundayken ve start_trig = '1' iken gönderime
--           başlar; gönderim sırasında (tx_busy = '1') gelen tetikler yok sayılır.
--   REQ-2 : Başlangıç anında word_in ile aktif config (pulse_dur, null_dur,
--           gap_dur) iç kopyaya alınır; böylece Word ortasında veri veya süre
--           değişse bile devam eden Word bozulmaz. Sıfır süre girilmişse en az
--           1 clk'e sabitlenir.
--   REQ-3 : Hat bit sırası ARINC 429 standardına ve a429_rx_decoder'a uygundur:
--             Bit 0..7  : word_in(7 downto 0) — Label MSB önce (bit 7 -> bit 0)
--             Bit 8..31 : word_in(31 downto 8) — SDI, Data, SSM, Parity LSB önce
--   REQ-4 : Her bit pulse_dur clk HIGH ("10" = bit 1) veya LOW ("01" = bit 0),
--           ardından null_dur clk NULL ("00") sürülür. 32. bitten sonra gap_dur
--           clk zorunlu Word Gap ("00") sürülür ve WT_IDLE'a dönülür.
--   REQ-5 : tx_busy tüm 32 bit + gap_dur boyunca '1', WT_IDLE'da '0' olmalıdır.
--           word_tx yakalanan 32-bit Word'ü (TX BIT Checker için) dışarı verir.
--   REQ-6 : soft_rst = '1' veya rst_n = '0' anında FSM WT_IDLE'a, çıkışlar
--           NULL ("00") durumuna döner.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity a429_tx_transmitter is
    port (
        clk        : in  std_logic;
        rst_n      : in  std_logic;
        soft_rst   : in  std_logic;

        act_cfg    : in  t_tx_cfg;
        start_trig : in  std_logic;
        word_in    : in  std_logic_vector(31 downto 0);

        line_high  : out std_logic;
        line_low   : out std_logic;
        tx_busy    : out std_logic;
        word_tx    : out std_logic_vector(31 downto 0)
    );
end entity a429_tx_transmitter;

architecture rtl of a429_tx_transmitter is
    type t_wt_state is (WT_IDLE, WT_PULSE, WT_NULL, WT_GAP);

    signal state    : t_wt_state;
    signal lat_word : std_logic_vector(31 downto 0);
    signal bit_idx  : natural range 0 to 31;
    signal dur_cnt  : unsigned(31 downto 0);
    signal r_pulse  : unsigned(15 downto 0);
    signal r_null   : unsigned(15 downto 0);
    signal r_gap    : unsigned(31 downto 0);
    signal wt_high  : std_logic;
    signal wt_low   : std_logic;

    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then
            return w(7 - k);
        else
            return w(k);
        end if;
    end function;
begin

    process (clk, rst_n)
        variable v_p : unsigned(15 downto 0);
        variable v_n : unsigned(15 downto 0);
        variable v_g : unsigned(31 downto 0);
        variable v_b : std_logic;
    begin
        if rst_n = '0' then
            state    <= WT_IDLE;
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
                state    <= WT_IDLE;
                lat_word <= (others => '0');
                bit_idx  <= 0;
                dur_cnt  <= (others => '0');
                wt_high  <= '0';
                wt_low   <= '0';
            else
                case state is
                    when WT_IDLE =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if start_trig = '1' then
                            v_p := unsigned(act_cfg.pulse_dur);
                            v_n := unsigned(act_cfg.null_dur);
                            v_g := unsigned(act_cfg.gap_dur);
                            if v_p = 0 then v_p := to_unsigned(1, 16); end if;
                            if v_n = 0 then v_n := to_unsigned(1, 16); end if;
                            if v_g = 0 then v_g := to_unsigned(1, 32); end if;

                            lat_word <= word_in;
                            r_pulse  <= v_p;
                            r_null   <= v_n;
                            r_gap    <= v_g;
                            bit_idx  <= 0;
                            dur_cnt  <= resize(v_p - 1, 32);
                            v_b      := wire_bit(word_in, 0);
                            wt_high  <= v_b;
                            wt_low   <= not v_b;
                            state    <= WT_PULSE;
                        end if;

                    when WT_PULSE =>
                        if dur_cnt = 0 then
                            wt_high <= '0';
                            wt_low  <= '0';
                            dur_cnt <= resize(r_null - 1, 32);
                            state   <= WT_NULL;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;

                    when WT_NULL =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if dur_cnt = 0 then
                            if bit_idx = 31 then
                                dur_cnt <= r_gap - 1;
                                state   <= WT_GAP;
                            else
                                bit_idx <= bit_idx + 1;
                                dur_cnt <= resize(r_pulse - 1, 32);
                                v_b     := wire_bit(lat_word, bit_idx + 1);
                                wt_high <= v_b;
                                wt_low  <= not v_b;
                                state   <= WT_PULSE;
                            end if;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;

                    when WT_GAP =>
                        wt_high <= '0';
                        wt_low  <= '0';
                        if dur_cnt = 0 then
                            state <= WT_IDLE;
                        else
                            dur_cnt <= dur_cnt - 1;
                        end if;
                end case;
            end if;
        end if;
    end process;

    line_high <= wt_high;
    line_low  <= wt_low;
    tx_busy   <= '0' when state = WT_IDLE else '1';
    word_tx   <= lat_word;

end architecture rtl;
