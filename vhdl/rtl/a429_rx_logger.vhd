--------------------------------------------------------------------------------
-- Dosya       : a429_rx_logger.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Tek bir RX veya TX BIT kanalının dairesel kayıt, zaman damgası yakalama,
--   FREEZE/DROP sayma ve 12-bit hata birleştirme motoru.
--
-- Gereksinimler:
--   REQ-1 : word_start = '1' anında 64-bit ts_now yakalanır (ts_word_lat) ve
--           Word RAM kaydının [143:80] alanına yazılır (Word başı zamanı).
--   REQ-2 : enable = '0' iken hiçbir RAM'e yazılmaz ve sayaçlar artmaz;
--           decoder arka planda çalışmaya devam eder.
--   REQ-3 : frozen = (freeze OR global_freeze) = '1' iken gelen Word ve
--           Error kayıtları RAM'e yazılmaz, bunun yerine drop_cnt +1 artar;
--           Bit Diagnostic yazmaları da durdurulur.
--   REQ-4 : Dairesel RAM formatları (DESIGN.md §9):
--             Word (144b)    : ts(64) & word(32) & gap(32) & gap_err(16)
--             Error (128b)   : ts(64) & code(16) & addr(16) & data(32)
--             Bit Diag (64b) : pulse(16) & pulse_err(16) & null(16) & null_err(16)
--           RAM tam dolduğunda word_wrap / err_wrap kalıcı '1' olur.
--   REQ-5 : Aynı clk'de birden fazla kaynaktan hata gelirse code bitleri
--           OR'lanır (hata kaybı olmaz); addr/data önceliği: 1. FSM,
--           2. Label filtresi, 3. Word Checker.
--   REQ-6 : clear = '1' veya soft_rst = '1' tüm sayaçları, last_word ve
--           wrap bayraklarını sıfırlar.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.a429_pkg.all;

entity a429_rx_logger is
    generic (
        G_WORD_DEPTH_LOG2    : positive := 8;
        G_ERR_DEPTH_LOG2     : positive := 8;
        G_BITDIAG_WORDS_LOG2 : positive := 3;
        G_BITDIAG_EN         : boolean  := true
    );
    port (
        clk                 : in  std_logic;
        rst_n               : in  std_logic;
        soft_rst            : in  std_logic;

        ts_now              : in  std_logic_vector(63 downto 0);

        -- Kontrol
        enable              : in  std_logic;
        freeze              : in  std_logic;
        global_freeze       : in  std_logic;
        clear               : in  std_logic;

        -- Decoder çıkışları
        word_start          : in  std_logic;
        word_data           : in  std_logic_vector(31 downto 0);
        word_gap_dur        : in  std_logic_vector(31 downto 0);
        word_gap_err_cnt    : in  std_logic_vector(15 downto 0);
        word_valid          : in  std_logic;

        bit_idx             : in  std_logic_vector(4 downto 0);
        bit_pulse_dur       : in  std_logic_vector(15 downto 0);
        bit_null_dur        : in  std_logic_vector(15 downto 0);
        bit_pulse_err_cnt   : in  std_logic_vector(15 downto 0);
        bit_null_err_cnt    : in  std_logic_vector(15 downto 0);
        bit_valid           : in  std_logic;

        err_bus_fault       : in  std_logic;
        err_noise_violation : in  std_logic;
        err_gap_violation   : in  std_logic;
        err_bit_early       : in  std_logic;
        err_pulse_glitch    : in  std_logic;
        err_pulse_stuck     : in  std_logic;
        err_bit_timeout     : in  std_logic;
        err_parity          : in  std_logic;
        err_addr            : in  std_logic_vector(15 downto 0);
        err_data            : in  std_logic_vector(31 downto 0);

        -- Opsiyonel Label filtresi ve Checker hataları
        err_label_filtered  : in  std_logic := '0';
        chk_mismatch        : in  std_logic := '0';
        chk_no_echo         : in  std_logic := '0';
        chk_unexpected      : in  std_logic := '0';
        chk_addr            : in  std_logic_vector(15 downto 0) := (others => '0');
        chk_data            : in  std_logic_vector(31 downto 0) := (others => '0');

        -- RAM yazma portları
        word_we             : out std_logic;
        word_waddr          : out std_logic_vector(G_WORD_DEPTH_LOG2 - 1 downto 0);
        word_wdata          : out std_logic_vector(143 downto 0);

        err_we              : out std_logic;
        err_waddr           : out std_logic_vector(G_ERR_DEPTH_LOG2 - 1 downto 0);
        err_wdata           : out std_logic_vector(127 downto 0);

        bit_we              : out std_logic;
        bit_waddr           : out std_logic_vector(G_BITDIAG_WORDS_LOG2 + 4 downto 0);
        bit_wdata           : out std_logic_vector(63 downto 0);

        -- Durum & sayaçlar
        frozen              : out std_logic;
        word_wrap           : out std_logic;
        err_wrap            : out std_logic;
        word_cnt            : out std_logic_vector(31 downto 0);
        err_cnt             : out std_logic_vector(31 downto 0);
        drop_cnt            : out std_logic_vector(31 downto 0);
        last_word           : out std_logic_vector(31 downto 0);
        rx_err_any          : out std_logic
    );
