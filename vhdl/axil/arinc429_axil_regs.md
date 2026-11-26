# arinc429_axil

IP version: `2.0.0`

ARINC 429 IP (1 RX, TX=Var, TX BIT=Var, 50 MHz)

Addresses below are offsets from the slave base address set on the interconnect.  
Decoded address bits: `[14:2]` (block repeats every 0x8000 bytes)

## Registers

| Offset | Register | Access | Reset | Description |
|---|---|---|---|---|
| 0x00 | IP_ID | RO | 0x41343239 | ARINC 429 IP kimliği ('A429') |
| 0x04 | IP_VERSION | RO | 0x00020000 | IP sürümü (2.0.0; [23:16] major, [15:8] minor, [7:0] patch) |
| 0x08 | CAPS | RO | 0x00000B01 | Donanım yetenekleri |
| 0x0C | CAPS_MEM | RO | 0x00030808 | RAM derinlikleri |
| 0x10 | CLK_HZ | RO | 0x02FAF080 | IP sistem saati (Hz) |
| 0x20 | SOFT_RESET | WO | 0x00000000 | Yumuşak reset darbeleri (self-clearing) |
| 0x24 | GLOBAL_FREEZE | RW | 0x00000000 | Tüm logger'ları eşzamanlı dondur |
| 0x28 | TS_CTRL | RW | 0x00000001 | Timestamp kontrol |
| 0x2C | TS_LSB | RO | 0x00000000 | Timestamp alt 32 bit (okununca MSB latch'lenir) |
| 0x30 | TS_MSB | RO | 0x00000000 | Latch'lenmiş timestamp üst 32 bit |
| 0x400 | TX_CTRL | RW | 0x00000000 | TX kanal kontrolü (kaynak ve mod seçimleri) |
| 0x404 | TX_WORD | RW | 0x80000000 | Word Builder alanları (ARINC 429 Word bit düzeninde) |
| 0x408 | TX_SEND_CMD | WO | 0x00000000 | Tek gönderim darbesi |
| 0x40C | TX_EXT_DATA | RW | 0x00000000 | Hazır 32-bit Word (BUILDER_EN=0) |
| 0x410 | TX_EXT_LINE | RW | 0x00000000 | Hat override (TRANSMITTER_EN=0): 10 HIGH, 01 LOW, 00 NULL, 11 HIGH-Z |
| 0x420 | TX_INITIAL_DELAY | RW | 0x00000000 | Scheduler başlangıç gecikmesi (clk) |
| 0x424 | TX_INTER_WORD_GAP | RW | 0x00000001 | Scheduler Word arası ekstra bekleme (clk, >=1) |
| 0x440 | TX_CFG | RW | 0x00000000 | TX config seçimi ve uygulama |
| 0x444 | TX_CUST_TIMING | RW | 0x00000000 | Custom bit zamanlaması |
| 0x448 | TX_CUST_GAP_DUR | RW | 0x00000000 | Custom Word Gap süresi (clk) |
| 0x44C | TX_CUST_SLP | RW | 0x00000000 | Custom SLP eğim çıkışı (1: HS, 0: LS) |
| 0x460 | TX_ACT_TIMING | RO | 0x00000000 | Aktif bit zamanlaması |
| 0x464 | TX_ACT_GAP_DUR | RO | 0x00000000 | Aktif Word Gap süresi (clk) |
| 0x468 | TX_ACT_SLP | RO | 0x00000000 | Aktif SLP eğim çıkışı |
| 0x480 | TX_STATUS | RO | 0x00000000 | TX durum register'ı |
| 0x484 | TX_WORD_CNT | RO | 0x00000000 | Gönderilen toplam Word sayısı |
| 0x800 | TB_CTRL | RW | 0x00000000 | TB kanal kontrolü |
| 0x804 | TB_STATUS | RO | 0x00000000 | TB kanal durumu ve hat teşhisi |
| 0x808 | TB_CFG | RW | 0x00000000 | RX config seçimi ve uygulama |
| 0x840 | TB_CUST_PULSE | RW | 0x00000000 | Custom pulse süre sınırları |
| 0x844 | TB_CUST_BIT | RW | 0x00000000 | Custom bit süre sınırları |
| 0x848 | TB_CUST_NOISE | RW | 0x00000000 | Custom pulse/null gürültü (glitch) limitleri |
| 0x84C | TB_CUST_FILTER | RW | 0x00000000 | Custom glitch filtresi ve gap gürültü limiti |
| 0x850 | TB_CUST_PARITY | RW | 0x00000001 | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x860 | TB_ACT_PULSE | RO | 0x00000000 | Aktif pulse süre sınırları |
| 0x864 | TB_ACT_BIT | RO | 0x00000000 | Aktif bit süre sınırları |
| 0x868 | TB_ACT_NOISE | RO | 0x00000000 | Aktif pulse/null gürültü (glitch) limitleri |
| 0x86C | TB_ACT_FILTER | RO | 0x00000000 | Aktif glitch filtresi ve gap gürültü limiti |
| 0x870 | TB_ACT_PARITY | RO | 0x00000000 | Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x8E0 | TB_WORD_CNT | RO | 0x00000000 | Geçerli Word sayısı |
| 0x8E4 | TB_ERR_CNT | RO | 0x00000000 | Hata kaydı sayısı |
| 0x8E8 | TB_DROP_CNT | RO | 0x00000000 | Freeze sırasında atılan kayıt sayısı |
| 0x8EC | TB_LAST_WORD | RO | 0x00000000 | Alınan son geçerli Word |
| 0x900 | TB_WORD_RADDR | RW | 0x00000000 | Word RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x904 | TB_WORD_RD_TS_MSB | RO | 0x00000000 | Word kaydı Timestamp MSB |
| 0x908 | TB_WORD_RD_TS_LSB | RO | 0x00000000 | Word kaydı Timestamp LSB |
| 0x90C | TB_WORD_RD_DATA | RO | 0x00000000 | Word kaydı 32-bit veri |
| 0x910 | TB_WORD_RD_GAP | RO | 0x00000000 | Word kaydı önceki Gap süresi (clk) |
| 0x914 | TB_WORD_RD_GAP_ERR | RO | 0x00000000 | Word kaydı Gap gürültü sayısı (okununca pointer +1) |
| 0x920 | TB_ERR_RADDR | RW | 0x00000000 | Error RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x924 | TB_ERR_RD_TS_MSB | RO | 0x00000000 | Error kaydı Timestamp MSB |
| 0x928 | TB_ERR_RD_TS_LSB | RO | 0x00000000 | Error kaydı Timestamp LSB |
| 0x92C | TB_ERR_RD_INFO | RO | 0x00000000 | Error kaydı hata kodu ve konumu |
| 0x930 | TB_ERR_RD_DATA | RO | 0x00000000 | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |
| 0x940 | TB_BIT_RADDR | RW | 0x00000000 | Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x944 | TB_BIT_RD_PULSE | RO | 0x00000000 | Bit Pulse süresi ve gürültüsü |
| 0x948 | TB_BIT_RD_NULL | RO | 0x00000000 | Bit Null süresi ve gürültüsü (okununca pointer +1) |
| 0x9C0 | TB_CHK_CTRL | RW | 0x00000000 | TX BIT Word Checker kontrol |
| 0x9C4 | TB_CHK_TIMEOUT | RW | 0x00000000 | Echo zaman aşımı (clk, 0=kapalı) |
| 0x9C8 | TB_CHK_OK_CNT | RO | 0x00000000 | Eşleşen Word sayısı |
| 0x9CC | TB_CHK_ERR_CNT | RO | 0x00000000 | Checker hata sayısı |
| 0x9D0 | TB_CHK_STATUS | RO | 0x00000000 | TX BIT Checker FIFO durumu |
| 0x4000 | RX0_CTRL | RW | 0x00000000 | RX0 kanal kontrolü |
| 0x4004 | RX0_STATUS | RO | 0x00000000 | RX0 kanal durumu ve hat teşhisi |
| 0x4008 | RX0_CFG | RW | 0x00000000 | RX config seçimi ve uygulama |
| 0x4040 | RX0_CUST_PULSE | RW | 0x00000000 | Custom pulse süre sınırları |
| 0x4044 | RX0_CUST_BIT | RW | 0x00000000 | Custom bit süre sınırları |
| 0x4048 | RX0_CUST_NOISE | RW | 0x00000000 | Custom pulse/null gürültü (glitch) limitleri |
| 0x404C | RX0_CUST_FILTER | RW | 0x00000000 | Custom glitch filtresi ve gap gürültü limiti |
| 0x4050 | RX0_CUST_PARITY | RW | 0x00000001 | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x4060 | RX0_ACT_PULSE | RO | 0x00000000 | Aktif pulse süre sınırları |
| 0x4064 | RX0_ACT_BIT | RO | 0x00000000 | Aktif bit süre sınırları |
| 0x4068 | RX0_ACT_NOISE | RO | 0x00000000 | Aktif pulse/null gürültü (glitch) limitleri |
| 0x406C | RX0_ACT_FILTER | RO | 0x00000000 | Aktif glitch filtresi ve gap gürültü limiti |
| 0x4070 | RX0_ACT_PARITY | RO | 0x00000000 | Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x40E0 | RX0_WORD_CNT | RO | 0x00000000 | Geçerli Word sayısı |
| 0x40E4 | RX0_ERR_CNT | RO | 0x00000000 | Hata kaydı sayısı |
| 0x40E8 | RX0_DROP_CNT | RO | 0x00000000 | Freeze sırasında atılan kayıt sayısı |
| 0x40EC | RX0_LAST_WORD | RO | 0x00000000 | Alınan son geçerli Word |
| 0x4100 | RX0_WORD_RADDR | RW | 0x00000000 | Word RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x4104 | RX0_WORD_RD_TS_MSB | RO | 0x00000000 | Word kaydı Timestamp MSB |
| 0x4108 | RX0_WORD_RD_TS_LSB | RO | 0x00000000 | Word kaydı Timestamp LSB |
| 0x410C | RX0_WORD_RD_DATA | RO | 0x00000000 | Word kaydı 32-bit veri |
| 0x4110 | RX0_WORD_RD_GAP | RO | 0x00000000 | Word kaydı önceki Gap süresi (clk) |
| 0x4114 | RX0_WORD_RD_GAP_ERR | RO | 0x00000000 | Word kaydı Gap gürültü sayısı (okununca pointer +1) |
| 0x4120 | RX0_ERR_RADDR | RW | 0x00000000 | Error RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x4124 | RX0_ERR_RD_TS_MSB | RO | 0x00000000 | Error kaydı Timestamp MSB |
| 0x4128 | RX0_ERR_RD_TS_LSB | RO | 0x00000000 | Error kaydı Timestamp LSB |
| 0x412C | RX0_ERR_RD_INFO | RO | 0x00000000 | Error kaydı hata kodu ve konumu |
| 0x4130 | RX0_ERR_RD_DATA | RO | 0x00000000 | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |
| 0x4140 | RX0_BIT_RADDR | RW | 0x00000000 | Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x4144 | RX0_BIT_RD_PULSE | RO | 0x00000000 | Bit Pulse süresi ve gürültüsü |
| 0x4148 | RX0_BIT_RD_NULL | RO | 0x00000000 | Bit Null süresi ve gürültüsü (okununca pointer +1) |

### 0x00 IP_ID

ARINC 429 IP kimliği ('A429')

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | IP_ID | CONST | 0x41343239 | `—` | ARINC 429 IP kimliği ('A429') |

### 0x04 IP_VERSION

IP sürümü (2.0.0; [23:16] major, [15:8] minor, [7:0] patch)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | IP_VERSION | CONST | 0x20000 | `—` | IP sürümü (2.0.0; [23:16] major, [15:8] minor, [7:0] patch) |

### 0x08 CAPS

Donanım yetenekleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [11] | BITDIAG | CONST | 0x1 | `—` | Bit diagnostic RAM var |
| [10] | RX_TEST | CONST | 0x0 | `—` | RX test pinleri var |
| [9] | TXBIT | CONST | 0x1 | `—` | TX BIT kanalı var |
| [8] | TX | CONST | 0x1 | `—` | TX kanalı var |
| [4:0] | NUM_RX | CONST | 0x1 | `—` | RX kanal sayısı |

### 0x0C CAPS_MEM

RAM derinlikleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [23:16] | BITDIAG_WORDS_LOG2 | CONST | 0x3 | `—` | Bit diagnostic Word sayısı (log2) |
| [15:8] | ERR_DEPTH_LOG2 | CONST | 0x8 | `—` | Error RAM derinliği (log2) |
| [7:0] | WORD_DEPTH_LOG2 | CONST | 0x8 | `—` | Word RAM derinliği (log2) |

### 0x10 CLK_HZ

IP sistem saati (Hz)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | CLK_HZ | CONST | 0x2FAF080 | `—` | IP sistem saati (Hz) |

### 0x20 SOFT_RESET

Yumuşak reset darbeleri (self-clearing)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [16] | RX0 | PULSE | 0 | `o_soft_reset_rx0` | RX0 kanalı reseti |
| [2] | TXBIT | PULSE | 0 | `o_soft_reset_txbit` | TX BIT kanalı reseti |
| [1] | TX | PULSE | 0 | `o_soft_reset_tx` | TX kanalı reseti |
| [0] | RST_ALL | PULSE | 0 | `o_soft_reset_rst_all` | Tüm IP yumuşak reseti |

### 0x24 GLOBAL_FREEZE

Tüm logger'ları eşzamanlı dondur

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | GLOBAL_FREEZE | RW | 0x0 | `o_global_freeze` | Tüm logger'ları eşzamanlı dondur |

### 0x28 TS_CTRL

Timestamp kontrol

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1] | CLEAR | PULSE | 0 | `o_ts_ctrl_clear` | Timestamp sayacını sıfırla |
| [0] | ENABLE | RW | 0x1 | `o_ts_ctrl_enable` | 64-bit timestamp sayacı etkin |

