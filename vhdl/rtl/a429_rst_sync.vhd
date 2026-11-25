--------------------------------------------------------------------------------
-- Dosya       : a429_rst_sync.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Dış aktif-düşük rst_n reset sinyalini IP saat domain'ine güvenli şekilde
--   senkronize eder (asenkron assert, senkron deassert).
--
-- Gereksinimler:
--   REQ-1 : rst_n = '0' olduğunda saat beklenmeden çıkış rst_n_sync anında
--           '0' olmalıdır (asenkron assert).
--   REQ-2 : rst_n = '1' bırakıldığında metastabiliteyi önlemek için en az 2
--           saat kenarı boyunca '0' tutulup 2. yükselen kenarda '1' olmalıdır
--           (senkron deassert).
--   REQ-3 : 2 kademeli FF zinciri ASYNC_REG = "TRUE" özniteliğine sahip
--           olmalıdır (Xilinx/Vivado yerleşim kısıtı).
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
