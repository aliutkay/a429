--------------------------------------------------------------------------------
-- a429_rx_cfg_sel
--
-- RX / TB kanalı için Preset (HS/LS) veya Custom shadow -> active seçicisi.
-- CFG_APPLY darbesiyle 1 clk içinde aktif değerler ve ACT_CFG güncellenir;
-- decoder iç kopyasını IDLE/ERR_RECOVERY'de güncellediği için yarım Word bozulmaz.
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
