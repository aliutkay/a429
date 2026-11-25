--------------------------------------------------------------------------------
-- a429_sdp_ram
--
-- Generic Simple Dual-Port RAM (tek clock, 1 clk senkron okuma).
-- Xilinx / Intel sentez araçları tarafından BRAM olarak çıkarılır.
-- raddr AXI4-Lite register'ından sürülür; sonraki okuma erişiminde rdata hazırdır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_sdp_ram is
    generic (
        G_ADDR_W : positive := 8;
        G_DATA_W : positive := 32
    );
    port (
        clk   : in  std_logic;
        we    : in  std_logic;
        waddr : in  std_logic_vector(G_ADDR_W - 1 downto 0);
        wdata : in  std_logic_vector(G_DATA_W - 1 downto 0);
        raddr : in  std_logic_vector(G_ADDR_W - 1 downto 0);
        rdata : out std_logic_vector(G_DATA_W - 1 downto 0)
    );
end entity a429_sdp_ram;

architecture rtl of a429_sdp_ram is
    type t_mem is array (0 to (2 ** G_ADDR_W) - 1) of std_logic_vector(G_DATA_W - 1 downto 0);
    signal mem : t_mem := (others => (others => '0'));
begin

    process (clk)
    begin
        if rising_edge(clk) then
            if we = '1' then
                mem(to_integer(unsigned(waddr))) <= wdata;
            end if;
            rdata <= mem(to_integer(unsigned(raddr)));
        end if;
    end process;

end architecture rtl;
