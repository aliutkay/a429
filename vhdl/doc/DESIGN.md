# arinc429_ip — Tasarım Dokümanı

ARINC 429 verici, verici doğrulama (TX BIT) ve çok kanallı alıcı IP'si. Tek clock domain, APB3 slave arayüzü.

Diyagramlar: [`arinc429_ip_arch.drawio`](arinc429_ip_arch.drawio) (blok seviyesi), [`arinc429_ip_detail.drawio`](arinc429_ip_detail.drawio) (sinyal seviyesi).

---

## 1. Genel yapı

```
            APB3 (IP clock'unda)
                 │
        ┌────────▼────────┐        ┌───────────────┐
        │  a429_apb_slave │        │ a429_timestamp│──── ts_now ──────────────┐
        └────────┬────────┘        └───────▲───────┘                          │
        ┌────────▼────────┐                │ ts_en/ts_clr                     │
        │  a429_reg_bank  │────────────────┘                                  │
        └──┬──────┬──────┬┘                                                   │
           │      │      └───────────────────────────────┐                    │
   ┌───────▼──────────────┐   ┌──────────────────┐       │                    │
   │   TX kanalı (0/1)    │──►│  a429_tx_router  │──► tx_high / tx_low / tx_slp
   │ regs·cfg·core·evt    │   │                  │──► rx_test_a/b[N] (opsiyonel)
   └───────┬──────────────┘   └──────────────────┘       │                    │
           │ word_start, word_tx                         │                    │
   ┌───────▼──────────────────────────────────┐          │                    │
   │ TX BIT kanalı (0/1) = RX kanalı + checker│◄── txbit_rx_high/low          │◄─┤
   │          (Label filtresi yok)            │                               │  │
   └──────────────────────────────────────────┘          │                    │
   ┌──────────────────────────────────────────┐          │                    │
   │ RX kanalı × G_NUM_RX (0–16)              │◄── rx_high/low[N] ◄───────────┘◄─┘
   │ (+ checker, G_RX_TEST_EN)                │
   └──────────────────────────────────────────┘
```

| Blok | İşlev |
|---|---|
| `a429_apb_slave` | APB3 transferlerini iç register bus'a çevirir |
| `a429_reg_bank` | Global Register'ları tutar, adresi modüllere dağıtır, okuma verisini toplar |
| `a429_timestamp` | Bütün logger'ların kullandığı 64 bit zaman sayacı |
| TX kanalı | ARINC 429 Word üretir ve gönderir |
| `a429_tx_router` | TX çıkışını line driver'a veya RX alıcılarının test pinlerine yönlendirir |
| RX kanalı | Hattan Word alır, zamanlama/hata analizini yapar, kayıtları RAM'e yazar |
| TX BIT kanalı | TX hattını dinleyen alıcı + gönderilen/alınan Word karşılaştırması (checker'lı, Label filtresiz RX kanalı) |

Bütün bloklar `clk` ve senkronlanmış `rst_n_sync` alır. Kanal blokları ayrıca kendi `soft_rst` sinyalini alır.

---

## 2. Generic'ler

| Generic | Varsayılan | Açıklama |
|---|---|---|
| `G_CLK_HZ` | 50_000_000 | IP clock'u (bilgi Register'ı ve sayaç genişliği kontrolü) |
| `G_TX_EN` | true | TX kanalı |
| `G_TXBIT_EN` | true | TX BIT kanalı (`G_TX_EN` gerekir) |
| `G_NUM_RX` | 4 | RX kanal sayısı (0–16) |
| `G_RX_TEST_EN` | false | RX alıcı test pinleri (`rx_test_a/b`) ve RX kanallarındaki checker'lar |
| `G_SYNC_STAGES` | 4 | Giriş senkronizasyon FF sayısı |
| `G_DUR_W` | 16 | Pulse/Null/Bit süre sayacı genişliği |
| `G_GAP_W` | 32 | Gap süre sayacı genişliği |
| `G_WORD_DEPTH_LOG2` | 8 | Kanal başına Word kaydı (256) |
| `G_ERR_DEPTH_LOG2` | 8 | Kanal başına Error kaydı (256) |
| `G_BITDIAG_WORDS_LOG2` | 3 | Bit diagnostic tutulan Word sayısı (8 × 32 bit satırı) |
| `G_BITDIAG_EN` | true | Bit diagnostic RAM'i |
| `G_CHK_FIFO_DEPTH` | 4 | Checker beklenen Word FIFO derinliği |

---

## 3. Dış arayüz

