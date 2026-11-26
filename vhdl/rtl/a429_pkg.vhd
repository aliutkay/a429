--------------------------------------------------------------------------------
-- Dosya       : a429_pkg.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   ARINC 429 IP'nin tüm blokları arasında paylaşılan sabitler, config
--   record'ları, AXIL Studio register arayüzü record'ları ve yardımcı
--   dönüşüm fonksiyonlarını tanımlar.
--
-- Gereksinimler:
--   REQ-1 : Config seçim kodları DESIGN.md ile birebir uyumlu olmalıdır:
--             "00" = High Speed Preset (100 kbps)
--             "01" = Low Speed Preset (12.5 kbps)
--             "10" = Custom (CUST_* register değerleri)
--   REQ-2 : Parity mod kodları: "00" kapalı, "01" Odd, "10" Even.
--   REQ-3 : 12 bitlik hata kodu bit indeksleri (C_ERR_BUS_FAULT=0 ..
--           C_ERR_LABEL_FILTERED=11) DESIGN.md §9 ve Python a429/decode.py
--           ERR_NAMES listesi ile birebir örtüşmelidir.
--   REQ-4 : t_rx_reg_in/out ve t_tx_reg_in/out record'ları AXIL Studio'nun
--           ürettiği arinc429_axil.v portlarını temiz şekilde gruplamalıdır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package a429_pkg is

    -- Config seçim kodları (CFG_SEL / ACT_CFG)
    constant C_CFG_HS     : std_logic_vector(1 downto 0) := "00";  -- High Speed Preset (100 kbps)
    constant C_CFG_LS     : std_logic_vector(1 downto 0) := "01";  -- Low Speed Preset (12.5 kbps)
    constant C_CFG_CUSTOM : std_logic_vector(1 downto 0) := "10";  -- Custom (CUST_* register'ları)

    -- Parity modları
    constant C_PAR_NONE : std_logic_vector(1 downto 0) := "00";
    constant C_PAR_ODD  : std_logic_vector(1 downto 0) := "01";
    constant C_PAR_EVEN : std_logic_vector(1 downto 0) := "10";

    -- Hata kodu bitmask indeksleri (DESIGN.md §9 & a429/decode.py ERR_NAMES)
    constant C_ERR_BUS_FAULT       : natural := 0;
    constant C_ERR_NOISE_VIOLATION : natural := 1;
    constant C_ERR_GAP_VIOLATION   : natural := 2;
    constant C_ERR_BIT_EARLY       : natural := 3;
    constant C_ERR_PULSE_GLITCH    : natural := 4;
    constant C_ERR_PULSE_STUCK     : natural := 5;
    constant C_ERR_BIT_TIMEOUT     : natural := 6;
    constant C_ERR_PARITY          : natural := 7;
    constant C_ERR_WORD_MISMATCH   : natural := 8;
    constant C_ERR_NO_ECHO         : natural := 9;
    constant C_ERR_UNEXPECTED_WORD : natural := 10;
    constant C_ERR_LABEL_FILTERED  : natural := 11;

    -- RX kanal aktif / custom config record'u
    type t_rx_cfg is record
        glitch_filter_size : std_logic_vector(15 downto 0);
        min_pulse          : std_logic_vector(15 downto 0);
        max_pulse          : std_logic_vector(15 downto 0);
        min_bit            : std_logic_vector(15 downto 0);
        max_bit            : std_logic_vector(15 downto 0);
        max_pulse_err      : std_logic_vector(15 downto 0);
        max_null_err       : std_logic_vector(15 downto 0);
        max_gap_err        : std_logic_vector(15 downto 0);
        parity_mode        : std_logic_vector(1 downto 0);
    end record;

    -- TX kanal aktif / custom config record'u
    type t_tx_cfg is record
        pulse_dur : std_logic_vector(15 downto 0);
        null_dur  : std_logic_vector(15 downto 0);
        gap_dur   : std_logic_vector(31 downto 0);
        slp       : std_logic;
    end record;

    -- AXIL Studio (arinc429_axil) -> RX/TB kanal kayıt girişleri
    type t_rx_reg_in is record
        ctrl_enable      : std_logic;
        ctrl_freeze      : std_logic;
        ctrl_clear       : std_logic;
        cfg_sel          : std_logic_vector(1 downto 0);
        cfg_apply        : std_logic;
        cust             : t_rx_cfg;
        word_raddr       : std_logic_vector(15 downto 0);
        word_raddr_wr    : std_logic;
        word_rd_last     : std_logic;
        err_raddr        : std_logic_vector(15 downto 0);
        err_raddr_wr     : std_logic;
        err_rd_last      : std_logic;
        bit_raddr_bit    : std_logic_vector(4 downto 0);
        bit_raddr_word   : std_logic_vector(7 downto 0);
        bit_raddr_wr     : std_logic;
        bit_rd_last      : std_logic;
        chk_enable       : std_logic;
        chk_clear        : std_logic;
        chk_timeout      : std_logic_vector(31 downto 0);
    end record;

    -- RX/TB kanal -> AXIL Studio (arinc429_axil) durum ve okuma çıkışları
    type t_rx_reg_out is record
        status_frozen    : std_logic;
        status_word_wrap : std_logic;
        status_err_wrap  : std_logic;
        status_act_cfg   : std_logic_vector(1 downto 0);
        status_line_high : std_logic;   -- senkronlanmış ham hat HIGH (alıcı OUTA)
        status_line_low  : std_logic;   -- senkronlanmış ham hat LOW  (alıcı OUTB)
        status_sync_wait : std_logic;   -- decoder hat senkronu (temiz NULL) bekliyor
        act              : t_rx_cfg;
        word_cnt         : std_logic_vector(31 downto 0);
        err_cnt          : std_logic_vector(31 downto 0);
        drop_cnt         : std_logic_vector(31 downto 0);
        last_word        : std_logic_vector(31 downto 0);
        word_rd_ts_msb   : std_logic_vector(31 downto 0);
        word_rd_ts_lsb   : std_logic_vector(31 downto 0);
        word_rd_data     : std_logic_vector(31 downto 0);
        word_rd_gap      : std_logic_vector(31 downto 0);
        word_rd_gap_err  : std_logic_vector(15 downto 0);
        err_rd_ts_msb    : std_logic_vector(31 downto 0);
        err_rd_ts_lsb    : std_logic_vector(31 downto 0);
        err_rd_code      : std_logic_vector(15 downto 0);
        err_rd_addr      : std_logic_vector(15 downto 0);
        err_rd_data      : std_logic_vector(31 downto 0);
        bit_rd_pulse     : std_logic_vector(15 downto 0);
        bit_rd_pulse_err : std_logic_vector(15 downto 0);
        bit_rd_null      : std_logic_vector(15 downto 0);
        bit_rd_null_err  : std_logic_vector(15 downto 0);
        chk_ok_cnt       : std_logic_vector(31 downto 0);
        chk_err_cnt      : std_logic_vector(31 downto 0);
        chk_fifo_level   : std_logic_vector(3 downto 0);
        chk_fifo_ovf     : std_logic;
    end record;

    type t_rx_reg_in_arr  is array (natural range <>) of t_rx_reg_in;
    type t_rx_reg_out_arr is array (natural range <>) of t_rx_reg_out;

    -- AXIL Studio (arinc429_axil) -> TX kanal kayıt girişleri
    type t_tx_reg_in is record
        transmitter_en : std_logic;
        msg_sched_en   : std_logic;
        builder_en     : std_logic;
        label_val      : std_logic_vector(7 downto 0);
        sdi            : std_logic_vector(1 downto 0);
        data           : std_logic_vector(18 downto 0);
        ssm            : std_logic_vector(1 downto 0);
        parity_type    : std_logic;
        sched_en       : std_logic;
        initial_delay  : std_logic_vector(31 downto 0);
        inter_word_gap : std_logic_vector(31 downto 0);
        send_cmd       : std_logic;
        ext_data       : std_logic_vector(31 downto 0);
        ext_high       : std_logic;
        ext_low        : std_logic;
        cfg_sel        : std_logic_vector(1 downto 0);
        cfg_apply      : std_logic;
        cust           : t_tx_cfg;
    end record;

    -- TX kanal -> AXIL Studio (arinc429_axil) durum çıkışları
    type t_tx_reg_out is record
        act          : t_tx_cfg;
        busy         : std_logic;
        sched_active : std_logic;
        act_cfg      : std_logic_vector(1 downto 0);
        word_cnt     : std_logic_vector(31 downto 0);
    end record;

    constant C_RX_CFG_ZERO : t_rx_cfg := (
        glitch_filter_size => (others => '0'),
        min_pulse          => (others => '0'),
        max_pulse          => (others => '0'),
        min_bit            => (others => '0'),
        max_bit            => (others => '0'),
        max_pulse_err      => (others => '0'),
        max_null_err       => (others => '0'),
        max_gap_err        => (others => '0'),
        parity_mode        => C_PAR_ODD
    );

    constant C_TX_CFG_ZERO : t_tx_cfg := (
        pulse_dur => (others => '0'),
        null_dur  => (others => '0'),
        gap_dur   => (others => '0'),
        slp       => '0'
    );

    constant C_RX_REG_IN_ZERO : t_rx_reg_in := (
        ctrl_enable    => '0',
        ctrl_freeze    => '0',
        ctrl_clear     => '0',
        cfg_sel        => C_CFG_HS,
        cfg_apply      => '0',
        cust           => C_RX_CFG_ZERO,
        word_raddr     => (others => '0'),
        word_raddr_wr  => '0',
        word_rd_last   => '0',
        err_raddr      => (others => '0'),
        err_raddr_wr   => '0',
        err_rd_last    => '0',
        bit_raddr_bit  => (others => '0'),
        bit_raddr_word => (others => '0'),
        bit_raddr_wr   => '0',
        bit_rd_last    => '0',
        chk_enable     => '0',
        chk_clear      => '0',
        chk_timeout    => (others => '0')
    );

    constant C_TX_REG_IN_ZERO : t_tx_reg_in := (
        transmitter_en => '0',
        msg_sched_en   => '0',
        builder_en     => '0',
        label_val      => (others => '0'),
        sdi            => (others => '0'),
        data           => (others => '0'),
        ssm            => (others => '0'),
        parity_type    => '1',
        sched_en       => '0',
        initial_delay  => (others => '0'),
        inter_word_gap => std_logic_vector(to_unsigned(1, 32)),
        send_cmd       => '0',
        ext_data       => (others => '0'),
        ext_high       => '0',
        ext_low        => '0',
        cfg_sel        => C_CFG_HS,
        cfg_apply      => '0',
        cust           => C_TX_CFG_ZERO
    );

    function u16(n : natural) return std_logic_vector;
    function u32(n : natural) return std_logic_vector;
    function max_nat(a, b : natural) return natural;

end package a429_pkg;

package body a429_pkg is

    function u16(n : natural) return std_logic_vector is
    begin
        return std_logic_vector(to_unsigned(n, 16));
    end function;

    function u32(n : natural) return std_logic_vector is
    begin
        return std_logic_vector(to_unsigned(n, 32));
    end function;

    function max_nat(a, b : natural) return natural is
    begin
        if a >= b then
            return a;
        else
            return b;
        end if;
    end function;

end package body a429_pkg;
