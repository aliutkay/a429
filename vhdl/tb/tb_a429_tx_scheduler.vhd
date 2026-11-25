--------------------------------------------------------------------------------
-- tb_a429_tx_scheduler — a429_tx_scheduler birim testi (VHDL-93 / VHDL-2008)
--   * initial_delay = 0 ve > 0, inter_word_gap = 1 ve > 1
--   * enable = 0 ile temiz durdurma ve sched_active kontrolü
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_tx_scheduler is
end entity tb_a429_tx_scheduler;

architecture sim of tb_a429_tx_scheduler is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst, en, tx_busy : std_logic := '0';
    signal sim_done : boolean := false;
    signal init_dly : std_logic_vector(31 downto 0) := (others => '0');
    signal iw_gap   : std_logic_vector(31 downto 0) := u32(1);
    signal trig, act: std_logic;
    signal busy_cnt : natural := 0;
    signal trig_cnt : natural := 0;
    signal errors   : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_tx_scheduler
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            enable => en, tx_busy => tx_busy,
            initial_delay => init_dly, inter_word_gap => iw_gap,
            sched_trig => trig, sched_active => act
        );

    -- Basit sahte Transmitter modeli: her trig'de tam 10 clk tx_busy='1'
    process (clk, rst_n)
    begin
        if rst_n = '0' then
            tx_busy  <= '0';
            busy_cnt <= 0;
            trig_cnt <= 0;
        elsif rising_edge(clk) then
            if trig = '1' then
                trig_cnt <= trig_cnt + 1;
                tx_busy  <= '1';
                busy_cnt <= 9;
            elsif busy_cnt > 0 then
                busy_cnt <= busy_cnt - 1;
            else
                tx_busy  <= '0';
            end if;
        end if;
    end process;

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop wait until rising_edge(clk); wait for 1 ns; end loop;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
        variable c0 : natural;
    begin
        rst_n <= '0'; tick(3); rst_n <= '1'; tick(2);
        chk(act = '0' and trig = '0', "Reset sonrasi pasif olmali");

        -- 1) initial_delay = 5, inter_word_gap = 4 -> ilk 5 clk tetik yok, 6. clk trig='1', 7. clk trig_cnt=1
        init_dly <= u32(5); iw_gap <= u32(4); en <= '1';
        tick(5);
        chk(trig = '0' and trig_cnt = 0 and act = '1', "initial_delay sirasinda tetik uretilmemeli");
        tick(1);
        chk(trig = '1', "initial_delay=5 bitiminde (6. clk) ilk trig='1' olmali");
        tick(1);
        chk(trig_cnt = 1, "Ilk tetik verici tarafindan yakalanmali");

        -- 2) Periyot = 10 (busy) + 4 (gap) = 14 clk -> 30 clk sonra 2 yeni tetik daha (toplam 3)
        tick(30);
        chk(trig_cnt = 3, "inter_word_gap=4 ile toplam 3 tetik olmali");

        -- 3) enable=0 -> durmalı, yeni tetik gelmemeli
        en <= '0';
        tick(2);
        c0 := trig_cnt;
        chk(act = '0', "enable=0 sonrasi sched_active=0 olmali");
        tick(25);
        chk(trig_cnt = c0, "Durdurulunca yeni tetik uretilmemeli");

        -- 4) initial_delay = 0, inter_word_gap = 1 -> 1. clk'de trig='1' ve arka arkaya akış
        init_dly <= u32(0); iw_gap <= u32(1); en <= '1';
        tick(1);
        chk(trig = '1', "initial_delay=0 iken 1. clk'de trig='1' olmali");
        tick(25);
        chk(trig_cnt >= c0 + 3, "inter_word_gap=1 ile ardisik tetikler gelmeli");
        en <= '0'; tick(2);

        if errors = 0 then
            report "PASS: tb_a429_tx_scheduler" severity note;
        else
            report "FAIL: tb_a429_tx_scheduler (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
