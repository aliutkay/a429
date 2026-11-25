--------------------------------------------------------------------------------
-- Dosya       : a429_tx_scheduler.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Periyodik ARINC 429 mesaj gönderimi için Message Scheduler FSM'i.
--   a429_tx_core içindeki MUX 2'nin (msg_sched_en = '1') tetik kaynağıdır.
--
-- Gereksinimler:
--   REQ-1 : Yalnızca enable = '1' (transmitter_en='1' AND msg_sched_en='1' AND
--           sched_en='1') iken çalışır; enable = '0' veya soft_rst = '1'
--           durumunda anında SC_IDLE durumuna döner ve yeni tetik üretmez
--           (hatta devam eden Word kesilmez, Transmitter kendisi tamamlar).
--   REQ-2 : Başlatıldığında initial_delay > 0 ise tam initial_delay clock
--           bekledikten sonra ilk 1 clk'lik sched_trig darbesini üretir;
--           initial_delay = 0 ise beklemeden (tx_busy = '0' iken) tetikler.
--   REQ-3 : Her Word bitip tx_busy = '0' olduktan sonra iki Word arasında en az
--           max(1, inter_word_gap) clock bekleyip yeni sched_trig üretir.
--           Böylece tx_busy en az 1 clk '0' kalır ve a429_tx_word_evt her Word
--           için ayrı word_start / word_done darbesi üretebilir.
--   REQ-4 : Toplam mesaj periyodu = 32*(pulse+null) + gap_dur + inter_word_gap
--           (a429/txlive.py hesabı ile birebir uyumlu).
--   REQ-5 : sched_active, FSM SC_IDLE dışındayken '1' olur.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_tx_scheduler is
    port (
        clk            : in  std_logic;
        rst_n          : in  std_logic;
        soft_rst       : in  std_logic;

        enable         : in  std_logic;   -- transmitter_en AND msg_sched_en AND sched_en
        tx_busy        : in  std_logic;
        initial_delay  : in  std_logic_vector(31 downto 0);
        inter_word_gap : in  std_logic_vector(31 downto 0);

        sched_trig     : out std_logic;   -- 1 clk Word başlatma darbesi
        sched_active   : out std_logic    -- '1': Scheduler çalışıyor
    );
end entity a429_tx_scheduler;

architecture rtl of a429_tx_scheduler is
    type t_sc_state is (SC_IDLE, SC_INIT_DELAY, SC_WAIT_TX, SC_INTER_GAP);
    signal state   : t_sc_state;
    signal cnt     : unsigned(31 downto 0);
    signal trig_r  : std_logic;
begin

    process (clk, rst_n)
        variable v_gap : unsigned(31 downto 0);
    begin
        if rst_n = '0' then
            state  <= SC_IDLE;
            cnt    <= (others => '0');
            trig_r <= '0';
        elsif rising_edge(clk) then
            trig_r <= '0';
            if soft_rst = '1' or enable = '0' then
                state <= SC_IDLE;
                cnt   <= (others => '0');
            else
                case state is
                    when SC_IDLE =>
                        if unsigned(initial_delay) = 0 then
                            if tx_busy = '0' then
                                trig_r <= '1';
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt   <= unsigned(initial_delay) - 1;
                            state <= SC_INIT_DELAY;
                        end if;

                    when SC_INIT_DELAY =>
                        if cnt = 0 then
                            if tx_busy = '0' then
                                trig_r <= '1';
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt <= cnt - 1;
                        end if;

                    when SC_WAIT_TX =>
                        -- trig_r darbesinin ertesi clk'inde tx_busy='1' olur;
                        -- Word tamamlanıp tx_busy='0' olunca inter_word_gap sayılır.
                        if trig_r = '0' and tx_busy = '0' then
                            v_gap := unsigned(inter_word_gap);
                            if v_gap <= 1 then
                                trig_r <= '1';   -- en az 1 clk busy=0 garantilendi
                            else
                                cnt   <= v_gap - 2;
                                state <= SC_INTER_GAP;
                            end if;
                        end if;

                    when SC_INTER_GAP =>
                        if cnt = 0 then
                            if tx_busy = '0' then
                                trig_r <= '1';
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt <= cnt - 1;
                        end if;
                end case;
            end if;
        end if;
    end process;

    sched_trig   <= trig_r;
    sched_active <= '0' when state = SC_IDLE else '1';

end architecture rtl;
