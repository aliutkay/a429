--------------------------------------------------------------------------------
-- Dosya       : a429_rx_cfg_sel.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Tek bir RX veya TX BIT kanalı için aktif zamanlama/gürültü/parity config
--   kaynağını (High Speed Preset, Low Speed Preset veya Custom) seçer ve
--   CFG_APPLY darbesiyle shadow -> active kopyalamasını yapar.
--
-- Gereksinimler:
--   REQ-1 : Reset (rst_n = '0') ve soft_rst = '1' sonrasında varsayılan olarak
--           C_RX_PRESET_HS (act_mode = "00") yüklenir.
--   REQ-2 : cfg_sel veya cust_cfg değişse bile cfg_apply = '1' gelmeden
--           act_cfg ve act_mode DEĞİŞMEMELİDİR (shadow izolasyonu).
--   REQ-3 : cfg_apply = '1' geldiğinde 1 clk içinde seçili preset ("00" HS,
--           "01" LS) veya cust_cfg ("10" Custom) aktif çıkışlara (ACT_*) ve
--           act_mode (STATUS.ACT_CFG) portuna aktarılır.
--   REQ-4 : Decoder iç kopyasını yalnızca IDLE/ERR_RECOVERY'de güncellediği
--           için anlık aktivasyon Word ortasında bozulmaya yol açmaz.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;
use work.a429_presets_pkg.all;

entity a429_rx_cfg_sel is
    port (
        clk       : in  std_logic;
        rst_n     : in  std_logic;
        soft_rst  : in  std_logic;
        cfg_sel   : in  std_logic_vector(1 downto 0);
        cfg_apply : in  std_logic;
        cust_cfg  : in  t_rx_cfg;
        act_cfg   : out t_rx_cfg;
        act_mode  : out std_logic_vector(1 downto 0)
    );
end entity a429_rx_cfg_sel;

architecture rtl of a429_rx_cfg_sel is
    signal r_cfg  : t_rx_cfg;
    signal r_mode : std_logic_vector(1 downto 0);
begin

    process (clk, rst_n)
    begin
        if rst_n = '0' then
            r_cfg  <= C_RX_PRESET_HS;
            r_mode <= C_CFG_HS;
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                r_cfg  <= C_RX_PRESET_HS;
                r_mode <= C_CFG_HS;
            elsif cfg_apply = '1' then
                case cfg_sel is
                    when C_CFG_LS =>
                        r_cfg  <= C_RX_PRESET_LS;
                        r_mode <= C_CFG_LS;
                    when C_CFG_CUSTOM =>
                        r_cfg  <= cust_cfg;
                        r_mode <= C_CFG_CUSTOM;
                    when others =>
                        r_cfg  <= C_RX_PRESET_HS;
                        r_mode <= C_CFG_HS;
                end case;
            end if;
        end if;
    end process;

    act_cfg  <= r_cfg;
    act_mode <= r_mode;

end architecture rtl;
