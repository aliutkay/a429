# arinc429_axil

IP version: `1.0.0`

ARINC 429 IP (1 RX, TX=Var, TX BIT=Var, 50 MHz)

Addresses below are offsets from the slave base address set on the interconnect.  
Decoded address bits: `[14:2]` (block repeats every 0x8000 bytes)

## Registers

| Offset | Register | Access | Reset | Description |
|---|---|---|---|---|
| 0x00 | IP_ID | RO | 0x41343239 | ARINC 429 IP kimliği ('A429') |
| 0x04 | IP_VERSION | RO | 0x00010000 | IP sürümü (1.0.0) |
| 0x08 | CAPS | RO | 0x00000B01 | Donanım yetenekleri |
| 0x0C | CAPS_MEM | RO | 0x00030808 | RAM derinlikleri |
| 0x10 | CLK_HZ | RO | 0x02FAF080 | IP sistem saati (Hz) |
| 0x20 | SOFT_RESET | WO | 0x00000000 | Yumuşak reset darbeleri (self-clearing) |
| 0x24 | GLOBAL_FREEZE | RW | 0x00000000 | Tüm logger'ları eşzamanlı dondur |
| 0x28 | TS_CTRL | RW | 0x00000001 | Timestamp kontrol |
| 0x2C | TS_LSB | RO | 0x00000000 | Timestamp alt 32 bit (okununca MSB latch'lenir) |
| 0x30 | TS_MSB | RO | 0x00000000 | Latch'lenmiş timestamp üst 32 bit |
| 0x400 | TX_TRANSMITTER_EN | RW | 0x00000000 | 1: Word Transmitter, 0: EXT_HIGH/LOW override |
| 0x404 | TX_MSG_SCHED_EN | RW | 0x00000000 | 1: Message Scheduler, 0: SEND_CMD tek gönderim |
| 0x408 | TX_BUILDER_EN | RW | 0x00000000 | 1: Word Builder alanları, 0: EXT_DATA |
| 0x40C | TX_LABEL | RW | 0x00000000 | ARINC 429 Label (octal 000-377) |
| 0x410 | TX_SDI | RW | 0x00000000 | SDI (0-3) |
| 0x414 | TX_DATA | RW | 0x00000000 | Data (19-bit) |
| 0x418 | TX_SSM | RW | 0x00000000 | SSM (0-3) |
| 0x41C | TX_PARITY_TYPE | RW | 0x00000001 | Parity tipi (1: Odd, 0: Even) |
| 0x420 | TX_SCHED_EN | RW | 0x00000000 | Message Scheduler başlat/durdur |
| 0x424 | TX_INITIAL_DELAY | RW | 0x00000000 | Scheduler başlangıç gecikmesi (clk) |
| 0x428 | TX_INTER_WORD_GAP | RW | 0x00000001 | Scheduler Word arası ekstra bekleme (clk, >=1) |
| 0x42C | TX_SEND_CMD | WO | 0x00000000 | Tek gönderim darbesi |
| 0x430 | TX_EXT_DATA | RW | 0x00000000 | Hazır 32-bit Word |
| 0x434 | TX_EXT_HIGH | RW | 0x00000000 | Hat override HIGH çıkışı |
| 0x438 | TX_EXT_LOW | RW | 0x00000000 | Hat override LOW çıkışı |
| 0x440 | TX_CFG_SEL | RW | 0x00000000 | Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom) |
| 0x444 | TX_CFG_APPLY | WO | 0x00000000 | TX Config uygula |
| 0x448 | TX_CUST_PULSE_DUR | RW | 0x00000000 | Custom Pulse süresi (clk) |
| 0x44C | TX_CUST_NULL_DUR | RW | 0x00000000 | Custom Null süresi (clk) |
| 0x450 | TX_CUST_GAP_DUR | RW | 0x00000000 | Custom Word Gap süresi (clk) |
| 0x454 | TX_CUST_SLP | RW | 0x00000000 | Custom SLP eğim çıkışı (1: HS, 0: LS) |
| 0x460 | TX_ACT_PULSE_DUR | RO | 0x00000000 | Aktif Pulse süresi (clk) |
| 0x464 | TX_ACT_NULL_DUR | RO | 0x00000000 | Aktif Null süresi (clk) |
| 0x468 | TX_ACT_GAP_DUR | RO | 0x00000000 | Aktif Word Gap süresi (clk) |
| 0x46C | TX_ACT_SLP | RO | 0x00000000 | Aktif SLP eğim çıkışı |
| 0x480 | TX_STATUS | RO | 0x00000000 | TX durum register'ı |
| 0x484 | TX_WORD_CNT | RO | 0x00000000 | Gönderilen toplam Word sayısı |
| 0x800 | TB_CTRL | RW | 0x00000000 | TB_ kanal kontrolü |
| 0x804 | TB_STATUS | RO | 0x00000000 | TB_ kanal durumu |
| 0x808 | TB_CFG_SEL | RW | 0x00000000 | Config seçimi (0: HS, 1: LS, 2: Custom) |
| 0x80C | TB_CFG_APPLY | WO | 0x00000000 | RX Config uygula |
| 0x840 | TB_CUST_GLITCH_FILTER_SIZE | RW | 0x00000000 | Custom Glitch Filter boyu (clk) |
| 0x844 | TB_CUST_MIN_PULSE | RW | 0x00000000 | Custom Min Pulse (clk) |
| 0x848 | TB_CUST_MAX_PULSE | RW | 0x00000000 | Custom Max Pulse (clk) |
| 0x84C | TB_CUST_MIN_BIT | RW | 0x00000000 | Custom Min Bit (clk) |
| 0x850 | TB_CUST_MAX_BIT | RW | 0x00000000 | Custom Max Bit (clk) |
| 0x854 | TB_CUST_MAX_PULSE_ERR | RW | 0x00000000 | Custom Max Pulse Glitch Error |
| 0x858 | TB_CUST_MAX_NULL_ERR | RW | 0x00000000 | Custom Max Null Glitch Error |
| 0x85C | TB_CUST_MAX_GAP_ERR | RW | 0x00000000 | Custom Max Gap Glitch Error |
| 0x860 | TB_CUST_PARITY_MODE | RW | 0x00000001 | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x8A0 | TB_ACT_GLITCH_FILTER_SIZE | RO | 0x00000000 | Aktif Glitch Filter boyu (clk) |
| 0x8A4 | TB_ACT_MIN_PULSE | RO | 0x00000000 | Aktif Min Pulse (clk) |
| 0x8A8 | TB_ACT_MAX_PULSE | RO | 0x00000000 | Aktif Max Pulse (clk) |
| 0x8AC | TB_ACT_MIN_BIT | RO | 0x00000000 | Aktif Min Bit (clk) |
| 0x8B0 | TB_ACT_MAX_BIT | RO | 0x00000000 | Aktif Max Bit (clk) |
| 0x8B4 | TB_ACT_MAX_PULSE_ERR | RO | 0x00000000 | Aktif Max Pulse Glitch Error |
| 0x8B8 | TB_ACT_MAX_NULL_ERR | RO | 0x00000000 | Aktif Max Null Glitch Error |
| 0x8BC | TB_ACT_MAX_GAP_ERR | RO | 0x00000000 | Aktif Max Gap Glitch Error |
| 0x8C0 | TB_ACT_PARITY_MODE | RO | 0x00000000 | Aktif Parity modu |
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
| 0x92C | TB_ERR_RD_CODE | RO | 0x00000000 | Error kaydı hata kodu bitmask |
| 0x930 | TB_ERR_RD_ADDR | RO | 0x00000000 | Error kaydı konum/bit/FIFO adresi |
| 0x934 | TB_ERR_RD_DATA | RO | 0x00000000 | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |
| 0x940 | TB_BIT_RADDR | RW | 0x00000000 | Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x944 | TB_BIT_RD_PULSE | RO | 0x00000000 | Bit Pulse süresi (clk) |
| 0x948 | TB_BIT_RD_PULSE_ERR | RO | 0x00000000 | Bit Pulse gürültü sayısı |
| 0x94C | TB_BIT_RD_NULL | RO | 0x00000000 | Bit Null süresi (clk) |
| 0x950 | TB_BIT_RD_NULL_ERR | RO | 0x00000000 | Bit Null gürültü sayısı (okununca pointer +1) |
| 0x9C0 | TB_CHK_CTRL | RW | 0x00000000 | TX BIT Word Checker kontrol |
| 0x9C4 | TB_CHK_TIMEOUT | RW | 0x00000000 | Echo zaman aşımı (clk, 0=kapalı) |
| 0x9C8 | TB_CHK_OK_CNT | RO | 0x00000000 | Eşleşen Word sayısı |
| 0x9CC | TB_CHK_ERR_CNT | RO | 0x00000000 | Checker hata sayısı |
| 0x9D0 | TB_CHK_STATUS | RO | 0x00000000 | TX BIT Checker FIFO durumu |
| 0x4000 | RX0_CTRL | RW | 0x00000000 | RX0_ kanal kontrolü |
| 0x4004 | RX0_STATUS | RO | 0x00000000 | RX0_ kanal durumu |
| 0x4008 | RX0_CFG_SEL | RW | 0x00000000 | Config seçimi (0: HS, 1: LS, 2: Custom) |
| 0x400C | RX0_CFG_APPLY | WO | 0x00000000 | RX Config uygula |
| 0x4040 | RX0_CUST_GLITCH_FILTER_SIZE | RW | 0x00000000 | Custom Glitch Filter boyu (clk) |
| 0x4044 | RX0_CUST_MIN_PULSE | RW | 0x00000000 | Custom Min Pulse (clk) |
| 0x4048 | RX0_CUST_MAX_PULSE | RW | 0x00000000 | Custom Max Pulse (clk) |
| 0x404C | RX0_CUST_MIN_BIT | RW | 0x00000000 | Custom Min Bit (clk) |
| 0x4050 | RX0_CUST_MAX_BIT | RW | 0x00000000 | Custom Max Bit (clk) |
| 0x4054 | RX0_CUST_MAX_PULSE_ERR | RW | 0x00000000 | Custom Max Pulse Glitch Error |
| 0x4058 | RX0_CUST_MAX_NULL_ERR | RW | 0x00000000 | Custom Max Null Glitch Error |
| 0x405C | RX0_CUST_MAX_GAP_ERR | RW | 0x00000000 | Custom Max Gap Glitch Error |
| 0x4060 | RX0_CUST_PARITY_MODE | RW | 0x00000001 | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |
| 0x40A0 | RX0_ACT_GLITCH_FILTER_SIZE | RO | 0x00000000 | Aktif Glitch Filter boyu (clk) |
| 0x40A4 | RX0_ACT_MIN_PULSE | RO | 0x00000000 | Aktif Min Pulse (clk) |
| 0x40A8 | RX0_ACT_MAX_PULSE | RO | 0x00000000 | Aktif Max Pulse (clk) |
| 0x40AC | RX0_ACT_MIN_BIT | RO | 0x00000000 | Aktif Min Bit (clk) |
| 0x40B0 | RX0_ACT_MAX_BIT | RO | 0x00000000 | Aktif Max Bit (clk) |
| 0x40B4 | RX0_ACT_MAX_PULSE_ERR | RO | 0x00000000 | Aktif Max Pulse Glitch Error |
| 0x40B8 | RX0_ACT_MAX_NULL_ERR | RO | 0x00000000 | Aktif Max Null Glitch Error |
| 0x40BC | RX0_ACT_MAX_GAP_ERR | RO | 0x00000000 | Aktif Max Gap Glitch Error |
| 0x40C0 | RX0_ACT_PARITY_MODE | RO | 0x00000000 | Aktif Parity modu |
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
| 0x412C | RX0_ERR_RD_CODE | RO | 0x00000000 | Error kaydı hata kodu bitmask |
| 0x4130 | RX0_ERR_RD_ADDR | RO | 0x00000000 | Error kaydı konum/bit/FIFO adresi |
| 0x4134 | RX0_ERR_RD_DATA | RO | 0x00000000 | Error kaydı ölçüm/beklenen veri (okununca pointer +1) |
| 0x4140 | RX0_BIT_RADDR | RW | 0x00000000 | Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir) |
| 0x4144 | RX0_BIT_RD_PULSE | RO | 0x00000000 | Bit Pulse süresi (clk) |
| 0x4148 | RX0_BIT_RD_PULSE_ERR | RO | 0x00000000 | Bit Pulse gürültü sayısı |
| 0x414C | RX0_BIT_RD_NULL | RO | 0x00000000 | Bit Null süresi (clk) |
| 0x4150 | RX0_BIT_RD_NULL_ERR | RO | 0x00000000 | Bit Null gürültü sayısı (okununca pointer +1) |