| Port | Yön | Genişlik | Açıklama |
|---|---|---|---|
| `clk`, `rst_n` | in | 1 | IP clock'u, aktif-düşük reset |
| `psel`, `penable`, `pwrite` | in | 1 | APB3 kontrol |
| `paddr` | in | 32 | Sadece `[15:2]` çözülür |
| `pwdata` | in | 32 | Yazma verisi (sadece 32 bit yazma) |
| `prdata` | out | 32 | Okuma verisi |
| `pready` | out | 1 | Transfer tamam |
| `pslverr` | out | 1 | Geçersiz adres / olmayan modül |
| `tx_high`, `tx_low` | out | 1 | Line driver TX1IN / TX0IN (`11` = HIGH-Z, sürücü destekliyorsa) |
| `tx_slp` | out | 1 | Line driver eğim seçimi (1: High Speed) |
| `txbit_rx_high`, `txbit_rx_low` | in | 1 | TX hattını dinleyen alıcının ROUTA/ROUTB çıkışları |
| `rx_high`, `rx_low` | in | N | RX alıcılarının ROUTA/ROUTB çıkışları |
| `rx_test_a`, `rx_test_b` | out | N | RX alıcılarının TESTA/TESTB pinleri |

---

## 4. Adres haritası

IP 64 KB'lık bir pencere kaplar; sistem base adresine eklenir. `PADDR[15:10]` modül, `PADDR[9:2]` Register numarası.

| Modül | Offset |
|---|---|
| Global | `0x0000` |
| TX | `0x0400` |
| TX BIT | `0x0800` |
| RX *n* (n = 0–15) | `0x4000 + n × 0x400` |

Register offset'i = Register no × 4. Olmayan modül veya tanımsız Register: `pslverr = 1`, okuma `0`.
Bütün Register'lar 32 bit; kullanılmayan bitler 0 okunur.

---

## 5. Global bloklar

### 5.0 `a429_rst_sync`

Dış `rst_n`'i IP clock'una senkronlar: **asenkron assert, senkron deassert** (2 FF). Çıkış bütün bloklara gider.

| Giriş | Çıkış |
|---|---|
| `clk`, `rst_n` | `rst_n_sync` |

### 5.1 `a429_apb_slave`

APB3 setup/access fazlarını iç register bus'a çevirir. Yazma, access fazında 1 clk'lik `bus_wr` darbesidir.
Okuma, reg_bank'tan `bus_ready` gelene kadar `pready = 0` tutularak tamamlanır (sabit 1 wait state).

| Giriş | Çıkış |
|---|---|
| `psel`, `penable`, `pwrite`, `paddr`, `pwdata` | `bus_wr`, `bus_rd`, `bus_addr[15:2]`, `bus_wdata[31:0]` |
| `bus_rdata[31:0]`, `bus_ready`, `bus_err` | `prdata`, `pready`, `pslverr` |

### 5.2 `a429_reg_bank`

Adresin modül alanına göre ilgili modüle `rb_wr_*` / `rb_rd_*` strobe'u verir; `rb_addr[7:0]` ve `rb_wdata` bütün modüllere ortaktır.
Modülün `rb_rdata_*` / `rb_ready_*` cevabını APB'ye geri taşır. Global Register'ları kendisi tutar.

| Giriş | Çıkış |
|---|---|
| `bus_*` | `bus_rdata`, `bus_ready`, `bus_err` |
| `rb_rdata_*`, `rb_ready_*` (her modülden) | `rb_addr[7:0]`, `rb_wdata[31:0]`, `rb_wr_*`, `rb_rd_*` |
| `ts_now[63:0]` | `soft_rst_tx`, `soft_rst_tb`, `soft_rst_rx[n]`, `global_freeze` |
| | `ts_en`, `ts_clr`, `route_mode`, `line_idle`, `route_test_mask[N-1:0]` |

**Global Register'lar**

| Offset | Ad | R/W | Reset | Açıklama |
|---|---|---|---|---|
| 0x00 | `IP_ID` | R | `0x41343239` | "A429" |
| 0x04 | `IP_VERSION` | R | — | [23:16] major, [15:8] minor, [7:0] patch |
| 0x08 | `CAPS` | R | — | [4:0] NUM_RX, [8] TX, [9] TXBIT, [10] RX_TEST, [11] BITDIAG |
| 0x0C | `CAPS_MEM` | R | — | [7:0] WORD_DEPTH_LOG2, [15:8] ERR_DEPTH_LOG2, [23:16] BITDIAG_WORDS_LOG2 |
| 0x10 | `CLK_HZ` | R | `G_CLK_HZ` | |
| 0x20 | `SOFT_RESET` | W | 0 | [0] tüm IP, [1] TX, [2] TX BIT, [16+n] RX n. Yazınca 1 clk darbe |
| 0x24 | `GLOBAL_FREEZE` | RW | 0 | [0] bütün logger'ları dondur |
| 0x28 | `TS_CTRL` | RW | 1 | [0] enable, [1] clear (darbe) |
| 0x2C | `TS_LSB` | R | — | Okununca MSB latch'lenir |
| 0x30 | `TS_MSB` | R | — | Latch'lenmiş MSB |
| 0x40 | `ROUTE_CTRL` | RW | 0 | [0] route: 0 line driver, 1 RX test pinleri; [1] line_idle: test modunda line driver 0 NULL / 1 HIGH-Z |
| 0x44 | `ROUTE_TEST_MASK` | RW | 0 | [n] = 1 → RX n'nin test pinleri sürülür |

