--------------------------------------------------------------------------------
-- Dosya       : a429_timestamp.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Tüm RX ve TX BIT logger'ları için ortak 64-bit sistem zaman damgası
--   sayacını (clk cinsinden) ve 32-bit AXI4-Lite bus üzerinden atomik
--   TS_LSB + TS_MSB okuma mekanizmasını sağlar.
--
-- Gereksinimler:
--   REQ-1 : ts_en = '1' iken her yükselen saat kenarında 64-bit sayaç +1 artar;
--           ts_en = '0' iken mevcut değerini korur.
--   REQ-2 : soft_rst = '1', ts_clr = '1' veya rst_n = '0' durumunda sayaç,
--           msb_d1 ve msb_latch sıfırlanır.
--   REQ-3 : Atomik 64-bit okuma: AXIL Studio (easyaxil) TS_LSB okumasından
--           1 clk sonra ts_lsb_rd = '1' darbesi üretir. 32-bit LSB -> MSB
--           taşma sınırında dahi tutarlılık için 1 clk gecikmeli msb_d1
--           değeri msb_latch'e kopyalanır (TS_LSB'nin okunduğu clock'taki MSB).
--   REQ-4 : ts_now(63 downto 0) her clock canlı olarak tüm logger'lara gider.
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
