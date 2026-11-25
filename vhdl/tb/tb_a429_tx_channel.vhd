--------------------------------------------------------------------------------
-- tb_a429_tx_channel — a429_tx_channel birim testi (VHDL-93 / VHDL-2008 uyumlu)
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;
use work.a429_presets_pkg.all;

entity tb_a429_tx_channel is
end entity tb_a429_tx_channel;

architecture sim of tb_a429_tx_channel is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst : std_logic := '0';
    signal sim_done : boolean := false;
    signal reg_in   : t_tx_reg_in := C_TX_REG_IN_ZERO;
    signal reg_out  : t_tx_reg_out;
    signal tx_h, tx_l, tx_slp, ws, wd : std_logic;
    signal w_tx     : std_logic_vector(31 downto 0);
    signal n_ws, n_wd : natural := 0;
    signal errors   : natural := 0;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_tx_channel
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            reg_in => reg_in, reg_out => reg_out,
            tx_high => tx_h, tx_low => tx_l, tx_slp => tx_slp,
            tx_word_start => ws, tx_word_done => wd, tx_word_tx => w_tx
        );

    process (clk)
    begin
        if rising_edge(clk) then
            if ws = '1' then n_ws <= n_ws + 1; end if;
            if wd = '1' then n_wd <= n_wd + 1; end if;
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
    begin
        rst_n <= '0'; tick(3); rst_n <= '1'; tick(1);
        chk(reg_out.act_cfg = C_CFG_HS and unsigned(reg_out.word_cnt) = 0, "Reset HS Preset ve cnt=0");

        -- Custom hızlandırılmış config
        reg_in.cfg_sel   <= C_CFG_CUSTOM;
        reg_in.cust      <= (pulse_dur => u16(4), null_dur => u16(4), gap_dur => u32(16), slp => '0');
        reg_in.cfg_apply <= '1'; tick(1); reg_in.cfg_apply <= '0';
        chk(reg_out.act_cfg = C_CFG_CUSTOM and tx_slp = '0', "Custom config ve slp=0 uygulandi");

        -- 2 adet tek Word gönder
        reg_in.transmitter_en <= '1';
        reg_in.msg_sched_en   <= '0';
        reg_in.builder_en     <= '0';
        reg_in.ext_data       <= x"A0000181";
        for i in 1 to 2 loop
            reg_in.send_cmd <= '1'; tick(1); reg_in.send_cmd <= '0';
            while reg_out.busy = '1' loop tick(1); end loop;
            tick(2);
        end loop;
        chk(unsigned(reg_out.word_cnt) = 2 and n_ws = 2 and n_wd = 2 and w_tx = x"A0000181",
            "TX_WORD_CNT=2, word_start=2, word_done=2 olmali");

        -- soft_rst
        soft_rst <= '1'; tick(1); soft_rst <= '0';
        chk(unsigned(reg_out.word_cnt) = 0 and reg_out.act_cfg = C_CFG_HS and reg_out.act = C_TX_PRESET_HS,
            "soft_rst TX_WORD_CNT ve Preset'i sifirlamali");

        if errors = 0 then
            report "PASS: tb_a429_tx_channel" severity note;
        else
            report "FAIL: tb_a429_tx_channel (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