### 5.3 `a429_timestamp`

64 bit serbest sayaç; `ts_en = 1` iken her clk +1, `ts_clr` ile sıfırlanır. Değer = clk sayısı.

| Giriş | Çıkış |
|---|---|
| `ts_en`, `ts_clr` | `ts_now[63:0]` |

---

## 6. TX kanalı

```
tx_regs ──► cfg_sel ──► tx_core ──► tx_word_evt
   │                       │  line_high/low ──► tx_router
   └───────────────────────┘  word_tx ─────────► bütün checker'lar (TX BIT + RX)
```

### 6.1 `a429_tx_regs`

TX sayfasının Register'ları. Değerleri `tx_core` ve `cfg_sel`'e verir, durum bilgisini okur.

| Giriş | Çıkış |
|---|---|
| `rb_wr_tx`, `rb_rd_tx`, `rb_addr`, `rb_wdata`, `soft_rst_tx` | `rb_rdata_tx`, `rb_ready_tx` |
| `tx_busy`, `tx_word_done` | TX Register değerleri (aşağıdaki tablo), `tx_send_cmd` (1 clk darbe) |
| `tx_pulse_dur`, `tx_null_dur`, `tx_gap_dur`, `tx_slp_cfg` (geri okuma) | `tx_cfg_sel`, `tx_cfg_apply`, `tx_cust_*` |

**TX Register'ları**

| Offset | Ad | R/W | Reset | Açıklama |
|---|---|---|---|---|
| 0x00 | `TRANSMITTER_EN` | RW | 0 | 1: hat Word Transmitter'dan, 0: `EXT_HIGH/EXT_LOW` ile sürülür |
| 0x04 | `MSG_SCHED_EN` | RW | 0 | 1: Message Scheduler modu, 0: `SEND_CMD` ile tek tek gönderim |
| 0x08 | `BUILDER_EN` | RW | 0 | 1: Word alanlardan, 0: `EXT_DATA`'dan |
| 0x0C | `LABEL` | RW | 0 | [7:0] |
| 0x10 | `SDI` | RW | 0 | [1:0] |
| 0x14 | `DATA` | RW | 0 | [18:0] |
| 0x18 | `SSM` | RW | 0 | [1:0] |
| 0x1C | `PARITY_TYPE` | RW | 1 | 1 Odd, 0 Even |
| 0x20 | `SCHED_EN` | RW | 0 | Scheduler başlat/durdur (en son yazılır) |
| 0x24 | `INITIAL_DELAY` | RW | 0 | clk |
| 0x28 | `INTER_WORD_GAP` | RW | 1 | clk, ≥ 1 |
| 0x2C | `SEND_CMD` | W | — | 1 yaz: TX'e tek gönderim tetiği (1 clk darbe, kendiliğinden temizlenir) |
| 0x30 | `EXT_DATA` | RW | 0 | [31:0] hazır Word |
| 0x34 | `EXT_HIGH` | RW | 0 | Override: 00 NULL, 10 HIGH, 01 LOW, 11 HIGH-Z |
| 0x38 | `EXT_LOW` | RW | 0 | |
| 0x40 | `CFG_SEL` | RW | 0 | 0 High Speed, 1 Low Speed, 2 Custom |
| 0x44 | `CFG_APPLY` | W | — | 1: seçili config'i etkinleştir |
| 0x48 | `CUST_PULSE_DUR` | RW | 0 | Custom pulse (clk) |
| 0x4C | `CUST_NULL_DUR` | RW | 0 | Custom null (clk) |
| 0x50 | `CUST_GAP_DUR` | RW | 0 | Custom Word gap (clk) |
| 0x54 | `CUST_SLP` | RW | 0 | Custom SLP |
| 0x60–0x6C | `ACT_PULSE/NULL/GAP/SLP` | R | — | Etkin config |
| 0x80 | `TX_STATUS` | R | — | [0] busy, [1] scheduler aktif, [3:2] aktif config |
| 0x84 | `TX_WORD_CNT` | R | 0 | Gönderilen Word sayısı |

#### 6.1.1 `SEND_CMD`

`SEND_CMD`'ye 1 yazılınca `tx_core`'a tek bir 1 clk'lik `tx_send_cmd` darbesi gider; Register kendiliğinden 0'a döner (okuma her zaman 0).
IP sonucu takip etmez:
- Word kaynağına (Builder / `EXT_DATA`) bakmaz.
- `MSG_SCHED_EN = 1` iken de darbe iletilir; MUX2 Scheduler'ı seçtiği için etkisizdir.
- `TRANSMITTER_EN = 0` (override) iken Word Transmitter tetiği kabul etmez, `busy` üretmez.
- TX meşgulken gelen darbenin ne olacağı TX koduna bağlıdır; yazılım göndermeden önce `TX_STATUS.busy = 0` olmasını bekler.

