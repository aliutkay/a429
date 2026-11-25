--------------------------------------------------------------------------------
-- tb_a429_tx_word_evt — a429_tx_word_evt birim testi (VHDL-93 / VHDL-2008)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity tb_a429_tx_word_evt is
end entity tb_a429_tx_word_evt;

architecture sim of tb_a429_tx_word_evt is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst, tx_busy : std_logic := '0';
    signal sim_done : boolean := false;
    signal ws, wd   : std_logic;
    signal errors   : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_tx_word_evt
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            tx_busy => tx_busy, tx_word_start => ws, tx_word_done => wd
        );

    process
        procedure tick is
        begin
            wait until rising_edge(clk); wait for 1 ns;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
    begin
        rst_n <= '0'; tick; tick; rst_n <= '1'; tick;
        chk(ws = '0' and wd = '0', "Baslangicta 0 olmali");

        -- Yükselen kenar -> 1 clk ws='1'
        tx_busy <= '1'; wait for 1 ns;
        chk(ws = '1' and wd = '0', "tx_busy 0->1 gecisinde ws=1 olmali");
        tick;
        chk(ws = '0' and wd = '0', "1 clk sonra ws=0'a donmeli");
        tick;

        -- Düşen kenar -> 1 clk wd='1'
        tx_busy <= '0'; wait for 1 ns;
        chk(ws = '0' and wd = '1', "tx_busy 1->0 gecisinde wd=1 olmali");
        tick;
        chk(ws = '0' and wd = '0', "1 clk sonra wd=0'a donmeli");

        if errors = 0 then
            report "PASS: tb_a429_tx_word_evt" severity note;
        else
            report "FAIL: tb_a429_tx_word_evt (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
