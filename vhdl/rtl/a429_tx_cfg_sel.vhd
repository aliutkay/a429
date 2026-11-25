--------------------------------------------------------------------------------
-- a429_tx_cfg_sel
--
-- TX kanalı için Preset (HS/LS) veya Custom shadow -> active seçicisi.
-- TX boştayken (tx_busy = '0') CFG_APPLY 1 clk içinde anında uygulanır;
-- gönderim ortasında gelirse Word bitiminde (tx_busy = '0') uygulanır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;
use work.a429_presets_pkg.all;

entity a429_tx_cfg_sel is
    port (
        clk       : in  std_logic;
        rst_n     : in  std_logic;
        soft_rst  : in  std_logic;
        tx_busy   : in  std_logic;
        cfg_sel   : in  std_logic_vector(1 downto 0);
        cfg_apply : in  std_logic;
        cust_cfg  : in  t_tx_cfg;
        act_cfg   : out t_tx_cfg;
        act_mode  : out std_logic_vector(1 downto 0)
    );
end entity a429_tx_cfg_sel;

architecture rtl of a429_tx_cfg_sel is
    signal r_cfg     : t_tx_cfg;
    signal r_mode    : std_logic_vector(1 downto 0);
    signal pend      : std_logic;
    signal pend_sel  : std_logic_vector(1 downto 0);
    signal pend_cust : t_tx_cfg;
begin

    process (clk, rst_n)
        procedure load_cfg(sel : std_logic_vector(1 downto 0); c : t_tx_cfg) is
        begin
            case sel is
                when C_CFG_LS =>
                    r_cfg  <= C_TX_PRESET_LS;
                    r_mode <= C_CFG_LS;
                when C_CFG_CUSTOM =>
                    r_cfg  <= c;
                    r_mode <= C_CFG_CUSTOM;
                when others =>
                    r_cfg  <= C_TX_PRESET_HS;
                    r_mode <= C_CFG_HS;
            end case;
        end procedure;
    begin
        if rst_n = '0' then
            r_cfg     <= C_TX_PRESET_HS;
            r_mode    <= C_CFG_HS;
            pend      <= '0';
            pend_sel  <= C_CFG_HS;
            pend_cust <= C_TX_CFG_ZERO;
        elsif rising_edge(clk) then
            if soft_rst = '1' then
                r_cfg     <= C_TX_PRESET_HS;
                r_mode    <= C_CFG_HS;
                pend      <= '0';
                pend_sel  <= C_CFG_HS;
                pend_cust <= C_TX_CFG_ZERO;
            elsif cfg_apply = '1' then
                if tx_busy = '0' then
                    load_cfg(cfg_sel, cust_cfg);
                    pend <= '0';
                else
                    pend      <= '1';
                    pend_sel  <= cfg_sel;
                    pend_cust <= cust_cfg;
                end if;
            elsif pend = '1' and tx_busy = '0' then
                load_cfg(pend_sel, pend_cust);
                pend <= '0';
            end if;
        end if;
    end process;

    act_cfg  <= r_cfg;
    act_mode <= r_mode;

end architecture rtl;