### 6.2 `a429_cfg_sel` (TX)

Seçili preset'in veya custom değerlerin **etkin** kopyasını tutar. `CFG_APPLY` yazıldığında, TX boştayken (`tx_busy = 0`) kopyalar;
böylece Word ortasında config değişmez. Preset'ler `a429_presets_pkg` sabitleridir.

| Giriş | Çıkış |
|---|---|
| `tx_cfg_sel`, `tx_cfg_apply`, `tx_cust_pulse_dur`, `tx_cust_null_dur`, `tx_cust_gap_dur`, `tx_cust_slp`, `tx_busy` | `tx_pulse_dur`, `tx_null_dur`, `tx_gap_dur`, `tx_slp_cfg` |

### 6.3 `a429_tx_core` (mevcut TX kodu)

Word'ü oluşturur ve hatta seri gönderir. İçinde üç seçici vardır:
- **MUX1** (`BUILDER_EN`): Word kaynağı — Word Builder (Label/SDI/Data/SSM + Parity) veya `EXT_DATA`.
- **MUX2** (`MSG_SCHED_EN`): gönderim tetiği — Message Scheduler (`INITIAL_DELAY`, `INTER_WORD_GAP`) veya `tx_send_cmd` darbesi (§6.1.1).
- **MUX3** (`TRANSMITTER_EN`): hattı süren — Word Transmitter veya `EXT_HIGH/EXT_LOW` override.

| Giriş | Çıkış |
|---|---|
| TX Register değerleri | `tx_line_high`, `tx_line_low` |
| `tx_pulse_dur`, `tx_null_dur`, `tx_gap_dur`, `tx_slp_cfg` | `tx_slp` |
| | `tx_busy` (32 bit + gap boyunca 1) |
| | `tx_word_tx[31:0]` (gönderilen Word) |

### 6.4 `a429_tx_word_evt`

`tx_busy` kenarlarından Word olayları üretir: yükselen kenar → `tx_word_start`, düşen kenar → `tx_word_done` (1 clk darbe).

### 6.5 `a429_tx_router`

