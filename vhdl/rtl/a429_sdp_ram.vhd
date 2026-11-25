--------------------------------------------------------------------------------
-- Dosya       : a429_sdp_ram.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Word RAM (144-bit), Error RAM (128-bit) ve Bit Diagnostic RAM (64-bit)
--   için generic, tek saatli Simple Dual-Port RAM bloğu.
--
-- Gereksinimler:
--   REQ-1 : Derinlik 2^G_ADDR_W, veri genişliği G_DATA_W bit olarak generic
--           parametrelerle ayarlanabilmelidir.
--   REQ-2 : Yazma portu (we, waddr, wdata) ile okuma portu (raddr, rdata)
--           bağımsız çalışmalı, Xilinx/Intel sentez araçlarında BRAM olarak
--           çıkarılabilmelidir (reset içermeyen standart SDP şablonu).
--   REQ-3 : Okuma senkron olup tam 1 clk gecikmelidir (raddr yükselen kenarda
--           örneklenir, rdata ertesi clk'de geçerli olur).
--   REQ-4 : Yazma işlemi yalnızca we = '1' iken waddr adresini günceller.
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
    constant C_DEPTH : positive := 2 ** G_ADDR_W;
    type t_mem is array (0 to C_DEPTH - 1) of std_logic_vector(G_DATA_W - 1 downto 0);
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
