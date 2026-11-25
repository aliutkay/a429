--------------------------------------------------------------------------------
-- a429_timestamp
--
-- Ortak 64-bit zaman damgası sayacı (clk cinsinden).
-- AXIL Studio (easyaxil) TS_LSB okuma zamanlaması ile atomik MSB latch:
--   Clk T   : AXI4-Lite okuma kabulü -> axil_read_data <= i_ts_lsb (ts_now[31:0])
--   Clk T+1 : o_ts_lsb_rd = '1' -> bu an ts_msb_d1 (= Clk T'deki ts_now[63:32])
--             msb_latch'e kopyalanır; 32-bit taşma sınırında bile atomiktir.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity a429_timestamp is
    port (
        clk       : in  std_logic;
        rst_n     : in  std_logic;
        soft_rst  : in  std_logic;
        ts_en     : in  std_logic;
        ts_clr    : in  std_logic;
        ts_lsb_rd : in  std_logic;   -- easyaxil o_ts_lsb_rd (okumadan 1 clk sonra '1')
        ts_now    : out std_logic_vector(63 downto 0);
        ts_lsb    : out std_logic_vector(31 downto 0);
        ts_msb    : out std_logic_vector(31 downto 0)
    );
end entity a429_timestamp;

architecture rtl of a429_timestamp is
    signal cnt       : unsigned(63 downto 0);
    signal msb_d1    : std_logic_vector(31 downto 0);
    signal msb_latch : std_logic_vector(31 downto 0);
begin

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            cnt       <= (others => '0');
            msb_d1    <= (others => '0');
            msb_latch <= (others => '0');
        elsif rising_edge(clk) then
            if soft_rst = '1' or ts_clr = '1' then
                cnt       <= (others => '0');
                msb_d1    <= (others => '0');
                msb_latch <= (others => '0');
            else
                msb_d1 <= std_logic_vector(cnt(63 downto 32));
                if ts_lsb_rd = '1' then
                    msb_latch <= msb_d1;
                end if;
                if ts_en = '1' then
                    cnt <= cnt + 1;
                end if;
            end if;
        end if;
    end process;

    ts_now <= std_logic_vector(cnt);
    ts_lsb <= std_logic_vector(cnt(31 downto 0));
    ts_msb <= msb_latch;

end architecture rtl;