### 0x00 IP_ID

ARINC 429 IP kimliği ('A429')

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | IP_ID | CONST | 0x41343239 | `—` | ARINC 429 IP kimliği ('A429') |

### 0x04 IP_VERSION

IP sürümü (1.0.0)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | IP_VERSION | CONST | 0x10000 | `—` | IP sürümü (1.0.0) |

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

### 0x400 TX_TRANSMITTER_EN

1: Word Transmitter, 0: EXT_HIGH/LOW override

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_TRANSMITTER_EN | RW | 0x0 | `o_tx_transmitter_en` | 1: Word Transmitter, 0: EXT_HIGH/LOW override |

### 0x404 TX_MSG_SCHED_EN

1: Message Scheduler, 0: SEND_CMD tek gönderim

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_MSG_SCHED_EN | RW | 0x0 | `o_tx_msg_sched_en` | 1: Message Scheduler, 0: SEND_CMD tek gönderim |

### 0x408 TX_BUILDER_EN

1: Word Builder alanları, 0: EXT_DATA

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_BUILDER_EN | RW | 0x0 | `o_tx_builder_en` | 1: Word Builder alanları, 0: EXT_DATA |

### 0x40C TX_LABEL

ARINC 429 Label (octal 000-377)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [7:0] | TX_LABEL | RW | 0x0 | `o_tx_label` | ARINC 429 Label (octal 000-377) |