### 0x2C TS_LSB

Timestamp alt 32 bit (okununca MSB latch'lenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TS_LSB | RO | 0 | `i_ts_lsb` | Timestamp alt 32 bit (okununca MSB latch'lenir) |

Strobes: `o_ts_lsb_rd`

### 0x30 TS_MSB

Latch'lenmiş timestamp üst 32 bit

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TS_MSB | RO | 0 | `i_ts_msb` | Latch'lenmiş timestamp üst 32 bit |

### 0x400 TX_CTRL

TX kanal kontrolü (kaynak ve mod seçimleri)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [3] | SCHED_EN | RW | 0x0 | `o_tx_ctrl_sched_en` | Message Scheduler başlat/durdur |
| [2] | BUILDER_EN | RW | 0x0 | `o_tx_ctrl_builder_en` | 1: Word Builder (TX_WORD), 0: EXT_DATA |
| [1] | MSG_SCHED_EN | RW | 0x0 | `o_tx_ctrl_msg_sched_en` | 1: Message Scheduler, 0: SEND_CMD tek gönderim |
| [0] | TRANSMITTER_EN | RW | 0x0 | `o_tx_ctrl_transmitter_en` | 1: Word Transmitter, 0: EXT_LINE hat override |

### 0x404 TX_WORD

Word Builder alanları (ARINC 429 Word bit düzeninde)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31] | PARITY_TYPE | RW | 0x1 | `o_tx_word_parity_type` | Parity tipi (1: Odd, 0: Even); parity bitini IP hesaplar |
| [30:29] | SSM | RW | 0x0 | `o_tx_word_ssm` | SSM (0-3) |
| [28:10] | DATA | RW | 0x0 | `o_tx_word_data` | Data (19-bit) |
| [9:8] | SDI | RW | 0x0 | `o_tx_word_sdi` | SDI (0-3) |
| [7:0] | LABEL_VAL | RW | 0x0 | `o_tx_word_label_val` | ARINC 429 Label (octal 000-377) |

