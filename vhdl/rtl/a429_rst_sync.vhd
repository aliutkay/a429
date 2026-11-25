--------------------------------------------------------------------------------
-- a429_rst_sync
--
-- Dış aktif-düşük rst_n sinyalini IP clock'una senkronlar:
-- asenkron assert, senkron deassert (2 FF).
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity a429_rst_sync is
    port (
        clk        : in  std_logic;
        rst_n      : in  std_logic;
        rst_n_sync : out std_logic
    );
end entity a429_rst_sync;

architecture rtl of a429_rst_sync is
    signal sync_ff : std_logic_vector(1 downto 0);

    attribute ASYNC_REG : string;
    attribute ASYNC_REG of sync_ff : signal is "TRUE";
begin

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            sync_ff <= (others => '0');
        elsif rising_edge(clk) then
            sync_ff <= sync_ff(0) & '1';
        end if;
    end process;

    rst_n_sync <= sync_ff(1);

end architecture rtl;
