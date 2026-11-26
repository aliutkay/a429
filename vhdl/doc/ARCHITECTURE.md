# ARINC 429 IP — Mimari (taslak v0.5)

Bu doküman VHDL yazılmadan önce mimariyi netleştirmek içindir. Bloklar, generic'ler, portlar ve
blok arası sinyaller tanımlanır; RTL buna göre yazılır.

Diyagram: [`arinc429_ip_arch.drawio`](arinc429_ip_arch.drawio) (Sayfa 1 genel, Sayfa 2 RX kanalı, Sayfa 3 TX + yönlendirme + checker).

## Kararlar

| Konu | Karar |
|---|---|
| a429tool uyumu | Gerekmiyor; tool IP'ye göre yeniden yazılacak |
| Clock | IP içinde **tek clock domain** (APB dahil). AXI tarafı farklı clock'ta olabilir, dönüşüm IP dışında (§5.1) |
| Bus | **APB3 slave**. Sistemde AXI4-Lite master → AXI interconnect → AXI-to-APB bridge → IP |
| Adres | IP sadece `PADDR`'ın alt 16 bitini çözer (64 KB pencere); üst bitler sistemdeki base adres (§5.2) |
| Preset'ler | `a429_presets_pkg` içinde sabitler; değerleri kullanıcı ileride tool ile hesaplayıp yazacak |
| Low Speed preset | High Speed ile aynı yapıda bir preset; değerleri IP bitince tool ile hesaplanıp girilecek (pakette yer tutucu) |
| TX BIT alıcısı | TX hattını dinleyen **ayrı fiziksel alıcı entegresi** |
| TX çıkışı | **Ya** line driver'a **ya** seçili RX'lerin TESTA/TESTB pinlerine. FPGA içi loopback yok |
| RX test pinleri | Generic ile opsiyonel (`G_RX_TEST_EN`); reset'te TX line driver'a bağlı |
| HIGH-Z | Ayrı `tx_oe` yok; `tx_high = tx_low = 1` (line driver destekliyorsa) |
| RAM'ler | Şimdilik IP içinde `a429_sdp_ram` örnekleri; logger–RAM arayüzü sade tutulur, ileride dışarı alınabilir |
| Bellek derinlikleri | Generic: varsayılan Word 256, Error 256, Bit diagnostic 8 Word |
| Bit diagnostic | Sadece geçerli Word'ler (adres `word_cnt`); hatalı Word'ün bitleri sonraki Word ile ezilir |
| Checker hataları | TX BIT logger'ının Error belleğine; Error satırı 128 bit |
| Checker timeout | Sadece Register'dan (`CHK_TIMEOUT`, 0 = kapalı) |
| Timestamp | Clock sayısı (64 bit) |
| Parity | `parity_mode`: 0 kontrol yok, 1 Odd, 2 Even |
| Label filtresi | **Config ile ayarlanır** (enable + 256 bit maske, kanal Register'ları). Filtrelenen Word → Error RAM'e `LABEL_FILTERED` |
| TX `busy` | 32 bit + gap boyunca 1. Yükselen kenarı = `word_start`, düşen kenarı = `word_done`; `word_tx` TX kodundan dışarı alınır |
| IRQ | Yok (polling) |
| Hata enjeksiyonu | TX arayüzünde yer bırakılır |
| `rx_controller` | = **RX Logger** |

---

## 1. Hedefler

1. **Generic ve taşınabilir:** 0–1 TX, 0–1 TX BIT, 0–16 RX; kullanılmayan bloklar sentezlenmez.
2. **Hazır config + custom config:** Her TX/RX modülü tek Register yazmasıyla gömülü preset'e alınır; istenirse custom config yüklenir.
3. **RX entegre testi:** TX çıkışı istenince RX alıcılarının TESTA/TESTB pinlerine yönlendirilir.
4. **Ortak zaman:** Bütün logger'lar tek 64 bit timestamp'ten beslenir.
5. **Kanal başına ayrı kayıt:** Her alıcı (TX BIT dahil) Word, Error ve Bit diagnostic kayıtlarını kendi RAM'lerinde tutar.
6. **TX BIT (wraparound) kontrolü:** TX'in gönderdiği her Word, TX hattını dinleyen alıcıdan dönen Word ile karşılaştırılır.

---

## 2. Üst seviye blok yapısı

```
 AXI4-Lite master ─► AXI interconnect ─► (clock converter) ─► AXI-to-APB bridge ─► APB3
                                                                                   │  (IP clock'unda)
                        ┌──────────────── arinc429_ip (tek clock) ─────────────────┴────────┐
                        │ a429_apb_slave ─► a429_reg_bank (Global · TX · TXBIT · RX0..15)   │
                        │ a429_timestamp ─────────────► ts_now (bütün logger'lar)           │
                        │                                                                   │
                        │ tx_channel (G_TX_EN) ─► a429_tx_router ─┬─ line_en ─────────────► │ tx_high, tx_low, tx_slp
                        │      │ word_start/word_tx              └─ test_en (G_RX_TEST_EN) ► │ rx_test_a/b[N]
                        │      ▼                                                            │
                        │ txbit_channel (G_TXBIT_EN): rx_channel + word_checker  ◄──────────│ txbit_rx_high/low
                        │ rx_channel × G_NUM_RX                                  ◄──────────│ rx_high/low[N]
                        └───────────────────────────────────────────────────────────────────┘
```

### Entity listesi

| Entity | Görev |
|---|---|
| `a429_pkg` | Tipler, config record'ları, hata kodları, adres sabitleri, yardımcı fonksiyonlar |
| `a429_presets_pkg` | Gömülü TX/RX preset sabitleri (kullanıcı dolduracak) |
| `arinc429_ip` | Top; generate ile modülleri oluşturur |
| `a429_apb_slave` | APB3 → iç register bus |
| `a429_reg_bank` | Global Register'lar + modül sayfalarına adres çözme + okuma mux'ı |
| `a429_timestamp` | 64 bit sayaç, enable/clear, atomik okuma |
| `a429_cfg_sel` | Preset / custom seçimi, shadow → active (APPLY) |
| `a429_tx_core` | **Mevcut TX kodu** + arayüz sarmalayıcısı (sonra entegre) |
| `a429_tx_router` | TX çıkışını line driver **veya** RX test pinlerine yönlendirir |
| `a429_rx_channel` | Bir alıcı kanalı: cdc + filter + fsm + label filter + logger + RAM'ler + kanal Register'ları |
| `a429_cdc_sync` | 2/3-FF senkronizasyon |
| `a429_glitch_filter` | Glitch filtresi + `filter_err_cnt` |
| `a429_rx_fsm` | Receiver (mevcut `arinc429_rx_fsm`, güncellenmiş) |
| `a429_label_filter` | Config ile ayarlanan Label maskesi |
| `a429_rx_logger` | Timestamp'li kayıt, sayaçlar, freeze, dairesel yazma (eski `rx_controller`) |
| `a429_sdp_ram` | Generic simple dual-port RAM (şimdilik içeride; ileride dışarı alınabilir) |
| `a429_word_checker` | TX BIT karşılaştırma |

---

## 3. Generic'ler

| Generic | Tip / aralık | Varsayılan | Açıklama |
|---|---|---|---|
| `G_CLK_HZ` | natural | 50_000_000 | Bilgi (`CLK_HZ` Register'ı) + sayaç genişliği `assert`'leri |
| `G_TX_EN` | boolean | true | TX modülü |
| `G_TXBIT_EN` | boolean | true | TX BIT kanalı (`G_TX_EN = false` ise yok) |
| `G_NUM_RX` | natural 0–16 | 4 | RX kanal sayısı |
| `G_RX_TEST_EN` | boolean | false | `rx_test_a/b` çıkışları ve test yönlendirmesi |
| `G_TX_INJECT_EN` | boolean | false | TX hata enjeksiyonu (TX kodu destekleyince) |
| `G_SYNC_STAGES` | natural 2–3 | 2 | CDC FF sayısı |
| `G_DUR_W` | natural | 16 | Pulse/Null/Bit süre sayaç genişliği |
| `G_GAP_W` | natural | 32 | Gap süre sayaç genişliği |
| `G_WORD_DEPTH_LOG2` | natural | 8 | Kanal başına Word kaydı (256) |
| `G_ERR_DEPTH_LOG2` | natural | 8 | Kanal başına Error kaydı (256) |
| `G_BITDIAG_WORDS_LOG2` | natural | 3 | Bit diagnostic tutulan Word sayısı (8; her Word 32 satır) |
| `G_BITDIAG_EN` | boolean | true | Bit diagnostic RAM'i |
| `G_CHK_FIFO_DEPTH` | natural | 4 | Checker beklenen Word FIFO derinliği |
| `G_APB_ADDR_W` | natural | 16 | IP'nin çözdüğü adres biti sayısı |

> `G_NUM_RX = 0` iken null range portlar bazı araçlarda sorun çıkarır; portlar `max(G_NUM_RX,1)` genişlikte tanımlanır, fazlası bağlanmaz.

---

## 4. Top seviye portlar

| Port | Yön | Genişlik | Ne zaman kullanılır | Açıklama |
|---|---|---|---|---|
| `clk` | in | 1 | her zaman | IP clock'u (ör. 50 MHz), APB de bu clock'ta |
| `rst_n` | in | 1 | her zaman | Aktif-düşük; asenkron assert, senkron deassert |
| `psel, penable, pwrite` | in | 1 | her zaman | APB3 |
| `paddr` | in | 32 | her zaman | Sadece `[G_APB_ADDR_W-1:2]` çözülür |
| `pwdata` | in | 32 | her zaman | APB3'te PSTRB yok → sadece 32 bit yazma |
| `prdata` | out | 32 | her zaman | |
| `pready` | out | 1 | her zaman | RAM okumasında wait state |
| `pslverr` | out | 1 | her zaman | Geçersiz adres / sentezlenmemiş modül |
| `tx_high, tx_low` | out | 1 | `G_TX_EN` | Line driver TX1IN / TX0IN. `11` = HIGH-Z (sürücü destekliyorsa) |
| `tx_slp` | out | 1 | `G_TX_EN` | 1: 1.5 µs (High Speed), 0: Low Speed eğim |
| `txbit_rx_high, txbit_rx_low` | in | 1 | `G_TXBIT_EN` | TX hattını dinleyen alıcının ROUTA / ROUTB çıkışları |
| `rx_high, rx_low` | in | N | `G_NUM_RX > 0` | RX alıcılarının ROUTA / ROUTB çıkışları |
| `rx_test_a, rx_test_b` | out | N | `G_RX_TEST_EN` | RX alıcılarının TESTA / TESTB pinleri |

> Generic false olan portlar entity'de kalır (VHDL'de port koşullu olamaz); çıkışlar sabit `'0'`, girişler kullanılmaz.

---

## 5. Sistem bağlantısı ve adresleme

### 5.1 Clock

IP içi tek clock (ör. 50 MHz). AXI interconnect başka bir clock'ta (ör. 100 MHz) çalışabilir; dönüşüm **IP'nin dışında**
yapılır, IP'ye CDC eklenmez:

```
AXI master (aclk_a) ─► AXI interconnect / SmartConnect ─► [clock dönüşümü] ─► AXI-to-APB bridge (clk_ip) ─► arinc429_ip (clk_ip)
```

- Xilinx'te AXI Interconnect / SmartConnect, slave portunda farklı clock verilince dönüşümü kendisi yapar; ya da araya **AXI Clock Converter** konur.
- AXI-to-APB bridge IP ile **aynı clock'ta** çalışmalı; böylece APB sinyalleri doğrudan IP clock'undadır.

### 5.2 Adres

Sistem 32 bit adres kullanır. Interconnect'in adres editöründe IP'ye bir **base adres** ve **64 KB aralık** verilir
(ör. `0x4000_0000 – 0x4000_FFFF`). Interconnect üst bitlere bakıp isteği IP'ye yönlendirir; IP sadece alt 16 biti çözer:

```
 31 ................ 16 | 15 ....... 10 | 9 ........ 2 | 1 0
   sistem base adresi    |   modül ID    | Register no  | 00
   (interconnect çözer)  |        IP çözer (64 KB)      |
```

Yani "16 bit AXI'ye, 16 bit bize" diye sabit bir bölünme yok; üst bitler sistemin adres haritasında IP'nin nerede durduğunu,
alt 16 bit IP içindeki Register'ı seçer. Aralık 64 KB olduğu sürece base adres 64 KB hizalı herhangi bir yer olabilir.

| Modül ID | Offset | Modül |
|---|---|---|
| `0x00` | `0x0000` | Global |
| `0x01` | `0x0400` | TX |
| `0x02` | `0x0800` | TX BIT |
| `0x10`–`0x1F` | `0x4000`–`0x7C00` | RX0 – RX15 |

Sentezlenmemiş modüle veya tanımsız Register'a erişim: `pslverr = 1`, okuma `0`.

### 5.3 Global sayfa

| Reg | Offset | Ad | R/W | Açıklama |
|---|---|---|---|---|
| 00 | 0x00 | `IP_ID` | R | `0x41343239` ("A429") |
| 01 | 0x04 | `IP_VERSION` | R | major.minor.patch |
| 02 | 0x08 | `CAPS` | R | NUM_RX, TX, TXBIT, TEST, INJECT, BITDIAG bayrakları |
| 03 | 0x0C | `CAPS_MEM` | R | Word / Err / BitDiag derinlikleri (log2), DUR_W, GAP_W |
| 04 | 0x10 | `CLK_HZ` | R | `G_CLK_HZ` |
| 08 | 0x20 | `SOFT_RESET` | W | bit0 tüm IP, bit1 TX, bit2 TX BIT, bit16+n RXn (self-clearing) |
| 09 | 0x24 | `GLOBAL_FREEZE` | RW | Bütün logger'ları aynı anda dondurur |
| 0A | 0x28 | `TS_CTRL` | RW | bit0 enable, bit1 clear (self-clearing) |
| 0B | 0x2C | `TS_LSB` | R | Okununca MSB latch'lenir |
| 0C | 0x30 | `TS_MSB` | R | Latch'lenmiş MSB |
| 10 | 0x40 | `ROUTE_CTRL` | RW | bit0 `route` (0 line driver [reset], 1 RX test pinleri), bit1 `line_idle` (test modunda line driver: 0 NULL, 1 HIGH-Z) |
| 11 | 0x44 | `ROUTE_TEST_MASK` | RW | Test modunda TESTA/TESTB'si sürülecek RX kanalları |

### 5.4 Kanal sayfası (RX0–RX15 ve TX BIT ortak)

> **Güncel harita (IP 2.0.0):** AXIL Studio register'larında ilgili 16-bit alanlar tek register'da gruplanmıştır
> (`CUST_PULSE [MIN|MAX]`, `ERR_RD_INFO [CODE|ADDR]`, `BIT_RD_PULSE/NULL [DUR|ERR]` …) ve `STATUS`'a
> `LINE_HIGH/LINE_LOW/SYNC_WAIT` hat teşhis bitleri eklenmiştir. Kesin offset/bit düzeni için
> `vhdl/axil/arinc429_axil_regs.md` ve tek kaynak `a429/ipmap.py` geçerlidir; aşağıdaki tablo mimari açıklamadır.

| Reg | Ad | R/W | Açıklama |
|---|---|---|---|
| 00 | `CTRL` | RW | bit0 enable, bit1 freeze, bit2 clear (self-clear) |
| 01 | `STATUS` | R | FSM durumu, frozen, Word/Error RAM wrap bayrakları, aktif preset |
| 02 | `CFG_SEL` | RW | 0 High Speed, 1 Low Speed, 2 Custom |
| 03 | `CFG_APPLY` | W | Shadow → active (FSM IDLE'dayken uygulanır) |
| 10–18 | `CFG_*` | RW | Custom: glitch_filter_size, min/max pulse, min/max bit, max pulse/null/gap err, parity_mode |
| 19 | `LABEL_FILTER_EN` | RW | 1: Label filtresi aktif |
| 1A–21 | `LABEL_MASK[0..7]` | RW | 256 bit Label maskesi (bit = 1 → Label kabul) |
| 28–30 | `ACT_*` | R | Aktif config geri okuma |
| 38 | `WORD_CNT` | R | Geçerli Word sayısı |
| 39 | `ERR_CNT` | R | Hata sayısı |
| 3A | `DROP_CNT` | R | Freeze sırasında atılanlar |
| 3B | `LAST_WORD` | R | Son geçerli Word (canlı izleme) |
| 40 | `WORD_RADDR` | RW | Word RAM okuma adresi |
| 41–45 | `WORD_RD_*` | R | TS MSB, TS LSB, data, gap, gap_err |
| 48 | `ERR_RADDR` | RW | Error RAM okuma adresi |
| 49–4D | `ERR_RD_*` | R | TS MSB, TS LSB, code, addr, data |
| 50 | `BIT_RADDR` | RW | {Word index, bit index} |
| 51–54 | `BIT_RD_*` | R | pulse, pulse_err, null, null_err |
| 70–7F | Checker | | Sadece TX BIT: CHK_CTRL, CHK_TIMEOUT, CHK_OK_CNT, CHK_ERR_CNT, FIFO durumu |

### 5.5 TX sayfası

Mevcut TX Register'ları (transmitter_en, msg_sched_en, builder_en, label/sdi/data/ssm, parity_type, scheduler_en,
initial_delay, inter_word_gap, pulse/null/gap_dur, slp, ext_data_valid, ext_data, ext_high/low) korunur, yeni sayfada
yeniden numaralanır. Ek olarak:

| Ad | Açıklama |
|---|---|
| `CFG_SEL` / `CFG_APPLY` | Preset/custom; Word sınırında uygulanır |
| `TX_STATUS` | busy, scheduler aktif |
| `TX_WORD_CNT` | Gönderilen Word sayısı |
| `INJ_CTRL` / `INJ_PARAM` | Hata enjeksiyonu için ayrılmış (`G_TX_INJECT_EN`) |

---

## 6. Blok detayları

### 6.1 `a429_apb_slave` + `a429_reg_bank`
- APB3 setup/access fazları; yazma access fazında tek clk strobe.
- Okuma: modül içinde kayıtlı okuma verisi + global mux; RAM okuması için sabit wait state (deterministik).

### 6.2 `a429_timestamp`
- 64 bit, her clk +1; `enable`, `clear`. `ts_now` bütün logger'lara gider.
- 32 bit bus ile atomik okuma: `TS_LSB` okunduğu an MSB latch'lenir.

### 6.3 `a429_cfg_sel`
- Preset'ler `a429_presets_pkg`'de `C_RX_PRESET(0..1)`, `C_TX_PRESET(0..1)` record dizileri; değerler kullanıcıdan.
- **Shadow → active:** Host'un yazdığı config Register'ları (`CFG_SEL`, `CFG_*`) doğrudan çalışan bloğa gitmez; önce
  **shadow** Register'larda bekler. Bloğun gerçekten kullandığı değerler **active** Register'lardır. Host bütün alanları yazıp
  `CFG_APPLY = 1` yaptığında shadow → active kopyalanır; kopyalama RX'te FSM `IDLE`/`ERR_RECOVERY`'deyken, TX'te `busy = 0`
  iken olur. Böylece (1) birden çok Register tek tek yazılırken blok yarı-eski yarı-yeni bir config ile çalışmaz,
  (2) Word ortasında config değişip o Word bozulmaz. `ACT_*` Register'ları active değerleri geri okur.

RX config record: `glitch_filter_size`, `min_pulse`, `max_pulse`, `min_bit`, `max_bit`, `max_pulse_err`, `max_null_err`,
`max_gap_err`, `parity_mode` (0 yok, 1 Odd, 2 Even).
TX config record: `pulse_dur`, `null_dur`, `gap_dur`, `slp`, `parity_type`.

Label filtresi (enable + maske) preset'ten bağımsız kanal Register'larıdır; değişiklik FSM IDLE'dayken etkin olur.

### 6.4 TX kanalı (`a429_tx_core`, mevcut kod)

İçinde 3 MUX: MUX1 Word Builder / ext_data, MUX2 Message Scheduler / ext_data_valid, MUX3 Word Transmitter / Line Override.

| Sinyal | Yön | Açıklama |
|---|---|---|
| `cfg`, `regs` | in | Config record + TX Register'ları |
| `line_high, line_low` | out | MUX3 sonrası hat seviyeleri (`11` = HIGH-Z) |
| `slp` | out | |
| `busy` | out | Mevcut; 32 bit + gap boyunca 1 |
| `word_tx[31:0]` | out | Gönderilen Word (hatta çıkan haliyle, parity dahil); `busy` yükselirken geçerli |
| `inj_en, inj_type, inj_param` | in | Hata enjeksiyonu için ayrılmış |

Sarmalayıcı `busy`'den kenar algılama ile üretir: yükselen kenar → `word_start` (1 clk), düşen kenar → `word_done` (1 clk).
Arka arkaya Word'lerde `inter_word_gap ≥ 1 clk` olduğu için `busy` iki Word arasında en az 1 clk düşer, her Word ayrı yakalanır.

**Hata enjeksiyonu (ileride):**

| `inj_type` | Etki | RX'te beklenen hata |
|---|---|---|
| parity flip | Bit 32 ters | `PARITY` |
| short pulse | Seçilen bitte pulse = `inj_param` clk | `PULSE_GLITCH` |
| long pulse | Seçilen bitte pulse uzun | `PULSE_STUCK` |
| bit count 31 | Son bit gönderilmez | `BIT_TIMEOUT` / `GAP_VIOLATION` |
| bit count 33 | Fazladan bit | `GAP_VIOLATION` |
| short gap | Gap = `inj_param` | `GAP_VIOLATION` |
| bus fault | `11` durumu | `BUS_FAULT` |

### 6.5 `a429_tx_router`

TX çıkışı **iki hedeften birine** gider (`ROUTE_CTRL.route`):

| `route` | `tx_high/tx_low` (line driver) | `rx_test_a/b[n]` |
|---|---|---|
| 0 (reset) | TX sinyali | `00` (alıcılar normal) |
| 1 (test) | `line_idle`: `00` NULL veya `11` HIGH-Z | Maske set olan kanallara TX sinyali (aşağıdaki kodlama), diğerleri `00` |

Test pin kodlaması (HI-8591 doğruluk tablosu):

| TX hat durumu | TESTA | TESTB | Alıcı çıkışı |
|---|---|---|---|
| Test kapalı | 0 | 0 | Normal ARINC girişi |
| HIGH (ONE) | 1 | 0 | ROUTA=1, ROUTB=0 |
| LOW (ZERO) | 0 | 1 | ROUTA=0, ROUTB=1 |
| NULL / HIGH-Z | **1** | **1** | 0 / 0 (test modunda kalır) |

NULL `11` olarak sürülür; `00` alıcıyı test modundan çıkarıp gerçek hattı içeri alır.
`route` değişikliği TX boştayken (`busy = 0`) uygulanır, yarım Word gönderilmez.

### 6.6 `a429_rx_channel`

```
pin_high/low ─► cdc_sync ─► glitch_filter ─► rx_fsm ─► label_filter ─► rx_logger ─┬─► Word RAM
                               │ filter_err_cnt  ▲ cfg_active               ▲ ts_now ├─► Error RAM
                               └─────────────────┘                          freeze  └─► Bit diag RAM
                                                                                        ▲ okuma portu (reg_bank)
```

`rx_fsm` için değişiklikler:
- **Word başlangıç timestamp'i:** bit 0'ın ilk kenarında `word_start` darbesi → logger ts'yi o an yakalar (şu an Word sonunda alınıyor).
- **Parity:** `parity_mode` 0 ise kontrol yok, 1/2 ise Odd/Even.

### 6.7 `a429_label_filter`
- `LABEL_FILTER_EN = 1` iken maskede biti 0 olan Label'lı Word **Word RAM'e yazılmaz**, `word_cnt` artmaz.
- Bunun yerine Error RAM'e `LABEL_FILTERED` yazılır: `addr` = Label, `data` = Word.
- Diğer hatalar Label'dan bağımsız loglanır.

### 6.8 `a429_rx_logger` (eski `rx_controller`)

| RAM | Satır | Genişlik | Yazma adresi |
|---|---|---|---|
| Word | ts(64), word(32), gap_dur(32), gap_err(16) | 144 | `word_cnt mod 2^G_WORD_DEPTH_LOG2` |
| Error | ts(64), code(16), addr(16), data(32) | 128 | `err_cnt mod 2^G_ERR_DEPTH_LOG2` |
| Bit diag | pulse(16), pulse_err(16), null(16), null_err(16) | 64 | `{word_cnt mod 2^G_BITDIAG_WORDS_LOG2, bit_idx}` |

- Dairesel yazma; sayaçlar 32 bit, alt bitleri yazma pointer'ı.
- **Freeze** (`CTRL.freeze` OR `GLOBAL_FREEZE`): yazma durur, gelenler atılır, `DROP_CNT` artar; timestamp saymaya devam eder.
- Hata kodu bitmask'i logger'da üretilir.

**Logger ↔ RAM arayüzü** (her RAM için aynı; ileride RAM dışarı alınırsa bu sinyaller porta çıkar):

| Sinyal | Yön (logger tarafından) | Açıklama |
|---|---|---|
| `we` | out | Yazma enable |
| `waddr` | out | Yazma adresi |
| `wdata` | out | Satır verisi |
| `raddr` | in (reg_bank'tan) | Host okuma adresi |
| `rdata` | → reg_bank | Okunan satır (1 clk gecikme) |

### 6.9 `a429_word_checker` (TX BIT)

- `word_start` geldiğinde `word_tx` + `ts_now` beklenen FIFO'ya girer.
- TX BIT alıcısından geçerli Word gelince FIFO başı ile karşılaştırılır:
  - eşit → `CHK_OK_CNT++`
  - farklı → `WORD_MISMATCH`; `data` = **beklenen** Word (alınan Word TX BIT Word RAM'inde)
- FIFO başı `CHK_TIMEOUT` clk içinde eşleşmezse → `NO_ECHO` (0 = timeout kapalı). FIFO boşken Word gelirse → `UNEXPECTED_WORD`.
- TX BIT alıcısı bir Word'ü hatalı aldıysa (FSM hatası) FIFO başı düşürülür; aynı Word için ayrıca `NO_ECHO` basılmaz.
- TX test pinlerine yönlendirildiğinde (`route = 1`) TX hattı sürülmediği için checker kapatılmalı (ya da otomatik pasif).

### 6.10 Hata kodu tablosu (16 bit bitmask)

| Bit | Kod | Kaynak | `addr` | `data` |
|---|---|---|---|---|
| 0 | `BUS_FAULT` | rx_fsm | bit idx | süre |
| 1 | `NOISE_VIOLATION` | rx_fsm | bit idx / 32=gap | filter_err_cnt |
| 2 | `GAP_VIOLATION` | rx_fsm | 32 | gap süresi |
| 3 | `BIT_EARLY` | rx_fsm | bit idx | süre |
| 4 | `PULSE_GLITCH` | rx_fsm | bit idx | süre |
| 5 | `PULSE_STUCK` | rx_fsm | bit idx | süre |
| 6 | `BIT_TIMEOUT` | rx_fsm | bit idx | süre |
| 7 | `PARITY` | rx_fsm | 31 | Word |
| 8 | `WORD_MISMATCH` | checker | FIFO idx | beklenen Word |
| 9 | `NO_ECHO` | checker | FIFO idx | beklenen Word |
| 10 | `UNEXPECTED_WORD` | checker | — | alınan Word |
| 11 | `LABEL_FILTERED` | label_filter | Label | Word |
| 12–15 | rezerve | | | |

---

## 7. Çalışma modları

| Mod | `route` | Line driver | Test pinleri | Checker |
|---|---|---|---|---|
| Normal (reset) | 0 | TX | `00` | açık (TX BIT) |
| RX alıcı testi | 1 | NULL / HIGH-Z | seçili RX'ler | kapalı; sonuç RX kanallarının logger'larında |
| Sadece dinleme | 0, TX kapalı | NULL | `00` | kapalı |

---

## 8. Kaynak / zamanlama notları
- Low Speed'de en uzun bit ≈ 83 µs → 16 bit süre sayacı ~786 MHz'e kadar yeterli (50 MHz'te ≈ 4 200 clk); `assert` ile kontrol.
- **RAM (varsayılan derinlik, kanal başına):** Word 256 × 144, Error 256 × 128, Bit diag 256 × 64 → Xilinx 7-serisinde ≈ 4.5 BRAM36.
  16 RX + TX BIT ≈ 77 BRAM36; küçük FPGA'larda derinlik generic'leri veya `G_NUM_RX` düşürülür.
- 18 modül × 256 Register okuma mux'ı: modül içinde kayıtlı okuma + global mux, sabit wait state.

---

## 9. Açık sorular
Yok. Preset değerleri (High Speed ve Low Speed) IP bitince tool ile hesaplanıp `a429_presets_pkg`'e girilecek.

---

## 10. Sonraki adımlar
1. Register haritasının kesin numaralandırması (TX sayfası dahil).
2. `a429_pkg`, `a429_presets_pkg`.
3. RX zinciri: cdc_sync, glitch_filter, rx_fsm, label_filter, rx_logger, sdp_ram, rx_channel + testbench.
4. timestamp, cfg_sel, reg_bank, apb_slave, top + testbench.
5. tx_router, word_checker, mevcut TX kodunun entegrasyonu.
