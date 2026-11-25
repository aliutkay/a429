--------------------------------------------------------------------------------
-- tb_a429_timestamp — a429_timestamp birim testi (VHDL-93 / VHDL-2008 uyumlu)
--   * sayma, durdurma (ts_en=0), temizleme (ts_clr), soft_rst
--   * easyaxil o_ts_lsb_rd zamanlaması ile atomik TS_MSB latch doğrulaması
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_a429_timestamp is
end entity tb_a429_timestamp;

architecture sim of tb_a429_timestamp is
    constant T_CLK   : time := 20 ns;
    signal clk       : std_logic := '0';
    signal sim_done  : boolean := false;
    signal rst_n     : std_logic := '0';
    signal soft_rst  : std_logic := '0';
    signal ts_en     : std_logic := '1';
    signal ts_clr    : std_logic := '0';
    signal ts_lsb_rd : std_logic := '0';
    signal ts_now    : std_logic_vector(63 downto 0);
    signal ts_lsb    : std_logic_vector(31 downto 0);
    signal ts_msb    : std_logic_vector(31 downto 0);
    signal errors    : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_timestamp
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            ts_en => ts_en, ts_clr => ts_clr, ts_lsb_rd => ts_lsb_rd,
            ts_now => ts_now, ts_lsb => ts_lsb, ts_msb => ts_msb
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
        variable v_before : unsigned(31 downto 0);
    begin
        rst_n <= '0';
        tick(3);
        chk(unsigned(ts_now) = 0 and unsigned(ts_msb) = 0, "Reset degeri 0 olmali");

        rst_n <= '1';
        ts_en <= '1';
        tick(10);
        wait for 1 ns;
        chk(unsigned(ts_lsb) = 10 and unsigned(ts_now) = 10, "10 clk sonra ts=10 olmali");

        -- Duraklatma
        ts_en <= '0';
        tick(5);
        wait for 1 ns;
        chk(unsigned(ts_lsb) = 10, "ts_en=0 iken sayac sabit kalmali");

        -- ts_clr ile sıfırlama
        ts_clr <= '1';
        tick(1);
        ts_clr <= '0';
        wait for 1 ns;
        chk(unsigned(ts_now) = 0, "ts_clr sayaci sifirlamali");

        -- Atomik TS_LSB okuma + ertesi clk ts_lsb_rd latch testi
        ts_en <= '1';
        tick(4);
        v_before := unsigned(ts_lsb);
        ts_lsb_rd <= '1';
        tick(1);
        ts_lsb_rd <= '0';
        wait for 1 ns;
        chk(unsigned(ts_msb) = 0 and unsigned(ts_lsb) = v_before + 1, "ts_lsb_rd msb_d1 degerini latch etmeli");

        -- soft_rst sıfırlaması
        soft_rst <= '1';
        tick(1);
        soft_rst <= '0';
        wait for 1 ns;
        chk(unsigned(ts_now) = 0, "soft_rst sayaci sifirlamali");

        if errors = 0 then
            report "PASS: tb_a429_timestamp" severity note;
        else
            report "FAIL: tb_a429_timestamp (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
