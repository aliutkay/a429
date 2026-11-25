--------------------------------------------------------------------------------
-- a429_glitch_filter
--
-- Süre koruyan glitch filtresi. rx_high/rx_low iki bitlik hat durumu (00 NULL,
-- 10 HIGH, 01 LOW, 11 bus fault) TEK SEMBOL olarak filtrelenir; böylece iki bitin
-- ayrı ayrı filtrelenmesinden doğacak sahte 11 / 00 durumları oluşmaz.
--
-- Yeni bir hat durumu en az glitch_size + 1 clk değişmeden kalırsa geçerli (stable)
-- durum olarak kabul edilir (glitch_size = 0 ve 1 aynı davranır). Daha kısa süren her
-- değişim bir glitch'tir ve çıkışa yansımaz.
-- Bütün geçişler aynı sabit gecikmeyle (glitch_size + 1 clk) çıkışa yansıdığı için
-- pulse / null / gap süreleri korunur.
--
-- Sayaçlar:
--   glitch_total_cnt : başlangıçtan beri toplam glitch (doyumlu)
--   glitch_win_cnt   : mevcut stable durum boyunca görülen glitch (stable durum
--                      değişince sıfırlanır, doyumlu). Decoder faz gürültüsü için kullanır.
--
-- Not: eski arinc429_line_filter'ın filtre kısmıdır; CDC ayrı entity'ye
-- (a429_cdc_sync) alındı, sayaçlar taşmak yerine doyuma gider.
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
