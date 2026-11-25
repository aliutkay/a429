--------------------------------------------------------------------------------
-- tb_a429_rx_logger — a429_rx_logger birim testi (VHDL-93 / VHDL-2008 uyumlu)
--   * word_start timestamp yakalama, enable=0 kapama, FREEZE/GLOBAL_FREEZE DROP
--   * dairesel RAM sarma (word_wrap), eşzamanlı çoklu hata OR + öncelik, clear
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_rx_logger is
end entity tb_a429_rx_logger;

architecture sim of tb_a429_rx_logger is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst, enable, freeze, gfreeze, clear : std_logic := '0';
    signal sim_done : boolean := false;
    signal ts_now : std_logic_vector(63 downto 0) := (others => '0');

    signal word_start, word_valid, bit_valid : std_logic := '0';
    signal word_data : std_logic_vector(31 downto 0) := (others => '0');
    signal word_gap  : std_logic_vector(31 downto 0) := (others => '0');
    signal word_gerr : std_logic_vector(15 downto 0) := (others => '0');
    signal bit_idx   : std_logic_vector(4 downto 0) := (others => '0');
    signal b_p, b_n, b_pe, b_ne : std_logic_vector(15 downto 0) := (others => '0');

    signal e_bus, e_noise, e_gap, e_early, e_pg, e_st, e_to, e_par : std_logic := '0';
    signal err_addr : std_logic_vector(15 downto 0) := (others => '0');
    signal err_data : std_logic_vector(31 downto 0) := (others => '0');
    signal e_lbl, c_mm, c_ne, c_un : std_logic := '0';
    signal c_addr : std_logic_vector(15 downto 0) := (others => '0');
    signal c_data : std_logic_vector(31 downto 0) := (others => '0');

    signal word_we, err_we, bit_we : std_logic;
    signal word_waddr, err_waddr : std_logic_vector(1 downto 0); -- depth = 4 (wrap testi kolay)
    signal bit_waddr : std_logic_vector(6 downto 0);
    signal word_wdata : std_logic_vector(143 downto 0);
    signal err_wdata  : std_logic_vector(127 downto 0);
    signal bit_wdata  : std_logic_vector(63 downto 0);

    signal frozen, word_wrap, err_wrap, rx_err_any : std_logic;
    signal word_cnt, err_cnt, drop_cnt, last_word  : std_logic_vector(31 downto 0);
    signal errors : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rx_logger
        generic map (G_WORD_DEPTH_LOG2 => 2, G_ERR_DEPTH_LOG2 => 2, G_BITDIAG_WORDS_LOG2 => 2, G_BITDIAG_EN => true)
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst, ts_now => ts_now,
            enable => enable, freeze => freeze, global_freeze => gfreeze, clear => clear,
            word_start => word_start, word_data => word_data, word_gap_dur => word_gap,
            word_gap_err_cnt => word_gerr, word_valid => word_valid,
            bit_idx => bit_idx, bit_pulse_dur => b_p, bit_null_dur => b_n,
            bit_pulse_err_cnt => b_pe, bit_null_err_cnt => b_ne, bit_valid => bit_valid,
            err_bus_fault => e_bus, err_noise_violation => e_noise, err_gap_violation => e_gap,
            err_bit_early => e_early, err_pulse_glitch => e_pg, err_pulse_stuck => e_st,
            err_bit_timeout => e_to, err_parity => e_par, err_addr => err_addr, err_data => err_data,
            err_label_filtered => e_lbl, chk_mismatch => c_mm, chk_no_echo => c_ne,
            chk_unexpected => c_un, chk_addr => c_addr, chk_data => c_data,
            word_we => word_we, word_waddr => word_waddr, word_wdata => word_wdata,
            err_we => err_we, err_waddr => err_waddr, err_wdata => err_wdata,
            bit_we => bit_we, bit_waddr => bit_waddr, bit_wdata => bit_wdata,
            frozen => frozen, word_wrap => word_wrap, err_wrap => err_wrap,
            word_cnt => word_cnt, err_cnt => err_cnt, drop_cnt => drop_cnt,
            last_word => last_word, rx_err_any => rx_err_any
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

        -- 1) enable=0 iken yazmamalı
        enable <= '0';
        ts_now <= x"0000000000000100"; word_start <= '1'; tick; word_start <= '0';
        word_data <= x"12345678"; word_valid <= '1'; tick; word_valid <= '0';
        chk(word_we = '0' and unsigned(word_cnt) = 0, "enable=0 iken kayit yazilmamali");

        -- 2) enable=1: word_start timestamp'ini yakalayıp Word RAM'e yazmalı
        enable <= '1';
        ts_now <= x"0000000100000AAA"; word_start <= '1'; tick; word_start <= '0';
        ts_now <= x"0000000100000BBB";
        word_data <= x"CAFEBABE"; word_gap <= u32(500); word_gerr <= u16(3); word_valid <= '1';
        tick; word_valid <= '0';
        chk(word_we = '1' and word_waddr = "00" and word_wdata(143 downto 80) = x"0000000100000AAA"
            and word_wdata(79 downto 48) = x"CAFEBABE" and last_word = x"CAFEBABE" and unsigned(word_cnt) = 1,
            "Word RAM kaydi ve word_start timestamp'i dogru olmali");

        -- 3) FREEZE=1 ve GLOBAL_FREEZE=1 -> DROP_CNT artmalı
        freeze <= '1';
        word_valid <= '1'; tick; word_valid <= '0';
        chk(frozen = '1' and word_we = '0' and unsigned(drop_cnt) = 1 and unsigned(word_cnt) = 1,
            "FREEZE sirasinda DROP_CNT artmali");
        freeze <= '0'; gfreeze <= '1';
        c_ne <= '1'; tick; c_ne <= '0';
        chk(frozen = '1' and err_we = '0' and unsigned(drop_cnt) = 2, "GLOBAL_FREEZE hatayi drop etmeli");
        gfreeze <= '0';

        -- 4) Eşzamanlı çoklu hata: FSM (e_bus) + Checker (c_ne) -> code OR'lanır, addr/data FSM'den alınır
        e_bus <= '1'; err_addr <= u16(7); err_data <= u32(99);
        c_ne  <= '1'; c_addr <= u16(2); c_data <= x"DEAD0001";
        tick;
        e_bus <= '0'; c_ne <= '0';
        chk(err_we = '1' and err_wdata(63 downto 48) = x"0201"
            and err_wdata(47 downto 32) = u16(7) and err_wdata(31 downto 0) = u32(99),
            "Coklu hata OR'lanmali ve FSM oncelikli olmali");

        -- 5) Word wrap testi (derinlik=4 -> 4. Word'de word_wrap='1')
        for i in 1 to 3 loop
            word_valid <= '1'; tick; word_valid <= '0';
        end loop;
        chk(unsigned(word_cnt) = 4 and word_wrap = '1', "4. Word'de word_wrap=1 olmali");

        -- 6) CLEAR tüm sayaç ve wrap'leri sıfırlamalı
        clear <= '1'; tick; clear <= '0';
        chk(unsigned(word_cnt) = 0 and unsigned(err_cnt) = 0 and unsigned(drop_cnt) = 0 and word_wrap = '0',
            "clear tum sayac ve bayraklari sifirlamali");

        if errors = 0 then
            report "PASS: tb_a429_rx_logger" severity note;
        else
            report "FAIL: tb_a429_rx_logger (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
