--------------------------------------------------------------------------------
-- Dosya       : a429_tx_word_evt.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   TX vericisinin tx_busy sinyalinin yükselen ve düşen kenarlarını algılayarak
--   1 clock genişliğinde tx_word_start ve tx_word_done olay darbeleri üretir.
--
-- Gereksinimler:
--   REQ-1 : tx_busy '0' -> '1' geçişinde tam 1 clk tx_word_start = '1' üretilir
--           (TX_WORD_CNT artımı ve TX BIT Checker FIFO eklemesi için).
--   REQ-2 : tx_busy '1' -> '0' geçişinde tam 1 clk tx_word_done = '1' üretilir.
--   REQ-3 : rst_n = '0' veya soft_rst = '1' durumunda dahili busy_d1 sıfırlanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity a429_tx_word_evt is
    port (
        clk           : in  std_logic;
        rst_n         : in  std_logic;
        soft_rst      : in  std_logic;
        tx_busy       : in  std_logic;
        tx_word_start : out std_logic;
        tx_word_done  : out std_logic
    );
end entity a429_tx_word_evt;

architecture rtl of a429_tx_word_evt is
    signal busy_d1 : std_logic;
begin

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            busy_d1 <= '0';
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                busy_d1 <= '0';
            else
                busy_d1 <= tx_busy;
            end if;
        end if;
    end process;

    tx_word_start <= tx_busy and (not busy_d1);
    tx_word_done  <= (not tx_busy) and busy_d1;

end architecture rtl;
