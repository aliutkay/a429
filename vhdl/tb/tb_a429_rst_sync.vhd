--------------------------------------------------------------------------------
-- tb_a429_rst_sync — a429_rst_sync birim testi (VHDL-93 / VHDL-2008 uyumlu)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity tb_a429_rst_sync is
end entity tb_a429_rst_sync;

architecture sim of tb_a429_rst_sync is
    constant T_CLK   : time := 20 ns;
    signal clk       : std_logic := '0';
    signal sim_done  : boolean := false;
    signal rst_n     : std_logic := '0';
    signal rst_n_out : std_logic;
    signal errors    : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rst_sync
        port map (clk => clk, rst_n => rst_n, rst_n_sync => rst_n_out);

    process
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then
                report "HATA: " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;
    begin
        -- 1) Asenkron assert kontrolü (saat kenarı olmadan)
        rst_n <= '0';
        wait for 3 ns;
        chk(rst_n_out = '0', "rst_n=0 aninda rst_n_sync=0 olmali");

        -- 2) Senkron deassert kontrolü (tam 2 saat kenarı)
        wait until rising_edge(clk);
        rst_n <= '1';
        wait for 1 ns;
        chk(rst_n_out = '0', "rst_n=1 hemen sonra cikis 0 kalmali");
        wait until rising_edge(clk);
        wait for 1 ns;
        chk(rst_n_out = '0', "1. saat kenarinda cikis hala 0 olmali");
        wait until rising_edge(clk);
        wait for 1 ns;
        chk(rst_n_out = '1', "2. saat kenarinda cikis 1 olmali");

        -- 3) Çalışırken ani asenkron reset
        wait for 4 ns;
        rst_n <= '0';
        wait for 2 ns;
        chk(rst_n_out = '0', "Calisirken rst_n=0 aninda rst_n_sync=0 olmali");

        if errors = 0 then
            report "PASS: tb_a429_rst_sync" severity note;
        else
            report "FAIL: tb_a429_rst_sync (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
