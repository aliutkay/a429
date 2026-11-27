--------------------------------------------------------------------------------
-- tb_a429_glitch_filter — a429_glitch_filter birim testi (VHDL-93 / VHDL-2008)
--   * kısa glitch bastırma, glitch_tick, total_cnt (olay), win_cnt (glitch clk toplamı)
--   * glitch_size+1 clk sonra yeni stable durum kabulü ve win_cnt sıfırlama
--   * darbe süresi koruma ve soft_rst kontrolü
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_a429_glitch_filter is
end entity tb_a429_glitch_filter;

architecture sim of tb_a429_glitch_filter is
    constant T_CLK : time := 20 ns;
    signal clk     : std_logic := '0';
    signal sim_done: boolean := false;
    signal rst_n   : std_logic := '0';
    signal soft_rst: std_logic := '0';
    signal gsize   : std_logic_vector(15 downto 0) := std_logic_vector(to_unsigned(4, 16));
    signal hi_in   : std_logic := '0';
    signal lo_in   : std_logic := '0';
    signal hi_out  : std_logic;
    signal lo_out  : std_logic;
    signal gtick   : std_logic;
    signal gtot    : std_logic_vector(15 downto 0);
    signal gwin    : std_logic_vector(15 downto 0);
    signal errors  : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_glitch_filter
        generic map (G_SIZE_W => 16, G_CNT_W => 16)
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            glitch_size => gsize,
            rx_high_in => hi_in, rx_low_in => lo_in,
            rx_high_out => hi_out, rx_low_out => lo_out,
            glitch_tick => gtick, glitch_total_cnt => gtot, glitch_win_cnt => gwin
        );

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop
                wait until rising_edge(clk);
                wait for 1 ns;
            end loop;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then
                report "HATA: " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;
        variable high_clks : natural := 0;
    begin
        rst_n <= '0';
        tick(3);
        rst_n <= '1';
        tick(2);

        -- 1) 3 clk'lik kısa glitch (< glitch_size+1 = 5) bastırılmalı
        hi_in <= '1'; lo_in <= '0';
        tick(3);
        hi_in <= '0'; lo_in <= '0';
        tick(1);
        chk(hi_out = '0' and lo_out = '0', "Kisa glitch cikisa yansimamali");
        chk(gtick = '1' and unsigned(gtot) = 1 and unsigned(gwin) = 3,
            "3 clk glitch: total_cnt=1 (olay), win_cnt=3 (clk) olmali");

        -- 2) Bir glitch daha ("11" 2 clk) -> gtot=2, gwin=3+2=5
        hi_in <= '1'; lo_in <= '1';
        tick(2);
        hi_in <= '0'; lo_in <= '0';
        tick(1);
        chk(unsigned(gtot) = 2 and unsigned(gwin) = 5, "Ikinci glitch: total=2, win=5 clk olmali");

        -- 2b) Zincir glitch: HIGH 1 clk -> LOW 4 clk -> NULL: iki olay, 1 + 4 clk
        hi_in <= '1'; lo_in <= '0';
        tick(1);
        hi_in <= '0'; lo_in <= '1';
        tick(1);
        chk(unsigned(gtot) = 3 and unsigned(gwin) = 6, "Zincir glitch 1. parca: total=3, win=6 olmali");
        tick(3);
        hi_in <= '0'; lo_in <= '0';
        tick(1);
        chk(hi_out = '0' and lo_out = '0', "4 clk LOW (< 5) stable olmamali");
        chk(unsigned(gtot) = 4 and unsigned(gwin) = 10, "Zincir glitch 2. parca: total=4, win=10 olmali");

        -- 3) 20 clk'lik gerçek HIGH darbesi -> 5 clk gecikmeyle çıkmalı, toplam 20 clk sürmeli ve gwin=0 olmalı
        hi_in <= '1'; lo_in <= '0';
        high_clks := 0;
        for i in 1 to 20 loop
            tick(1);
            if hi_out = '1' then high_clks := high_clks + 1; end if;
        end loop;
        chk(hi_out = '1' and unsigned(gwin) = 0, "Gecerli darbe kabul edilmeli ve gwin sifirlanmali");
        hi_in <= '0'; lo_in <= '0';
        for i in 1 to 10 loop
            tick(1);
            if hi_out = '1' then high_clks := high_clks + 1; end if;
        end loop;
        chk(hi_out = '0' and high_clks = 20, "Darbe suresi tam 20 clk korunmali");

        -- 4) soft_rst testi
        soft_rst <= '1';
        tick(1);
        soft_rst <= '0';
        chk(unsigned(gtot) = 0 and unsigned(gwin) = 0, "soft_rst sayaclari sifirlamali");

        if errors = 0 then
            report "PASS: tb_a429_glitch_filter" severity note;
        else
            report "FAIL: tb_a429_glitch_filter (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
