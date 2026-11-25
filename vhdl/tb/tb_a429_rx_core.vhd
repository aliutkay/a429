--------------------------------------------------------------------------------
-- tb_a429_rx_core
--
-- a429_rx_core (CDC + glitch filter + decoder) için kendi kendini kontrol eden test.
-- 50 MHz clock, High Speed (100 kbps): bit = 500 clk, pulse = null = 250 clk.
-- Çalıştırma: ghdl -a --std=08 ...; ghdl -r --std=08 tb_a429_rx_core
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_a429_rx_core is
end entity;

architecture sim of tb_a429_rx_core is

    constant T_CLK   : time    := 20 ns;    -- 50 MHz
    constant C_PULSE : natural := 250;
    constant C_NULL  : natural := 250;
    constant C_BIT   : natural := C_PULSE + C_NULL;

    signal clk      : std_logic := '0';
    signal rst_n    : std_logic := '0';
    signal pin_high : std_logic := '0';
    signal pin_low  : std_logic := '0';
    signal parity_mode : std_logic_vector(1 downto 0) := "01";

    signal word_start, word_valid, bit_valid : std_logic;
    signal word_data   : std_logic_vector(31 downto 0);
    signal word_gap    : std_logic_vector(31 downto 0);
    signal word_gap_e  : std_logic_vector(15 downto 0);
    signal bit_idx     : std_logic_vector(4 downto 0);
    signal bit_pdur, bit_ndur, bit_perr, bit_nerr : std_logic_vector(15 downto 0);
    signal e_bus, e_noise, e_gap, e_early, e_pglitch, e_stuck, e_timeout, e_parity : std_logic;
    signal err_addr    : std_logic_vector(15 downto 0);
    signal err_data    : std_logic_vector(31 downto 0);
    signal glitch_tick : std_logic;
    signal glitch_tot  : std_logic_vector(15 downto 0);

    -- Monitör sayaçları
    signal n_word, n_start, n_bus, n_noise, n_gap, n_early, n_pglitch, n_stuck, n_timeout, n_parity : natural := 0;
    signal last_word   : std_logic_vector(31 downto 0) := (others => '0');
    signal last_errdat : std_logic_vector(31 downto 0) := (others => '0');
    signal last_gap    : natural := 0;
    signal max_nerr    : natural := 0;
    signal last_b31_null : natural := 0;

    signal errors      : natural := 0;
    signal sim_done    : boolean := false;

    -- Label bitleri okunduğu gibi [7:0]; hatta önce bit 7 gider
    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then
            return w(7 - k);
        else
            return w(k);
        end if;
    end function;

    function with_parity(w : std_logic_vector(31 downto 0); odd : boolean) return std_logic_vector is
        variable r    : std_logic_vector(31 downto 0) := w;
        variable ones : natural := 0;
    begin
        for i in 0 to 30 loop
            if w(i) = '1' then ones := ones + 1; end if;
        end loop;
        if odd then
            if ones mod 2 = 0 then r(31) := '1'; else r(31) := '0'; end if;
        else
            if ones mod 2 = 1 then r(31) := '1'; else r(31) := '0'; end if;
        end if;
        return r;
    end function;

