--------------------------------------------------------------------------------
-- Dosya       : a429_presets_pkg.vhd
-- Standart    : VHDL-93 / VHDL-2008 uyumlu
--
-- Amaç:
--   Reset sonrası veya CFG_SEL = 0/1 seçildiğinde donanıma yüklenen gömülü
--   High Speed (100 kbps) ve Low Speed (12.5 kbps) RX/TX preset sabitlerini
--   barındırır.
--
-- Gereksinimler:
--   REQ-1 : Tüm preset süreleri sıfırdan büyük, geçerli ARINC 429 zamanlama
--           sınırlarında olmalıdır (reset anında alıcı kilitlenmemelidir).
--   REQ-2 : Değerler ARINC 429 Test Aracı (a429/model.py, a429/txcfg.py) ile
--           50 MHz sistem saati, HI-8591 RX, HI-8597 TX ve LVCMOS33 için
--           hesaplanmıştır; farklı saat frekanslarında tool'dan güncellenir.
--   REQ-3 : Preset'lerde varsayılan parity modu Odd (C_PAR_ODD = "01"),
--           TX eğim pini HS için '1' (1.5 µs), LS için '0' (10 µs) olmalıdır.
--------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use work.a429_pkg.all;

package a429_presets_pkg is

    -- RX High Speed (100 kbps @ 50 MHz)
    constant C_RX_PRESET_HS : t_rx_cfg := (
        glitch_filter_size => u16(20),
        min_pulse          => u16(81),
        max_pulse          => u16(408),
        min_bit            => u16(463),
        max_bit            => u16(539),
        max_pulse_err      => u16(8),
        max_null_err       => u16(9),
        max_gap_err        => u16(185),
        parity_mode        => C_PAR_ODD
    );

    -- RX Low Speed (12.5 kbps @ 50 MHz)
    constant C_RX_PRESET_LS : t_rx_cfg := (
        glitch_filter_size => u16(245),
        min_pulse          => u16(980),
        max_pulse          => u16(2915),
        min_bit            => u16(3704),
        max_bit            => u16(4306),
        max_pulse_err      => u16(98),
        max_null_err       => u16(106),
        max_gap_err        => u16(1481),
        parity_mode        => C_PAR_ODD
    );

    -- TX High Speed (100 kbps @ 50 MHz: 5 µs pulse, 5 µs null, 40 µs gap, SLP=1)
    constant C_TX_PRESET_HS : t_tx_cfg := (
        pulse_dur => u16(250),
        null_dur  => u16(250),
        gap_dur   => u32(2000),
        slp       => '1'
    );

    -- TX Low Speed (12.5 kbps @ 50 MHz: 40 µs pulse, 40 µs null, 320 µs gap, SLP=0)
    constant C_TX_PRESET_LS : t_tx_cfg := (
        pulse_dur => u16(2000),
        null_dur  => u16(2000),
        gap_dur   => u32(16000),
        slp       => '0'
    );

end package a429_presets_pkg;
