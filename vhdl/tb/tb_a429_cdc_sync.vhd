--------------------------------------------------------------------------------
-- tb_a429_cdc_sync — a429_cdc_sync birim testi (VHDL-93 / VHDL-2008 uyumlu)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity tb_a429_cdc_sync is
end entity tb_a429_cdc_sync;

architecture sim of tb_a429_cdc_sync is
    constant T_CLK    : time := 20 ns;
    constant C_STAGES : positive := 4;
    signal clk        : std_logic := '0';
    signal sim_done   : boolean := false;
    signal rst_n      : std_logic := '0';
    signal async_in   : std_logic_vector(1 downto 0) := "00";
    signal sync_out   : std_logic_vector(1 downto 0);
    signal errors     : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_cdc_sync
        generic map (G_STAGES => C_STAGES, G_WIDTH => 2, G_RST_VALUE => '0')
        port map (clk => clk, rst_n => rst_n, async_in => async_in, sync_out => sync_out);

    process
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then
                report "HATA: " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;
    begin
        rst_n    <= '0';
        async_in <= "10";
        wait for 5 ns;
        chk(sync_out = "00", "Reset sirasinda cikis G_RST_VALUE=00 olmali");

        wait until rising_edge(clk);
        rst_n <= '1';
        -- Tam G_STAGES = 4 yükselen kenar sonra "10" çıkışta görünmeli
        for k in 1 to C_STAGES - 1 loop
            wait until rising_edge(clk);
            wait for 1 ns;
            chk(sync_out = "00", "G_STAGES oncesi erken cikis");
        end loop;
        wait until rising_edge(clk);
        wait for 1 ns;
        chk(sync_out = "10", "Tam 4 clk sonra sync_out=10 olmali");

        -- "01" geçişini doğrula
        async_in <= "01";
        for k in 1 to C_STAGES - 1 loop
            wait until rising_edge(clk);
            wait for 1 ns;
            chk(sync_out = "10", "01 gecisinde erken cikis");
        end loop;
        wait until rising_edge(clk);
        wait for 1 ns;
        chk(sync_out = "01", "Tam 4 clk sonra sync_out=01 olmali");

        if errors = 0 then
            report "PASS: tb_a429_cdc_sync" severity note;
        else
            report "FAIL: tb_a429_cdc_sync (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
