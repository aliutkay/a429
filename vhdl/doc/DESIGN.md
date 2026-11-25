# arinc429_ip — AXI4-Lite + AXIL Studio Tasarım Dokümanı

ARINC 429 verici (TX), verici doğrulama (TX BIT + Word Checker) ve çok kanallı alıcı (RX0..RXn) IP'si.
Bus katmanı **AXI4-Lite**'tır ve doğrudan **AXIL Studio** (`axilgen` / ZipCPU `easyaxil.v`) ile üretilir; çekirdek mantığı saf **VHDL-2008**'dir.

> Eski APB3 tabanlı tasarım dokümanları arşiv olarak [`legacy_apb3/`](legacy_apb3/) altında saklanmıştır.

---

## 1. Genel Mimari

```text
                AXI4-Lite (S_AXI_*) — IP clock (S_AXI_ACLK)
                                    │
                  ┌─────────────────▼─────────────────┐
                  │  arinc429_axil.v (AXIL Studio)    │  <- vhdl/axil/arinc429_axil.regspec.json
                  │  easyaxil tabanlı AXI4-Lite slave │     (171 register, 64 KB pencere)
                  │  RW / RO / PULSE / CONST / rd_stb │
                  └─────────────────┬─────────────────┘
                     o_* / i_*      │      (arinc429_ip.vhd bağlar)
                  ┌─────────────────▼─────────────────┐
                  │      arinc429_core.vhd (VHDL)     │
                  │  • a429_rst_sync                  │
                  │  • a429_timestamp (64-bit, atomik)│
                  │  • a429_tx_channel   ──► tx_high / tx_low / tx_slp
                  │      │ word_start, word_tx        │
                  │      ▼                            │
                  │  • a429_rx_channel (TB + Checker) ◄── txbit_rx_high / txbit_rx_low
                  │  • a429_rx_channel × G_NUM_RX     ◄── rx_high[N-1:0] / rx_low[N-1:0]
                  └───────────────────────────────────┘
```

### Dosya Yapısı