begin

    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rx_core
        generic map (G_SYNC_STAGES => 4)
        port map (
            clk => clk, rst_n => rst_n,
            pin_high => pin_high, pin_low => pin_low,
            cfg_glitch_size   => std_logic_vector(to_unsigned(10, 16)),
            cfg_min_pulse     => std_logic_vector(to_unsigned(200, 16)),
            cfg_max_pulse     => std_logic_vector(to_unsigned(300, 16)),
            cfg_min_bit       => std_logic_vector(to_unsigned(450, 16)),
            cfg_max_bit       => std_logic_vector(to_unsigned(550, 16)),
            cfg_max_pulse_err => std_logic_vector(to_unsigned(3, 16)),
            cfg_max_null_err  => std_logic_vector(to_unsigned(3, 16)),
            cfg_max_gap_err   => std_logic_vector(to_unsigned(3, 16)),
            cfg_parity_mode   => parity_mode,
            word_start => word_start, word_data => word_data, word_gap_dur => word_gap,
            word_gap_err_cnt => word_gap_e, word_valid => word_valid,
            bit_idx => bit_idx, bit_pulse_dur => bit_pdur, bit_null_dur => bit_ndur,
            bit_pulse_err_cnt => bit_perr, bit_null_err_cnt => bit_nerr, bit_valid => bit_valid,
            err_bus_fault => e_bus, err_noise_violation => e_noise, err_gap_violation => e_gap,
            err_bit_early => e_early, err_pulse_glitch => e_pglitch, err_pulse_stuck => e_stuck,
            err_bit_timeout => e_timeout, err_parity => e_parity,
            err_addr => err_addr, err_data => err_data,
            glitch_tick => glitch_tick, glitch_total_cnt => glitch_tot
        );

    -- Monitör
    process (clk)
        variable nerr : integer;
    begin
        if rising_edge(clk) then
            if word_valid = '1' then
                n_word    <= n_word + 1;
                last_word <= word_data;
                last_gap  <= to_integer(unsigned(word_gap));
            end if;
            if word_start = '1' then n_start <= n_start + 1; end if;
            if e_bus = '1'     then n_bus <= n_bus + 1; end if;
            if e_noise = '1'   then n_noise <= n_noise + 1; end if;
            if e_gap = '1'     then n_gap <= n_gap + 1; end if;
            if e_early = '1'   then n_early <= n_early + 1; end if;
            if e_pglitch = '1' then n_pglitch <= n_pglitch + 1; end if;
            if e_stuck = '1'   then n_stuck <= n_stuck + 1; end if;
            if e_timeout = '1' then n_timeout <= n_timeout + 1; end if;
            if e_parity = '1'  then n_parity <= n_parity + 1; last_errdat <= err_data; end if;
            if bit_valid = '1' then
                nerr := to_integer(unsigned(bit_nerr));
                if nerr > max_nerr then max_nerr <= nerr; end if;
                if unsigned(bit_idx) = 31 then last_b31_null <= to_integer(unsigned(bit_ndur)); end if;
                -- Bir clk'de birden fazla hata olmamalı
            end if;
            if (unsigned'("" & e_bus) + unsigned'("" & e_noise) + unsigned'("" & e_gap) + unsigned'("" & e_early) +
                unsigned'("" & e_pglitch) + unsigned'("" & e_stuck) + unsigned'("" & e_timeout) + unsigned'("" & e_parity)) > 1 then
                report "HATA: ayni clk'de birden fazla hata bayragi" severity error;
            end if;
        end if;
    end process;

    -- Uyarıcı
    process
        procedure wait_clk(n : natural) is
        begin
            for i in 1 to n loop
                wait until rising_edge(clk);
            end loop;
        end procedure;

        procedure line(h, l : std_logic; n : natural) is
        begin
            pin_high <= h; pin_low <= l;
            wait_clk(n);
        end procedure;

        -- Bir Word gönder; isteğe bağlı olarak belirli bitte kısa pulse ya da null'da glitch
        procedure send(w : std_logic_vector(31 downto 0);
                       gap_bits      : natural := 4;
                       short_bit     : integer := -1;   -- bu bitte pulse 100 clk
                       glitch_bit    : integer := -1;   -- bu bitin null'unda 3 clk'lik glitch
                       fault_bit     : integer := -1) is  -- bu bitte 11 durumu
            variable b : std_logic;
            variable p : natural;
        begin
            for k in 0 to 31 loop
                b := wire_bit(w, k);
                p := C_PULSE;
                if k = short_bit then p := 100; end if;
                if k = fault_bit then
                    line('1', '1', p);
                elsif b = '1' then
                    line('1', '0', p);
                else
                    line('0', '1', p);
                end if;
                if k = glitch_bit then
                    line('0', '0', 100);
                    line('1', '0', 3);       -- glitch_size (10) altında
                    line('0', '0', C_BIT - p - 103);
                else
                    line('0', '0', C_BIT - p);
                end if;
            end loop;
            line('0', '0', gap_bits * C_BIT);
        end procedure;

        procedure check(cond : boolean; msg : string) is
        begin
            if cond then
                report "OK   : " & msg;
            else
                report "HATA : " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;

        constant W1 : std_logic_vector(31 downto 0) := with_parity(x"12345601", true);   -- Label 0x01
        constant W2 : std_logic_vector(31 downto 0) := with_parity(x"0ABCDEB7", true);   -- Label 0xB7 (267 octal)
        constant WE : std_logic_vector(31 downto 0) := with_parity(x"0ABCDEB7", false);  -- Even parity
        variable n0 : natural;
    begin
        rst_n <= '0';
        wait_clk(10);
        rst_n  <= '1';
        line('0', '0', 6 * C_BIT);    -- ERR_RECOVERY'den IDLE'a geçiş için NULL

        -- 1. Doğru Word
        send(W1);
        wait_clk(5);
        check(n_word = 1 and last_word = W1, "1 dogru Word alindi (Label 0x01)");
        check(n_start = 1, "word_start uretildi");

        send(W2);
        wait_clk(5);
        check(n_word = 2 and last_word = W2, "2 Label 0xB7 bit sirasi dogru");
        -- Bit 31 sonu = pulse + bit 30 null → gap gerçek değer: 4 bit + 5 clk bekleme
        check(last_gap = 4 * C_BIT + 5, "gercek gap olculdu: " & integer'image(last_gap));
        check(last_b31_null = C_NULL, "bit 31 null = bit 30 null: " & integer'image(last_b31_null));

        -- 2. Parity hatası: Word geçersiz, sadece hata
        send(WE);
        wait_clk(5);
        check(n_word = 2, "parity hatali Word word_valid uretmedi");
        check(n_parity = 1 and last_errdat = WE, "PARITY hatasi ve err_data = Word");

        -- 3. Parity kontrolü kapalı
        parity_mode <= "00";
        line('0', '0', C_BIT);
        send(WE);
        wait_clk(5);
        check(n_word = 3 and last_word = WE, "parity kontrolu kapaliyken Word gecerli");
        parity_mode <= "01";
        line('0', '0', C_BIT);

        -- 4. Glitch bastırma: null fazında 3 clk'lik glitch
        n0 := to_integer(unsigned(glitch_tot));
        send(W1, glitch_bit => 5);
        wait_clk(5);
        check(n_word = 4 and last_word = W1, "glitch'li Word dogru alindi");
        check(to_integer(unsigned(glitch_tot)) > n0, "glitch sayildi");
        check(max_nerr >= 1, "bit null_err_cnt glitch'i gosterdi");

        -- 5. Kısa pulse
        send(W1, short_bit => 10);
        wait_clk(5);
        check(n_pglitch = 1 and n_word = 4, "kisa pulse -> PULSE_GLITCH, Word yok");

        -- Toparlanma
        send(W2);
        wait_clk(5);
        check(n_word = 5 and last_word = W2, "hatadan sonra toparlandi");

        -- 6. Gap ihlali (2 bit gap)
        send(W1, gap_bits => 2);
        send(W2);
        wait_clk(5);
        check(n_gap = 1, "2 bit gap -> GAP_VIOLATION");

        line('0', '0', 4 * C_BIT);
        send(W1);
        wait_clk(5);
        check(last_word = W1, "gap ihlalinden sonra toparlandi");

        -- 7. Bus fault
        send(W2, fault_bit => 12);
        wait_clk(5);
        check(n_bus = 1, "11 durumu -> BUS_FAULT");

        -- 8. Bus fault sonrası toparlanma
        n0 := n_word;
        send(W1);
        wait_clk(5);
        check(n_word = n0 + 1 and last_word = W1, "bus fault sonrasi toparlandi");

        check(n_noise = 0 and n_early = 0 and n_stuck = 0 and n_timeout = 0, "beklenmeyen hata yok");

        wait_clk(2);
        if errors = 0 then
            report "SONUC: TUM TESTLER GECTI";
        else
            report "SONUC: " & integer'image(errors) & " TEST BASARISIZ" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;

end architecture sim;
