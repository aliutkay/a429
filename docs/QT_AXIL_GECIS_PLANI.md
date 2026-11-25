# a429tool → Qt + AXIL Studio IP arayüzü geçiş planı

Bu doküman, işi devralacak geliştirici (veya AI) içindir. Kararlar kullanıcıyla netleştirildi; burada yazmayan
bir tasarım kararı gerekirse **kullanıcıya sorun** (kullanıcı IP'de ve projede değişiklik yapmaya açık).

---

## 0. Hedef (tek cümle)

a429tool'u, AXIL Studio'nun **UART-to-AXI Debug Bridge**'inden açılan bir **IP arayüzü** (PySide6/Qt) hâline getir:
seri port / handshake / komut şablonu / Register Düzenleyici tamamen kalkar; karta erişim yalnızca
`axil_client.AxilClient` üzerinden olur, register adresleri Studio'daki IP register haritasından **adla** bulunur.
Sekmeler: **Config**, **RX Okunan Veriler**, **TX Gönderilen Veriler** kalır; **Bağlantı** sekmesi kalkar.

## 1. Kullanıcı kararları (kesin)

| Konu | Karar |
|---|---|
| IP Studio'da nasıl görünür | **Tek IP, tek register haritası**: Global + TX + TX BIT + RX kanalları, `vhdl/doc/DESIGN.md` §4'teki sayfa offset'leriyle (Global `0x0000`, TX `0x0400`, TX BIT `0x0800`, RX n `0x4000 + n·0x400`). Arayüz bu IP için açılır. |
| Register erişimi | Register/alan **adları kodda sabit**; offset'ler `client.ip["registers"]`'tan adla çözülür. Eksik register → anlaşılır uyarı (hangi adlar yok), ilgili düğmeler kapalı. |
| Studio olmadan | **Çevrimdışı mod**: Config hesabı + kayıtlı okumaları açma/görüntüleme çalışır; okuma/yazma düğmeleri kapalı. |
| Dil | **Sadece Türkçe** (i18n / `tr()` yok). |
| Kodun yeri | **a429tool reposunda** kalır; repo köküne `axil-interface.json` eklenir; Studio'da *Debug → IP arayüzü klasörleri…* ile eklenir. |
| RX kanalları | Arayüzde **kanal seçici** (RX0..RXn, TX BIT). Config gönderme ve okuma seçili kanal için yapılır. |
| UI | tkinter → **PySide6** (axil-studio ile aynı). matplotlib → `backend_qtagg`. |

## 2. Referans: axil-studio

- Repo: https://github.com/aliutkay/axil-studio (bir kopyası:
  `~/.gemini/antigravity/brain/f28f87dc-ca01-414a-a60e-75d3ca47ffca/scratch/axil-studio`; yoksa yeniden klonla — ağ erişimi gerekir).