### 0x410 TX_SDI

SDI (0-3)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TX_SDI | RW | 0x0 | `o_tx_sdi` | SDI (0-3) |

### 0x414 TX_DATA

Data (19-bit)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [18:0] | TX_DATA | RW | 0x0 | `o_tx_data` | Data (19-bit) |

### 0x418 TX_SSM

SSM (0-3)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TX_SSM | RW | 0x0 | `o_tx_ssm` | SSM (0-3) |

### 0x41C TX_PARITY_TYPE

Parity tipi (1: Odd, 0: Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_PARITY_TYPE | RW | 0x1 | `o_tx_parity_type` | Parity tipi (1: Odd, 0: Even) |

### 0x420 TX_SCHED_EN

Message Scheduler başlat/durdur

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_SCHED_EN | RW | 0x0 | `o_tx_sched_en` | Message Scheduler başlat/durdur |

### 0x424 TX_INITIAL_DELAY

Scheduler başlangıç gecikmesi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_INITIAL_DELAY | RW | 0x0 | `o_tx_initial_delay` | Scheduler başlangıç gecikmesi (clk) |

### 0x428 TX_INTER_WORD_GAP

Scheduler Word arası ekstra bekleme (clk, >=1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_INTER_WORD_GAP | RW | 0x1 | `o_tx_inter_word_gap` | Scheduler Word arası ekstra bekleme (clk, >=1) |

### 0x42C TX_SEND_CMD

Tek gönderim darbesi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | SEND | PULSE | 0 | `o_tx_send_cmd_send` | Tek Word gönderim tetiği |

### 0x430 TX_EXT_DATA

Hazır 32-bit Word

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_EXT_DATA | RW | 0x0 | `o_tx_ext_data` | Hazır 32-bit Word |

### 0x434 TX_EXT_HIGH

Hat override HIGH çıkışı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_EXT_HIGH | RW | 0x0 | `o_tx_ext_high` | Hat override HIGH çıkışı |

### 0x438 TX_EXT_LOW

Hat override LOW çıkışı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_EXT_LOW | RW | 0x0 | `o_tx_ext_low` | Hat override LOW çıkışı |

### 0x440 TX_CFG_SEL

Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TX_CFG_SEL | RW | 0x0 | `o_tx_cfg_sel` | Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom) |

### 0x444 TX_CFG_APPLY

TX Config uygula

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | APPLY | PULSE | 0 | `o_tx_cfg_apply_apply` | Seçili TX config'i etkinleştir |

### 0x448 TX_CUST_PULSE_DUR

Custom Pulse süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TX_CUST_PULSE_DUR | RW | 0x0 | `o_tx_cust_pulse_dur` | Custom Pulse süresi (clk) |

### 0x44C TX_CUST_NULL_DUR

Custom Null süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TX_CUST_NULL_DUR | RW | 0x0 | `o_tx_cust_null_dur` | Custom Null süresi (clk) |

### 0x450 TX_CUST_GAP_DUR

Custom Word Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_CUST_GAP_DUR | RW | 0x0 | `o_tx_cust_gap_dur` | Custom Word Gap süresi (clk) |

### 0x454 TX_CUST_SLP

Custom SLP eğim çıkışı (1: HS, 0: LS)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | TX_CUST_SLP | RW | 0x0 | `o_tx_cust_slp` | Custom SLP eğim çıkışı (1: HS, 0: LS) |

### 0x460 TX_ACT_PULSE_DUR

Aktif Pulse süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TX_ACT_PULSE_DUR | RO | 0 | `i_tx_act_pulse_dur` | Aktif Pulse süresi (clk) |

### 0x464 TX_ACT_NULL_DUR

Aktif Null süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TX_ACT_NULL_DUR | RO | 0 | `i_tx_act_null_dur` | Aktif Null süresi (clk) |

### 0x468 TX_ACT_GAP_DUR

Aktif Word Gap süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [31:0] | TX_ACT_GAP_DUR | RO | 0 | `i_tx_act_gap_dur` | Aktif Word Gap süresi (clk) |

### 0x46C TX_ACT_SLP

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

TB_ kanal kontrolü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [2] | CLEAR | PULSE | 0 | `o_tb_ctrl_clear` | Sayaç ve RAM pointer'larını temizle |
| [1] | FREEZE | RW | 0x0 | `o_tb_ctrl_freeze` | RAM okuma için dondur |
| [0] | ENABLE | RW | 0x0 | `o_tb_ctrl_enable` | Logger kayıt etkin |

### 0x804 TB_STATUS

TB_ kanal durumu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [9:8] | ACT_CFG | RO | 0 | `i_tb_status_act_cfg` | Aktif RX config modu (0:HS, 1:LS, 2:Custom) |
| [6] | ERR_WRAP | RO | 0 | `i_tb_status_err_wrap` | Error RAM taştı/döndü |
| [5] | WORD_WRAP | RO | 0 | `i_tb_status_word_wrap` | Word RAM taştı/döndü |
| [4] | FROZEN | RO | 0 | `i_tb_status_frozen` | Logger donduruldu |

### 0x808 TB_CFG_SEL

Config seçimi (0: HS, 1: LS, 2: Custom)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TB_CFG_SEL | RW | 0x0 | `o_tb_cfg_sel` | Config seçimi (0: HS, 1: LS, 2: Custom) |

### 0x80C TB_CFG_APPLY

RX Config uygula

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | APPLY | PULSE | 0 | `o_tb_cfg_apply_apply` | Seçili RX config'i uygula |

### 0x840 TB_CUST_GLITCH_FILTER_SIZE

Custom Glitch Filter boyu (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_GLITCH_FILTER_SIZE | RW | 0x0 | `o_tb_cust_glitch_filter_size` | Custom Glitch Filter boyu (clk) |

### 0x844 TB_CUST_MIN_PULSE

Custom Min Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MIN_PULSE | RW | 0x0 | `o_tb_cust_min_pulse` | Custom Min Pulse (clk) |

### 0x848 TB_CUST_MAX_PULSE

Custom Max Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MAX_PULSE | RW | 0x0 | `o_tb_cust_max_pulse` | Custom Max Pulse (clk) |

### 0x84C TB_CUST_MIN_BIT

Custom Min Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MIN_BIT | RW | 0x0 | `o_tb_cust_min_bit` | Custom Min Bit (clk) |

### 0x850 TB_CUST_MAX_BIT

Custom Max Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MAX_BIT | RW | 0x0 | `o_tb_cust_max_bit` | Custom Max Bit (clk) |

### 0x854 TB_CUST_MAX_PULSE_ERR

Custom Max Pulse Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MAX_PULSE_ERR | RW | 0x0 | `o_tb_cust_max_pulse_err` | Custom Max Pulse Glitch Error |

### 0x858 TB_CUST_MAX_NULL_ERR

Custom Max Null Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MAX_NULL_ERR | RW | 0x0 | `o_tb_cust_max_null_err` | Custom Max Null Glitch Error |

### 0x85C TB_CUST_MAX_GAP_ERR

Custom Max Gap Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_CUST_MAX_GAP_ERR | RW | 0x0 | `o_tb_cust_max_gap_err` | Custom Max Gap Glitch Error |

### 0x860 TB_CUST_PARITY_MODE

Custom Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TB_CUST_PARITY_MODE | RW | 0x1 | `o_tb_cust_parity_mode` | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x8A0 TB_ACT_GLITCH_FILTER_SIZE

Aktif Glitch Filter boyu (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_GLITCH_FILTER_SIZE | RO | 0 | `i_tb_act_glitch_filter_size` | Aktif Glitch Filter boyu (clk) |

### 0x8A4 TB_ACT_MIN_PULSE

Aktif Min Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MIN_PULSE | RO | 0 | `i_tb_act_min_pulse` | Aktif Min Pulse (clk) |

### 0x8A8 TB_ACT_MAX_PULSE

Aktif Max Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MAX_PULSE | RO | 0 | `i_tb_act_max_pulse` | Aktif Max Pulse (clk) |

### 0x8AC TB_ACT_MIN_BIT

Aktif Min Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MIN_BIT | RO | 0 | `i_tb_act_min_bit` | Aktif Min Bit (clk) |

### 0x8B0 TB_ACT_MAX_BIT

Aktif Max Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MAX_BIT | RO | 0 | `i_tb_act_max_bit` | Aktif Max Bit (clk) |

### 0x8B4 TB_ACT_MAX_PULSE_ERR

Aktif Max Pulse Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MAX_PULSE_ERR | RO | 0 | `i_tb_act_max_pulse_err` | Aktif Max Pulse Glitch Error |

### 0x8B8 TB_ACT_MAX_NULL_ERR

Aktif Max Null Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MAX_NULL_ERR | RO | 0 | `i_tb_act_max_null_err` | Aktif Max Null Glitch Error |

### 0x8BC TB_ACT_MAX_GAP_ERR

Aktif Max Gap Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ACT_MAX_GAP_ERR | RO | 0 | `i_tb_act_max_gap_err` | Aktif Max Gap Glitch Error |

### 0x8C0 TB_ACT_PARITY_MODE

Aktif Parity modu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | TB_ACT_PARITY_MODE | RO | 0 | `i_tb_act_parity_mode` | Aktif Parity modu |

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

### 0x92C TB_ERR_RD_CODE

Error kaydı hata kodu bitmask

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ERR_RD_CODE | RO | 0 | `i_tb_err_rd_code` | Error kaydı hata kodu bitmask |

### 0x930 TB_ERR_RD_ADDR

Error kaydı konum/bit/FIFO adresi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_ERR_RD_ADDR | RO | 0 | `i_tb_err_rd_addr` | Error kaydı konum/bit/FIFO adresi |

### 0x934 TB_ERR_RD_DATA

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

Bit Pulse süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_BIT_RD_PULSE | RO | 0 | `i_tb_bit_rd_pulse` | Bit Pulse süresi (clk) |

### 0x948 TB_BIT_RD_PULSE_ERR

Bit Pulse gürültü sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_BIT_RD_PULSE_ERR | RO | 0 | `i_tb_bit_rd_pulse_err` | Bit Pulse gürültü sayısı |

### 0x94C TB_BIT_RD_NULL

Bit Null süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_BIT_RD_NULL | RO | 0 | `i_tb_bit_rd_null` | Bit Null süresi (clk) |

### 0x950 TB_BIT_RD_NULL_ERR

Bit Null gürültü sayısı (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | TB_BIT_RD_NULL_ERR | RO | 0 | `i_tb_bit_rd_null_err` | Bit Null gürültü sayısı (okununca pointer +1) |

Strobes: `o_tb_bit_rd_null_err_rd`

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

RX0_ kanal kontrolü

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [2] | CLEAR | PULSE | 0 | `o_rx0_ctrl_clear` | Sayaç ve RAM pointer'larını temizle |
| [1] | FREEZE | RW | 0x0 | `o_rx0_ctrl_freeze` | RAM okuma için dondur |
| [0] | ENABLE | RW | 0x0 | `o_rx0_ctrl_enable` | Logger kayıt etkin |

### 0x4004 RX0_STATUS

RX0_ kanal durumu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [9:8] | ACT_CFG | RO | 0 | `i_rx0_status_act_cfg` | Aktif RX config modu (0:HS, 1:LS, 2:Custom) |
| [6] | ERR_WRAP | RO | 0 | `i_rx0_status_err_wrap` | Error RAM taştı/döndü |
| [5] | WORD_WRAP | RO | 0 | `i_rx0_status_word_wrap` | Word RAM taştı/döndü |
| [4] | FROZEN | RO | 0 | `i_rx0_status_frozen` | Logger donduruldu |

### 0x4008 RX0_CFG_SEL

Config seçimi (0: HS, 1: LS, 2: Custom)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | RX0_CFG_SEL | RW | 0x0 | `o_rx0_cfg_sel` | Config seçimi (0: HS, 1: LS, 2: Custom) |

### 0x400C RX0_CFG_APPLY

RX Config uygula

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [0] | APPLY | PULSE | 0 | `o_rx0_cfg_apply_apply` | Seçili RX config'i uygula |

### 0x4040 RX0_CUST_GLITCH_FILTER_SIZE

Custom Glitch Filter boyu (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_GLITCH_FILTER_SIZE | RW | 0x0 | `o_rx0_cust_glitch_filter_size` | Custom Glitch Filter boyu (clk) |

### 0x4044 RX0_CUST_MIN_PULSE

Custom Min Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MIN_PULSE | RW | 0x0 | `o_rx0_cust_min_pulse` | Custom Min Pulse (clk) |

### 0x4048 RX0_CUST_MAX_PULSE

Custom Max Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MAX_PULSE | RW | 0x0 | `o_rx0_cust_max_pulse` | Custom Max Pulse (clk) |

### 0x404C RX0_CUST_MIN_BIT

Custom Min Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MIN_BIT | RW | 0x0 | `o_rx0_cust_min_bit` | Custom Min Bit (clk) |

### 0x4050 RX0_CUST_MAX_BIT

Custom Max Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MAX_BIT | RW | 0x0 | `o_rx0_cust_max_bit` | Custom Max Bit (clk) |

### 0x4054 RX0_CUST_MAX_PULSE_ERR

Custom Max Pulse Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MAX_PULSE_ERR | RW | 0x0 | `o_rx0_cust_max_pulse_err` | Custom Max Pulse Glitch Error |

### 0x4058 RX0_CUST_MAX_NULL_ERR

Custom Max Null Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MAX_NULL_ERR | RW | 0x0 | `o_rx0_cust_max_null_err` | Custom Max Null Glitch Error |

### 0x405C RX0_CUST_MAX_GAP_ERR

Custom Max Gap Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_CUST_MAX_GAP_ERR | RW | 0x0 | `o_rx0_cust_max_gap_err` | Custom Max Gap Glitch Error |

### 0x4060 RX0_CUST_PARITY_MODE

Custom Parity modu (0:Kapalı, 1:Odd, 2:Even)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | RX0_CUST_PARITY_MODE | RW | 0x1 | `o_rx0_cust_parity_mode` | Custom Parity modu (0:Kapalı, 1:Odd, 2:Even) |

### 0x40A0 RX0_ACT_GLITCH_FILTER_SIZE

Aktif Glitch Filter boyu (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_GLITCH_FILTER_SIZE | RO | 0 | `i_rx0_act_glitch_filter_size` | Aktif Glitch Filter boyu (clk) |

### 0x40A4 RX0_ACT_MIN_PULSE

Aktif Min Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MIN_PULSE | RO | 0 | `i_rx0_act_min_pulse` | Aktif Min Pulse (clk) |

### 0x40A8 RX0_ACT_MAX_PULSE

Aktif Max Pulse (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MAX_PULSE | RO | 0 | `i_rx0_act_max_pulse` | Aktif Max Pulse (clk) |

### 0x40AC RX0_ACT_MIN_BIT

Aktif Min Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MIN_BIT | RO | 0 | `i_rx0_act_min_bit` | Aktif Min Bit (clk) |

### 0x40B0 RX0_ACT_MAX_BIT

Aktif Max Bit (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MAX_BIT | RO | 0 | `i_rx0_act_max_bit` | Aktif Max Bit (clk) |

### 0x40B4 RX0_ACT_MAX_PULSE_ERR

Aktif Max Pulse Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MAX_PULSE_ERR | RO | 0 | `i_rx0_act_max_pulse_err` | Aktif Max Pulse Glitch Error |

### 0x40B8 RX0_ACT_MAX_NULL_ERR

Aktif Max Null Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MAX_NULL_ERR | RO | 0 | `i_rx0_act_max_null_err` | Aktif Max Null Glitch Error |

### 0x40BC RX0_ACT_MAX_GAP_ERR

Aktif Max Gap Glitch Error

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ACT_MAX_GAP_ERR | RO | 0 | `i_rx0_act_max_gap_err` | Aktif Max Gap Glitch Error |

### 0x40C0 RX0_ACT_PARITY_MODE

Aktif Parity modu

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [1:0] | RX0_ACT_PARITY_MODE | RO | 0 | `i_rx0_act_parity_mode` | Aktif Parity modu |

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

### 0x412C RX0_ERR_RD_CODE

Error kaydı hata kodu bitmask

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ERR_RD_CODE | RO | 0 | `i_rx0_err_rd_code` | Error kaydı hata kodu bitmask |

### 0x4130 RX0_ERR_RD_ADDR

Error kaydı konum/bit/FIFO adresi

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_ERR_RD_ADDR | RO | 0 | `i_rx0_err_rd_addr` | Error kaydı konum/bit/FIFO adresi |

### 0x4134 RX0_ERR_RD_DATA

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

Bit Pulse süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_BIT_RD_PULSE | RO | 0 | `i_rx0_bit_rd_pulse` | Bit Pulse süresi (clk) |

### 0x4148 RX0_BIT_RD_PULSE_ERR

Bit Pulse gürültü sayısı

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_BIT_RD_PULSE_ERR | RO | 0 | `i_rx0_bit_rd_pulse_err` | Bit Pulse gürültü sayısı |

### 0x414C RX0_BIT_RD_NULL

Bit Null süresi (clk)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_BIT_RD_NULL | RO | 0 | `i_rx0_bit_rd_null` | Bit Null süresi (clk) |

### 0x4150 RX0_BIT_RD_NULL_ERR

Bit Null gürültü sayısı (okununca pointer +1)

| Bits | Field | Kind | Reset | Port | Description |
|---|---|---|---|---|---|
| [15:0] | RX0_BIT_RD_NULL_ERR | RO | 0 | `i_rx0_bit_rd_null_err` | Bit Null gürültü sayısı (okununca pointer +1) |

Strobes: `o_rx0_bit_rd_null_err_rd`

## Field kinds

- **RW**: Control: written by the bus, output to the IP (o_)
- **RO**: Status: input from the IP (i_), read by the bus
- **PULSE**: Writing 1 gives a one-clock pulse (o_), reads 0
- **W1C**: IP event flag (i_ sets it), held, cleared by writing 1
- **CONST**: Constant value (ID, version), no port
