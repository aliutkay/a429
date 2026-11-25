--------------------------------------------------------------------------------
-- tb_a429_tx_core — a429_tx_core 3-MUX birim testi (VHDL-93 / VHDL-2008 uyumlu)
--   * MUX 1: Word Builder vs EXT_DATA
--   * MUX 2: Message Scheduler vs SEND_CMD
--   * MUX 3: Word Transmitter vs Hat Override (NULL, HIGH, LOW, HIGH-Z "11")
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;

entity tb_a429_tx_core is
end entity tb_a429_tx_core;

architecture sim of tb_a429_tx_core is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst : std_logic := '0';
    signal sim_done : boolean := false;

    signal act_cfg : t_tx_cfg := (pulse_dur => u16(4), null_dur => u16(4), gap_dur => u32(16), slp => '1');
    signal tx_en, sched_mode, bld_en, par_type, sched_en, send_cmd, ext_h, ext_l : std_logic := '0';
    signal lbl  : std_logic_vector(7 downto 0)  := x"C8";
    signal sdi  : std_logic_vector(1 downto 0)  := "01";
    signal data : std_logic_vector(18 downto 0) := "000" & x"0001";
    signal ssm  : std_logic_vector(1 downto 0)  := "10";
    signal idly : std_logic_vector(31 downto 0) := u32(2);
    signal iwgp : std_logic_vector(31 downto 0) := u32(2);
    signal extd : std_logic_vector(31 downto 0) := x"DEADBEEF";

    signal tx_h, tx_l, tx_slp, tx_busy, sc_act : std_logic;
    signal tx_w : std_logic_vector(31 downto 0);
    signal errors : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_tx_core
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst, act_cfg => act_cfg,
            transmitter_en => tx_en, msg_sched_en => sched_mode, builder_en => bld_en,
            label_val => lbl, sdi => sdi, data => data, ssm => ssm, parity_type => par_type,
            sched_en => sched_en, initial_delay => idly, inter_word_gap => iwgp,
            send_cmd => send_cmd, ext_data => extd, ext_high => ext_h, ext_low => ext_l,
            tx_high => tx_h, tx_low => tx_l, tx_slp => tx_slp,
            tx_busy => tx_busy, tx_sched_act => sc_act, tx_word_tx => tx_w
        );

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop wait until rising_edge(clk); wait for 1 ns; end loop;
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
    begin
        rst_n <= '0'; tick(3); rst_n <= '1'; tick(1);

        -- 1) MUX 3 Override testi (transmitter_en = 0): HIGH, LOW, HIGH-Z (11), NULL
        tx_en <= '0';
        ext_h <= '1'; ext_l <= '0'; tick(1); chk(tx_h = '1' and tx_l = '0', "Override HIGH (10)");
        ext_h <= '0'; ext_l <= '1'; tick(1); chk(tx_h = '0' and tx_l = '1', "Override LOW (01)");
        ext_h <= '1'; ext_l <= '1'; tick(1); chk(tx_h = '1' and tx_l = '1', "Override HIGH-Z (11)");
        ext_h <= '0'; ext_l <= '0'; tick(1); chk(tx_h = '0' and tx_l = '0', "Override NULL (00)");

        -- Override iken SEND_CMD transmitter'ı tetiklememeli
        send_cmd <= '1'; tick(1); send_cmd <= '0'; tick(1);
        chk(tx_busy = '0', "Override modunda SEND_CMD etkisiz olmali");

        -- 2) MUX 1 = EXT_DATA (builder_en=0), MUX 2 = SEND_CMD (msg_sched_en=0), MUX 3 = Transmitter (1)
        tx_en <= '1'; sched_mode <= '0'; bld_en <= '0';
        send_cmd <= '1'; tick(1); send_cmd <= '0';
        chk(tx_busy = '1' and tx_w = x"DEADBEEF", "MUX1=EXT_DATA + MUX2=SEND_CMD calismali");
        while tx_busy = '1' loop tick(1); end loop;

        -- 3) MUX 1 = Word Builder (builder_en=1), MUX 2 = Scheduler (msg_sched_en=1)
        bld_en <= '1'; par_type <= '1'; sched_mode <= '1'; sched_en <= '1';
        tick(5);
        chk(sc_act = '1' and tx_busy = '1' and tx_w(7 downto 0) = x"C8",
            "MUX1=Builder + MUX2=Scheduler calismali");
        chk(tx_slp = '1', "tx_slp aktif config'ten surulmeli");
        sched_en <= '0';
        while tx_busy = '1' loop tick(1); end loop;

        if errors = 0 then
            report "PASS: tb_a429_tx_core" severity note;
        else
            report "FAIL: tb_a429_tx_core (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
