--------------------------------------------------------------------------------
-- tb_a429_word_checker — a429_word_checker birim testi (VHDL-93 / VHDL-2008)
--   * OK eşleşme, WORD_MISMATCH, UNEXPECTED_WORD, rx_err_any sessiz FIFO düşürme,
--     NO_ECHO timeout, eşzamanlı timeout+match önceliği, FIFO taşma ve chk_clear
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_word_checker is
end entity tb_a429_word_checker;

architecture sim of tb_a429_word_checker is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst : std_logic := '0';
    signal sim_done : boolean := false;
    signal chk_en, chk_clear, tx_ws, rx_wv, rx_err : std_logic := '0';
    signal chk_timeout : std_logic_vector(31 downto 0) := (others => '0');
    signal ts_now      : std_logic_vector(63 downto 0) := (others => '0');
    signal tx_w, rx_w  : std_logic_vector(31 downto 0) := (others => '0');

    signal c_mm, c_ne, c_un, fovf : std_logic;
    signal c_addr : std_logic_vector(15 downto 0);
    signal c_data, ok_cnt, err_cnt : std_logic_vector(31 downto 0);
    signal flev   : std_logic_vector(3 downto 0);
    signal errors : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_word_checker
        generic map (G_FIFO_DEPTH => 4)
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            chk_en => chk_en, chk_clear => chk_clear, chk_timeout => chk_timeout, chk_route_ok => '1',
            ts_now => ts_now, tx_word_start => tx_ws, tx_word_tx => tx_w,
            rx_word_data => rx_w, rx_word_valid => rx_wv, rx_err_any => rx_err,
            chk_mismatch => c_mm, chk_no_echo => c_ne, chk_unexpected => c_un,
            chk_addr => c_addr, chk_data => c_data,
            chk_ok_cnt => ok_cnt, chk_err_cnt => err_cnt,
            chk_fifo_level => flev, chk_fifo_ovf => fovf
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
        chk_en <= '1'; chk_timeout <= u32(100);

        -- 1) Eşleşen Word -> OK=1
        ts_now <= x"0000000000000010"; tx_w <= x"11223344"; tx_ws <= '1'; tick; tx_ws <= '0';
        chk(unsigned(flev) = 1, "FIFO seviyesi 1 olmali");
        ts_now <= x"0000000000000020"; rx_w <= x"11223344"; rx_wv <= '1'; tick; rx_wv <= '0';
        chk(unsigned(ok_cnt) = 1 and unsigned(flev) = 0, "Eslesen Word -> OK=1, FIFO=0");

        -- 2) Farklı Word -> WORD_MISMATCH (data = beklenen)
        ts_now <= x"0000000000000030"; tx_w <= x"AABBCCDD"; tx_ws <= '1'; tick; tx_ws <= '0';
        ts_now <= x"0000000000000040"; rx_w <= x"AABBCC00"; rx_wv <= '1'; tick; rx_wv <= '0';
        chk(c_mm = '1' and c_data = x"AABBCCDD" and unsigned(err_cnt) = 1, "WORD_MISMATCH beklenen Word'u vermeli");

        -- 3) FIFO boşken Word -> UNEXPECTED_WORD (data = alınan)
        rx_w <= x"55667788"; rx_wv <= '1'; tick; rx_wv <= '0';
        chk(c_un = '1' and c_data = x"55667788" and unsigned(err_cnt) = 2, "UNEXPECTED_WORD alinan Word'u vermeli");

        -- 4) rx_err_any -> FIFO başı sessizce düşürülür (err_cnt artmaz)
        ts_now <= x"0000000000000050"; tx_w <= x"01020304"; tx_ws <= '1'; tick; tx_ws <= '0';
        rx_err <= '1'; tick; rx_err <= '0';
        chk(unsigned(flev) = 0 and unsigned(err_cnt) = 2 and c_ne = '0', "rx_err_any FIFO'yu sessizce dusurmeli");

        -- 5) NO_ECHO timeout
        ts_now <= x"0000000000000100"; tx_w <= x"CAFE0001"; tx_ws <= '1'; tick; tx_ws <= '0';
        ts_now <= x"0000000000000164"; -- +100 clk
        tick;
        chk(c_ne = '1' and c_data = x"CAFE0001" and unsigned(err_cnt) = 3, "Timeout -> NO_ECHO");

        -- 6) Eşzamanlı timeout + geçerli Word: karşılaştırma öncelikli olmalı (NO_ECHO yok!)
        ts_now <= x"0000000000000200"; tx_w <= x"CAFE0002"; tx_ws <= '1'; tick; tx_ws <= '0';
        ts_now <= x"0000000000000270"; rx_w <= x"CAFE0002"; rx_wv <= '1'; tick; rx_wv <= '0';
        chk(c_ne = '0' and unsigned(ok_cnt) = 2, "Eszamanli timeout+match durumunda OK kazanmali");

        -- 7) FIFO taşması (derinlik=4 -> 5. eklemede fovf='1') + chk_clear
        chk_timeout <= u32(0);
        for i in 1 to 5 loop
            tx_w <= u32(i); tx_ws <= '1'; tick; tx_ws <= '0';
        end loop;
        chk(fovf = '1' and unsigned(flev) = 4, "5. eklemede FIFO ovf=1 olmali");
        chk_clear <= '1'; tick; chk_clear <= '0';
        chk(fovf = '0' and unsigned(flev) = 0, "chk_clear FIFO ve ovf'yi temizlemeli");

        if errors = 0 then
            report "PASS: tb_a429_word_checker" severity note;
        else
            report "FAIL: tb_a429_word_checker (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