TX çıkışını iki hedeften birine verir. `route` değişikliği `tx_busy = 0` iken uygulanır. Çıkışlar registerlıdır (glitch'siz).

| `route` | `tx_high/tx_low` | `rx_test_a/b[n]` |
|---|---|---|
| 0 | TX sinyali | `00` |
| 1 | `line_idle`: `00` veya `11` | maske set ise TX sinyali, değilse `00` |

Test pin kodlaması (HI-8591): HIGH → `10`, LOW → `01`, NULL/HIGH-Z → `11`, test kapalı → `00`.

| Giriş | Çıkış |
|---|---|
| `tx_line_high`, `tx_line_low`, `tx_busy`, `route_mode`, `line_idle`, `route_test_mask` | `tx_high`, `tx_low`, `rx_test_a[N-1:0]`, `rx_test_b[N-1:0]` |
| | `tb_chk_route_ok`, `rx_chk_route_ok[N-1:0]` (checker'ların aktiflik koşulu) |

---

## 7. RX kanalı (`a429_rx_channel`)

Her RX kanalı ve TX BIT kanalı aynı entity'dir; iki generic ile farklılaşır:

| Kanal generic'i | RX kanalı | TX BIT kanalı |
|---|---|---|
| `G_HAS_LABEL_FILTER` | true | false |
| `G_HAS_CHECKER` | `G_RX_TEST_EN` | true |

Olmayan bloğun Register'ları okunurken 0 döner, `word_valid` doğrudan logger'a/checker'a gider.

```
pin ─► cdc_sync ─► glitch_filter ─► rx_decoder ─► [label_filter] ─► rx_logger ─► Word RAM / Error RAM / Bit RAM
                                                    │                ▲
                                                    └─► [word_checker] (tx_word_start, tx_word_tx)
                         ▲               ▲                        ▲              │ okuma
                         └──── cfg_sel ──┘                     ts_now            ▼
                                  ▲                                          rx_regs
                               rx_regs
```

### 7.1 `a429_rx_regs`

Kanal sayfasının Register'ları; RAM okuma portlarını ve durum sayaçlarını APB'ye bağlar.

| Giriş | Çıkış |
|---|---|
| `rb_wr`, `rb_rd`, `rb_addr`, `rb_wdata`, `soft_rst` | `rb_rdata`, `rb_ready` |
| `word_cnt`, `err_cnt`, `drop_cnt`, `last_word` | `enable`, `freeze`, `clear` (logger'a) |
| `word_rdata[143:0]`, `err_rdata[127:0]`, `bit_rdata[63:0]` | `cfg_sel`, `cfg_apply`, `cust_*` (9 alan) |
| Etkin config (9 alan, geri okuma) | (Label filtresi varsa) `label_filter_en`, `label_mask[255:0]` |
| (checker varsa) `chk_ok_cnt`, `chk_err_cnt`, `chk_fifo_level` | `word_raddr`, `err_raddr`, `bit_raddr` |
| | (checker varsa) `chk_en`, `chk_timeout` |

**Kanal Register'ları**

| Offset | Ad | R/W | Reset | Açıklama |
|---|---|---|---|---|
| 0x00 | `CTRL` | RW | 0 | [0] enable (logger kayıt yapar), [1] freeze, [2] clear (darbe: sayaçlar + RAM pointer'ları) |
| 0x04 | `STATUS` | R | — | [4] frozen, [5] Word RAM döndü, [6] Error RAM döndü, [9:8] aktif config |
| 0x08 | `CFG_SEL` | RW | 0 | 0 High Speed, 1 Low Speed, 2 Custom |
| 0x0C | `CFG_APPLY` | W | — | 1: seçili config'i hemen etkinleştir |
| 0x40 | `CUST_GLITCH_FILTER_SIZE` | RW | 0 | clk |
| 0x44 | `CUST_MIN_PULSE` | RW | 0 | clk |
| 0x48 | `CUST_MAX_PULSE` | RW | 0 | clk |
| 0x4C | `CUST_MIN_BIT` | RW | 0 | clk |
| 0x50 | `CUST_MAX_BIT` | RW | 0 | clk |
| 0x54 | `CUST_MAX_PULSE_ERR` | RW | 0 | Pulse fazında izin verilen gürültü |
| 0x58 | `CUST_MAX_NULL_ERR` | RW | 0 | Null fazında izin verilen gürültü |
| 0x5C | `CUST_MAX_GAP_ERR` | RW | 0 | Gap'te izin verilen gürültü |
| 0x60 | `CUST_PARITY_MODE` | RW | 1 | 0 kontrol yok, 1 Odd, 2 Even |
| 0x64 | `LABEL_FILTER_EN` | RW | 0 | 1: Label filtresi aktif (TX BIT'te yok) |
| 0x68–0x84 | `LABEL_MASK0..7` | RW | 0xFFFFFFFF | 256 bit; bit *k* = 1 → Label *k* kabul |
| 0xA0–0xC0 | `ACT_*` | R | — | Etkin config'in 9 alanı (CUST_* sırasıyla) |
| 0xE0 | `WORD_CNT` | R | 0 | Geçerli Word sayısı |
| 0xE4 | `ERR_CNT` | R | 0 | Hata kaydı sayısı |
| 0xE8 | `DROP_CNT` | R | 0 | Freeze sırasında atılan kayıt sayısı |
| 0xEC | `LAST_WORD` | R | 0 | Son geçerli Word |
| 0x100 | `WORD_RADDR` | RW | 0 | Word RAM okuma adresi |
| 0x104–0x114 | `WORD_RD_TS_MSB/TS_LSB/DATA/GAP/GAP_ERR` | R | — | Seçili Word kaydı |
| 0x120 | `ERR_RADDR` | RW | 0 | Error RAM okuma adresi |
| 0x124–0x134 | `ERR_RD_TS_MSB/TS_LSB/CODE/ADDR/DATA` | R | — | Seçili Error kaydı |
| 0x140 | `BIT_RADDR` | RW | 0 | [4:0] bit no, [12:8] Word index |
| 0x144–0x150 | `BIT_RD_PULSE/PULSE_ERR/NULL/NULL_ERR` | R | — | Seçili bit kaydı |

### 7.2 `a429_cfg_sel` (RX)

Preset / custom değerlerin etkin kopyası; `CFG_APPLY` gelince **hemen** uygulanır. Yarım Word bozulmaz, çünkü decoder zaman / gürültü / parity
değerlerini sadece Word almıyorken (`IDLE` / `ERR_RECOVERY`) kendi içine kopyalar. Glitch filter boyu ise anında etkilidir; Word ortasında
değişirse o andaki tek geçiş birkaç clk kayar, bu yüzden glitch boyu kanal boştayken (`CTRL.enable = 0`) değiştirilmelidir.

| Giriş | Çıkış |
|---|---|
| `cfg_sel`, `cfg_apply`, `cust_*` (9) | `glitch_filter_size`, `min_pulse`, `max_pulse`, `min_bit`, `max_bit`, `max_pulse_err`, `max_null_err`, `max_gap_err`, `parity_mode` |

### RX çekirdeği (`a429_rx_core`)

`a429_cdc_sync` + `a429_glitch_filter` + `a429_rx_decoder` tek sarmalayıcıda birleşir (RTL: `vhdl/rtl/`, test: `vhdl/tb/tb_a429_rx_core.vhd`).
Pin → decoder sabit gecikmesi: `G_SYNC_STAGES + glitch_size + 1` clk.

### 7.3 `a429_cdc_sync`

Asenkron alıcı çıkışlarını `G_SYNC_STAGES` FF (varsayılan 4, `ASYNC_REG`) ile IP clock'una senkronlar.

| Giriş | Çıkış |
|---|---|
| `rx_high`, `rx_low` (pin) | `rx_high_s`, `rx_low_s` |

### 7.4 `a429_glitch_filter`

2 bitlik hat durumunu **tek sembol** olarak filtreler: yeni durum en az `glitch_size + 1` clk sürmezse bastırılır. Bütün geçişler aynı gecikmeyle geçtiği için süreler korunur.
Bastırılan glitch'leri sayar: `glitch_total_cnt` (toplam) ve `glitch_win_cnt` (mevcut stable durum boyunca; decoder faz gürültüsü için kullanır). Sayaçlar doyumludur.

| Giriş | Çıkış |
|---|---|
| `rx_high_s`, `rx_low_s`, `glitch_size` | `rx_high_f`, `rx_low_f`, `glitch_tick`, `glitch_total_cnt`, `glitch_win_cnt` |

### 7.5 `a429_rx_decoder` (eski `arinc429_rx_fsm`)

Hat durumunu çözer (`00` NULL, `10`/`01` pulse, `11` bus fault), bitleri ölçer, Word'ü toplar ve hataları tespit eder.

Durumlar: `IDLE` (gap ölç, bit 0'ı bekle) → `PULSE_PHASE` → `NULL_PHASE` → (32 bit sonra) `WAIT_MIN_GAP` (4 bit gap) → `IDLE`.
Herhangi bir hatada `ERR_RECOVERY` (en az 4 bit NULL bekler).

**Gap ölçümü:** Son bitin (bit 31) sonu hattan belli olmadığı için bit 31'in null süresi bit 30'un null süresine eşit kabul edilir
(bit 31 sonu = bit 31 pulse + bit 30 null, `min_bit`–`max_bit` arasına sınırlı). `word_gap_dur` bu noktadan sonraki NULL'dur; ek Register
gerekmeden gerçek gap ölçülür. Bit 31'in bit diagnostic null süresi de bu tahmindir.

**Parity:** `parity_mode ≠ 0` ve parity hatalıysa Word **geçerli sayılmaz**: `word_valid` üretilmez, sadece `PARITY` hatası üretilir
(Word Error kaydının `data` alanındadır). Böylece hatalı Word ne Word RAM'e ne de checker'a gider.

FSM bir clk'de en fazla **bir** hata bayrağı üretir.

| Giriş | Çıkış |
|---|---|
| `rx_high_f`, `rx_low_f`, `glitch_win_cnt` | `word_start` (bit 0 başı), `word_data[31:0]`, `word_gap_dur[31:0]`, `word_gap_err_cnt[15:0]`, `word_valid` |
| `min/max_pulse`, `min/max_bit`, `max_pulse/null/gap_err`, `parity_mode` | `bit_idx[4:0]`, `bit_pulse_dur`, `bit_null_dur`, `bit_pulse_err_cnt`, `bit_null_err_cnt`, `bit_valid` |
| | 8 hata bayrağı (bkz. §9), `err_addr[15:0]`, `err_data[31:0]` |

### 7.6 `a429_label_filter`

Sadece RX kanallarında vardır (TX BIT'te yok). `label_filter_en = 1` iken maskede biti 0 olan Label'lı Word'ün `word_valid_f`'sini üretmez (Word RAM'e yazılmaz),
bunun yerine `LABEL_FILTERED` hatası üretir. Parity'si hatalı Word buraya hiç ulaşmaz. Checker filtreden bağımsızdır (filtrelenen Word de karşılaştırılır).

| Giriş | Çıkış |
|---|---|
| `word_data`, `word_valid`, `label_filter_en`, `label_mask` | `word_valid_f`, `err_label_filtered` |

### 7.7 `a429_rx_logger`

`word_start`'ta timestamp'i yakalar; geçerli Word'ü, bit ölçümlerini ve hataları kendi RAM'lerine dairesel olarak yazar.
`enable = 0` (`CTRL.enable`) iken hiçbir kayıt yazmaz ve sayaçları artırmaz; decoder her zaman çalışır, böylece kanal açıldığında ilk Word kaçmaz.
Hata bayraklarından 16 bit hata kodunu üretir. `freeze` (kanal) veya `global_freeze` aktifken yazmaz, atılanları `drop_cnt` ile sayar.

**Aynı clk'de birden fazla hata:** Logger her clk'de en fazla **bir** Error kaydı yazar. Aynı clk'de birden fazla kaynak hata verirse
hata bitleri kaydın `code` alanında **OR'lanır** (hiçbir hata kodu kaybolmaz); `addr` ve `data` en öncelikli kaynaktan alınır:

| Öncelik | Kaynak | `addr` / `data` |
|---|---|---|
| 1 | FSM (8 hata, clk başına en fazla 1) | bit no / süre, gürültü veya Word |
| 2 | Label filtresi | Label / alınan Word |
| 3 | Checker (`WORD_MISMATCH`, `UNEXPECTED_WORD`, `NO_ECHO`) | FIFO idx / beklenen veya alınan Word |

Olası çakışmalar: `LABEL_FILTERED` + `WORD_MISMATCH`/`UNEXPECTED_WORD` (filtrelenen Word checker'da da hatalı), `NO_ECHO` + FSM veya Label hatası.
FSM hatası ile Label/checker hatası aynı Word için oluşmaz (FSM hatasında `word_valid` yoktur).

| Giriş | Çıkış |
|---|---|
| `ts_now`, FSM Word / bit / hata çıkışları, `word_valid_f`, `err_label_filtered` | `word_we`, `word_waddr`, `word_wdata[143:0]` |
| (checker varsa) `chk_mismatch`, `chk_no_echo`, `chk_unexpected`, `chk_addr`, `chk_data` | `err_we`, `err_waddr`, `err_wdata[127:0]` |
| `enable`, `freeze`, `global_freeze`, `clear` | `bit_we`, `bit_waddr`, `bit_wdata[63:0]` |
| | `word_cnt`, `err_cnt`, `drop_cnt`, `last_word`, (checker varsa) `rx_err_any` |

### 7.8 `a429_sdp_ram` (×3)

Simple dual-port RAM: yazma portu logger'da, okuma portu `rx_regs`'te (1 clk okuma gecikmesi).
İleride harici RAM kullanılırsa bu örnekler kaldırılıp aynı sinyaller dışarı verilir.

| RAM | Derinlik | Genişlik | Yazma adresi |
|---|---|---|---|
| Word | 2^`G_WORD_DEPTH_LOG2` | 144 | `word_cnt` alt bitleri |
| Error | 2^`G_ERR_DEPTH_LOG2` | 128 | `err_cnt` alt bitleri |
| Bit diag | 2^`G_BITDIAG_WORDS_LOG2` × 32 | 64 | {`word_cnt` alt bitleri, `bit_idx`} |

---

## 8. Word Checker (TX BIT ve RX alıcı testi)

TX BIT kanalı = Label filtresiz, checker'lı RX kanalı; girişi TX hattını dinleyen ayrı alıcıdır (`txbit_rx_high/low`).
RX kanallarında checker `G_RX_TEST_EN = true` ise vardır ve RX alıcı testinde kullanılır.

### 8.1 `a429_word_checker`

TX'in gönderdiği her Word'ü (`tx_word_start` anında `tx_word_tx`) beklenen FIFO'ya yazar. Kanalın aldığı her geçerli Word'ü
FIFO başı ile karşılaştırır. Hatalar kanalın **kendi** logger'ına yazılır.

**Aktif olduğu durum** (`chk_route_ok`, router üretir):

| Kanal | Aktif |
|---|---|
| TX BIT | `route = 0` (TX line driver'da) |
| RX *n* | `route = 1` ve `ROUTE_TEST_MASK[n] = 1` |

Test modunda maskede seçili bütün RX kanalları aynı anda doğrulanır.

| Durum | Sonuç |
|---|---|
| Eşit | `CHK_OK_CNT` +1 |
| Farklı | `WORD_MISMATCH` hatası, `data` = beklenen Word |
| FIFO başı `CHK_TIMEOUT` clk içinde gelmedi | `NO_ECHO` hatası |
| FIFO boşken Word geldi | `UNEXPECTED_WORD` hatası |
| Alıcı Word'ü hatalı aldı (`rx_err_any`) | FIFO başı düşülür (hata FSM tarafından zaten loglandı) |
| FIFO başının timeout'u ile Word aynı clk'de | Önce karşılaştırma yapılır; eşleşirse `NO_ECHO` üretilmez |

TX override modunda (`TRANSMITTER_EN = 0`) otomatik pasifleştirme yoktur; gerekiyorsa kullanıcı TX BIT kanalını/checker'ı kapatır.

| Giriş | Çıkış |
|---|---|
| `tx_word_start`, `tx_word_tx`, `ts_now` | `chk_mismatch`, `chk_no_echo`, `chk_unexpected`, `chk_addr`, `chk_data` |
| `word_data`, `word_valid` (Label filtresinden **önce**), `rx_err_any` | `chk_ok_cnt`, `chk_err_cnt`, `chk_fifo_level` |
| `chk_en`, `chk_timeout`, `chk_route_ok` | |

**Checker Register'ları** (TX BIT sayfası ve checker'lı RX sayfaları)

| Offset | Ad | R/W | Reset | Açıklama |
|---|---|---|---|---|
| 0x1C0 | `CHK_CTRL` | RW | 0 | [0] enable, [1] FIFO temizle (darbe) |
| 0x1C4 | `CHK_TIMEOUT` | RW | 0 | clk; 0 = timeout kontrolü kapalı |
| 0x1C8 | `CHK_OK_CNT` | R | 0 | Eşleşen Word sayısı |
| 0x1CC | `CHK_ERR_CNT` | R | 0 | Checker hata sayısı |
| 0x1D0 | `CHK_STATUS` | R | — | [3:0] FIFO doluluk, [4] FIFO taştı |

---

## 9. Veri formatları

**Word kaydı (144 bit)**

| Bitler | Alan |
|---|---|
| [143:80] | Timestamp (Word başı, clk) |
| [79:48] | Word |
| [47:16] | Önceki gap süresi (clk; önceki Word'ün bit 31 sonundan, bkz. §7.5) |
| [15:0] | Gap'teki gürültü sayısı |

**Error kaydı (128 bit)**

| Bitler | Alan |
|---|---|
| [127:64] | Timestamp |
| [63:48] | Hata kodu (bitmask) |
| [47:32] | Adres (bit no, 32 = gap, Label, FIFO idx) |
| [31:0] | Veri (süre, gürültü sayısı veya Word) |

**Bit kaydı (64 bit)**: [63:48] pulse süresi, [47:32] pulse gürültüsü, [31:16] null süresi, [15:0] null gürültüsü.

**Hata kodu**

| Bit | Kod | Açıklama |
|---|---|---|
| 0 | `BUS_FAULT` | Hat `11` (iki çıkış birden 1) |
| 1 | `NOISE_VIOLATION` | Fazdaki gürültü toleransı aşıldı |
| 2 | `GAP_VIOLATION` | Word'ler arası gap 4 bitten kısa |
| 3 | `BIT_EARLY` | Bit süresi `min_bit`'ten kısa |
| 4 | `PULSE_GLITCH` | Pulse `min_pulse`'tan kısa veya polarite değişti |
| 5 | `PULSE_STUCK` | Pulse `max_pulse`'ı aştı |
| 6 | `BIT_TIMEOUT` | Bit `max_bit` içinde bitmedi |
| 7 | `PARITY` | Parity hatası (Word geçerli sayılmaz) |
| 8 | `WORD_MISMATCH` | Checker: hatasız alınan Word, gönderilen Word'den farklı |
| 9 | `NO_ECHO` | Checker: gönderilen Word `CHK_TIMEOUT` içinde alınmadı |
| 10 | `UNEXPECTED_WORD` | Checker: gönderilmemiş bir Word alındı |
| 11 | `LABEL_FILTERED` | Maske dışı Label |

---

## 10. Kullanım akışları

**Config yükleme (kanal veya TX):** `CFG_SEL` (+ Custom ise `CUST_*`) yaz → `CFG_APPLY = 1` → `ACT_*` ile doğrula.

**RX başlatma:** config yükle → `CTRL.enable = 1`.

**Kayıtları okuma:** `CTRL.freeze = 1` (veya `GLOBAL_FREEZE`) → `WORD_CNT`/`ERR_CNT` oku → her kayıt için `*_RADDR` yaz, `*_RD_*` oku → `freeze = 0`.

**TX gönderim:** TX config yükle → Word alanlarını veya `EXT_DATA`'yı yaz → `BUILDER_EN`, `MSG_SCHED_EN`, `TRANSMITTER_EN` → Scheduler ise `SCHED_EN = 1` (en son), değilse her Word için `TX_STATUS.busy = 0` bekle → `SEND_CMD = 1`.

**TX BIT:** TX BIT kanalını config'le ve enable et → `CHK_TIMEOUT` yaz → `CHK_CTRL.enable = 1` → TX gönderimi.

**Hatalı Word ile RX testi:** TX'i Custom config ile çalıştır; `CUST_PULSE_DUR` / `CUST_NULL_DUR` / `CUST_GAP_DUR` limit dışına alınarak
zaman hataları, `PARITY_TYPE` RX'in beklediğinin tersine ayarlanarak parity hatası üretilir. Ayrı bir hata enjeksiyonu bloğu yoktur.

**RX alıcı testi:** test edilecek RX kanallarında `CHK_TIMEOUT` ve `CHK_CTRL.enable = 1` → `ROUTE_TEST_MASK` yaz → `ROUTE_CTRL.route = 1` →
TX gönderimi → her kanalın `CHK_OK_CNT` / `CHK_ERR_CNT` ve Error kayıtlarını oku → `route = 0`.