- Okunacak dosyalar (sırayla):
  1. `interfaces/README.md` — arayüz protokolü (aşağıda özeti var).
  2. `interfaces/sdk/axil_client.py` — istemci (tek dosya, stdlib). Studio bunu `PYTHONPATH`'e koyar.
  3. `interfaces/axiluart_phy/uart_ui.py` + `look.py` — **örnek uygulama**: `Worker` sınıfı, `_on_event`, `_call`,
     bağlantı pill'i, `closeEvent`, `main()`. Yapıyı buradan kopyala.
  4. `interfaces/cmd_seq/seq_ui.py`, `seq_core.py` — ikinci örnek (GUI'siz çekirdek + Qt UI ayrımı).
  5. `axil_studio/core/axilgen.py` başı — alan türleri: `RW`, `RO`, `PULSE` (1 yaz → 1 clk darbe, 0 okunur), `W1C`, `CONST`.
  6. `axil_studio/core/model.py` `Register.to_dict()` — `ip["registers"]` formatı:
     `{"name", "offset": "0x00000010", "access": "RW|RO|WO", "reset", "desc", "fields": [{"name","lsb","width","kind","values",...}]}`
     (offset **hex string**, `int(x, 0)` ile çöz).

### 2.1 Protokol özeti (sürüm 1)

- `axil-interface.json` (manifest), klasörde:
  ```json
  {"format": "axil-interface", "protocol": 1, "id": "arinc429", "version": "0.1.0",
   "title": "ARINC 429 arayüzü", "desc": "ARINC 429 IP: Config hesabı, RX okuma ve çözümleme, TX kontrol",
   "command": ["{python}", "a429_ui.py"]}
  ```
  `{python}` = Studio'yu çalıştıran Python → **o Python'da `matplotlib` kurulu olmalı** (README'ye yaz). IP'nin
  register haritasında *IP arayüzü* (`panel`) alanına `arinc429` yazılmalı.
- Studio ortam değişkenleri: `AXIL_STUDIO_PORT`, `AXIL_STUDIO_TOKEN`, `AXIL_STUDIO_LANG`, `PYTHONPATH` (+ `interfaces/sdk`).
- İstemci:
  ```python
  from axil_client import AxilClient, AxilError
  c = AxilClient.from_env("ARINC 429 arayüzü")   # Studio yoksa AxilError("no_studio") → çevrimdışı mod
  c.ip  # {"name","base","registers":[...],"panel",...}; c.connected; c.settings; c.theme
  c.read(offset) / c.write(offset, value)        # offset = IP tabanından
  c.batch([("write", off, v), ("read", off), ...])  # okunanlar listesi (yazmalar None)
  c.lock() / c.unlock()                          # uzun okuma boyunca Debug Bridge'in canlı izlemesi durur
  c.set_settings(key=json) / c.settings          # Studio projesinde bu IP örneği için saklanır
  c.status(text) / c.log(text) / c.show_register(name)
  c.on_event = fn   # okuyucu thread'den: connection, ip, ip_removed, theme, raise, closing
  ```
  Hata kodları: `not_connected`, `busy`, `bus`, `ip_removed`, `closed`, `bad_request`… `quiet=True` erişimleri
  Debug Bridge trafik günlüğüne yazmaz (toplu okumada kullan).
- Olaylar GUI thread'ine `Signal(dict)` + `QueuedConnection` ile taşınır (uart_ui.py satır ~173–220).
- Tüm Studio çağrıları **tek worker thread**'de (uart_ui.py `Worker`), sonuç GUI thread'ine sinyalle döner.

## 3. Register adlandırma sözleşmesi (tek IP → adlar benzersiz olmalı)

Studio'da bir IP'nin register adları benzersizdir. Önerilen önekler (**kullanıcıya teyit ettir**, sonra kodda sabitle):

| Sayfa | Önek | Örnek |
|---|---|---|
| Global | yok | `IP_ID`, `CAPS`, `CAPS_MEM`, `CLK_HZ`, `SOFT_RESET`, `GLOBAL_FREEZE`, `TS_CTRL`, `TS_LSB`, `TS_MSB`, `ROUTE_CTRL`, `ROUTE_TEST_MASK` |
| TX | `TX_` | `TX_TRANSMITTER_EN`, `TX_LABEL`, `TX_SEND_CMD`, `TX_CFG_SEL`, `TX_CUST_PULSE_DUR`, `TX_STATUS` … |
| TX BIT | `TB_` | `TB_CTRL`, `TB_WORD_CNT`, `TB_WORD_RADDR`, `TB_CHK_CTRL` … |
| RX n | `RX{n}_` | `RX0_CTRL`, `RX0_CUST_MIN_PULSE`, `RX0_WORD_RADDR`, `RX0_WORD_RD_DATA` … |

Kanal sayfasındaki adlar (DESIGN.md §7.1, önekten sonra): `CTRL` (alanlar `ENABLE`, `FREEZE`, `CLEAR`(PULSE)), `STATUS`,
`CFG_SEL`, `CFG_APPLY`(PULSE), `CUST_GLITCH_FILTER_SIZE`, `CUST_MIN_PULSE`, `CUST_MAX_PULSE`, `CUST_MIN_BIT`, `CUST_MAX_BIT`,
`CUST_MAX_PULSE_ERR`, `CUST_MAX_NULL_ERR`, `CUST_MAX_GAP_ERR`, `CUST_PARITY_MODE`, `LABEL_FILTER_EN`, `LABEL_MASK0..7`,
`ACT_*` (CUST_* ile aynı sıra), `WORD_CNT`, `ERR_CNT`, `DROP_CNT`, `LAST_WORD`,
`WORD_RADDR`, `WORD_RD_TS_MSB`, `WORD_RD_TS_LSB`, `WORD_RD_DATA`, `WORD_RD_GAP`, `WORD_RD_GAP_ERR`,
`ERR_RADDR`, `ERR_RD_TS_MSB`, `ERR_RD_TS_LSB`, `ERR_RD_CODE`, `ERR_RD_ADDR`, `ERR_RD_DATA`,
`BIT_RADDR` (alanlar `BIT` [4:0], `WORD` [12:8]), `BIT_RD_PULSE`, `BIT_RD_PULSE_ERR`, `BIT_RD_NULL`, `BIT_RD_NULL_ERR`,
checker: `CHK_CTRL`, `CHK_TIMEOUT`, `CHK_OK_CNT`, `CHK_ERR_CNT`, `CHK_STATUS`.

**Kanal keşfi**: `re.fullmatch(r"RX(\d+)_CTRL", name)` olan register'lar + `TB_CTRL` varsa "TX BIT". `CAPS` okunabiliyorsa
`NUM_RX`/`TX`/`TXBIT` bitleriyle karşılaştır, uyuşmazsa uyar. Bellek derinlikleri `CAPS_MEM`'den (WORD/ERR/BITDIAG log2);
okunamazsa varsayılan 256/256/8.

**Alan erişimi**: alanı olan register'da `(reg, field)` → mask/shift `fields`'tan hesaplanır; alan tanımlı değilse tüm 32 bit
kullanılır. RW alan yazarken read-modify-write (aynı `batch` içinde değil; önce oku, sonra yaz) — ya da IP'yi tek alanlı
register'larla tasarlamayı öner.

### 3.1 Eski → yeni eşleme (davranışı korumak için)

| Eski (a429tool) | Yeni |
|---|---|
| `LinkSettings.reg_wcnt/reg_ecnt` (`50`/`51`) | `RX{n}_WORD_CNT` / `RX{n}_ERR_CNT` |
| `reg_ts_lsb/msb` + MSB-LSB-MSB tekrar okuma | `TS_LSB` sonra `TS_MSB` (LSB okununca MSB latch'lenir, tek tur yeter) |
| `reg_waddr` + `reg_w[5]` | `RX{n}_WORD_RADDR` + `WORD_RD_TS_MSB, TS_LSB, DATA, GAP, GAP_ERR` (aynı sıra → `decode.py` değişmez) |
| `reg_eaddr` + `reg_e[5]` | `RX{n}_ERR_RADDR` + `ERR_RD_TS_MSB, TS_LSB, CODE, ADDR, DATA` |
| `reg_baddr` + `reg_b[4]` (adres `wno%8*32+bit`) | `RX{n}_BIT_RADDR` = `(word_idx << 8) | bit` + `BIT_RD_PULSE, PULSE_ERR, NULL, NULL_ERR` |
| `rx_read_mode` (`1C`) | `RX{n}_CTRL.FREEZE` = 1 okuma süresince (finally'de 0) |
| `verify_select` (adres geri okuma) | AXI'de gereksiz; kaldır (istenirse `RADDR` geri okunur) |
| RX Config yazma (`14`–`1B`, formüllü write_regs) | `CFG_SEL=2` (Custom) → `CUST_*` → `CFG_APPLY=1` → `ACT_*` geri okunup karşılaştırılır |
| `ip_reset` | `SOFT_RESET` (PULSE alanları: `ALL`, `TX`, `TXBIT`, `RX<n>`) |
| TX: `tx_ext_valid` 1→0 darbesi | `TX_SEND_CMD` = 1 (PULSE); önce `TX_STATUS.BUSY = 0` beklenir (`read_until`) |
| TX: `tx_pulse_dur/null/gap/slp` | `TX_CFG_SEL=2` + `TX_CUST_PULSE_DUR/NULL_DUR/GAP_DUR/SLP` + `TX_CFG_APPLY` |
| Diğer TX anahtarları (`tx_label`, `sched_delay`…) | `TX_LABEL`, `TX_SDI`, `TX_DATA`, `TX_SSM`, `TX_PARITY_TYPE`, `TX_BUILDER_EN`, `TX_MSG_SCHED_EN`, `TX_TRANSMITTER_EN`, `TX_SCHED_EN`, `TX_INITIAL_DELAY`, `TX_INTER_WORD_GAP`, `TX_EXT_DATA`, `TX_EXT_HIGH`, `TX_EXT_LOW` |

**Error kodu değişti**: `decode.ERR_NAMES` yeni 16 bitlik tabloya (DESIGN.md §9: bit 0 `BUS_FAULT` … bit 11 `LABEL_FILTERED`)
güncellenmeli; `decode_errors` içindeki padding kontrolü `code < 256` → `code < 65536`.
**Timestamp anı**: yeni IP'de Word **başı** (`word_start`) → `DecodeSettings.ts_at_word_end` varsayılanı `False`.
**Gap**: yeni IP önceki gap'i Word kaydında tutuyor (anlam aynı, kontrol et).

## 4. Hedef dosya yapısı

```
a429tool/
  axil-interface.json          (yeni)  id "arinc429", command ["{python}", "a429_ui.py"]
  a429_ui.py                   (yeni)  giriş: AxilClient.from_env → olmazsa çevrimdışı; --sim bayrağı
  main.py                      (güncelle) a429_ui.main()'i çağırır
  a429/
    model.py      (güncelle) regmap alanı kalkar; Result.regs → [(görünen ad, register adı, değer)]
    decode.py     (güncelle) ERR_NAMES, padding, ts varsayılanı
    charts.py, formulas.py     (aynı; yalnız Figure kullanıyor)
    txlive.py     (aynı, OVERRIDE_LINES/TRIGGER anahtarları yeni adlara)
    txcfg.py      (yeniden yaz) compute_tx → [(görünen ad, register adı, değer)], kontroller
    project.py    (güncelle) LinkSettings yerine ReadSettings; eski dosyalardaki "link" anahtarını tolere et
    regs.py       (yeni) sabit adlar + RegMap: ad→offset, alan mask/shift, kanal keşfi, eksik listesi
    ip.py         (yeni) IP işlemleri (GUI'siz): send_rx_config, read_channel, tx_write, soft_reset; bus = AxilClient benzeri
    sim.py        (yeni) SimClient: AxilClient arayüzünü taklit eden sahte IP (eski SimDevice verisiyle) — test ve --sim
    qt/
      look.py     (axil-studio interfaces/cmd_seq/look.py kopyası; tema token'ları)
      worker.py   (uart_ui.py'deki Worker)
      figpanel.py (FigPanel + ChartWindow; FigureCanvasQTAgg + NavigationToolbar2QT, aynı zoom/pan davranışı)
      celltable.py(QTableView + QAbstractTableModel: Background/Foreground/ToolTip rolleri, sağ tık → neden)
      main_window.py (App'in Qt karşılığı; başlık kartı + 3 sekme + alt işlem çubuğu + log)
      config_tab.py, read_tab.py, tx_sent_tab.py
      dialogs.py  (ARINC profilleri, Receiver entegresi, FPGA, Glitch, Formül penceresi, Okuma ayarları)
      txwindow.py (TX Canlı Kontrol, Qt)
  SİLİNECEK: a429/protocol.py, a429/regmap.py, a429/regedit.py, a429/gui.py, a429/celltable.py, a429/txwindow.py (Qt'ye taşındıktan sonra)
```

`requirements.txt`: `PySide6>=6.5`, `matplotlib>=3.5` (`pyserial` kalkar).

## 5. UI düzeni (Qt)

- **Başlık kartı** (`look.Card`): başlık "ARINC 429", IP adı + `0x%08X` base, **Kanal** combobox (RX0..n, TX BIT),
  System Clock (Config'teki `clk_mhz` ile senkron), bağlantı `look.Pill` ("● Debug Bridge bağlı" / "bağlı değil" /
  "Çevrimdışı"), "Debug Bridge'de göster" düğmesi.
- **Sekmeler** (`QTabWidget`, documentMode):
  1. **Config** — eski sol panel (Genel / RX Config / TX Config) + sağda RX/TX alt sekmeleri. "Komut ve Register
     Düzenleyici" düğmeleri **kalkar**. RX/TX Config Register tablosu sütunları: `Register`, `Studio register adı`,
     `Offset`, `Değer`, `Değer (hex)`; register haritasında olmayan satır kırmızı + tooltip "IP haritasında yok".
     "Komutları panoya kopyala" → "Değerleri panoya kopyala" (`AD=0x...`) ve **"Debug Bridge config listesine ekle"**
     (`client.add_config(rows)`).
  2. **RX Okunan Veriler** — aynen (Word Listesi, Word Dalga Formu, Bit Diagnostic, Error Listesi, İstatistik).
     Üst çubuğa okuma oturumu seçimi + kanal etiketi (oturum hangi kanaldan okundu: `session["channel"]`).
  3. **TX Gönderilen Veriler** — yer tutucu (ileride `TX_WORD_CNT`, TB_ kayıtları).
- **Alt işlem çubuğu** (Bağlantı sekmesinin yerine, tüm sekmelerde görünür): `RX Config gönder`, `RX verilerini oku`,
  `Config + oku`, `Okuma ayarları…`, `TX Config gönder`, `TX Canlı Kontrol…`, `IP reset`, `Durdur`, `QProgressBar`;
  altında katlanabilir log (`QPlainTextEdit`, mono). Önemli satırlar ayrıca `client.log()` ile Debug Bridge'e.
- **Okuma ayarları…** diyaloğu: Word/Error/Bit için Tümü / Son N / Okunmasın, okuma klasörü, "TTL/Excel txt yaz",
  "Register yazma logunu kaydet", "Okumada tüm erişimleri Debug Bridge'e logla" (= `quiet=False`).
- Düğme etkinliği: `connected and regs_ok and not busy`; çevrimdışıda hepsi kapalı, Config ve okuma görüntüleme açık.

### 5.1 tkinter → Qt karşılıkları

| tkinter | Qt |
|---|---|
| `ttk.Notebook` | `QTabWidget` |
| `ttk.LabelFrame` | `look.Card(title)` veya `QGroupBox` |
| `StringVar.trace_add` + `after(300)` recalc | `textChanged` → tek `QTimer(singleShot, 300)` |
| `ttk.Treeview` (`make_tree/fill_tree`, tag renkleri) | `QTableWidget` (+ `look.color("success"/"danger")`) |
| `CellTable` (Canvas) | `QTableView` + model (`BackgroundRole`, `ForegroundRole`, `ToolTipRole`), `doubleClicked` |
| `Toplevel` ayar pencereleri | modeless `QDialog` (tek örnek, `raise_()`) |
| `messagebox` / `filedialog` / `simpledialog` | `QMessageBox` / `QFileDialog` / `QInputDialog` |
| `queue` + `after(50, _poll)` | `Signal` (worker → GUI) |
| `FigureCanvasTkAgg`, `NavigationToolbar2Tk` | `FigureCanvasQTAgg`, `NavigationToolbar2QT` (`home` override) |
| Bad.TEntry kırmızı giriş | `setProperty("bad", True)` + stylesheet `QLineEdit[bad="true"]` |
| `bind_all(<Command-s>)` | `QShortcut(QKeySequence.Save)` |
| Menü (Dosya/Ayarlar/Yardım) | `QMenuBar` yerine başlık kartında "Dosya ▾" `QToolButton` menüsü (Studio arayüzleri `QWidget`); "Ayarlar → Register Düzenleyici" kalkar |

## 6. İşlem algoritmaları (`a429/ip.py`, GUI'siz, `bus` = AxilClient veya SimClient)

```python
def send_rx_config(bus, rm, ch, values, verify=True):          # values: {"CUST_MIN_PULSE": 123, ...}
    p = rm.prefix(ch)                                            # "RX0_" / "TB_"
    ops = [("write", rm.off(p+"CFG_SEL"), 2)] + [("write", rm.off(p+k), v) for k, v in values.items()]
    ops += [("write", rm.off(p+"CFG_APPLY"), 1)]
    bus.batch(ops, quiet=True)
    if verify:
        got = bus.batch([("read", rm.off(p+"ACT_"+k[5:])) for k in values], quiet=True)   # CUST_X → ACT_X
        # uyuşmayanları listele → hata

def read_channel(bus, rm, ch, opts, progress, stop):            # dönen dict = eski Link._read_all çıktısı + "channel"
    bus.lock()
    try:
        set_field(bus, rm, p+"CTRL", "FREEZE", 1)
        wtot, etot, lsb, msb = bus.batch([("read", WORD_CNT), ("read", ERR_CNT), ("read", TS_LSB), ("read", TS_MSB)])
        # derinlikler CAPS_MEM'den; wn/en/bn eski limit() mantığıyla
        # Word: her kayıt için [("write", WORD_RADDR, addr)] + 5 read; 16–32 kaydı TEK batch'te gönder (hız),
        #       her batch sonrası progress() ve stop.is_set() kontrolü
        # Error, Bit aynı şekilde; Bit adresi (word_idx << 8) | bit, word_idx = wno % bit_words
        # sonda WORD_CNT/ERR_CNT tekrar okunur → freeze iken değişmemeli (DROP_CNT'yi de özete yaz)
    finally:
        set_field(..., "FREEZE", 0); bus.unlock()
```

Dönen yapı **eskisiyle aynı** (`summary`, `words[{"no","addr","w"[5]}]`, `errors[{"addr","w"[5]}]`,
`bits[{"word","bit","w"[4]}]`) + `summary["drop_cnt"]`, `session["channel"]`, `session["ip"]` (ad, base). Böylece
`decode.py`, `charts.py`, `project.py`, eski `.a429read/.a429proj` dosyaları çalışmaya devam eder.

TX: `tx_write(bus, rm, [(reg_adı, değer)])` → tek `batch`; doğrulama gereken RW'ler için ardından geri okuma batch'i;
PULSE alanlar (`SEND_CMD`, `CFG_APPLY`, `SOFT_RESET`) doğrulanmaz. Manuel periyodik gönderim `QTimer` ile, worker meşgulse atlanır
(eski `_tick` mantığı). Scheduler başlat: `sched_writes + TX_MSG_SCHED_EN=1 + TX_SCHED_EN=1` (en son).

## 7. Ayarların saklanması

- `.a429proj` / `.a429cfg` / `.a429read` formatları kalır (`project.py`), `link` yerine `read` anahtarı; eski dosyada
  `link` varsa `read_word/read_error/read_bit/..._n/out_dir` alanları alınır, gerisi yok sayılır.
  `config.regmap` anahtarı yüklenirken **yok sayılır**.
- Bağlıyken `ConfigInputs.to_dict()` + DecodeSettings + ReadSettings + seçili kanal `client.set_settings(a429=...)` ile
  Studio projesine de yazılır (değişiklikten 1 sn sonra, debounce); açılışta `client.settings["a429"]` varsa yüklenir
  (proje dosyası açılmadıysa). Okuma oturumları Studio'ya yazılmaz (büyük).

## 8. Uygulama sırası (her adım sonunda çalışır durumda bırak)

1. **Çekirdek temizliği** (GUI'siz, test edilebilir): `regs.py`, `sim.py` (SimClient: dict tabanlı register'lar,
   eski `SimDevice`'taki sahte Word/Bit/Error verisi, `RADDR` yazınca `RD_*` okumaları değişir, `CFG_APPLY` → `ACT_*`),
   `ip.py`, `model.py`/`txcfg.py`/`decode.py`/`project.py` güncellemesi. `protocol.py`, `regmap.py` sil.
   Test: `tests/test_ip.py` (pytest) — SimClient ile `send_rx_config` doğrulaması, `read_channel` → `decode_words` hatasız,
   eski bir `.a429proj` yüklenebiliyor (`regmap`/`link` içerenler).
2. **Qt iskeleti**: `a429_ui.py`, `qt/look.py`, `qt/worker.py`, `qt/main_window.py` (başlık kartı, kanal seçici, pill,
   olaylar, `closeEvent`, çevrimdışı mod, `--sim`). `python a429_ui.py --sim` açılabilmeli.
3. **Config sekmesi** + ayar diyalogları + `figpanel.py` (grafikler, formül penceresi). Hesap sonuçları eski uygulamayla
   aynı olmalı (aynı girişlerle `compute()` çıktısı değişmiyor; sadece `regs` biçimi).
4. **RX Okunan Veriler** sekmesi + `celltable.py` (tooltip/sağ tık nedeni, çift tık → dalga formu) + dosya menüsü.
5. **Alt işlem çubuğu**: RX Config gönder, oku, Config+oku, Durdur, IP reset, ilerleme, log, yazma logu dosyası,
   otomatik `.a429read` + txt kaydı.
6. **TX**: TX Config gönder, TX Canlı Kontrol (Qt), TX Gönderilen Veriler yer tutucusu.
7. **Studio entegrasyonu**: `axil-interface.json`, `set_settings` saklama, `add_config`, `show_register`, tema olayı
   (matplotlib figürleri açık temada beyaz kalabilir; isteğe bağlı koyu tema renkleri).
8. **Temizlik**: eski tkinter dosyalarını sil, `main.py`, `requirements.txt`, `README.md` (Bağlantı/Simülatör/Register
   Düzenleyici bölümleri kalkar; kurulum: Studio'nun Python'una `pip install matplotlib`; arayüz klasörü ekleme;
   IP'nin `panel` = `arinc429`; register adlandırma tablosu).

Kontrol komutları: `.venv/bin/pip install PySide6` (sandbox'ta ağ gerekebilir), `.venv/bin/python -m pytest tests`,
`.venv/bin/python -m py_compile a429/*.py a429/qt/*.py`, `QT_QPA_PLATFORM=offscreen .venv/bin/python a429_ui.py --sim`
(birkaç saniye açık kalıp hata vermemeli; kısa bir smoke test için `QTimer.singleShot(2000, app.quit)` bayrağı ekle).

## 9. Kullanıcıya sorulacak açık noktalar (başlamadan / ilgili adımda)

1. IP veri yolu: DESIGN.md **APB3** diyor; AXIL Studio'nun wrapper üreticisi **AXI4-Lite** (easyaxil) üretiyor. APB slave +
   reg_bank yerine Studio'nun ürettiği AXI-Lite wrapper mı kullanılacak? (Arayüz için fark etmez; register haritası Studio'da
   tanımlı olmalı.) 64 KB pencere (`0x0000–0xFFFF`) Studio'da IP penceresi olarak verilebilmeli.
2. §3'teki **önek sözleşmesi** (`TX_`, `TB_`, `RX{n}_`) ve alan adları (`CTRL.ENABLE/FREEZE/CLEAR`, `BIT_RADDR.WORD/BIT`)
   uygun mu? Kesinleşince `a429/regs.py` sabitleri ve README tablosu buna göre.
3. TX sayfasının kesin numaralandırması (ARCHITECTURE §10 madde 1 hâlâ açık).
4. `TS_LSB` okununca `TS_MSB` latch'leniyor mu (DESIGN §5.2 öyle diyor) — okuma sırası buna bağlı.
5. RX Config: her zaman Custom (`CFG_SEL=2`) mi gönderilsin, yoksa arayüzde High/Low Speed preset seçimi de olsun mu?
6. Label filtresi (`LABEL_FILTER_EN`, `LABEL_MASK0..7`) ve checker (`CHK_*`) için arayüz bu aşamada mı istenir?
7. TX BIT kanalı kanal seçicide RX gibi okunabilir mi (aynı sayfa yapısı, `TB_` önekiyle)?

## 10. Dikkat

- `{python}` Studio'nun Python'u: sanal ortam değil. matplotlib yoksa arayüz açılmaz → `a429_ui.py` başında
  `ImportError` yakalayıp anlaşılır `QMessageBox` göster.
- Studio çağrıları GUI thread'inde **asla** yapılmaz (bloklar). Worker tek thread; okuma sırasında başka istek kuyruğa girer.
- `closing` olayında: durdur bayrağını kur, `unlock`'u dene, pencereyi kapat. `connection` false olunca süren işlem
  `AxilError("not_connected")` ile biter → kullanıcıya mesaj, `FREEZE` bırakılamamış olabilir (log'a uyarı).
- `quiet=True` toplu okumalarda; tek tek kullanıcı eylemleri (`IP reset`, TX Word yaz) `quiet=False` kalabilir.
- Eski `.a429proj` dosyaları açılabilmeli (geriye uyumluluk testi ekle).