### 0x408 TX_SEND_CMD

Tek gönderim darbesi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | SEND | PULSE | 0 | `o_tx_send_cmd_send` | Tek Word gönderim tetiği |

### 0x40C TX_EXT_DATA

Hazır 32-bit Word (BUILDER_EN=0)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_EXT_DATA | RW | 0x0 | `o_tx_ext_data` | Hazır 32-bit Word (BUILDER_EN=0) |

### 0x410 TX_EXT_LINE

Hat override (TRANSMITTER_EN=0): 10 HIGH, 01 LOW, 00 NULL, 11 HIGH-Z

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1] | LOW | RW | 0x0 | `o_tx_ext_line_low` | Hat override LOW çıkışı |
| [0] | HIGH | RW | 0x0 | `o_tx_ext_line_high` | Hat override HIGH çıkışı |

### 0x420 TX_INITIAL_DELAY

Scheduler başlangıç gecikmesi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_INITIAL_DELAY | RW | 0x0 | `o_tx_initial_delay` | Scheduler başlangıç gecikmesi (clk) |

### 0x424 TX_INTER_WORD_GAP

Scheduler Word arası ekstra bekleme (clk, >=1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_INTER_WORD_GAP | RW | 0x1 | `o_tx_inter_word_gap` | Scheduler Word arası ekstra bekleme (clk, >=1) |

### 0x440 TX_CFG

TX config seçimi ve uygulama

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [4] | APPLY | PULSE | 0 | `o_tx_cfg_apply` | Seçili TX config'i etkinleştir |
| [1:0] | SEL | RW | 0x0 | `o_tx_cfg_sel` | Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom) |