| Konum | Açıklama |
|---|---|
| `vhdl/axil/arinc429.axproj.json` | Doğrudan **AXIL Studio**'da açılabilen proje dosyası (`"panel": "arinc429"` tanımlı) |
| `vhdl/axil/arinc429_axil.regspec.json` | AXIL Studio Slave Interface Wrapper register tanımı |
| `vhdl/axil/arinc429_axil.v` | AXIL Studio üretimi AXI4-Lite slave (`S_AXI_*` + `o_*`/`i_*` portları) |
| `vhdl/axil/arinc429_axil_pk.v` | HDL Designer için paketli (`SLAVE_AXI_REQ/RSP`) sarmalayıcı |
| `vhdl/axil/arinc429_axil_tb.v` | Icarus Verilog kendi kendini doğrulayan AXI4-Lite testbench (685 kontrol) |
| `vhdl/axil/arinc429_axil_regs.md` | Otomatik üretilmiş tam register haritası dokümanı |
| `vhdl/scripts/gen_axil_spec.py` | Farklı `G_NUM_RX` / `G_CLK_HZ` yapılandırmaları için spec + `arinc429_ip.vhd` üreteci |
| `vhdl/rtl/a429_pkg.vhd` | Config record'ları, hata kodu sabitleri, kanal register record'ları |
| `vhdl/rtl/a429_presets_pkg.vhd` | 50 MHz High Speed (100 kbps) ve Low Speed (12.5 kbps) RX/TX preset sabitleri |
| `vhdl/rtl/a429_rst_sync.vhd` | Asenkron assert, senkron deassert 2-FF reset senkronizatörü |
| `vhdl/rtl/a429_timestamp.vhd` | 64-bit zaman damgası; `o_ts_lsb_rd` ile 1-clk gecikmeli `msb_d1` atomik latch |
| `vhdl/rtl/a429_sdp_ram.vhd` | Generic Simple Dual-Port BRAM (Word 144b, Error 128b, Bit Diag 64b) |
| `vhdl/rtl/a429_cdc_sync.vhd` | `G_SYNC_STAGES` kademeli `ASYNC_REG` giriş senkronizatörü |
| `vhdl/rtl/a429_glitch_filter.vhd` | 2-bit tek sembol süre-koruyan glitch filtresi + doyumlu sayaçlar |
| `vhdl/rtl/a429_rx_decoder.vhd` | ARINC 429 bit/Word çözücü, bit-31 null tahmini, 8 fiziksel hata bayrağı |
| `vhdl/rtl/a429_rx_core.vhd` | `cdc_sync` → `glitch_filter` → `rx_decoder` ön ucu |
| `vhdl/rtl/a429_rx_cfg_sel.vhd` | RX Preset (HS/LS) / Custom seçici (`CFG_APPLY` → 1 clk aktifleşme, `ACT_CFG`) |
| `vhdl/rtl/a429_rx_logger.vhd` | Dairesel RAM yazıcı, `FREEZE`/`DROP_CNT`, `WORD_WRAP`/`ERR_WRAP`, 12-bit hata birleştirici |
| `vhdl/rtl/a429_word_checker.vhd` | TX BIT beklenen Word FIFO (`WORD_MISMATCH`, `NO_ECHO`, `UNEXPECTED_WORD`) |
| `vhdl/rtl/a429_rx_channel.vhd` | Tek alıcı kanalı (`cfg_sel` + `rx_core` + `rx_logger` + 3× `sdp_ram` + `wr/rd_strobe` otomatik artan RADDR pointer + ops. `word_checker`) |
| `vhdl/rtl/a429_tx_cfg_sel.vhd` | TX Preset (HS/LS) / Custom seçici (`tx_busy = 0`'da anında, meşgulken Word sınırında uygular) |
| `vhdl/rtl/a429_tx_core.vhd` | MUX1 (Word Builder / `EXT_DATA`), MUX2 (Message Scheduler / `SEND_CMD`), MUX3 (Transmitter / Override) |
| `vhdl/rtl/a429_tx_word_evt.vhd` | `tx_busy` kenarından `word_start` / `word_done` darbesi |
| `vhdl/rtl/a429_tx_channel.vhd` | TX kanalı (`tx_cfg_sel` + `tx_core` + `tx_word_evt` + `TX_WORD_CNT`) |
| `vhdl/rtl/arinc429_core.vhd` | Bus-bağımsız saf VHDL çekirdek (`G_NUM_RX`, `G_TX_EN`, `G_TXBIT_EN` generic) |
| `vhdl/rtl/arinc429_ip.vhd` | `arinc429_axil` (Verilog) + `arinc429_core` (VHDL) karma-dil AXI4-Lite üst modülü |

---

## 2. Adres Haritası Özeti (64 KB Pencere)

| Sayfa | Offset Aralığı | İçerik |
|---|---|---|
| Global | `0x0000 – 0x0030` | `IP_ID`, `IP_VERSION`, `CAPS`, `CAPS_MEM`, `CLK_HZ`, `SOFT_RESET`, `GLOBAL_FREEZE`, `TS_CTRL`, `TS_LSB` (`rd_strobe`), `TS_MSB` |
| TX | `0x0400 – 0x0484` | `TX_TRANSMITTER_EN..TX_EXT_LOW`, `TX_CFG_SEL/APPLY`, `TX_CUST_*`, `TX_ACT_*`, `TX_STATUS [BUSY, SCHED_ACTIVE, ACT_CFG]`, `TX_WORD_CNT` |
| TX BIT (`TB_`) | `0x0800 – 0x09D0` | RX kanal sayfası + `TB_CHK_CTRL`, `TB_CHK_TIMEOUT`, `TB_CHK_OK_CNT`, `TB_CHK_ERR_CNT`, `TB_CHK_STATUS` |
| RX *n* (`RX{n}_`) | `0x4000 + n×0x400` | `CTRL`, `STATUS [FROZEN, WORD_WRAP, ERR_WRAP, ACT_CFG]`, `CFG_SEL/APPLY`, `CUST_*`, `ACT_*`, sayaçlar, Word/Error/Bit RAM portları |

Tam bit-bazlı tablo: [`vhdl/axil/arinc429_axil_regs.md`](../axil/arinc429_axil_regs.md).

### RAM Okuma Mekanizması (`wr_strobe` + `rd_strobe` Auto-Increment)

- **Rastgele erişim:** `WORD_RADDR` / `ERR_RADDR` / `BIT_RADDR` yazıldığında (`wr_strobe`) kanal içi okuma pointer'ı doğrudan istenen adrese yüklenir ve BRAM çıkışı 1 clk içinde hazırlanır.
- **Blok okuma (otomatik artış):** Kaydın son register'ı (`WORD_RD_GAP_ERR`, `ERR_RD_DATA`, `BIT_RD_NULL_ERR`) okunduğunda (`rd_strobe`) dahili pointer dairesel olarak `+1` ilerler (`BIT` pointer'ında `{word_idx, bit_idx}` birlikte arttığından 31. bitten sonraki Word'ün 0. bitine otomatik geçilir).
- Böylece 1 kez başlangıç adresi yazıp tüm blok veya "Son N kayıt" hiç ek `RADDR` yazmadan okunur; kanal başı adres alanı **1 KB** kalır.

---

## 3. AXIL Studio ile Kullanım ve Yeniden Üretim

1. **AXIL Studio'da açma:** `vhdl/axil/arinc429.axproj.json` dosyasını AXIL Studio ile açın.
   - `ARINC429` IP'sinde `"panel": "arinc429"` kayıtlıdır; **Debug Bridge** üzerinden doğrudan bu repodaki PySide6 ARINC 429 arayüzü açılır.
   - **Slave Interface Wrapper** üzerinden `arinc429_axil.v` / `arinc429_axil_pk.v` dosyaları tek tıkla yeniden üretilebilir.
2. **Kanal sayısını veya saat frekansını değiştirme (ör. 4 RX kanalı):**
   ```bash
   python3 vhdl/scripts/gen_axil_spec.py -o vhdl/axil --num-rx 4 --clk-hz 50000000 --axil-studio /yol/axil-studio
   ```
   Bu komut `arinc429_axil.regspec.json`, `arinc429.axproj.json`, `arinc429_axil*.v` ve `vhdl/rtl/arinc429_ip.vhd` dosyalarını eşzamanlı günceller.

---

## 4. Simülasyon Doğrulaması

```bash
# 1) AXI4-Lite slave (Icarus Verilog)
iverilog -g2005 -o /tmp/arinc429_axil_tb.vvp vhdl/axil/arinc429_axil.v vhdl/axil/arinc429_axil_tb.v
vvp /tmp/arinc429_axil_tb.vvp

# 2) VHDL çekirdek + RX ön ucu (GHDL, VHDL-2008)
mkdir -p /tmp/ghdl_work
ghdl -a --std=08 --workdir=/tmp/ghdl_work \
  vhdl/rtl/a429_pkg.vhd vhdl/rtl/a429_presets_pkg.vhd vhdl/rtl/a429_rst_sync.vhd \
  vhdl/rtl/a429_timestamp.vhd vhdl/rtl/a429_sdp_ram.vhd vhdl/rtl/a429_cdc_sync.vhd \
  vhdl/rtl/a429_glitch_filter.vhd vhdl/rtl/a429_rx_decoder.vhd vhdl/rtl/a429_rx_core.vhd \
  vhdl/rtl/a429_rx_cfg_sel.vhd vhdl/rtl/a429_rx_logger.vhd vhdl/rtl/a429_word_checker.vhd \
  vhdl/rtl/a429_rx_channel.vhd vhdl/rtl/a429_tx_cfg_sel.vhd vhdl/rtl/a429_tx_core.vhd \
  vhdl/rtl/a429_tx_word_evt.vhd vhdl/rtl/a429_tx_channel.vhd vhdl/rtl/arinc429_core.vhd \
  vhdl/rtl/arinc429_ip.vhd vhdl/tb/tb_a429_rx_core.vhd vhdl/tb/tb_arinc429_core.vhd
(cd /tmp/ghdl_work && ghdl -e --std=08 tb_a429_rx_core && ./tb_a429_rx_core)
(cd /tmp/ghdl_work && ghdl -e --std=08 tb_arinc429_core && ./tb_arinc429_core)
```
