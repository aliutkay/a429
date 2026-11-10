# ARINC 429 RX Test Aracı (Python)

RX hesapları ve okuma hazırdır; TX tarafında canlı kontrol vardır, TX hesapları ve gönderilen veriler sonraki aşamadadır. Komut ve Register Düzenleyici ortaktır.

Excel + Tera Term TTL akışının bağımsız Python sürümü. Config hesaplama, seri porttan config
gönderme ve veri okuma, çözümleme, grafikler ve proje dosyaları tek programda.

## Kurulum

Python 3.9+ ve Tk 8.6 veya üstü gerekir. Mac ve Windows aynı kodu ve aynı arayüzü kullanır.
python.org kurulumu iki sistemde de tkinter ile gelir.

**Windows**

```
pip install -r requirements.txt
python main.py
```

`baslat.bat` dosyasına çift tıklayarak da açılır.

**Mac** (Apple'ın Komut Satırı Araçları'yla gelen Python'daki Tk 8.5 uygun değildir; python.org'dan Python 3.12 kurun)

```
/usr/local/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

`baslat.command` dosyasına çift tıklayarak da açılır.

Kullanılan kütüphaneler: `tkinter` (Python ile gelir), `pyserial`, `matplotlib`.

## Sekmeler

| Sekme | İçerik |
|---|---|
| **Config** | Sol kenarda ayarlar: **Genel** (System Clock ve toleransı, Komut ve Register Düzenleyici), **RX Config** (ARINC 429 profili, Receiver entegresi, FPGA giriş standardı, Glitch Filter ve limitler, test toleransı, grafikler), **TX Config** (ARINC 429 profili). RX ve TX aynı ARINC profil listesini kullanır ve ayrı profil seçebilir. Sağda **RX / TX** sekmeleriyle üstte kontroller, altta Config Register'ları gösterilir; ara hesaplarda satıra çift tıklayınca formül açılır. |
| **Bağlantı** | Port ayarları, hedef IP portu, Handshake dizisi ve cevabı, zamanlama, okunacak veriler (tümü / son N kayıt / okunmasın), okuma klasörü. Butonlar: Bağlan → Config gönder → Verileri oku (veya Hepsi). TX/RX log'u. |
| **TX Gönderilen Veriler** | Yer tutucu; sonraki aşamada doldurulacak. |
| **RX Okunan Veriler** | Word Listesi, Word Dalga Formu, Bit Diagnostic, Error Listesi, istatistik ve tutarlılık kontrolleri. Her okuma kendi clock'unu saklar, **Veri clock'u** alanından elle değiştirilebilir. PASS/FAIL durumu hücre rengiyle (yeşil/kırmızı) gösterilir; neden için hücrenin üzerine gelin veya sağ tıklayın. Word satırına çift tıklayınca dalga formu açılır. |

Grafiklerde fare: **tekerlek / iki parmak** = imleç etrafında iki eksende zoom, **Ctrl+tekerlek** = yalnız dikey zoom,
**sürükle** = iki eksende kaydır, **Shift+tekerlek** = yatay kaydır, **çift tık / Ev butonu** = başlangıç görünümü. Yakınlaştırınca yazılar da büyür;
süre etiketleri sığarsa yatay, sığmazsa dik yazılır. Araç çubuğundan PNG kaydedilebilir.

Config hesabı Excel ile birebir aynıdır (ARINC 1 Bit Time ve ½ Bit Time toleransları, Receiver tPLH/tPHL %50→%50, FPGA giriş eşiği
LVCMOS33/LVTTL/Custom, clock ppm). Grafiklerdeki MIN/MAX register değerleri Config tablosundaki değerlerin aynısıdır;
tek Bit analizi test toleransı eklenmemiş fiziksel değerleri gösterir ve başlığında CFG değerini de yazar.

Okumada `AB 00 00 00 00 CD` (32-bit 0) cevabı normal kabul edilir; 0 okunan Bit Diagnostic kayıtları
dalga formunda nominal süreyle çizilir.

**Kart olmadan denemek için** port listesinden `SIMÜLATÖR` seçin.

## TX Canlı Kontrol

Bağlantı sekmesindeki **TX Canlı Kontrol…** ayrı pencerede açılır: Word oluşturucu (Label, SDI, Data, SSM, Parity tipi) veya direkt 32-bit Word (hex/binary), Scheduler (internal delay, periyottan veya direkt Interword gap, ▶/⏸) veya manuel gönderim (tek gönderim ya da bilgisayar zamanlamasıyla periyodik ▶/⏸), hat override (HIGH, NULL, LOW, HIGH-Z); override etkinken Word ve Gönderim bölümleri kapalıdır. Süreler clk, ns, µs veya ms girilebilir. Periyot modunda Interword gap = periyot − 32 Bit Word süresi − 4 Bit gap süresi; Bit Time, TX ARINC profilinin Bit Rate NOM değerinden alınır.

Gönderim `ext_data_valid` 1→0 darbesiyle tetiklenir; override `Word Transmitter enable` 0 yapılıp `ext_high`/`ext_low` ile sürülür (00 NULL, 10 HIGH, 01 LOW, 11 HIGH-Z). Adresler **Komut ve Register Düzenleyici → TX ve kontrol Register'ları** sekmesindedir. **TX Config gönder** tüm TX sinyallerini başlangıç değerleriyle yazar (Pulse/Null/Gap TX profilinden, SLP Bit Rate'ten: 14.5 kbps üstü 1), `scheduler_en` en son ve 0 olarak yazılır. **Register yazma logunu da kaydet** seçiliyse tüm yazmalar okuma klasöründe `yazma_log_*.txt` dosyasına eklenir.

## Dosyalar

| Uzantı | İçerik |
|---|---|
| `.a429proj` | Proje: tüm ayarlar + projedeki tüm okumalar (ZIP). Dosya → Proje aç/kaydet. |
| `.a429cfg` | Sadece ayarlar (config, bağlantı, çözümleme). |
| `.a429read` | Tek okuma (ham register değerleri + o anki ayarların kopyası, JSON). |

Her okuma bittiğinde otomatik olarak okuma klasörüne `okuma_YYYYAAGG_SSDDss.a429read` olarak
kaydedilir ve projeye eklenir. İsteğe bağlı olarak yanına Tera Term/Excel uyumlu
`a429_words.txt`, `a429_errors.txt`, `a429_bits.txt`, `a429_summary.txt` dosyaları da yazılır.
Eski TTL çıktıları Dosya → *TTL/Excel txt dosyalarından içe aktar* ile açılabilir.

## Protokol özeti

- Handshake: `AA 11 BB 22 CC 33 DD 44` → echo, tekrar → ayarlanan Handshake cevabı (varsayılan 16 × `00`) = bağlı.
- Yazma: `C3 00 <ip> <reg> <data32>` (IP ACK göndermez).
- Okuma: `CF 00 <ip> <reg>` → `AB <data32> CD`.
- Word/Error/Bit BRAM adres seçimi `1D` / `1E` / `1F` (geri okunarak doğrulanır); okuma en yeniden eskiye, `rx_cfg_read_mode` (`1C`) okuma süresince 1.
- Register haritası `00`–`1F`: `00` IP reset, `01`–`13` TX, `14`–`1B` RX Config (16 bit), `1C` read mode, `1D`–`1F` BRAM adres seçimi. RX ve TX Config yazıldıktan sonra geri okunup doğrulanır.

Tüm adresler ve byte'lar **Ayarlar → Komut ve Register Düzenleyici** penceresinden değiştirilir ve projeyle birlikte kaydedilir.

## Komut ve Register Düzenleyici

- **Komut Yapısı:** Komutlar `C3 00 {IP} {REG} {DATA32}` gibi şablonlarla tanımlanır (`{IP}`, `{REG}`, `{REG16}`, `{DATA8}`…`{DATA64}`).
- **Yazma Register'ları:** Yeni Register eklenebilir; değeri hesaplanan değişkenlerden formülle üretilir, ör. `min_pulse + 2` veya `(max_bit << 16) | min_bit`.
- **Okuma Register'ları:** Word/Error/Bit Diagnostic adresleri ve BRAM derinlikleri; eklenen ek Register'lar okumada bir kez okunup İstatistik sekmesinde gösterilir.

Çözümleme limitleri Register tablosundan değil hesaplanan değişkenlerden alınır.