### 0x444 TX_CUST_TIMING

Custom bit zamanlaması

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_DUR | RW | 0x0 | `o_tx_cust_timing_null_dur` | Custom Null süresi (clk) |
| [15:0] | PULSE_DUR | RW | 0x0 | `o_tx_cust_timing_pulse_dur` | Custom Pulse süresi (clk) |

### 0x448 TX_CUST_GAP_DUR

Custom Word Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_CUST_GAP_DUR | RW | 0x0 | `o_tx_cust_gap_dur` | Custom Word Gap süresi (clk) |

### 0x44C TX_CUST_SLP

Custom SLP eğim çıkışı (1: HS, 0: LS)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_CUST_SLP | RW | 0x0 | `o_tx_cust_slp` | Custom SLP eğim çıkışı (1: HS, 0: LS) |

### 0x460 TX_ACT_TIMING

Aktif bit zamanlaması

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_DUR | RO | 0 | `i_tx_act_timing_null_dur` | Aktif Null süresi (clk) |
| [15:0] | PULSE_DUR | RO | 0 | `i_tx_act_timing_pulse_dur` | Aktif Pulse süresi (clk) |

### 0x464 TX_ACT_GAP_DUR

Aktif Word Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_ACT_GAP_DUR | RO | 0 | `i_tx_act_gap_dur` | Aktif Word Gap süresi (clk) |

### 0x468 TX_ACT_SLP

Aktif SLP eğim çıkışı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_ACT_SLP | RO | 0 | `i_tx_act_slp` | Aktif SLP eğim çıkışı |

### 0x480 TX_STATUS

TX durum register'ı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [3:2] | ACT_CFG | RO | 0 | `i_tx_status_act_cfg` | Aktif TX config modu (0:HS, 1:LS, 2:Custom) |
| [1] | SCHED_ACTIVE | RO | 0 | `i_tx_status_sched_active` | Scheduler aktif |
| [0] | BUSY | RO | 0 | `i_tx_status_busy` | TX gönderim yapıyor |

### 0x484 TX_WORD_CNT

Gönderilen toplam Word sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_WORD_CNT | RO | 0 | `i_tx_word_cnt` | Gönderilen toplam Word sayısı |

### 0x800 TB_CTRL

TB kanal kontrolü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [2] | CLEAR | PULSE | 0 | `o_tb_ctrl_clear` | Sayaç ve RAM pointer'larını temizle |
| [1] | FREEZE | RW | 0x0 | `o_tb_ctrl_freeze` | RAM okuma için dondur |
| [0] | ENABLE | RW | 0x0 | `o_tb_ctrl_enable` | Logger kayıt etkin (0 iken Word ve hata KAYDEDİLMEZ) |

### 0x804 TB_STATUS