end entity a429_rx_logger;

architecture rtl of a429_rx_logger is
    signal ts_word_lat : std_logic_vector(63 downto 0);
    signal r_word_cnt  : unsigned(31 downto 0);
    signal r_err_cnt   : unsigned(31 downto 0);
    signal r_drop_cnt  : unsigned(31 downto 0);
    signal r_last_word : std_logic_vector(31 downto 0);
    signal r_word_wrap : std_logic;
    signal r_err_wrap  : std_logic;
    signal frozen_i    : std_logic;
    signal fsm_err_any : std_logic;
begin

    frozen_i    <= freeze or global_freeze;
    fsm_err_any <= err_bus_fault or err_noise_violation or err_gap_violation or err_bit_early
                   or err_pulse_glitch or err_pulse_stuck or err_bit_timeout or err_parity;
    rx_err_any  <= fsm_err_any;

    process (clk, rst_n)
        variable v_code    : std_logic_vector(15 downto 0);
        variable v_addr    : std_logic_vector(15 downto 0);
        variable v_data    : std_logic_vector(31 downto 0);
        variable v_has_err : boolean;
        variable v_drop    : unsigned(1 downto 0);
    begin
        if rst_n = '0' then
            ts_word_lat <= (others => '0');
            r_word_cnt  <= (others => '0');
            r_err_cnt   <= (others => '0');
            r_drop_cnt  <= (others => '0');
            r_last_word <= (others => '0');
            r_word_wrap <= '0';
            r_err_wrap  <= '0';
            word_we     <= '0';
            word_waddr  <= (others => '0');
            word_wdata  <= (others => '0');
            err_we      <= '0';
            err_waddr   <= (others => '0');
            err_wdata   <= (others => '0');
            bit_we      <= '0';
            bit_waddr   <= (others => '0');
            bit_wdata   <= (others => '0');
        elsif rising_edge(clk) then
            word_we <= '0';
            err_we  <= '0';
            bit_we  <= '0';

            if soft_rst = '1' or clear = '1' then
                r_word_cnt  <= (others => '0');
                r_err_cnt   <= (others => '0');
                r_drop_cnt  <= (others => '0');
                r_last_word <= (others => '0');
                r_word_wrap <= '0';
                r_err_wrap  <= '0';
                if soft_rst = '1' then
                    ts_word_lat <= (others => '0');
                end if;
            else
                if word_start = '1' then
                    ts_word_lat <= ts_now;
                end if;

                v_code := (others => '0');
                v_code(C_ERR_BUS_FAULT)       := err_bus_fault;
                v_code(C_ERR_NOISE_VIOLATION) := err_noise_violation;
                v_code(C_ERR_GAP_VIOLATION)   := err_gap_violation;
                v_code(C_ERR_BIT_EARLY)       := err_bit_early;
                v_code(C_ERR_PULSE_GLITCH)    := err_pulse_glitch;
                v_code(C_ERR_PULSE_STUCK)     := err_pulse_stuck;
                v_code(C_ERR_BIT_TIMEOUT)     := err_bit_timeout;
                v_code(C_ERR_PARITY)          := err_parity;
                v_code(C_ERR_WORD_MISMATCH)   := chk_mismatch;
                v_code(C_ERR_NO_ECHO)         := chk_no_echo;
                v_code(C_ERR_UNEXPECTED_WORD) := chk_unexpected;
                v_code(C_ERR_LABEL_FILTERED)  := err_label_filtered;
                v_has_err := (v_code /= x"0000");

                -- Öncelik: 1. FSM, 2. Label filtresi, 3. Checker
                if fsm_err_any = '1' then
                    v_addr := err_addr;
                    v_data := err_data;
                elsif err_label_filtered = '1' then
                    v_addr := x"00" & word_data(7 downto 0);
                    v_data := word_data;
                else
                    v_addr := chk_addr;
                    v_data := chk_data;
                end if;

                if enable = '1' then
                    v_drop := (others => '0');

                    -- Word kaydı
                    if word_valid = '1' then
                        if frozen_i = '1' then
                            v_drop := v_drop + 1;
                        else
                            word_we     <= '1';
                            word_waddr  <= std_logic_vector(r_word_cnt(G_WORD_DEPTH_LOG2 - 1 downto 0));
                            word_wdata  <= ts_word_lat & word_data & word_gap_dur & word_gap_err_cnt;
                            r_last_word <= word_data;
                            if r_word_cnt >= to_unsigned((2 ** G_WORD_DEPTH_LOG2) - 1, 32) then
                                r_word_wrap <= '1';
                            end if;
                            r_word_cnt <= r_word_cnt + 1;
                        end if;
                    end if;

                    -- Bit Diagnostic kaydı
                    if G_BITDIAG_EN and bit_valid = '1' and frozen_i = '0' then
                        bit_we    <= '1';
                        bit_waddr <= std_logic_vector(r_word_cnt(G_BITDIAG_WORDS_LOG2 - 1 downto 0)) & bit_idx;
                        bit_wdata <= bit_pulse_dur & bit_pulse_err_cnt & bit_null_dur & bit_null_err_cnt;
                    end if;

                    -- Error kaydı
                    if v_has_err then
                        if frozen_i = '1' then
                            v_drop := v_drop + 1;
                        else
                            err_we    <= '1';
                            err_waddr <= std_logic_vector(r_err_cnt(G_ERR_DEPTH_LOG2 - 1 downto 0));
                            err_wdata <= ts_now & v_code & v_addr & v_data;
                            if r_err_cnt >= to_unsigned((2 ** G_ERR_DEPTH_LOG2) - 1, 32) then
                                r_err_wrap <= '1';
                            end if;
                            r_err_cnt <= r_err_cnt + 1;
                        end if;
                    end if;

                    if v_drop /= 0 then
                        r_drop_cnt <= r_drop_cnt + resize(v_drop, 32);
                    end if;
                end if;
            end if;
        end if;
    end process;

    frozen    <= frozen_i;
    word_wrap <= r_word_wrap;
    err_wrap  <= r_err_wrap;
    word_cnt  <= std_logic_vector(r_word_cnt);
    err_cnt   <= std_logic_vector(r_err_cnt);
    drop_cnt  <= std_logic_vector(r_drop_cnt);
    last_word <= r_last_word;

end architecture rtl;
