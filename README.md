# ARINC 429 Test Aracı (AXIL Studio IP Arayüzü · PySide6/Qt)

[AXIL Studio](https://github.com/aliutkay/axil-studio) **UART-to-AXI Debug Bridge** üzerinden çalışan
ARINC 429 IP test ve analiz uygulaması. Config hesaplama, IP register yazma/okuma, Word / Bit Diagnostic /
Error çözümleme, dalga formu grafikleri, TX canlı kontrol ve proje dosyaları tek arayüzdedir.

Seri port bağlantısı ve register erişimi tamamen **AXIL Studio Debug Bridge** üzerinden yapılır; uygulama
kendi seri portunu açmaz. Studio olmadan açıldığında **çevrimdışı modda** (Config hesabı ve kayıtlı
okumaları inceleme) çalışır.

## Kurulum

1. AXIL Studio'nun çalıştığı Python ortamına `matplotlib` kurun (`PySide6` AXIL Studio ile zaten kuruludur):
   ```bash
   pip install -r requirements.txt
   ```
2. **IP kütüphanesi (önerilen):** AXIL Studio → **IP Library** → *Kütüphaneler* → bu reponun kökündeki
   `arinc429.axlib.json` dosyasını açın. Kütüphanede `ARINC429` IP'si (sürüm `2.0.0`, 93 register,
   *IP arayüzü* `arinc429`, Wrapper için tam `regspec`) bulunur; *Projeye al* / *Adres haritasına ekle* ile
   projeye yerleştirin. Kütüphane `axil-interface.json` ile aynı klasörde olduğundan Debug Bridge arayüzü
   ek ayar olmadan bulur.
   - Alternatif: Debug Bridge → *Debug* menüsü → *IP arayüzü klasörleri…* bölümüne bu reponun klasörünü
     ekleyin ve Register Map Editor'da IP'nin *IP arayüzü* (`panel`) alanına `arinc429` yazın.
   - Kütüphane, register haritasıyla birlikte `python3 vhdl/scripts/gen_axil_spec.py` ile yeniden üretilir
     (`--library` ile yol değiştirilebilir).
3. Debug Bridge'de IP seçilince **ARINC 429 arayüzü** düğmesi görünür.

### Bağımsız / Simülatör çalıştırma

- Çevrimdışı mod (yalnızca hesap ve kayıtlı okumalar):
  ```bash
  python main.py
  ```
- Dahili IP simülatörüyle deneme (donanım ve Studio olmadan):
  ```bash
  python main.py --sim
  ```
- Gerçek RTL eş-simülasyonuyla (TX → RX0 loopback; `ghdl` + `verilator` ya da `iverilog` gerekli):
  ```bash
  python main.py --cosim
  ```

## Sekmeler

| Sekme | İçerik |
|---|---|
| **Config** | Sol panelde **Genel** (System Clock, ±ppm), **RX Config** (ARINC 429 profili, Receiver entegresi, FPGA giriş standardı, Glitch Filter ve limitler, test toleransı, örnek dalga formu / tek bit grafikleri) ve **TX Config** (ARINC 429 profili). Sağda **RX / TX** alt sekmeleri: kontroller, ara hesaplar (çift tık → formül), hesaplanan register değerleri, panoya kopyalama ve **Debug Bridge config listesine ekle**. |
| **Kontrol** | Okunacak RX verileri (Word / Error / Bit Diagnostic: Tümü / Son N / Okunmasın), okuma ve yazma dosyası ayarları, IP/kanal harita durumu; sağda **RX İşlemleri** (**RX Config gönder**, **RX verilerini oku**, **Config + oku**), **TX İşlemleri** (**TX Config gönder**, **TX Canlı Kontrol…**), **IP Kontrol** (**IP reset**, **Durdur**), ilerleme çubuğu ve **İşlem Logu**. |
| **RX Okunan Veriler** | Word Listesi, Word Dalga Formu, Bit Diagnostic, Error Listesi, İstatistik ve tutarlılık kontrolleri. PASS/FAIL hücre renklendirmesi (neden için üzerine gelin veya sağ tıklayın). Word satırına çift tık → dalga formu. |
| **Test** | TX → RX loopback otomatik testi (aşağıda **Test (Loopback) menüsü**). |
| **TX Gönderilen Veriler** | TX Canlı Kontrol gönderim geçmişi (filtreleme, CSV dışa aktarma, projeyle kayıt) ve **TX Built-In Test (TX BIT · Wraparound Checker)** canlı sayaçları (`TX_WORD_CNT`, `TB_WORD_CNT`, `CHK_OK_CNT`, `CHK_ERR_CNT`, FIFO), Checker kontrolü ve tek tıkla `TB_` okuması. |

