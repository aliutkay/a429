--------------------------------------------------------------------------------
-- tb_arinc429_core
--
-- arinc429_core (TX + TX BIT + RX0/RX1 + Timestamp + RAM'ler + Word Checker +
-- Preset/Custom Config) için uçtan uca kendi kendini kontrol eden testbench.
-- Hızlı simülasyon için TX/RX Custom sürelerle (10x hızlandırılmış) de test edilir.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;
use work.a429_presets_pkg.all;

entity tb_arinc429_core is
end entity tb_arinc429_core;

architecture sim of tb_arinc429_core is
    constant T_CLK : time := 20 ns;

    signal clk           : std_logic := '0';
    signal rst_n         : std_logic := '0';

    signal rst_all       : std_logic := '0';
    signal rst_tx        : std_logic := '0';
    signal rst_txbit     : std_logic := '0';
    signal rst_rx        : std_logic_vector(1 downto 0) := (others => '0');
    signal global_freeze : std_logic := '0';
    signal ts_en         : std_logic := '1';
    signal ts_clr        : std_logic := '0';
    signal ts_lsb_rd     : std_logic := '0';
    signal ts_lsb        : std_logic_vector(31 downto 0);
    signal ts_msb        : std_logic_vector(31 downto 0);

    signal tx_reg_in     : t_tx_reg_in := C_TX_REG_IN_ZERO;
    signal tx_reg_out    : t_tx_reg_out;
    signal tb_reg_in     : t_rx_reg_in := C_RX_REG_IN_ZERO;
    signal tb_reg_out    : t_rx_reg_out;
    signal rx_reg_in     : t_rx_reg_in_arr(0 to 1) := (others => C_RX_REG_IN_ZERO);
    signal rx_reg_out    : t_rx_reg_out_arr(0 to 1);

    signal tx_high       : std_logic;
    signal tx_low        : std_logic;
    signal tx_slp        : std_logic;
    signal tb_inj_corrupt: std_logic := '0';
    signal tb_cut_line   : std_logic := '0';
    signal tb_pin_h      : std_logic;
    signal tb_pin_l      : std_logic;
    signal rx_high       : std_logic_vector(1 downto 0);
    signal rx_low        : std_logic_vector(1 downto 0);

    signal errors        : natural := 0;
