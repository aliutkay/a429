--------------------------------------------------------------------------------
-- a429_tx_word_evt
--
-- tx_busy kenarlarından 1 clk'lik word_start ve word_done olay darbeleri üretir.
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
