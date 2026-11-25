--------------------------------------------------------------------------------
-- Dosya       : a429_glitch_filter.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Senkronlanmış 2-bitlik ARINC 429 hat durumunu (00 NULL, 10 HIGH, 01 LOW,
--   11 BUS_FAULT) tek sembol olarak filtreleyen, darbe/null/gap sürelerini
--   koruyan glitch filtresi ve gürültü sayacı.
--
-- Gereksinimler:
--   REQ-1 : rx_high_in & rx_low_in iki biti birlikte TEK SEMBOL olarak
--           filtrelenir; böylece iki bitin ayrı filtrelenmesinden doğacak
--           sahte "11" (bus fault) veya "00" geçişleri oluşmaz.
--   REQ-2 : Yeni bir aday hat durumu kesintisiz en az (glitch_size + 1) clk
--           boyunca sabit kalırsa stable_state çıkışına kabul edilir. Bütün
--           geçişler eşit gecikmeyle aktarıldığından darbe/null süreleri korunur.
--   REQ-3 : Aday durum stable olamadan değişirse 1 clk'lik glitch_tick üretilir;
--           glitch_total_cnt (toplam) ve glitch_win_cnt (mevcut stable durum
--           penceresi) doyumlu olarak +1 artar (taşma/sarma yapmaz).
--   REQ-4 : Yeni bir stable durum kabul edildiğinde glitch_win_cnt sıfırlanır
--           (decoder her fazın gürültüsünü bağımsız ölçer).
--   REQ-5 : soft_rst = '1' veya rst_n = '0' durumunda çıkış NULL ("00"), tüm
--           sayaçlar ve zamanlayıcı sıfırlanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_glitch_filter is
    generic (
        G_SIZE_W : positive := 16;   -- glitch_size genişliği
        G_CNT_W  : positive := 16    -- glitch sayaç genişliği
    );
    port (
        clk              : in  std_logic;
        rst_n            : in  std_logic;
        soft_rst         : in  std_logic := '0';

        glitch_size      : in  std_logic_vector(G_SIZE_W - 1 downto 0);  -- clk

        rx_high_in       : in  std_logic;   -- senkronlanmış ham hat
        rx_low_in        : in  std_logic;

        rx_high_out      : out std_logic;   -- filtrelenmiş hat
        rx_low_out       : out std_logic;

        glitch_tick      : out std_logic;   -- glitch görüldüğünde 1 clk
        glitch_total_cnt : out std_logic_vector(G_CNT_W - 1 downto 0);
        glitch_win_cnt   : out std_logic_vector(G_CNT_W - 1 downto 0)
    );
end entity a429_glitch_filter;

architecture rtl of a429_glitch_filter is

    constant C_CNT_MAX  : unsigned(G_CNT_W - 1 downto 0)  := (others => '1');
    constant C_TMR_MAX  : unsigned(G_SIZE_W - 1 downto 0) := (others => '1');

    signal cur_state    : std_logic_vector(1 downto 0);
    signal last_state   : std_logic_vector(1 downto 0);
    signal stable_state : std_logic_vector(1 downto 0);

    signal timer        : unsigned(G_SIZE_W - 1 downto 0);
    signal total_cnt    : unsigned(G_CNT_W - 1 downto 0);
    signal win_cnt      : unsigned(G_CNT_W - 1 downto 0);

begin

    cur_state <= rx_high_in & rx_low_in;

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            last_state   <= "00";
            stable_state <= "00";
            timer        <= (others => '0');
            total_cnt    <= (others => '0');
            win_cnt      <= (others => '0');
            glitch_tick  <= '0';
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                last_state   <= "00";
                stable_state <= "00";
                timer        <= (others => '0');
                total_cnt    <= (others => '0');
                win_cnt      <= (others => '0');
                glitch_tick  <= '0';
            else
                glitch_tick <= '0';

                if cur_state /= last_state then
                    -- Hat değişti. Önceki aday durum stable olamadan değiştiyse glitch.
                    if last_state /= stable_state then
                        glitch_tick <= '1';
                        if total_cnt /= C_CNT_MAX then
                            total_cnt <= total_cnt + 1;
                        end if;
                        if win_cnt /= C_CNT_MAX then
                            win_cnt <= win_cnt + 1;
                        end if;
                    end if;
                    last_state <= cur_state;
                    timer      <= to_unsigned(1, G_SIZE_W);

                elsif last_state /= stable_state then
                    -- Aday durum değişmeden duruyor: yeterli süre geçti mi?
                    if timer >= unsigned(glitch_size) then
                        stable_state <= last_state;
                        win_cnt      <= (others => '0');   -- yeni stable durum, yeni pencere
                    elsif timer /= C_TMR_MAX then
                        timer <= timer + 1;
                    end if;
                end if;
            end if;
        end if;
    end process;

    rx_high_out      <= stable_state(1);
    rx_low_out       <= stable_state(0);
    glitch_total_cnt <= std_logic_vector(total_cnt);
    glitch_win_cnt   <= std_logic_vector(win_cnt);

end architecture rtl;