begin

    clk <= not clk after T_CLK / 2;

    -- TX -> RX0 doğrudan loopback; TX -> TB (hata enjeksiyon anahtarlı)
    rx_high(0) <= tx_high;
    rx_low(0)  <= tx_low;
    rx_high(1) <= '0';
    rx_low(1)  <= '0';

    tb_pin_h <= '0'     when tb_cut_line = '1' else
                tx_low  when tb_inj_corrupt = '1' else
                tx_high;
    tb_pin_l <= '0'     when tb_cut_line = '1' else
                tx_high when tb_inj_corrupt = '1' else
                tx_low;

    dut : entity work.arinc429_core
        generic map (
            G_NUM_RX             => 2,
            G_TX_EN              => true,
            G_TXBIT_EN           => true,
            G_SYNC_STAGES        => 2,
            G_WORD_DEPTH_LOG2    => 8,
            G_ERR_DEPTH_LOG2     => 8,
            G_BITDIAG_WORDS_LOG2 => 3,
            G_BITDIAG_EN         => true,
            G_CHK_FIFO_DEPTH     => 4
        )
        port map (
            clk           => clk,
            rst_n         => rst_n,
            rst_all       => rst_all,
            rst_tx        => rst_tx,
            rst_txbit     => rst_txbit,
            rst_rx        => rst_rx,
            global_freeze => global_freeze,
            ts_en         => ts_en,
            ts_clr        => ts_clr,
            ts_lsb_rd     => ts_lsb_rd,
            ts_lsb        => ts_lsb,
            ts_msb        => ts_msb,
            tx_reg_in     => tx_reg_in,
            tx_reg_out    => tx_reg_out,
            tb_reg_in     => tb_reg_in,
            tb_reg_out    => tb_reg_out,
            rx_reg_in     => rx_reg_in,
            rx_reg_out    => rx_reg_out,
            tx_high       => tx_high,
            tx_low        => tx_low,
            tx_slp        => tx_slp,
            txbit_rx_high => tb_pin_h,
            txbit_rx_low  => tb_pin_l,
            rx_high       => rx_high,
            rx_low        => rx_low
        );

    stim : process
        procedure tick(n : natural := 1) is
        begin
            for i in 1 to n loop
                wait until rising_edge(clk);
            end loop;
        end procedure;

        procedure chk(cond : boolean; msg : string) is
        begin
            if cond then
                report "OK   : " & msg severity note;
            else
                report "HATA : " & msg severity error;
                errors <= errors + 1;
            end if;
        end procedure;

        variable fast_rx : t_rx_cfg;
        variable fast_tx : t_tx_cfg;
        variable w0      : std_logic_vector(31 downto 0);
        variable w_cnt0  : unsigned(31 downto 0);
    begin
        rst_n <= '0';
        tick(5);
        rst_n <= '1';
        tick(5);

        -- 1) Reset sonrası Preset HS (mode = 00) aktif olmalı
        chk(tx_reg_out.act_cfg = C_CFG_HS and tx_reg_out.act = C_TX_PRESET_HS,
            "Reset sonrasi TX High Speed Preset aktif");
        chk(rx_reg_out(0).status_act_cfg = C_CFG_HS and rx_reg_out(0).act = C_RX_PRESET_HS,
            "Reset sonrasi RX0 High Speed Preset aktif");
        chk(tb_reg_out.status_act_cfg = C_CFG_HS and tx_slp = '1',
            "Reset sonrasi TB High Speed Preset ve tx_slp=1");

        -- 2) Custom hızlandırılmış Config uygula (bit=40 clk, pulse=20, null=20, gap=160)
        fast_tx := (pulse_dur => u16(20), null_dur => u16(20), gap_dur => u32(160), slp => '1');
        fast_rx := (
            glitch_filter_size => u16(2),
            min_pulse          => u16(12),
            max_pulse          => u16(28),
            min_bit            => u16(32),
            max_bit            => u16(48),
            max_pulse_err      => u16(2),
            max_null_err       => u16(2),
            max_gap_err        => u16(4),
            parity_mode        => C_PAR_ODD
        );

        tx_reg_in.cfg_sel   <= C_CFG_CUSTOM;
        tx_reg_in.cust      <= fast_tx;
        tx_reg_in.cfg_apply <= '1';
        rx_reg_in(0).cfg_sel   <= C_CFG_CUSTOM;
        rx_reg_in(0).cust      <= fast_rx;
        rx_reg_in(0).cfg_apply <= '1';
        tb_reg_in.cfg_sel      <= C_CFG_CUSTOM;
        tb_reg_in.cust         <= fast_rx;
        tb_reg_in.cfg_apply    <= '1';
        tick(1);
        tx_reg_in.cfg_apply    <= '0';
        rx_reg_in(0).cfg_apply <= '0';
        tb_reg_in.cfg_apply    <= '0';
        tick(2);

        chk(tx_reg_out.act_cfg = C_CFG_CUSTOM and tx_reg_out.act = fast_tx,
            "TX Custom Config ACT_* ve ACT_CFG dogrulandi");
        chk(rx_reg_out(0).status_act_cfg = C_CFG_CUSTOM and rx_reg_out(0).act = fast_rx,
            "RX0 Custom Config ACT_* ve ACT_CFG dogrulandi");

        -- Decoder'ın ERR_RECOVERY'den çıkması için 4*min_bit + marj bekle
        rx_reg_in(0).ctrl_enable <= '1';
        tb_reg_in.ctrl_enable    <= '1';
        tb_reg_in.chk_enable     <= '1';
        tb_reg_in.chk_timeout    <= u32(3000);
        tick(200);

        -- 3) TX Word Builder ile tek Word gönder (Label=0o310=0xC8, SDI=1, Data=0x12345, SSM=3, Odd)
        tx_reg_in.transmitter_en <= '1';
        tx_reg_in.msg_sched_en   <= '0';
        tx_reg_in.builder_en     <= '1';
        tx_reg_in.label_val      <= x"C8";
        tx_reg_in.sdi            <= "01";
        tx_reg_in.data           <= "001" & x"2345";
        tx_reg_in.ssm            <= "11";
        tx_reg_in.parity_type    <= '1'; -- Odd
        tick(1);
        tx_reg_in.send_cmd <= '1';
        tick(1);
        tx_reg_in.send_cmd <= '0';

        -- Gönderim + RX decoding bitene kadar bekle
        tick(1800);

        w0 := '1' & "11" & "001" & x"2345" & "01" & x"C8"; -- 1 sayısı: 1+2+1+1+1+1+2+1+3=13 -> tek, parity='0' kontrol edelim
        chk(unsigned(tx_reg_out.word_cnt) = 1, "TX_WORD_CNT = 1");
        chk(unsigned(rx_reg_out(0).word_cnt) = 1, "RX0 WORD_CNT = 1");
        chk(unsigned(tb_reg_out.word_cnt) = 1, "TB WORD_CNT = 1");
        chk(unsigned(tb_reg_out.chk_ok_cnt) = 1 and unsigned(tb_reg_out.chk_err_cnt) = 0,
            "TX BIT Checker ilk Word'u eslestirdi (OK=1, ERR=0)");
        chk(rx_reg_out(0).last_word(30 downto 0) = ("11" & "001" & x"2345" & "01" & x"C8"),
            "RX0 LAST_WORD alanlari (Label/SDI/Data/SSM) birebir dogru");

        -- Word RAM & Bit Diagnostic RAM okuma testi (FREEZE=1 ile)
        rx_reg_in(0).ctrl_freeze    <= '1';
        rx_reg_in(0).word_raddr     <= u16(0);
        rx_reg_in(0).bit_raddr_word <= x"00";
        rx_reg_in(0).bit_raddr_bit  <= "00000";
        tick(3);
        chk(rx_reg_out(0).status_frozen = '1', "RX0 STATUS.FROZEN = 1");
        chk(rx_reg_out(0).word_rd_data = rx_reg_out(0).last_word, "RX0 Word RAM[0] verisi dogru");
        chk(unsigned(rx_reg_out(0).bit_rd_pulse) = 20 and unsigned(rx_reg_out(0).bit_rd_null) = 20,
            "RX0 Bit Diag RAM[0, bit0] pulse=20, null=20");

        -- 4) Freeze aktifken bir Word daha gönder -> RX0 DROP_CNT=1, TB normal almalı
        tx_reg_in.builder_en <= '0';
        tx_reg_in.ext_data   <= x"A0000181"; -- Odd parity (5 tane 1)
        tick(1);
        tx_reg_in.send_cmd <= '1';
        tick(1);
        tx_reg_in.send_cmd <= '0';
        tick(1800);

        chk(unsigned(rx_reg_out(0).drop_cnt) = 1 and unsigned(rx_reg_out(0).word_cnt) = 1,
            "RX0 FREEZE sirasinda gelen Word DROP_CNT'ye sayildi");
        chk(unsigned(tb_reg_out.chk_ok_cnt) = 2, "TB ikinci Word'u eslestirdi (OK=2)");
        rx_reg_in(0).ctrl_freeze <= '0';
        tick(2);

        -- 5) Message Scheduler testi (3+ Word gönderip durdur, Δ TX_WORD_CNT doğrula)
        w_cnt0 := unsigned(tx_reg_out.word_cnt);
        tx_reg_in.msg_sched_en   <= '1';
        tx_reg_in.initial_delay  <= u32(10);
        tx_reg_in.inter_word_gap <= u32(20);
        tx_reg_in.sched_en       <= '1';
        tick(4600);
        tx_reg_in.sched_en <= '0';
        tick(1800);
        chk(unsigned(tx_reg_out.word_cnt) - w_cnt0 >= 3, "Scheduler en az 3 Word gonderdi");
        chk(unsigned(tb_reg_out.chk_ok_cnt) = unsigned(tx_reg_out.word_cnt),
            "Scheduler Word'lerinin tamami TX BIT Checker'da OK");
        tx_reg_in.msg_sched_en <= '0';

        -- 6) TX BIT NO_ECHO timeout testi (hattı kes)
        tb_cut_line <= '1';
        tick(5);
        tx_reg_in.send_cmd <= '1';
        tick(1);
        tx_reg_in.send_cmd <= '0';
        tick(3500);
        tb_cut_line <= '0';
        chk(unsigned(tb_reg_out.chk_err_cnt) = 1 and unsigned(tb_reg_out.err_cnt) = 1,
            "Hat kesikken TX BIT NO_ECHO hatasi uretildi");
        tb_reg_in.err_raddr <= u16(0);
        tick(2);
        chk(tb_reg_out.err_rd_code(C_ERR_NO_ECHO) = '1' and tb_reg_out.err_rd_data = x"A0000181",
            "TB Error RAM[0] NO_ECHO kodu ve beklenen Word dogru");

        -- 7) Atomic Timestamp TS_LSB okuma latch'i testi
        ts_lsb_rd <= '1';
        tick(1);
        ts_lsb_rd <= '0';
        tick(1);
        chk(unsigned(ts_lsb) > 0 and unsigned(ts_msb) = 0, "Timestamp sayiyor ve TS_MSB latch edildi");

        -- 8) SOFT_RESET.ALL -> Preset HS'e geri dönüş
        rst_all <= '1';
        tick(1);
        rst_all <= '0';
        tick(3);
        chk(tx_reg_out.act_cfg = C_CFG_HS and rx_reg_out(0).status_act_cfg = C_CFG_HS,
            "SOFT_RESET.ALL sonrasi TX ve RX0 High Speed Preset'e dondu");
        chk(unsigned(tx_reg_out.word_cnt) = 0 and unsigned(rx_reg_out(0).word_cnt) = 0,
            "SOFT_RESET.ALL sonrasi sayaclar sifirlandi");

        if errors = 0 then
            report "SONUC: TUM ARINC429 CORE TESTLERI GECTI" severity note;
        else
            report "SONUC: " & integer'image(errors) & " HATA VAR" severity failure;
        end if;
        std.env.stop;
    end process;

end architecture sim;