TB kanal durumu ve hat teşhisi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [14] | SYNC_WAIT | RO | 0 | `i_tb_status_sync_wait` | Decoder hat senkronu bekliyor (en az 4 bit temiz NULL gerekli) |
| [13] | LINE_LOW | RO | 0 | `i_tb_status_line_low` | Hat anlık seviyesi: alıcı LOW çıkışı (senkronlanmış) |
| [12] | LINE_HIGH | RO | 0 | `i_tb_status_line_high` | Hat anlık seviyesi: alıcı HIGH çıkışı (senkronlanmış) |
| [9:8] | ACT_CFG | RO | 0 | `i_tb_status_act_cfg` | Aktif RX config modu (0:HS, 1:LS, 2:Custom) |
| [6] | ERR_WRAP | RO | 0 | `i_tb_status_err_wrap` | Error RAM taştı/döndü |
| [5] | WORD_WRAP | RO | 0 | `i_tb_status_word_wrap` | Word RAM taştı/döndü |
| [4] | FROZEN | RO | 0 | `i_tb_status_frozen` | Logger donduruldu |

### 0x808 TB_CFG

RX config seçimi ve uygulama

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [4] | APPLY | PULSE | 0 | `o_tb_cfg_apply` | Seçili config'i uygula |
| [1:0] | SEL | RW | 0x0 | `o_tb_cfg_sel` | Config seçimi (0: HS, 1: LS, 2: Custom) |

### 0x840 TB_CUST_PULSE

Custom pulse süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RW | 0x0 | `o_tb_cust_pulse_max` | Custom Max Pulse (clk) |
| [15:0] | MIN | RW | 0x0 | `o_tb_cust_pulse_min` | Custom Min Pulse (clk) |

### 0x844 TB_CUST_BIT

Custom bit süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RW | 0x0 | `o_tb_cust_bit_max` | Custom Max Bit (clk) |
| [15:0] | MIN | RW | 0x0 | `o_tb_cust_bit_min` | Custom Min Bit (clk) |

### 0x848 TB_CUST_NOISE

Custom pulse/null gürültü (glitch) limitleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_ERR | RW | 0x0 | `o_tb_cust_noise_null_err` | Custom Max Null Glitch Error |
| [15:0] | PULSE_ERR | RW | 0x0 | `o_tb_cust_noise_pulse_err` | Custom Max Pulse Glitch Error |

### 0x84C TB_CUST_FILTER

Custom glitch filtresi ve gap gürültü limiti

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | GAP_ERR | RW | 0x0 | `o_tb_cust_filter_gap_err` | Custom Max Gap Glitch Error |
| [15:0] | GLITCH_SIZE | RW | 0x0 | `o_tb_cust_filter_glitch_size` | Custom Glitch Filter boyu (clk) |

### 0x850 TB_CUST_PARITY

Custom Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TB_CUST_PARITY | RW | 0x1 | `o_tb_cust_parity` | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x860 TB_ACT_PULSE

Aktif pulse süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RO | 0 | `i_tb_act_pulse_max` | Aktif Max Pulse (clk) |
| [15:0] | MIN | RO | 0 | `i_tb_act_pulse_min` | Aktif Min Pulse (clk) |

### 0x864 TB_ACT_BIT

Aktif bit süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RO | 0 | `i_tb_act_bit_max` | Aktif Max Bit (clk) |
| [15:0] | MIN | RO | 0 | `i_tb_act_bit_min` | Aktif Min Bit (clk) |

### 0x868 TB_ACT_NOISE

Aktif pulse/null gürültü (glitch) limitleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_ERR | RO | 0 | `i_tb_act_noise_null_err` | Aktif Max Null Glitch Error |
| [15:0] | PULSE_ERR | RO | 0 | `i_tb_act_noise_pulse_err` | Aktif Max Pulse Glitch Error |

### 0x86C TB_ACT_FILTER

Aktif glitch filtresi ve gap gürültü limiti

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | GAP_ERR | RO | 0 | `i_tb_act_filter_gap_err` | Aktif Max Gap Glitch Error |
| [15:0] | GLITCH_SIZE | RO | 0 | `i_tb_act_filter_glitch_size` | Aktif Glitch Filter boyu (clk) |

### 0x870 TB_ACT_PARITY

Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TB_ACT_PARITY | RO | 0 | `i_tb_act_parity` | Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x8E0 TB_WORD_CNT

Geçerli Word sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_WORD_CNT | RO | 0 | `i_tb_word_cnt` | Geçerli Word sayısı |

### 0x8E4 TB_ERR_CNT

Hata kaydı sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_ERR_CNT | RO | 0 | `i_tb_err_cnt` | Hata kaydı sayısı |

### 0x8E8 TB_DROP_CNT

Freeze sırasında atılan kayıt sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_DROP_CNT | RO | 0 | `i_tb_drop_cnt` | Freeze sırasında atılan kayıt sayısı |

### 0x8EC TB_LAST_WORD

Alınan son geçerli Word

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_LAST_WORD | RO | 0 | `i_tb_last_word` | Alınan son geçerli Word |

### 0x900 TB_WORD_RADDR

Word RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [7:0] | TB_WORD_RADDR | RW | 0x0 | `o_tb_word_raddr` | Word RAM başlangıç okuma adresi (yazınca pointer yüklenir) |