Üst başlık çubuğundan hedef kanal (`RX0`…`RXn`, `TX BIT`) seçilir.

## Test (Loopback) menüsü

**Test** sekmesi ARINC 429 IP'sini ve hat entegrelerini (line driver / line receiver) birlikte otomatik test eder.
Kartın ARINC **TX** çıkışını dışarıdan test edilecek **RX** girişlerine bağlayın (loopback) ve bu RX'leri
işaretleyin; **TX BIT** kanalı TX hattını kart üzerindeki kendi alıcısıyla dinler ve Word Checker yankıyı karşılaştırır.

| Test | Ne doğrular |
|---|---|
| Bağlantı ve IP kimliği, Hazırlık | `IP_ID`, sürüm, `CAPS`, `CLK_HZ`; `SOFT_RESET`, logger'lar açık + sayaçlar sıfır, checker |
| Hat boşta seviyesi | Boşta tüm alıcılar `00` (ters / pull-up'lı alıcı `11` olarak yakalanır) |
| Hat polaritesi | TX override HIGH / LOW / NULL → her alıcıda `10` / `01` / `00`: **A/B ters bağlantı**, kopuk kablo, ters alıcı çıkışı; HIGH-Z davranışı (bilgi) |
| Tek Word *(HS / LS)* | Word Builder (Label/SDI/Data/SSM + IP parity) → TX, TB, RX sayaçları, `LAST_WORD`, Checker |
| Veri bütünlüğü deseni *(HS / LS)* | 0x00.., 0x7F.., 0x55.., 0x2A.., walking-1 Word'leri; Word RAM sırası ve içeriği birebir |
| Bit zamanlaması *(HS / LS)* | Bit Diagnostic: hattaki pulse / null / bit süreleri RX kabul aralığında mı; TX'e göre pulse farkı (sürücü + alıcı gecikme asimetrisi), gürültü sayısı |
| Scheduler periyodu ve gap ölçümü *(HS / LS)* | Timestamp farkları = 32 bit + gap + inter-word gap; RX'in ölçtüğü gap |
| Art arda gönderim *(HS / LS)* | Minimum gap (4 bit) ile kesintisiz akış: kayıpsız, hatasız, Checker FIFO taşmadan |
| HS ↔ LS art arda geçiş | 3 tur hız değişimi, her turda alım |
| Hız uyuşmazlığı tespiti | TX HS / RX LS ve TX LS / RX HS: Word kabul edilmez, `Pulse Glitch` / `Pulse Stuck` raporlanır |
| Parity hatası tespiti | Even parity'li Word reddedilir, `Parity Error` + hatalı Word Error RAM'de |
| Gap ihlali tespiti | 2 bit gap ile art arda Word → `Gap Violation`, standart gap'e dönünce alım devam |
| Logger kontrolleri | `ENABLE=0` (kayıt yok), `FREEZE` / `GLOBAL_FREEZE` (`DROP_CNT`) |
| Custom config | Config sekmesinde hesaplanan Custom TX / RX config ile desen + bit zamanlaması |

Başarısız kontrollerde olası neden yazılır (logger kapalı, hat `11`, A/B ters, tüm bitler ters, hatta sinyal yok,
son hata kodları). Sonuçlar ağaçta test → kontrol → ölçüm olarak listelenir, **Raporu Kaydet…** ile `.txt` / `.json`
alınır. Test sonunda kart High Speed preset, Word Transmitter ve açık logger'larla bırakılır.

**Kart olmadan (RTL eş-simülasyonu):** `python main.py --cosim` uygulamayı gerçek RTL'e (GHDL synth + Verilator,
yoksa Icarus) bağlar; TX RTL içinde RX0'a ve TX BIT'e loopback bağlıdır, Test menüsü RTL'e karşı koşar
(`tests/test_selftest.py` aynı testleri RTL'de çalıştırır ve A/B ters / ters alıcı / kopuk hat tanılarını doğrular).
`--sim` (dahili simülatör) ARINC hattını modellemediği için Test menüsü orada kapalıdır.

## Register Haritası (`arinc429_ip`, IP 2.0.0)

Register haritasının **tek kaynağı** `a429/ipmap.py`'dir: `vhdl/scripts/gen_axil_spec.py` buradan AXIL Studio
spec'ini (`.regspec.json` / `.axproj.json` / `arinc429.axlib.json`), AXIL Studio `axilgen` ile `arinc429_axil*.v`
dosyalarını ve top VHDL port bağlantılarını üretir; uygulama ve `--sim` simülatörü aynı haritayı kullanır.

İlgili küçük alanlar tek 32-bit register'da gruplanmıştır (IP 1.x'teki 128 register → 93):

