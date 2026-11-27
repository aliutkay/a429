--------------------------------------------------------------------------------
-- tb_a429_tx_transmitter — a429_tx_transmitter birim testi (VHDL-93 / 2008)
--   * 32 bit serileştirme sırası (Label MSB-first, SDI/Data/SSM/Parity LSB-first)
--   * pulse_dur / null_dur / gap_dur clock sayımları, tx_busy, meşgulken tetik reddi
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_tx_transmitter is
end entity tb_a429_tx_transmitter;

architecture sim of tb_a429_tx_transmitter is
    constant T_CLK : time := 20 ns;
    constant C_P   : natural := 4;
    constant C_N   : natural := 6;
    constant C_G   : natural := 16;

    signal clk, rst_n, soft_rst, start_trig : std_logic := '0';
    signal sim_done : boolean := false;
    signal act_cfg  : t_tx_cfg := (pulse_dur => u16(C_P), null_dur => u16(C_N), gap_dur => u32(C_G), slp => '1');
    signal word_in  : std_logic_vector(31 downto 0) := (others => '0');
    signal lh, ll, busy : std_logic;
    signal word_tx  : std_logic_vector(31 downto 0);
    signal errors   : natural := 0;

    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then return w(7 - k); else return w(k); end if;
    end function;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_tx_transmitter
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            act_cfg => act_cfg, start_trig => start_trig, word_in => word_in,
            line_high => lh, line_low => ll, tx_busy => busy, word_tx => word_tx
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
        constant W_TEST : std_logic_vector(31 downto 0) := x"B76543A5";
        variable exp_b  : std_logic;
    begin
        rst_n <= '0'; tick; tick; rst_n <= '1'; tick;
        chk(busy = '0' and lh = '0' and ll = '0', "Reset sonrasi IDLE ve NULL olmali");

        -- Gönderimi başlat ve ertesi clk word_in'i değiştir (latch edildiğini doğrula)
        word_in <= W_TEST; start_trig <= '1'; tick;
        start_trig <= '0'; word_in <= x"00000000";
        chk(busy = '1' and word_tx = W_TEST, "Ilk clk'de busy=1 ve word_tx=W_TEST olmali");

        -- 32 bitin her bir pulse (C_P clk) ve null (C_N clk) fazını tek tek kontrol et
        for k in 0 to 31 loop
            exp_b := wire_bit(W_TEST, k);
            for p in 1 to C_P loop
                chk(lh = exp_b and ll = (not exp_b) and busy = '1',
                    "Bit " & integer'image(k) & " pulse polaritesi yanlis");
                -- Gönderim ortasında sahte start_trig yok sayılmalı
                if k = 5 and p = 2 then start_trig <= '1'; else start_trig <= '0'; end if;
                tick;
            end loop;
            for n in 1 to C_N loop
                chk(lh = '0' and ll = '0' and busy = '1', "Bit " & integer'image(k) & " null fazinda 00 olmali");
                tick;
            end loop;
        end loop;

        -- Gap: C_G - 1 clk WT_GAP (NULL, busy=1) + 1 clk WT_IDLE (NULL, busy=0) = hatta tam C_G clk
        for g in 1 to C_G - 1 loop
            chk(lh = '0' and ll = '0' and busy = '1', "Gap fazinda NULL ve busy=1 olmali");
            tick;
        end loop;
        chk(busy = '0' and lh = '0' and ll = '0', "Gap'in son clk'i WT_IDLE'da (busy=0, NULL) olmali");
        -- Bu clk'te gelen tetik ile yeni Word, son bitin null'undan tam C_N + C_G clk sonra başlar
        word_in <= W_TEST; start_trig <= '1'; tick; start_trig <= '0';
        exp_b := wire_bit(W_TEST, 0);
        chk(lh = exp_b and ll = (not exp_b) and busy = '1', "Ardisik Word gap tam C_G clk olmali");
        for k in 1 to 32 * (C_P + C_N) + C_G + 2 loop
            tick;
        end loop;
        chk(busy = '0' and lh = '0' and ll = '0', "Ikinci Word sonrasi WT_IDLE'a donmeli");

        -- soft_rst gönderim ortasında kesebilmeli
        word_in <= W_TEST; start_trig <= '1'; tick; start_trig <= '0';
        tick; tick;
        soft_rst <= '1'; tick; soft_rst <= '0';
        chk(busy = '0' and lh = '0' and ll = '0', "soft_rst gonderimi hemen kesmeli");

        if errors = 0 then
            report "PASS: tb_a429_tx_transmitter" severity note;
        else
            report "FAIL: tb_a429_tx_transmitter (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