Strobes: `o_tb_word_raddr_wr`

### 0x904 TB_WORD_RD_TS_MSB

Word kaydı Timestamp MSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_WORD_RD_TS_MSB | RO | 0 | `i_tb_word_rd_ts_msb` | Word kaydı Timestamp MSB |

### 0x908 TB_WORD_RD_TS_LSB

Word kaydı Timestamp LSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_WORD_RD_TS_LSB | RO | 0 | `i_tb_word_rd_ts_lsb` | Word kaydı Timestamp LSB |

### 0x90C TB_WORD_RD_DATA

Word kaydı 32-bit veri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_WORD_RD_DATA | RO | 0 | `i_tb_word_rd_data` | Word kaydı 32-bit veri |

### 0x910 TB_WORD_RD_GAP

Word kaydı önceki Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_WORD_RD_GAP | RO | 0 | `i_tb_word_rd_gap` | Word kaydı önceki Gap süresi (clk) |

### 0x914 TB_WORD_RD_GAP_ERR

Word kaydı Gap gürültü sayısı (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_WORD_RD_GAP_ERR | RO | 0 | `i_tb_word_rd_gap_err` | Word kaydı Gap gürültü sayısı (okununca pointer +1) |

Strobes: `o_tb_word_rd_gap_err_rd`

### 0x920 TB_ERR_RADDR

Error RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [7:0] | TB_ERR_RADDR | RW | 0x0 | `o_tb_err_raddr` | Error RAM başlangıç okuma adresi (yazınca pointer yüklenir) |

Strobes: `o_tb_err_raddr_wr`

### 0x924 TB_ERR_RD_TS_MSB

Error kaydı Timestamp MSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_ERR_RD_TS_MSB | RO | 0 | `i_tb_err_rd_ts_msb` | Error kaydı Timestamp MSB |

### 0x928 TB_ERR_RD_TS_LSB

Error kaydı Timestamp LSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_ERR_RD_TS_LSB | RO | 0 | `i_tb_err_rd_ts_lsb` | Error kaydı Timestamp LSB |

### 0x92C TB_ERR_RD_INFO

Error kaydı hata kodu ve konumu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ADDR | RO | 0 | `i_tb_err_rd_info_addr` | Konum: bit no / 32 = gap / FIFO adresi |
| [15:0] | CODE | RO | 0 | `i_tb_err_rd_info_code` | Hata kodu bitmask |

### 0x930 TB_ERR_RD_DATA

Error kaydı ölçüm/beklenen veri (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_ERR_RD_DATA | RO | 0 | `i_tb_err_rd_data` | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |

Strobes: `o_tb_err_rd_data_rd`

### 0x940 TB_BIT_RADDR

Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [10:8] | WORD_IDX | RW | 0x0 | `o_tb_bit_raddr_word_idx` | Bit Diagnostic Word indeksi |
| [4:0] | BIT_IDX | RW | 0x0 | `o_tb_bit_raddr_bit_idx` | Bit indeksi (0-31) |

Strobes: `o_tb_bit_raddr_wr`

### 0x944 TB_BIT_RD_PULSE

Bit Pulse süresi ve gürültüsü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ERR | RO | 0 | `i_tb_bit_rd_pulse_err` | Bit Pulse gürültü sayısı |
| [15:0] | DUR | RO | 0 | `i_tb_bit_rd_pulse_dur` | Bit Pulse süresi (clk) |

### 0x948 TB_BIT_RD_NULL

Bit Null süresi ve gürültüsü (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ERR | RO | 0 | `i_tb_bit_rd_null_err` | Bit Null gürültü sayısı |
| [15:0] | DUR | RO | 0 | `i_tb_bit_rd_null_dur` | Bit Null süresi (clk) |

Strobes: `o_tb_bit_rd_null_rd`

### 0x9C0 TB_CHK_CTRL

TX BIT Word Checker kontrol

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1] | CLEAR | PULSE | 0 | `o_tb_chk_ctrl_clear` | Checker FIFO ve sayaçlarını temizle |
| [0] | ENABLE | RW | 0x0 | `o_tb_chk_ctrl_enable` | Word Checker etkin |

### 0x9C4 TB_CHK_TIMEOUT

Echo zaman aşımı (clk, 0=kapalı)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_CHK_TIMEOUT | RW | 0x0 | `o_tb_chk_timeout` | Echo zaman aşımı (clk, 0=kapalı) |

### 0x9C8 TB_CHK_OK_CNT

Eşleşen Word sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_CHK_OK_CNT | RO | 0 | `i_tb_chk_ok_cnt` | Eşleşen Word sayısı |

### 0x9CC TB_CHK_ERR_CNT

Checker hata sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TB_CHK_ERR_CNT | RO | 0 | `i_tb_chk_err_cnt` | Checker hata sayısı |

### 0x9D0 TB_CHK_STATUS

TX BIT Checker FIFO durumu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [4] | FIFO_OVF | RO | 0 | `i_tb_chk_status_fifo_ovf` | FIFO taşma bayrağı |
| [3:0] | FIFO_LEVEL | RO | 0 | `i_tb_chk_status_fifo_level` | Beklenen Word FIFO doluluğu |

### 0x4000 RX0_CTRL

RX0 kanal kontrolü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [2] | CLEAR | PULSE | 0 | `o_rx0_ctrl_clear` | Sayaç ve RAM pointer'larını temizle |
| [1] | FREEZE | RW | 0x0 | `o_rx0_ctrl_freeze` | RAM okuma için dondur |
| [0] | ENABLE | RW | 0x0 | `o_rx0_ctrl_enable` | Logger kayıt etkin (0 iken Word ve hata KAYDEDİLMEZ) |

### 0x4004 RX0_STATUS

RX0 kanal durumu ve hat teşhisi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [14] | SYNC_WAIT | RO | 0 | `i_rx0_status_sync_wait` | Decoder hat senkronu bekliyor (en az 4 bit temiz NULL gerekli) |
| [13] | LINE_LOW | RO | 0 | `i_rx0_status_line_low` | Hat anlık seviyesi: alıcı LOW çıkışı (senkronlanmış) |
| [12] | LINE_HIGH | RO | 0 | `i_rx0_status_line_high` | Hat anlık seviyesi: alıcı HIGH çıkışı (senkronlanmış) |
| [9:8] | ACT_CFG | RO | 0 | `i_rx0_status_act_cfg` | Aktif RX config modu (0:HS, 1:LS, 2:Custom) |
| [6] | ERR_WRAP | RO | 0 | `i_rx0_status_err_wrap` | Error RAM taştı/döndü |
| [5] | WORD_WRAP | RO | 0 | `i_rx0_status_word_wrap` | Word RAM taştı/döndü |
| [4] | FROZEN | RO | 0 | `i_rx0_status_frozen` | Logger donduruldu |

### 0x4008 RX0_CFG

RX config seçimi ve uygulama

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [4] | APPLY | PULSE | 0 | `o_rx0_cfg_apply` | Seçili config'i uygula |
| [1:0] | SEL | RW | 0x0 | `o_rx0_cfg_sel` | Config seçimi (0: HS, 1: LS, 2: Custom) |

### 0x4040 RX0_CUST_PULSE

Custom pulse süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RW | 0x0 | `o_rx0_cust_pulse_max` | Custom Max Pulse (clk) |
| [15:0] | MIN | RW | 0x0 | `o_rx0_cust_pulse_min` | Custom Min Pulse (clk) |

### 0x4044 RX0_CUST_BIT

Custom bit süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RW | 0x0 | `o_rx0_cust_bit_max` | Custom Max Bit (clk) |
| [15:0] | MIN | RW | 0x0 | `o_rx0_cust_bit_min` | Custom Min Bit (clk) |

### 0x4048 RX0_CUST_NOISE

Custom pulse/null gürültü (glitch) limitleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_ERR | RW | 0x0 | `o_rx0_cust_noise_null_err` | Custom Max Null Glitch Error |
| [15:0] | PULSE_ERR | RW | 0x0 | `o_rx0_cust_noise_pulse_err` | Custom Max Pulse Glitch Error |

### 0x404C RX0_CUST_FILTER

Custom glitch filtresi ve gap gürültü limiti

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | GAP_ERR | RW | 0x0 | `o_rx0_cust_filter_gap_err` | Custom Max Gap Glitch Error |
| [15:0] | GLITCH_SIZE | RW | 0x0 | `o_rx0_cust_filter_glitch_size` | Custom Glitch Filter boyu (clk) |

### 0x4050 RX0_CUST_PARITY

Custom Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | RX0_CUST_PARITY | RW | 0x1 | `o_rx0_cust_parity` | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x4060 RX0_ACT_PULSE

Aktif pulse süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RO | 0 | `i_rx0_act_pulse_max` | Aktif Max Pulse (clk) |
| [15:0] | MIN | RO | 0 | `i_rx0_act_pulse_min` | Aktif Min Pulse (clk) |

### 0x4064 RX0_ACT_BIT

Aktif bit süre sınırları

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | MAX | RO | 0 | `i_rx0_act_bit_max` | Aktif Max Bit (clk) |
| [15:0] | MIN | RO | 0 | `i_rx0_act_bit_min` | Aktif Min Bit (clk) |

### 0x4068 RX0_ACT_NOISE

Aktif pulse/null gürültü (glitch) limitleri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | NULL_ERR | RO | 0 | `i_rx0_act_noise_null_err` | Aktif Max Null Glitch Error |
| [15:0] | PULSE_ERR | RO | 0 | `i_rx0_act_noise_pulse_err` | Aktif Max Pulse Glitch Error |

### 0x406C RX0_ACT_FILTER

Aktif glitch filtresi ve gap gürültü limiti

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | GAP_ERR | RO | 0 | `i_rx0_act_filter_gap_err` | Aktif Max Gap Glitch Error |
| [15:0] | GLITCH_SIZE | RO | 0 | `i_rx0_act_filter_glitch_size` | Aktif Glitch Filter boyu (clk) |

### 0x4070 RX0_ACT_PARITY

Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | RX0_ACT_PARITY | RO | 0 | `i_rx0_act_parity` | Aktif Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x40E0 RX0_WORD_CNT

Geçerli Word sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_WORD_CNT | RO | 0 | `i_rx0_word_cnt` | Geçerli Word sayısı |

### 0x40E4 RX0_ERR_CNT

Hata kaydı sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_ERR_CNT | RO | 0 | `i_rx0_err_cnt` | Hata kaydı sayısı |

### 0x40E8 RX0_DROP_CNT

Freeze sırasında atılan kayıt sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_DROP_CNT | RO | 0 | `i_rx0_drop_cnt` | Freeze sırasında atılan kayıt sayısı |

### 0x40EC RX0_LAST_WORD

Alınan son geçerli Word

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_LAST_WORD | RO | 0 | `i_rx0_last_word` | Alınan son geçerli Word |

### 0x4100 RX0_WORD_RADDR

Word RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [7:0] | RX0_WORD_RADDR | RW | 0x0 | `o_rx0_word_raddr` | Word RAM başlangıç okuma adresi (yazınca pointer yüklenir) |

Strobes: `o_rx0_word_raddr_wr`

### 0x4104 RX0_WORD_RD_TS_MSB

Word kaydı Timestamp MSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_WORD_RD_TS_MSB | RO | 0 | `i_rx0_word_rd_ts_msb` | Word kaydı Timestamp MSB |

### 0x4108 RX0_WORD_RD_TS_LSB

Word kaydı Timestamp LSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_WORD_RD_TS_LSB | RO | 0 | `i_rx0_word_rd_ts_lsb` | Word kaydı Timestamp LSB |

### 0x410C RX0_WORD_RD_DATA

Word kaydı 32-bit veri

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_WORD_RD_DATA | RO | 0 | `i_rx0_word_rd_data` | Word kaydı 32-bit veri |

### 0x4110 RX0_WORD_RD_GAP

Word kaydı önceki Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_WORD_RD_GAP | RO | 0 | `i_rx0_word_rd_gap` | Word kaydı önceki Gap süresi (clk) |

### 0x4114 RX0_WORD_RD_GAP_ERR

Word kaydı Gap gürültü sayısı (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_WORD_RD_GAP_ERR | RO | 0 | `i_rx0_word_rd_gap_err` | Word kaydı Gap gürültü sayısı (okununca pointer +1) |

Strobes: `o_rx0_word_rd_gap_err_rd`

### 0x4120 RX0_ERR_RADDR

Error RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [7:0] | RX0_ERR_RADDR | RW | 0x0 | `o_rx0_err_raddr` | Error RAM başlangıç okuma adresi (yazınca pointer yüklenir) |

Strobes: `o_rx0_err_raddr_wr`

### 0x4124 RX0_ERR_RD_TS_MSB

Error kaydı Timestamp MSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_ERR_RD_TS_MSB | RO | 0 | `i_rx0_err_rd_ts_msb` | Error kaydı Timestamp MSB |

### 0x4128 RX0_ERR_RD_TS_LSB

Error kaydı Timestamp LSB

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_ERR_RD_TS_LSB | RO | 0 | `i_rx0_err_rd_ts_lsb` | Error kaydı Timestamp LSB |

### 0x412C RX0_ERR_RD_INFO

Error kaydı hata kodu ve konumu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ADDR | RO | 0 | `i_rx0_err_rd_info_addr` | Konum: bit no / 32 = gap / FIFO adresi |
| [15:0] | CODE | RO | 0 | `i_rx0_err_rd_info_code` | Hata kodu bitmask |

### 0x4130 RX0_ERR_RD_DATA

Error kaydı ölçüm/beklenen veri (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | RX0_ERR_RD_DATA | RO | 0 | `i_rx0_err_rd_data` | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |

Strobes: `o_rx0_err_rd_data_rd`

### 0x4140 RX0_BIT_RADDR

Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [10:8] | WORD_IDX | RW | 0x0 | `o_rx0_bit_raddr_word_idx` | Bit Diagnostic Word indeksi |
| [4:0] | BIT_IDX | RW | 0x0 | `o_rx0_bit_raddr_bit_idx` | Bit indeksi (0-31) |

Strobes: `o_rx0_bit_raddr_wr`

### 0x4144 RX0_BIT_RD_PULSE

Bit Pulse süresi ve gürültüsü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ERR | RO | 0 | `i_rx0_bit_rd_pulse_err` | Bit Pulse gürültü sayısı |
| [15:0] | DUR | RO | 0 | `i_rx0_bit_rd_pulse_dur` | Bit Pulse süresi (clk) |

### 0x4148 RX0_BIT_RD_NULL

Bit Null süresi ve gürültüsü (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:16] | ERR | RO | 0 | `i_rx0_bit_rd_null_err` | Bit Null gürültü sayısı |
| [15:0] | DUR | RO | 0 | `i_rx0_bit_rd_null_dur` | Bit Null süresi (clk) |

Strobes: `o_rx0_bit_rd_null_rd`

## Field kinds

- **RW**: Control: written by the bus, output to the IP (o_)
- **RO**: Status: input from the IP (i_), read by the bus
- **PULSE**: Writing 1 gives a one-clock pulse (o_), reads 0
- **W1C**: IP event flag (i_ sets it), held, cleared by writing 1
- **CONST**: Constant value (ID, version), no port
