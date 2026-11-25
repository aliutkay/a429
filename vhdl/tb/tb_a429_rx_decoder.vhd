--------------------------------------------------------------------------------
-- tb_a429_rx_decoder — a429_rx_decoder birim testi (VHDL-93 / VHDL-2008 uyumlu)
--   * Doğru Word + Label bit tersleme + Even/Odd/Kapalı parity
--   * 8 hata bayrağının tamamı: BUS_FAULT, NOISE_VIOLATION, GAP_VIOLATION,
--     BIT_EARLY, PULSE_GLITCH (kısa & polarite değişimi), PULSE_STUCK,
--     BIT_TIMEOUT, PARITY
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_rx_decoder is
end entity tb_a429_rx_decoder;

architecture sim of tb_a429_rx_decoder is
    constant T_CLK   : time := 20 ns;
    constant C_P     : natural := 20;
    constant C_N     : natural := 20;
    constant C_MIN_P : natural := 12;
    constant C_MAX_P : natural := 28;
    constant C_MIN_B : natural := 32;
    constant C_MAX_B : natural := 48;

    signal clk       : std_logic := '0';
    signal sim_done  : boolean := false;
    signal rst_n     : std_logic := '0';
    signal soft_rst  : std_logic := '0';
    signal par_mode  : std_logic_vector(1 downto 0) := C_PAR_ODD;
    signal rx_high   : std_logic := '0';
    signal rx_low    : std_logic := '0';
    signal gcnt      : std_logic_vector(15 downto 0) := (others => '0');

    signal word_start, word_valid, bit_valid : std_logic;
    signal word_data : std_logic_vector(31 downto 0);
    signal word_gap  : std_logic_vector(31 downto 0);
    signal word_gerr : std_logic_vector(15 downto 0);
    signal bit_idx   : std_logic_vector(4 downto 0);
    signal bit_pdur, bit_ndur, bit_perr, bit_nerr : std_logic_vector(15 downto 0);
    signal e_bus, e_noise, e_gap, e_early, e_pglitch, e_stuck, e_timeout, e_parity : std_logic;
    signal err_addr  : std_logic_vector(15 downto 0);
    signal err_data  : std_logic_vector(31 downto 0);

    signal n_word, n_bus, n_noise, n_gap, n_early, n_pglitch, n_stuck, n_timeout, n_parity : natural := 0;
    signal last_word : std_logic_vector(31 downto 0) := (others => '0');
    signal last_eaddr: std_logic_vector(15 downto 0) := (others => '0');
    signal errors    : natural := 0;

    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then return w(7 - k); else return w(k); end if;
    end function;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rx_decoder
        generic map (G_DUR_W => 16, G_GAP_W => 32, G_CNT_W => 16)
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            cfg_min_pulse => u16(C_MIN_P), cfg_max_pulse => u16(C_MAX_P),
            cfg_min_bit => u16(C_MIN_B), cfg_max_bit => u16(C_MAX_B),
            cfg_max_pulse_err => u16(2), cfg_max_null_err => u16(2), cfg_max_gap_err => u16(2),
            cfg_parity_mode => par_mode,
            rx_high => rx_high, rx_low => rx_low, glitch_cnt => gcnt,
            word_start => word_start, word_data => word_data, word_gap_dur => word_gap,
            word_gap_err_cnt => word_gerr, word_valid => word_valid,
            bit_idx => bit_idx, bit_pulse_dur => bit_pdur, bit_null_dur => bit_ndur,
            bit_pulse_err_cnt => bit_perr, bit_null_err_cnt => bit_nerr, bit_valid => bit_valid,
            err_bus_fault => e_bus, err_noise_violation => e_noise, err_gap_violation => e_gap,
            err_bit_early => e_early, err_pulse_glitch => e_pglitch, err_pulse_stuck => e_stuck,
            err_bit_timeout => e_timeout, err_parity => e_parity,
            err_addr => err_addr, err_data => err_data
        );

    process (clk)
    begin
        if rising_edge(clk) then
            if word_valid = '1' then n_word <= n_word + 1; last_word <= word_data; end if;
            if e_bus = '1'      then n_bus <= n_bus + 1; last_eaddr <= err_addr; end if;
            if e_noise = '1'    then n_noise <= n_noise + 1; end if;
            if e_gap = '1'      then n_gap <= n_gap + 1; end if;
            if e_early = '1'    then n_early <= n_early + 1; end if;
            if e_pglitch = '1'  then n_pglitch <= n_pglitch + 1; end if;
            if e_stuck = '1'    then n_stuck <= n_stuck + 1; end if;
            if e_timeout = '1'  then n_timeout <= n_timeout + 1; end if;
            if e_parity = '1'   then n_parity <= n_parity + 1; end if;
        end if;
    end process;

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop wait until rising_edge(clk); end loop;
        end procedure;
        procedure drive(h, l : std_logic; n : natural) is
        begin
            rx_high <= h; rx_low <= l; tick(n);
        end procedure;
        procedure send_word(w : std_logic_vector(31 downto 0); gap_n : natural := 160) is
            variable b : std_logic;
        begin
            for k in 0 to 31 loop
                b := wire_bit(w, k);
                drive(b, not b, C_P);
                drive('0', '0', C_N);
            end loop;
            drive('0', '0', gap_n);
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then
                report "HATA: " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;
        constant W_ODD  : std_logic_vector(31 downto 0) := x"A0000181"; -- tek 1 sayisi (5)
        constant W_EVEN : std_logic_vector(31 downto 0) := x"20000181"; -- cift 1 sayisi (4)
    begin
        rst_n <= '0'; tick(4); rst_n <= '1';
        drive('0', '0', 180); -- ERR_RECOVERY'den çık

        -- 1) Geçerli Odd Word
        par_mode <= C_PAR_ODD;
        send_word(W_ODD);
        chk(n_word = 1 and last_word = W_ODD, "Odd Word dogru cozulmeli");

        -- 2) Even parity modu + Parity hatası
        par_mode <= C_PAR_EVEN;
        send_word(W_EVEN);
        chk(n_word = 2 and last_word = W_EVEN, "Even Word dogru cozulmeli");
        send_word(W_ODD);
        chk(n_parity = 1 and n_word = 2, "Yanlis parity -> PARITY hatasi, word_valid yok");

        -- 3) PULSE_GLITCH (kısa pulse)
        par_mode <= C_PAR_ODD;
        drive('1', '0', 5); drive('0', '0', 180);
        chk(n_pglitch = 1, "Kisa pulse -> PULSE_GLITCH");

        -- 4) PULSE_GLITCH (polarite değişimi HIGH -> LOW)
        drive('1', '0', 15); drive('0', '1', 5); drive('0', '0', 180);
        chk(n_pglitch = 2, "Polarite degisimi -> PULSE_GLITCH");

        -- 5) PULSE_STUCK (> max_pulse = 28)
        drive('1', '0', 35); drive('0', '0', 180);
        chk(n_stuck = 1, "Uzun pulse -> PULSE_STUCK");

        -- 6) BIT_EARLY (bit süresi < min_bit = 32)
        drive('1', '0', 16); drive('0', '0', 8); drive('0', '1', 16); drive('0', '0', 180);
        chk(n_early = 1, "Erken bit -> BIT_EARLY");

        -- 7) BIT_TIMEOUT (> max_bit = 48)
        drive('1', '0', 20); drive('0', '0', 180);
        chk(n_timeout = 1, "Bit zaman asimi -> BIT_TIMEOUT");

        -- 8) GAP_VIOLATION (32 bit sonrası 4 bitten kısa gap)
        send_word(W_ODD, 40);
        drive('1', '0', 20); drive('0', '0', 180);
        chk(n_gap = 1, "Kisa gap -> GAP_VIOLATION");

        -- 9) NOISE_VIOLATION (glitch_cnt > max_gap_err = 2)
        gcnt <= u16(5); tick(2); gcnt <= u16(0); drive('0', '0', 180);
        chk(n_noise = 1, "Gurultu asimi -> NOISE_VIOLATION");

        -- 10) BUS_FAULT ("11") ST_IDLE'da -> addr = 32 (C_ADDR_GAP)
        drive('1', '1', 3); drive('0', '0', 180);
        chk(n_bus = 1 and unsigned(last_eaddr) = 32, "ST_IDLE'da BUS_FAULT addr=32 olmali");

        if errors = 0 then
            report "PASS: tb_a429_rx_decoder" severity note;
        else
            report "FAIL: tb_a429_rx_decoder (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