| Register | Alanlar |
|---|---|
| `TX_CTRL` | `TRANSMITTER_EN[0]`, `MSG_SCHED_EN[1]`, `BUILDER_EN[2]`, `SCHED_EN[3]` |
| `TX_WORD` | ARINC Word düzeninde: `LABEL_VAL[7:0]`, `SDI[9:8]`, `DATA[28:10]`, `SSM[30:29]`, `PARITY_TYPE[31]` |
| `TX_EXT_LINE` | `HIGH[0]`, `LOW[1]` (hat override) |
| `TX_CFG` / `{p}CFG` | `SEL[1:0]`, `APPLY[4]` (darbe) |
| `TX_CUST_TIMING` / `TX_ACT_TIMING` | `PULSE_DUR[15:0]`, `NULL_DUR[31:16]` |
| `{p}CUST_PULSE` / `{p}ACT_PULSE` | `MIN[15:0]`, `MAX[31:16]` |
| `{p}CUST_BIT` / `{p}ACT_BIT` | `MIN[15:0]`, `MAX[31:16]` |
| `{p}CUST_NOISE` / `{p}ACT_NOISE` | `PULSE_ERR[15:0]`, `NULL_ERR[31:16]` |
| `{p}CUST_FILTER` / `{p}ACT_FILTER` | `GLITCH_SIZE[15:0]`, `GAP_ERR[31:16]` |
| `{p}STATUS` | `FROZEN[4]`, `WORD_WRAP[5]`, `ERR_WRAP[6]`, `ACT_CFG[9:8]`, **`LINE_HIGH[12]`, `LINE_LOW[13]`, `SYNC_WAIT[14]`** (hat teşhisi) |
| `{p}ERR_RD_INFO` | `CODE[15:0]`, `ADDR[31:16]` |
| `{p}BIT_RD_PULSE` / `{p}BIT_RD_NULL` | `DUR[15:0]`, `ERR[31:16]` (`BIT_RD_NULL` okununca pointer +1) |

`{p}` = `TB_` (TX BIT) veya `RX{n}_`. Tam liste: `vhdl/axil/arinc429_axil_regs.md`.

Uygulama içte eski **mantıksal adları** (`TX_LABEL`, `RX0_CUST_MIN_PULSE`, `TB_ERR_RD_CODE` …) kullanır;
`RegMap.resolve` bunları gruplanmış register'daki alana (IP 2.x) ya da aynı adlı register'a (IP 1.x) çözer.
Yazmalar register bazında birleştirilir ve register'ın diğer alanları korunur. Config tablolarında Studio'daki
fiziksel ad (`RX0_CUST_PULSE.MIN @ 0x4040[15:0]`) gösterilir. Eksik register varsa ilgili düğme devre dışı kalır.

## IP Durumu

**Kontrol** sekmesindeki **IP Durumu** (bağlanınca otomatik çalışır), RX/TB'nin *hiç kayıt tutmamasına ve hata da
vermemesine* yol açan durumları karttan okuyarak listeler ve tek tıkla düzeltir:

- `CTRL.ENABLE=0` (reset sonrası varsayılan: logger kapalı, Word ve hata kaydedilmez), `CTRL.FREEZE=1`, `GLOBAL_FREEZE=1`
- Hat teşhisi (`STATUS.LINE_HIGH/LINE_LOW/SYNC_WAIT` örneklenir): hat sürekli `11` (alıcı çıkışı ters / pull-up /
  besleme yok), decoder senkron bekliyor, hatta aktivite yok (bağlanmamış `rx_high/rx_low`)
- IP kimliği / sürümü (bitstream ile harita uyumu), `CLK_HZ` ile Config sekmesi saati, TX bit süresinin RX/TB
  kabul aralığında olması (HS/LS uyuşmazlığı), TX hat override modu

RX kartında da logger kapalıyken veya hat sorunu varken belirgin bir uyarı şeridi ve **Logger'ı Aç** düğmesi görünür.

## Dosyalar

- `.a429proj`: Proje paketi (ayarlar + tüm okumalar, ZIP). Eski sürümlerden kaydedilmiş projelerle uyumludur.
- `.a429cfg`: Config, okuma ve çözümleme ayarları (JSON).
- `.a429read`: Tek bir okuma oturumu (JSON).
- Bağlıyken çalışma ayarları ayrıca AXIL Studio projesinde (`set_settings`) saklanır.
