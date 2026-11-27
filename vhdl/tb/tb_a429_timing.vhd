--------------------------------------------------------------------------------
-- tb_a429_timing — clock hassasiyetinde zamanlama doğrulaması (VHDL-93 / VHDL-2008)
--
--   Bölüm A (TX, a429_tx_core): hatta her pulse tam pulse_dur clk, her null tam
--     null_dur clk; Word'ler arası NULL ve periyot:
--       * Scheduler     : son bitin null'u + gap_dur + inter_word_gap
--                         (periyot = 32*(pulse+null) + gap_dur + inter_word_gap)
--       * SEND_CMD (sürekli): son bitin null'u + gap_dur (gap asla gap_dur'dan kısa değil)
--       * initial_delay : SCHED_EN'den ilk pulse'a kadar tam initial_delay clk fark
--   Bölüm B (RX, a429_rx_core): Bit Diagnostic pulse / null süreleri ve Word gap
--     süresi hattakiyle clk'i clk'ine aynı; min/max pulse, min/max bit ve
--     4 x min_bit gap sınırları tam değerde kabul, ±1 clk dışında ret.
--   Bölüm C (TX -> RX uçtan uca): TX'in ürettiği hat RX'te aynı sürelerle ölçülür.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_timing is
end entity tb_a429_timing;

architecture sim of tb_a429_timing is
    constant T_CLK : time := 20 ns;
    signal clk      : std_logic := '0';
    signal rst_n    : std_logic := '0';
    signal sim_done : boolean := false;

    -- ---------------- TX
    constant C_P : natural := 7;
    constant C_N : natural := 5;
    constant C_G : natural := 23;
    signal tx_cfg      : t_tx_cfg := (pulse_dur => u16(C_P), null_dur => u16(C_N), gap_dur => u32(C_G), slp => '1');
    signal tx_en, msg_sched_en, sched_en, send_cmd : std_logic := '0';
    signal init_dly    : std_logic_vector(31 downto 0) := (others => '0');
    signal iw_gap      : std_logic_vector(31 downto 0) := u32(1);
    signal tx_high, tx_low, tx_busy : std_logic;
    signal ext_data    : std_logic_vector(31 downto 0) := x"A5C3_0F12";

    -- TX hat ölçümü (segment uzunlukları)
    type t_nat_arr is array (natural range <>) of natural;
    signal seg_cnt     : natural := 0;
    signal seg_state   : std_logic_vector(1 downto 0) := "00";
    signal pulse_log   : t_nat_arr(0 to 255) := (others => 0);
    signal null_log    : t_nat_arr(0 to 255) := (others => 0);
    signal n_pulse     : natural := 0;
    signal n_null      : natural := 0;
    signal pstart_log  : t_nat_arr(0 to 255) := (others => 0);   -- pulse başlangıç clk'i
    signal clk_no      : natural := 0;
    signal meas_clr    : std_logic := '0';

    -- ---------------- RX
    signal rx_src      : std_logic := '0';     -- '0': stimulus, '1': TX hattı
    signal st_high, st_low : std_logic := '0';
    signal pin_high, pin_low : std_logic;
    signal cfg_gs      : std_logic_vector(15 downto 0) := u16(2);
    signal cfg_minp    : std_logic_vector(15 downto 0) := u16(5);
    signal cfg_maxp    : std_logic_vector(15 downto 0) := u16(9);
    signal cfg_minb    : std_logic_vector(15 downto 0) := u16(10);
    signal cfg_maxb    : std_logic_vector(15 downto 0) := u16(14);
    signal cfg_err     : std_logic_vector(15 downto 0) := x"FFFF";
    signal word_valid, bit_valid : std_logic;
    signal word_data   : std_logic_vector(31 downto 0);
    signal word_gap    : std_logic_vector(31 downto 0);
    signal bit_idx     : std_logic_vector(4 downto 0);
    signal bit_pdur, bit_ndur : std_logic_vector(15 downto 0);
    signal e_bus, e_noise, e_gap, e_early, e_pglitch, e_stuck, e_tout, e_par : std_logic;
    signal err_data    : std_logic_vector(31 downto 0);

    -- RX olay sayaçları
    signal rx_words    : natural := 0;
    signal rx_last_gap : natural := 0;
    signal rx_err_gap, rx_err_early, rx_err_pg, rx_err_stuck, rx_err_tout, rx_err_other : natural := 0;
    signal bp_log      : t_nat_arr(0 to 31) := (others => 0);
    signal bn_log      : t_nat_arr(0 to 31) := (others => 0);

begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    -- ======================= TX =======================
    u_tx : entity work.a429_tx_core
        port map (
            clk => clk, rst_n => rst_n, soft_rst => '0', act_cfg => tx_cfg,
            transmitter_en => tx_en, msg_sched_en => msg_sched_en, builder_en => '0',
            label_val => (others => '0'), sdi => "00", data => (others => '0'), ssm => "00", parity_type => '1',
            sched_en => sched_en, initial_delay => init_dly, inter_word_gap => iw_gap,
            send_cmd => send_cmd, ext_data => ext_data, ext_high => '0', ext_low => '0',
            tx_high => tx_high, tx_low => tx_low, tx_slp => open, tx_busy => tx_busy,
            tx_sched_act => open, tx_word_tx => open
        );

    -- Hat segment ölçümü: her clk'te hat durumu örneklenir
    process (clk)
        variable v_st : std_logic_vector(1 downto 0);
    begin
        if rising_edge(clk) then
            clk_no <= clk_no + 1;
            v_st := tx_high & tx_low;
            if meas_clr = '1' then
                n_pulse <= 0; n_null <= 0; seg_cnt <= 1; seg_state <= v_st;
            elsif v_st /= seg_state then
                if seg_state = "00" then
                    if n_null <= 255 then null_log(n_null) <= seg_cnt; end if;
                    n_null <= n_null + 1;
                else
                    if n_pulse <= 255 then pulse_log(n_pulse) <= seg_cnt; end if;
                    n_pulse <= n_pulse + 1;
                end if;
                if v_st /= "00" and n_pulse <= 255 then
                    pstart_log(n_pulse) <= clk_no;
                end if;
                seg_state <= v_st;
                seg_cnt   <= 1;
            else
                seg_cnt <= seg_cnt + 1;
            end if;
        end if;
    end process;

    -- ======================= RX =======================
    pin_high <= tx_high when rx_src = '1' else st_high;
    pin_low  <= tx_low  when rx_src = '1' else st_low;

    u_rx : entity work.a429_rx_core
        port map (
            clk => clk, rst_n => rst_n, soft_rst => '0', pin_high => pin_high, pin_low => pin_low,
            cfg_glitch_size => cfg_gs, cfg_min_pulse => cfg_minp, cfg_max_pulse => cfg_maxp,
            cfg_min_bit => cfg_minb, cfg_max_bit => cfg_maxb,
            cfg_max_pulse_err => cfg_err, cfg_max_null_err => cfg_err, cfg_max_gap_err => cfg_err,
            cfg_parity_mode => "00",
            word_start => open, word_data => word_data, word_gap_dur => word_gap, word_gap_err_cnt => open,
            word_valid => word_valid, bit_idx => bit_idx, bit_pulse_dur => bit_pdur, bit_null_dur => bit_ndur,
            bit_pulse_err_cnt => open, bit_null_err_cnt => open, bit_valid => bit_valid,
            err_bus_fault => e_bus, err_noise_violation => e_noise, err_gap_violation => e_gap,
            err_bit_early => e_early, err_pulse_glitch => e_pglitch, err_pulse_stuck => e_stuck,
            err_bit_timeout => e_tout, err_parity => e_par, err_addr => open, err_data => err_data,
            glitch_tick => open, glitch_total_cnt => open
        );

    process (clk)
    begin
        if rising_edge(clk) then
            if word_valid = '1' then
                rx_words    <= rx_words + 1;
                rx_last_gap <= to_integer(unsigned(word_gap));
            end if;
            if bit_valid = '1' then
                bp_log(to_integer(unsigned(bit_idx))) <= to_integer(unsigned(bit_pdur));
                bn_log(to_integer(unsigned(bit_idx))) <= to_integer(unsigned(bit_ndur));
            end if;
            if e_gap = '1'     then rx_err_gap   <= rx_err_gap + 1;   end if;
            if e_early = '1'   then rx_err_early <= rx_err_early + 1; end if;
            if e_pglitch = '1' then rx_err_pg    <= rx_err_pg + 1;    end if;
            if e_stuck = '1'   then rx_err_stuck <= rx_err_stuck + 1; end if;
            if e_tout = '1'    then rx_err_tout  <= rx_err_tout + 1;  end if;
            if (e_bus or e_noise or e_par) = '1' then rx_err_other <= rx_err_other + 1; end if;
        end if;
    end process;

    -- ======================= Senaryo =======================
    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop wait until rising_edge(clk); wait for 1 ns; end loop;
        end procedure;
        variable n_err : natural := 0;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; n_err := n_err + 1; end if;
        end procedure;
        function img(n : natural) return string is
        begin
            return integer'image(n);
        end function;

        -- TX: kayıtlı segmentlerden Word'leri kontrol eder (ilk nw Word)
        procedure chk_tx_words(nw : natural; exp_iw_null : natural; what : string) is
            variable bad_p, bad_n : natural := 0;
        begin
            chk(n_pulse >= 32 * nw, what & ": en az " & img(32 * nw) & " pulse beklendi, " & img(n_pulse));
            for i in 0 to 32 * nw - 1 loop
                if pulse_log(i) /= C_P then bad_p := bad_p + 1; end if;
            end loop;
            chk(bad_p = 0, what & ": " & img(bad_p) & " pulse " & img(C_P) & " clk degil (ilk: " & img(pulse_log(0)) & ")");
            -- null_log(0) Word öncesi boşta bekleme; bit null'ları 1.. ile başlar
            for w in 0 to nw - 1 loop
                for b in 0 to 30 loop
                    if null_log(1 + 32 * w + b) /= C_N then bad_n := bad_n + 1; end if;
                end loop;
            end loop;
            chk(bad_n = 0, what & ": " & img(bad_n) & " bit null'u " & img(C_N) & " clk degil");
            for w in 0 to nw - 2 loop
                chk(null_log(32 * (w + 1)) = exp_iw_null,
                    what & ": Word " & img(w) & " -> " & img(w + 1) & " arasi NULL " & img(null_log(32 * (w + 1)))
                    & " clk, beklenen " & img(exp_iw_null) & " (= null + gap" & ")");
                chk(pstart_log(32 * (w + 1)) - pstart_log(32 * w) = 32 * (C_P + C_N) - C_N + exp_iw_null,
                    what & ": periyot " & img(pstart_log(32 * (w + 1)) - pstart_log(32 * w)) & " clk, beklenen "
                    & img(32 * (C_P + C_N) - C_N + exp_iw_null));
            end loop;
        end procedure;

        -- RX stimulus: tek Word (her bit pulse p / null n), ardından g clk ek NULL
        procedure send_word(w : std_logic_vector(31 downto 0); p, n, g : natural;
                            p_bad_bit : integer := -1; p_bad : natural := 0;
                            n_bad_bit : integer := -1; n_bad : natural := 0) is
            variable b  : std_logic;
            variable pp, nn : natural;
        begin
            for k in 0 to 31 loop
                if k < 8 then b := w(7 - k); else b := w(k); end if;
                pp := p; nn := n;
                if k = p_bad_bit then pp := p_bad; end if;
                if k = n_bad_bit then nn := n_bad; end if;
                st_high <= b; st_low <= not b;
                tick(pp);
                st_high <= '0'; st_low <= '0';
                tick(nn);
            end loop;
            tick(g);
        end procedure;

        procedure rx_idle is
        begin
            st_high <= '0'; st_low <= '0';
            tick(200);                 -- ERR_RECOVERY / ilk senkron için uzun NULL
        end procedure;

        variable w0, e0 : natural;
        variable t0     : natural;
    begin
        rst_n <= '0'; tick(3); rst_n <= '1'; tick(3);

        ------------------------------------------------------------------
        -- A1) Scheduler, inter_word_gap = 1
        ------------------------------------------------------------------
        tx_en <= '1'; msg_sched_en <= '1'; iw_gap <= u32(1);
        meas_clr <= '1'; tick(1); meas_clr <= '0';
        sched_en <= '1';
        tick(4 * (32 * (C_P + C_N) + C_G + 10));
        sched_en <= '0';
        tick(32 * (C_P + C_N) + C_G + 10);
        chk_tx_words(3, C_N + C_G + 1, "A1 Scheduler iwg=1");

        -- A2) Scheduler, inter_word_gap = 2 ve 9
        for iwg in 2 to 9 loop
            if iwg = 2 or iwg = 9 then
                iw_gap <= u32(iwg);
                meas_clr <= '1'; tick(1); meas_clr <= '0';
                sched_en <= '1';
                tick(4 * (32 * (C_P + C_N) + C_G + 20));
                sched_en <= '0';
                tick(32 * (C_P + C_N) + C_G + 20);
                chk_tx_words(3, C_N + C_G + iwg, "A2 Scheduler iwg=" & img(iwg));
            end if;
        end loop;

        -- A3) SEND_CMD sürekli '1' (en hızlı tek gönderim): gap asla gap_dur'dan kısa olmamalı
        msg_sched_en <= '0';
        meas_clr <= '1'; tick(1); meas_clr <= '0';
        send_cmd <= '1';
        tick(4 * (32 * (C_P + C_N) + C_G + 10));
        send_cmd <= '0';
        tick(32 * (C_P + C_N) + C_G + 10);
        chk_tx_words(3, C_N + C_G, "A3 SEND_CMD surekli");

        -- A3b) gap_dur uç değerleri (1 ve 2): SEND_CMD sürekli -> NULL = null_dur + gap_dur
        for gd in 1 to 2 loop
            tx_cfg.gap_dur <= u32(gd);
            tick(40);
            meas_clr <= '1'; tick(1); meas_clr <= '0';
            send_cmd <= '1';
            tick(4 * (32 * (C_P + C_N) + gd + 10));
            send_cmd <= '0';
            tick(32 * (C_P + C_N) + 40);
            chk_tx_words(3, C_N + gd, "A3b SEND_CMD gap_dur=" & img(gd));
        end loop;
        tx_cfg.gap_dur <= u32(C_G);
        tick(40);

        -- A4) initial_delay: 0 ile D arasındaki fark tam D clk
        msg_sched_en <= '1'; iw_gap <= u32(1);
        for d in 0 to 1 loop
            if d = 0 then init_dly <= u32(0); else init_dly <= u32(37); end if;
            meas_clr <= '1'; tick(1); meas_clr <= '0';
            t0 := clk_no;
            sched_en <= '1';
            tick(32 * (C_P + C_N) + 60);
            sched_en <= '0';
            tick(2 * (32 * (C_P + C_N) + C_G + 10));
            if d = 0 then
                w0 := pstart_log(0) - t0;
            else
                chk(pstart_log(0) - t0 = w0 + 37,
                    "A4 initial_delay=37: ilk pulse gecikmesi " & img(pstart_log(0) - t0) & ", beklenen " & img(w0 + 37));
            end if;
        end loop;
        init_dly <= u32(0);
        tx_en <= '0';

        ------------------------------------------------------------------
        -- B) RX ölçüm ve sınırlar (stimulus; glitch_size=2)
        --    min_pulse 5, max_pulse 9, min_bit 10, max_bit 14, min gap 4*10 = 40
        ------------------------------------------------------------------
        rx_src <= '0';
        rx_idle;
        -- B1) Ölçüm: pulse 7, null 5 ve gap 47 (bit 31 null 5 + 47 => tahmini bitiş sonrası 47)
        w0 := rx_words;
        send_word(x"0000_0000", 7, 5, 47);
        send_word(x"FFFF_FFFF", 7, 5, 60);
        tick(5);
        chk(rx_words = w0 + 2, "B1: 2 Word alinmali, alinan " & img(rx_words - w0));
        for k in 0 to 30 loop
            chk(bp_log(k) = 7 and bn_log(k) = 5,
                "B1: bit " & img(k) & " pulse/null " & img(bp_log(k)) & "/" & img(bn_log(k)) & ", beklenen 7/5");
        end loop;
        chk(bp_log(31) = 7, "B1: bit 31 pulse " & img(bp_log(31)));
        chk(rx_last_gap = 47, "B1: Word gap " & img(rx_last_gap) & " clk, beklenen 47");

        -- B2) Sınırlar: (pulse, null, gap, beklenen) — ilk Word geçerli, sınır Word'ü ikinci
        -- min_pulse = 5 kabul, 4 ret (Pulse Glitch)
        rx_idle; w0 := rx_words; e0 := rx_err_pg;
        send_word(x"1234_5678", 5, 6, 60);
        chk(rx_words = w0 + 1, "B2 min_pulse=5 tam degerde kabul edilmeli");
        rx_idle; w0 := rx_words;
        send_word(x"1234_5678", 6, 6, 60, p_bad_bit => 9, p_bad => 4);
        rx_idle;
        chk(rx_words = w0 and rx_err_pg = e0 + 1, "B2 pulse=4 (< min 5) Pulse Glitch ile reddedilmeli");
        -- max_pulse = 9 kabul, 10 ret (Pulse Stuck)
        rx_idle; w0 := rx_words; e0 := rx_err_stuck;
        send_word(x"1234_5678", 7, 5, 60, p_bad_bit => 12, p_bad => 9);
        chk(rx_words = w0 + 1, "B2 max_pulse=9 tam degerde kabul edilmeli");
        rx_idle; w0 := rx_words;
        send_word(x"1234_5678", 7, 5, 60, p_bad_bit => 12, p_bad => 10);
        rx_idle;
        chk(rx_words = w0 and rx_err_stuck = e0 + 1, "B2 pulse=10 (> max 9) Pulse Stuck ile reddedilmeli");
        -- min_bit = 10 kabul (5+5), 9 ret (Bit Early)
        rx_idle; w0 := rx_words; e0 := rx_err_early;
        send_word(x"1234_5678", 6, 5, 60, n_bad_bit => 3, n_bad => 4);
        chk(rx_words = w0 + 1, "B2 bit=10 (min_bit) tam degerde kabul edilmeli");
        rx_idle; w0 := rx_words;
        send_word(x"1234_5678", 6, 5, 60, n_bad_bit => 3, n_bad => 3);
        rx_idle;
        chk(rx_words = w0 and rx_err_early = e0 + 1, "B2 bit=9 (< min 10) Bit Early ile reddedilmeli");
        -- max_bit = 14 kabul (7+7), 15 ret (Bit Timeout)
        rx_idle; w0 := rx_words; e0 := rx_err_tout;
        send_word(x"1234_5678", 7, 5, 60, n_bad_bit => 20, n_bad => 7);
        chk(rx_words = w0 + 1, "B2 bit=14 (max_bit) tam degerde kabul edilmeli");
        rx_idle; w0 := rx_words;
        send_word(x"1234_5678", 7, 5, 60, n_bad_bit => 20, n_bad => 8);
        rx_idle;
        chk(rx_words = w0 and rx_err_tout = e0 + 1, "B2 bit=15 (> max 14) Bit Timeout ile reddedilmeli");
        -- Gap = 4*min_bit = 40 kabul, 39 ret (Gap Violation); bit 31 null'u 5 => hat NULL = 5 + gap
        rx_idle; w0 := rx_words; e0 := rx_err_gap;
        send_word(x"0F0F_0F0F", 7, 5, 40);
        send_word(x"0F0F_0F0F", 7, 5, 60);
        chk(rx_words = w0 + 2 and rx_err_gap = e0 and rx_last_gap = 40,
            "B2 gap=40 (4*min_bit) tam degerde kabul edilmeli (Word " & img(rx_words - w0) & ", gap " & img(rx_last_gap) & ")");
        rx_idle; w0 := rx_words;
        send_word(x"0F0F_0F0F", 7, 5, 39);
        send_word(x"0F0F_0F0F", 7, 5, 60);
        rx_idle;
        chk(rx_err_gap = e0 + 1 and rx_words = w0, "B2 gap=39 (< 40) Gap Violation ile reddedilmeli");
        chk(rx_err_other = 0, "B: beklenmeyen Bus Fault / Noise / Parity hatasi: " & img(rx_err_other));

        ------------------------------------------------------------------
        -- C) TX -> RX uçtan uca: TX hattı RX'te aynı sürelerle ölçülmeli
        ------------------------------------------------------------------
        rx_src <= '1';
        tick(300);
        tx_en <= '1'; msg_sched_en <= '1'; iw_gap <= u32(30);   -- gap = 23 + 30 = 53 >= 40
        w0 := rx_words;
        sched_en <= '1';
        tick(3 * (32 * (C_P + C_N) + C_G + 40));
        sched_en <= '0';
        tick(32 * (C_P + C_N) + C_G + 200);
        chk(rx_words >= w0 + 2, "C: TX -> RX en az 2 Word alinmali, alinan " & img(rx_words - w0));
        for k in 0 to 30 loop
            chk(bp_log(k) = C_P and bn_log(k) = C_N,
                "C: bit " & img(k) & " RX pulse/null " & img(bp_log(k)) & "/" & img(bn_log(k)));
        end loop;
        chk(rx_last_gap = C_G + 30, "C: RX Word gap " & img(rx_last_gap) & " clk, TX gap_dur + inter_word_gap = " & img(C_G + 30));

        if n_err = 0 then
            report "PASS: tb_a429_timing" severity note;
        else
            report "FAIL: tb_a429_timing (" & integer'image(n_err) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
