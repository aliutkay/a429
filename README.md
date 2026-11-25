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
2. AXIL Studio → **UART-to-AXI Debug Bridge** → *Debug* menüsü → *IP arayüzü klasörleri…* bölümüne bu
   reponun klasörünü (`axil-interface.json` dosyasının bulunduğu dizin) ekleyin.
3. AXIL Studio **Register Map Editor**'da ARINC 429 IP'sinin *IP arayüzü* (`panel`) alanına `arinc429` yazın.
4. Debug Bridge'de IP seçilince **ARINC 429 arayüzü** düğmesi görünür.

### Bağımsız / Simülatör çalıştırma

- Çevrimdışı mod (yalnızca hesap ve kayıtlı okumalar):
  ```bash
  python main.py
  ```
- Dahili IP simülatörüyle deneme (donanım ve Studio olmadan):
  ```bash
  python main.py --sim
  ```

## Sekmeler

| Sekme | İçerik |
|---|---|
| **Config** | Sol panelde **Genel** (System Clock, ±ppm), **RX Config** (ARINC 429 profili, Receiver entegresi, FPGA giriş standardı, Glitch Filter ve limitler, test toleransı, örnek dalga formu / tek bit grafikleri) ve **TX Config** (ARINC 429 profili). Sağda **RX / TX** alt sekmeleri: kontroller, ara hesaplar (çift tık → formül), hesaplanan register değerleri, panoya kopyalama ve **Debug Bridge config listesine ekle**. |
| **Kontrol** | Okunacak RX verileri (Word / Error / Bit Diagnostic: Tümü / Son N / Okunmasın), okuma ve yazma dosyası ayarları, IP/kanal harita durumu; sağda **RX İşlemleri** (**RX Config gönder**, **RX verilerini oku**, **Config + oku**), **TX İşlemleri** (**TX Config gönder**, **TX Canlı Kontrol…**), **IP Kontrol** (**IP reset**, **Durdur**), ilerleme çubuğu ve **İşlem Logu**. |
| **RX Okunan Veriler** | Word Listesi, Word Dalga Formu, Bit Diagnostic, Error Listesi, İstatistik ve tutarlılık kontrolleri. PASS/FAIL hücre renklendirmesi (neden için üzerine gelin veya sağ tıklayın). Word satırına çift tık → dalga formu. |
| **TX Gönderilen Veriler** | TX Canlı Kontrol gönderim geçmişi (filtreleme, CSV dışa aktarma, projeyle kayıt) ve **TX Built-In Test (TX BIT · Wraparound Checker)** canlı sayaçları (`TX_WORD_CNT`, `TB_WORD_CNT`, `CHK_OK_CNT`, `CHK_ERR_CNT`, FIFO), Checker kontrolü ve tek tıkla `TB_` okuması. |

Üst başlık çubuğundan hedef kanal (`RX0`…`RXn`, `TX BIT`) seçilir.

## Register Adlandırma Sözleşmesi (`arinc429_ip`)

Uygulama, register offset'lerini AXIL Studio'daki IP register haritasından **adla** bulur (bkz. `vhdl/doc/DESIGN.md`).
Eksik register varsa ilgili düğme devre dışı kalır ve tooltip'te eksik adlar listelenir.

| Sayfa | Önek | Örnek register adları |
|---|---|---|
| Global | *(yok)* | `IP_ID`, `CAPS`, `CAPS_MEM`, `CLK_HZ`, `SOFT_RESET`, `GLOBAL_FREEZE`, `TS_LSB`, `TS_MSB` |
| TX | `TX_` | `TX_TRANSMITTER_EN`, `TX_MSG_SCHED_EN`, `TX_BUILDER_EN`, `TX_LABEL`, `TX_SDI`, `TX_DATA`, `TX_SSM`, `TX_PARITY_TYPE`, `TX_SCHED_EN`, `TX_INITIAL_DELAY`, `TX_INTER_WORD_GAP`, `TX_SEND_CMD`, `TX_EXT_DATA`, `TX_EXT_HIGH`, `TX_EXT_LOW`, `TX_CFG_SEL`, `TX_CFG_APPLY`, `TX_CUST_PULSE_DUR`, `TX_CUST_NULL_DUR`, `TX_CUST_GAP_DUR`, `TX_CUST_SLP`, `TX_ACT_*`, `TX_STATUS`, `TX_WORD_CNT` |
| TX BIT | `TB_` | `TB_CTRL`, `TB_CFG_SEL`, `TB_CFG_APPLY`, `TB_CUST_*`, `TB_ACT_*`, `TB_WORD_CNT`, `TB_ERR_CNT`, `TB_WORD_RADDR`, `TB_WORD_RD_*`, `TB_ERR_RADDR`, `TB_ERR_RD_*`, `TB_BIT_RADDR`, `TB_BIT_RD_*` |
| RX *n* | `RX{n}_` | `TB_` ile aynı kanal register seti (`RX0_CTRL`, `RX0_CUST_MIN_PULSE`, `RX0_WORD_RADDR`, …) |

## Dosyalar

- `.a429proj`: Proje paketi (ayarlar + tüm okumalar, ZIP). Eski sürümlerden kaydedilmiş projelerle uyumludur.
- `.a429cfg`: Config, okuma ve çözümleme ayarları (JSON).
- `.a429read`: Tek bir okuma oturumu (JSON).
- Bağlıyken çalışma ayarları ayrıca AXIL Studio projesinde (`set_settings`) saklanır.
