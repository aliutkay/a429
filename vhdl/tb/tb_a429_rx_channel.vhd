--------------------------------------------------------------------------------
-- tb_a429_rx_channel — a429_rx_channel birim testi (VHDL-93 / VHDL-2008 uyumlu)
--   * Custom config, 2 ardışık Word alımı + Checker, Bit Diag bit31->word1 sarma
--   * wr_strobe rastgele erişim + rd_strobe auto-increment okuma doğrulaması
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity tb_a429_rx_channel is
end entity tb_a429_rx_channel;

architecture sim of tb_a429_rx_channel is
    constant T_CLK : time := 20 ns;
    signal clk, rst_n, soft_rst, gfreeze : std_logic := '0';
    signal sim_done : boolean := false;
    signal pin_h, pin_l, tx_ws : std_logic := '0';
    signal ts_now : std_logic_vector(63 downto 0) := (others => '0');
    signal tx_w   : std_logic_vector(31 downto 0) := (others => '0');
    signal reg_in : t_rx_reg_in := C_RX_REG_IN_ZERO;
    signal reg_out: t_rx_reg_out;
    signal errors : natural := 0;

    function wire_bit(w : std_logic_vector(31 downto 0); k : natural) return std_logic is
    begin
        if k < 8 then return w(7 - k); else return w(k); end if;
    end function;
begin
    clk <= not clk after T_CLK / 2 when not sim_done else '0';

    dut : entity work.a429_rx_channel
        generic map (
            G_SYNC_STAGES => 2, G_WORD_DEPTH_LOG2 => 4, G_ERR_DEPTH_LOG2 => 4,
            G_BITDIAG_WORDS_LOG2 => 2, G_BITDIAG_EN => true, G_HAS_CHECKER => true
        )
        port map (
            clk => clk, rst_n => rst_n, soft_rst => soft_rst,
            pin_high => pin_h, pin_low => pin_l, ts_now => ts_now, global_freeze => gfreeze,
            tx_word_start => tx_ws, tx_word_tx => tx_w,
            reg_in => reg_in, reg_out => reg_out
        );

    process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop
                wait until rising_edge(clk);
                ts_now <= std_logic_vector(unsigned(ts_now) + 1);
            end loop;
            wait for 1 ns;
        end procedure;
        procedure send_frame(w : std_logic_vector(31 downto 0)) is
            variable b : std_logic;
        begin
            tx_w <= w; tx_ws <= '1'; tick(1); tx_ws <= '0';
            for k in 0 to 31 loop
                b := wire_bit(w, k);
                pin_h <= b; pin_l <= not b; tick(20);
                pin_h <= '0'; pin_l <= '0'; tick(20);
            end loop;
            pin_h <= '0'; pin_l <= '0'; tick(160);
        end procedure;
        procedure chk(cond : boolean; msg : string) is
        begin
            if not cond then report "HATA: " & msg severity error; errors <= errors + 1; end if;
        end procedure;
        constant W1 : std_logic_vector(31 downto 0) := x"A0000181"; -- 5 tane 1 (Odd)
        constant W2 : std_logic_vector(31 downto 0) := x"400002C8"; -- 5 tane 1 (Odd)
    begin
        rst_n <= '0'; tick(4); rst_n <= '1'; tick(2);

        -- Hızlı custom config uygula
        reg_in.cfg_sel   <= C_CFG_CUSTOM;
        reg_in.cust      <= (u16(2), u16(12), u16(28), u16(32), u16(48), u16(2), u16(2), u16(4), C_PAR_ODD);
        reg_in.cfg_apply <= '1'; tick(1); reg_in.cfg_apply <= '0';
        reg_in.ctrl_enable <= '1'; reg_in.chk_enable <= '1';
        tick(180);

        send_frame(W1);
        send_frame(W2);
        tick(20);

        chk(unsigned(reg_out.word_cnt) = 2 and unsigned(reg_out.chk_ok_cnt) = 2,
            "2 Word alindi ve Checker eslestirdi");

        -- 1) Rastgele erişim: doğrudan Word[1]'e atla
        reg_in.word_raddr <= u16(1); reg_in.word_raddr_wr <= '1'; tick(1); reg_in.word_raddr_wr <= '0'; tick(1);
        chk(reg_out.word_rd_data = W2, "Rastgele atlama ile Word[1] okunmali");

        -- 2) Word[0]'dan başlayıp rd_strobe auto-inc ile Word[0] -> Word[1] oku
        reg_in.word_raddr <= u16(0); reg_in.word_raddr_wr <= '1'; tick(1); reg_in.word_raddr_wr <= '0'; tick(1);
        chk(reg_out.word_rd_data = W1, "Word[0] okundu");
        reg_in.word_rd_last <= '1'; tick(1); reg_in.word_rd_last <= '0'; tick(1);
        chk(reg_out.word_rd_data = W2, "rd_strobe ile Word[1]'e otomatik gecti");

        -- 3) Bit Diag bit 31 -> Word 1 bit 0 geçişi (auto-inc carry)
        reg_in.bit_raddr_word <= x"00"; reg_in.bit_raddr_bit <= "11111";
        reg_in.bit_raddr_wr <= '1'; tick(1); reg_in.bit_raddr_wr <= '0'; tick(1);
        chk(unsigned(reg_out.bit_rd_pulse) = 20, "Word0 bit31 pulse=20");
        reg_in.bit_rd_last <= '1'; tick(1); reg_in.bit_rd_last <= '0'; tick(1);
        chk(unsigned(reg_out.bit_rd_pulse) = 20 and unsigned(reg_out.bit_rd_null) = 20,
            "bit31 -> Word1 bit0 otomatik ilerledi");

        if errors = 0 then
            report "PASS: tb_a429_rx_channel" severity note;
        else
            report "FAIL: tb_a429_rx_channel (" & integer'image(errors) & " hata)" severity failure;
        end if;
        sim_done <= true;
        wait;
    end process;
end architecture sim;
