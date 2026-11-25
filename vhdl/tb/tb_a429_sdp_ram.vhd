--------------------------------------------------------------------------------
-- tb_a429_sdp_ram — a429_sdp_ram birim testi (VHDL-93 / VHDL-2008 uyumlu)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_a429_sdp_ram is
end entity tb_a429_sdp_ram;

architecture sim of tb_a429_sdp_ram is
    constant T_CLK  : time := 20 ns;
    signal clk      : std_logic := '0';
    signal sim_done : boolean := false;
    signal we       : std_logic := '0';
    signal waddr    : std_logic_vector(3 downto 0) := (others => '0');
    signal wdata    : std_logic_vector(63 downto 0) := (others => '0');
    signal raddr    : std_logic_vector(3 downto 0) := (others => '0');
    signal rdata    : std_logic_vector(63 downto 0);
    signal errors   : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_sdp_ram
        generic map (G_ADDR_W => 4, G_DATA_W => 64)
        port map (clk => clk, we => we, waddr => waddr, wdata => wdata, raddr => raddr, rdata => rdata);

    process
        procedure tick is
        begin
            wait until rising_edge(clk);
            wait for 1 ns;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then
                report "HATA: " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;
    begin
        -- Tüm 16 adrese benzersiz desen yaz
        for i in 0 to 15 loop
            we    <= '1';
            waddr <= std_logic_vector(to_unsigned(i, 4));
            wdata <= std_logic_vector(to_unsigned(i * 17 + 1, 32)) & std_logic_vector(to_unsigned(16#A500# + i, 32));
            tick;
        end loop;
        we <= '0';

        -- Geri oku ve 1 clk gecikmeyi doğrula
        for i in 0 to 15 loop
            raddr <= std_logic_vector(to_unsigned(i, 4));
            tick;
            chk(rdata = std_logic_vector(to_unsigned(i * 17 + 1, 32)) & std_logic_vector(to_unsigned(16#A500# + i, 32)),
                "Adres " & integer'image(i) & " geri okuma hatasi");
        end loop;

        -- we=0 iken yazma olmamalı, eşzamanlı farklı adrese yazma + okuma çalışmalı
        we    <= '0';
        waddr <= x"3";
        wdata <= (others => '1');
        raddr <= x"3";
        tick;
        chk(rdata /= x"FFFFFFFFFFFFFFFF", "we=0 iken veri degismemeli");

        we    <= '1';
        waddr <= x"5";
        wdata <= x"DEADBEEFCAFEBABE";
        raddr <= x"2";
        tick;
        chk(rdata = std_logic_vector(to_unsigned(2 * 17 + 1, 32)) & std_logic_vector(to_unsigned(16#A502#, 32)),
            "Eszamanli yazma sirasinda farkli adresten okuma bozulmamali");
        we    <= '0';
        raddr <= x"5";
        tick;
        chk(rdata = x"DEADBEEFCAFEBABE", "Yeni yazilan adres 5 okunmali");

        if errors = 0 then
            report "PASS: tb_a429_sdp_ram" severity note;
        else
            report "FAIL: tb_a429_sdp_ram (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
