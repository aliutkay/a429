--------------------------------------------------------------------------------
-- tb_a429_rx_cfg_sel — a429_rx_cfg_sel birim testi (VHDL-93 / VHDL-2008 uyumlu)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;
use work.a429_presets_pkg.all;

entity tb_a429_rx_cfg_sel is
end entity tb_a429_rx_cfg_sel;

architecture sim of tb_a429_rx_cfg_sel is
    constant T_CLK   : time := 20 ns;
    signal clk       : std_logic := '0';
    signal sim_done  : boolean := false;
    signal rst_n     : std_logic := '0';
    signal soft_rst  : std_logic := '0';
    signal cfg_sel   : std_logic_vector(1 downto 0) := C_CFG_HS;
    signal cfg_apply : std_logic := '0';
    signal cust_cfg  : t_rx_cfg := C_RX_CFG_ZERO;
    signal act_cfg   : t_rx_cfg;
    signal act_mode  : std_logic_vector(1 downto 0);
    signal errors    : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rx_cfg_sel
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            cfg_sel => cfg_sel, cfg_apply => cfg_apply, cust_cfg => cust_cfg,
            act_cfg => act_cfg, act_mode => act_mode
        );

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop wait until rising_edge(clk); wait for 1 ns; end loop;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
        variable custom1 : t_rx_cfg;
    begin
        rst_n <= '0'; tick(3); rst_n <= '1'; tick(1);
        chk(act_mode = C_CFG_HS and act_cfg = C_RX_PRESET_HS, "Reset sonrasi HS Preset olmali");

        -- Shadow izolasyonu: apply olmadan değişmemeli
        custom1 := (u16(5), u16(50), u16(200), u16(300), u16(400), u16(4), u16(5), u16(20), C_PAR_EVEN);
        cfg_sel  <= C_CFG_CUSTOM;
        cust_cfg <= custom1;
        tick(3);
        chk(act_mode = C_CFG_HS and act_cfg = C_RX_PRESET_HS, "cfg_apply olmadan active degismemeli");

        -- Custom uygula
        cfg_apply <= '1'; tick(1); cfg_apply <= '0';
        chk(act_mode = C_CFG_CUSTOM and act_cfg = custom1, "Custom config 1 clk'de uygulanmali");

        -- LS Preset uygula
        cfg_sel <= C_CFG_LS; cfg_apply <= '1'; tick(1); cfg_apply <= '0';
        chk(act_mode = C_CFG_LS and act_cfg = C_RX_PRESET_LS, "LS Preset uygulanmali");

        -- soft_rst -> HS Preset'e dönüş
        soft_rst <= '1'; tick(1); soft_rst <= '0';
        chk(act_mode = C_CFG_HS and act_cfg = C_RX_PRESET_HS, "soft_rst HS Preset'e donmeli");

        if errors = 0 then
            report "PASS: tb_a429_rx_cfg_sel" severity note;
        else
            report "FAIL: tb_a429_rx_cfg_sel (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
