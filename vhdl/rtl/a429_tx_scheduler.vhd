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
--   REQ-5 : sched_active, FSM SC_IDLE ve SC_DONE dışındayken '1' olur.
--   REQ-6 : sched_count = 0 ise gönderim sınırsızdır (enable düşene kadar).
--           sched_count = N > 0 ise başlangıçta (SC_IDLE'dan çıkarken) N iç
--           kopyaya alınır; tam N sched_trig üretildikten ve son Word bitip
--           tx_busy = '0' olduktan sonra FSM SC_DONE'a geçer, sched_done = '1'
--           olur ve yeni tetik üretilmez. Yeniden başlatmak için enable '0'
--           yapılıp tekrar '1' yapılır (SCHED_EN 0 -> 1).
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
        sched_count    : in  std_logic_vector(31 downto 0) := (others => '0');  -- 0: sınırsız

        sched_trig     : out std_logic;   -- 1 clk Word başlatma darbesi
        sched_active   : out std_logic;   -- '1': Scheduler çalışıyor
        sched_done     : out std_logic    -- '1': sched_count Word gönderildi, durdu
    );
end entity a429_tx_scheduler;

architecture rtl of a429_tx_scheduler is
    type t_sc_state is (SC_IDLE, SC_INIT_DELAY, SC_WAIT_TX, SC_INTER_GAP, SC_DONE);
    signal state   : t_sc_state;
    signal cnt     : unsigned(31 downto 0);
    signal trig_r  : std_logic;
    signal limited : std_logic;              -- '1': sched_count > 0 ile başlatıldı
    signal remain  : unsigned(31 downto 0);  -- kalan tetik sayısı (limited = '1' iken)
begin

    process (clk, rst_n)
        variable v_gap    : unsigned(31 downto 0);
        variable v_remain : unsigned(31 downto 0);
        variable v_fire   : boolean;
    begin
        if rst_n = '0' then
            state   <= SC_IDLE;
            cnt     <= (others => '0');
            trig_r  <= '0';
            limited <= '0';
            remain  <= (others => '0');
        elsif rising_edge(clk) then
            trig_r <= '0';
            if soft_rst = '1' or enable = '0' then
                state   <= SC_IDLE;
                cnt     <= (others => '0');
                limited <= '0';
                remain  <= (others => '0');
            else
                v_remain := remain;
                v_fire   := false;
                case state is
                    when SC_IDLE =>
                        -- Başlangıç: Word sayısı sınırı iç kopyaya alınır
                        v_remain := unsigned(sched_count);
                        if unsigned(sched_count) = 0 then
                            limited <= '0';
                        else
                            limited <= '1';
                        end if;
                        if unsigned(initial_delay) = 0 then
                            if tx_busy = '0' then
                                v_fire := true;
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt   <= unsigned(initial_delay) - 1;
                            state <= SC_INIT_DELAY;
                        end if;

                    when SC_INIT_DELAY =>
                        if cnt = 0 then
                            if tx_busy = '0' then
                                v_fire := true;
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt <= cnt - 1;
                        end if;

                    when SC_WAIT_TX =>
                        -- trig_r darbesinin ertesi clk'inde tx_busy='1' olur;
                        -- Word tamamlanıp tx_busy='0' olunca inter_word_gap sayılır.
                        if trig_r = '0' and tx_busy = '0' then
                            if limited = '1' and remain = 0 then
                                state <= SC_DONE;        -- sched_count Word gönderildi
                            else
                                v_gap := unsigned(inter_word_gap);
                                if v_gap <= 1 then
                                    v_fire := true;      -- en az 1 clk busy=0 garantilendi
                                else
                                    cnt   <= v_gap - 2;
                                    state <= SC_INTER_GAP;
                                end if;
                            end if;
                        end if;

                    when SC_INTER_GAP =>
                        if cnt = 0 then
                            if tx_busy = '0' then
                                v_fire := true;
                                state  <= SC_WAIT_TX;
                            end if;
                        else
                            cnt <= cnt - 1;
                        end if;

                    when SC_DONE =>
                        null;                            -- enable '0' olana kadar bekle
                end case;

                if v_fire then
                    trig_r <= '1';
                    if v_remain /= 0 then
                        v_remain := v_remain - 1;
                    end if;
                end if;
                remain <= v_remain;
            end if;
        end if;
    end process;

    sched_trig   <= trig_r;
    sched_active <= '0' when state = SC_IDLE or state = SC_DONE else '1';
    sched_done   <= '1' when state = SC_DONE else '0';

end architecture rtl;
