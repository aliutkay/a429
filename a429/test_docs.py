"""Test bilgi kataloğu (ⓘ yardım pencereleri) ve zengin HTML test raporu üreteci."""
from __future__ import annotations

import html as _html
from dataclasses import dataclass


@dataclass(frozen=True)
class TestDoc:
    tid: str
    title: str
    what: str
    checks: str
    causes: str


# =====================================================================================
# Tüm test modları için ortak + moda özel teknik açıklamalar
# =====================================================================================
TEST_DOCS: dict[str, TestDoc] = {
    # ---- Ortak / Loopback / PCS testleri ----
    "ident": TestDoc(
        "ident", "IP Kimliği ve Bağlantı (IP_ID)",
        "AXI4-Lite köprüsü üzerinden ARINC 429 IP çekirdeğine erişilebildiğini ve doğru IP'nin cevap verdiğini doğrular.",
        "IP_ID register'ının 0x41343239 ('A429') değerini döndürdüğünü ve bus hatası (SLVERR/DECERR) oluşmadığını kontrol eder.",
        "Yanlış taban adresi (IP_BASE), FPGA reset altında, saat (CLK) durmuş veya AXI4-Lite interconnect yönlendirme hatası.",
    ),
    "prep": TestDoc(
        "prep", "Hazırlık: Soft Reset, Logger ve Checker",
        "IP'yi temiz başlangıç durumuna getirip timestamp sayacını, kanal logger'larını ve TX BIT Checker'ı etkinleştirir.",
        "SOFT_RESET sonrası sayaçların sıfırlandığını, TS_CTRL / CTRL.ENABLE / TB_CHK_CTRL bitlerinin aktif olduğunu kontrol eder.",
        "Reset hattı kilitli, AXI yazma erişimi engelli veya IP donanım yapılandırması register haritasıyla uyuşmuyor.",
    ),
    "idle": TestDoc(
        "idle", "Hat Boşta Seviyesi (NULL 00, SYNC_WAIT = 0)",
        "Verici gönderim yapmıyorken ARINC 429 diferansiyel hattının temiz NULL (00) seviyesinde olduğunu ve alıcının senkron bekleyişte kilitlenmediğini doğrular.",
        "Her seçili kanalda STATUS.LINE_HIGH=0, STATUS.LINE_LOW=0 ve STATUS.SYNC_WAIT=0 (STATUS & 0x7000 == 0) koşulunu kontrol eder.",
        "Alıcı entegre çıkışları ters/kısa devre, diferansiyel hatta sabit DC ofset / pull-up arızası, hat sürücüsü beslemesi yok veya sürekli gürültü.",
    ),
    "polarity": TestDoc(
        "polarity", "Hat Polaritesi (Override HIGH / LOW / NULL)",
        "TX hattı manuel override (TX_EXT_LINE) ile sırasıyla LOW (01), HIGH (10) ve NULL (00) sürülerek fiziksel kablolama, sürücü ve alıcı polaritesi test edilir.",
        "Her adımda 30 µs beklendikten sonra alıcı STATUS.LINE_HIGH / LINE_LOW bitlerinin sürülen polariteyle bire bir eşleştiğini doğrular.",
        "Loopback kablosu kopuk/takılı değil (sürekli NULL), A ve B telleri ters bağlanmış (HIGH↔LOW ters), sürücü (HI-8597) veya alıcı (HI-8591) entegre arızası.",
    ),
    "single": TestDoc(
        "single", "Tek Word (Word Builder + Odd Parity)",
        "Word Builder (Label, SDI, Data, SSM, Odd Parity) donanım yolunu ve tüm alıcıların tek Word'ü hatasız yakaladığını doğrular.",
        "TX_WORD_CNT +1, seçili tüm RX/TB kanallarında WORD_CNT +1, ERR_CNT +0, LAST_WORD beklenen bit düzeninde ve TB_CHK_OK_CNT +1.",
        "HS/LS saat veya preset uyuşmazlığı, Label bit sırası hatası, sürücü SLP pini arızası, kablo kopuk veya alıcı eşik gerilimi sorunu.",
    ),
    "single_hs": TestDoc(
        "single_hs", "HS Tek Word (100 kbps · Word Builder + Odd Parity + TB)",
        "High Speed (100 kbps) modda Word Builder ile oluşturulan tek ARINC 429 Word'ünün tüm alıcılarda ve TX BIT Checker'da hatasız alındığını doğrular.",
        "HS preset'te TX_WORD_CNT +1, tüm kanallarda WORD_CNT +1, ERR_CNT +0, LAST_WORD eşleşmesi ve TB_CHK OK/ERR/OVF kontrolü.",
        "HS 100 kbps yol arızası, kablo kopuk, sürücü SLP=1 geçiş sorunu, alıcı HS pencere dışı bit süresi veya TB Checker uyumsuzluğu.",
    ),
    "single_ls": TestDoc(
        "single_ls", "LS Tek Word (12.5 kbps · Word Builder + SLP + TB)",
        "Low Speed (12.5 kbps) modda sürücü SLP=0 (yavaş eğim) geçişiyle tek Word gönderilip tüm alıcılarda hatasız alındığını doğrular.",
        "LS preset'te TX_WORD_CNT +1, tüm kanallarda WORD_CNT +1, ERR_CNT +0, LAST_WORD eşleşmesi ve TB_CHK kontrolü.",
        "Sürücü SLP pini FPGA'ya bağlı değil veya ters, LS 12.5 kbps preset zamanlaması/saat frekansı hatalı, kablo kopuk.",
    ),
    "pattern": TestDoc(
        "pattern", "Veri Bütünlüğü Deseni (Uç Desenler + Walking-1)",
        "0x00000000, 0x7FFFFFFF, 0x55555555, 0x2AAAAAAA ve tüm bit pozisyonlarını tarayan desenlerle tek-bit bozulma, sıkışmış bit ve crosstalk arar.",
        "Gönderilen her Word'ün tüm kanallarda bire bir (LAST_WORD) ve sıfır hata (ERR_CNT +0) ile alındığını doğrular.",
        "Hat yansıması/sonlandırma eksikliği, uzun ardışık aynı polaritede (0x00/0x7F) AC kuplaj düşümü, crosstalk veya tek bit düşmesi.",
    ),
    "pattern_hs": TestDoc(
        "pattern_hs", "HS Veri Bütünlüğü (Uç Desenler + xorshift32)",
        "High Speed (100 kbps) hızda 6 sabit uç desen (0x00.., 0x7F.., 0x55.., 0x2A.., 0x0F.., 0x70..) + her turda değişen 4 rastgele xorshift32 Odd-Parity Word gönderir.",
        "10 Word'ün her birinde TX/RX WORD_CNT +1, ERR_CNT +0, LAST_WORD bit-birebir eşleşme ve TB_CHK doğrulaması yapar.",
        "HS hızda sinyal bütünlüğü bozulması, kablo sonlandırma/empedans uyumsuzluğu, gürültü kaynaklı tek-bit çevrilmesi veya stuck-bit.",
    ),
    "pattern_ls": TestDoc(
        "pattern_ls", "LS Veri Bütünlüğü (Uç Desenler + xorshift32)",
        "Low Speed (12.5 kbps) hızda 6 uç desenle hat kararlılığını ve uzun 40 µs darbelerde bozulma olmadığını doğrular.",
        "6 Word'ün her birinde WORD_CNT +1, ERR_CNT +0, LAST_WORD eşleşmesi ve TB_CHK kontrolü yapar.",
        "LS hızda hat kapasitansı/sürücü yükleme sorunu, düşük frekansta gürültü veya kablo temassızlığı.",
    ),
    "burst": TestDoc(
        "burst", "Art Arda Gönderim (Minimum 4-bit Gap Burst)",
        "Message Scheduler ile minimum standart 4-bit Word Gap (+1 clk) kullanarak art arda çok sayıda Word gönderir; alıcı ve FIFO kayıpsızlığını test eder.",
        "TX_SCHED_COUNT ile gönderilen tüm Word'lerin tüm kanallarda eksiksiz (WORD_CNT +N, ERR_CNT +0, DROP_CNT +0) ve TB_CHK taşmasız (FIFO_OVF=0) alındığını doğrular.",
        "Minimum 4-bit gap sonrası decoder toparlanma gecikmesi, alıcı/TB_CHK FIFO taşması, kablo gevşekliği veya ara paket kaybı.",
    ),
    "burst_hs": TestDoc(
        "burst_hs", "HS Minimum 4-bit Gap Burst (TX_SCHED_COUNT)",
        "HS (100 kbps) modda donanımsal TX_SCHED_COUNT ile art arda minimum 4-bit aralıklı burst göndererek yüksek bant genişliğinde kayıpsız alımı doğrular.",
        "Tüm burst Word'lerinin TX/RX/TB WORD_CNT sayacında tam eşleştiğini, ERR_CNT +0 olduğunu ve TB_CHK_STATUS.FIFO_OVF=0 kaldığını kontrol eder.",
        "HS minimum gap sınırında alıcı senkron kaybı, sürücü/alıcı ısınması, TB_CHK FIFO taşması veya ara temassızlık.",
    ),
    "burst_ls": TestDoc(
        "burst_ls", "LS Minimum 4-bit Gap Burst (TX_SCHED_COUNT)",
        "LS (12.5 kbps) modda minimum 4-bit aralıklı art arda gönderim yaparak düşük hızda paket kaybı veya zaman aşımı olmadığını doğrular.",
        "LS burst sonunda WORD_CNT +N, ERR_CNT +0, LAST_WORD ve TB_CHK OK/ERR/OVF kontrolü yapar.",
        "LS hızda scheduler zaman aşımı, TB_CHK timeout penceresi yetersizliği veya paket kaybı.",
    ),
    "period": TestDoc(
        "period", "Scheduler Periyodu ve Gap Ölçümü",
        "Message Scheduler'ın belirlenen INTER_WORD_GAP ile sabit periyotta Word ürettiğini ve alıcı timestamp/gap ölçümünün doğruluğunu test eder.",
        "Ardışık Word timestamp farklarının beklenen periyotla, ölçülen WORD_RD_GAP değerinin ise TX gap + IWG ile tolerans içinde eşleştiğini doğrular.",
        "FPGA saat frekansı ayarı yanlış, scheduler periyot sayacı sapması veya timestamp/gap ölçüm hatası.",
    ),
    "switch": TestDoc(
        "switch", "HS ↔ LS Hız Geçişi (Sürücü SLP + Alıcı)",
        "TX ve tüm alıcıları art arda HS ↔ LS hızları arasında çevirip her geçişten hemen sonra gönderilen ilk Word'ün kayıpsız alındığını doğrular.",
        "Her hız geçişinde settle sonrası gönderilen Word'ün WORD_CNT +1, ERR_CNT +0 ve LAST_WORD bire bir eşleştiğini kontrol eder.",
        "Hız geçişinde sürücü SLP pini yavaş oturuyor, alıcı config shadow→active geçişinde kilitlenme veya ilk Word kaybı.",
    ),
    "parity": TestDoc(
        "parity", "Parity Hatası Tespiti (Even → ERR + Toparlanma)",
        "Bilerek yanlış (Even) parity'li bir Word gönderip alıcının bunu reddettiğini, Error RAM'e PARITY kodu yazdığını ve hemen ardından doğru (Odd) Word ile toparlandığını doğrular.",
        "Hatalı Word'de WORD_CNT +0, ERR_CNT >= 1, ERR_RD_INFO'da Parity Error (bit 7) + ERR_RD_DATA == hatalı Word; ardından doğru Word'de WORD_CNT +1.",
        "Alıcı parity kontrolü kapalı/bozuk, Error RAM okuma pointer'ı hatalı, hata sonrası ST_ERR_RECOVERY kilitlenmesi veya kablo kopuk.",
    ),
    "mismatch": TestDoc(
        "mismatch", "Hız Uyuşmazlığı Tespiti (HS/LS ↔ LS/HS)",
        "TX HS / RX LS ve TX LS / RX HS kombinasyonlarıyla yanlış hızdaki sinyallerin asla geçerli Word olarak kabul edilmediğini ve LS→HS yönünde Pulse Stuck hatası üretildiğini doğrular.",
        "Her iki yönde WORD_CNT +0; TX LS / RX HS yönünde Error RAM'de Pulse Stuck (bit 5) raporlandığını kontrol eder.",
        "Alıcı pulse/bit süre penceresi fazla geniş, glitch filtresi yanlış veya TX/RX hız seçimi donanıma uygulanmıyor.",
    ),
    "gapviol": TestDoc(
        "gapviol", "Gap İhlali Tespiti (2-bit Gap → Gap Violation)",
        "Custom TX ile standart 4-bit yerine 2-bit Word Gap (ACT_GAP / 2) ile art arda 3 Word gönderip alıcının Gap Violation hatası ürettiğini ve HS'e dönünce hemen toparlandığını doğrular.",
        "2-bit gap'li burst'te WORD_CNT +0 ve Error RAM'de Gap Violation (bit 2); HS preset'e dönünce gönderilen toparlanma Word'ünde WORD_CNT +1 ve TB_CHK temiz.",
        "Alıcı min-gap detektörü (4×min_bit) çalışmıyor, Custom TX gap uygulanmıyor, eski TX_INTER_WORD_GAP yüksek kalmış veya toparlanma sonrası senkron kaybı.",
    ),
    "bittime": TestDoc(
        "bittime", "Bit Zamanlaması & Hat Gürültüsü (Bit Diagnostic)",
        "Alınan gerçek bir Word'ün 32 bitinin tamamında ölçülen pulse/null/bit sürelerinin alıcının aktif kabul penceresi içinde olduğunu doğrular ve maksimum hat gürültüsünü (glitch clk) kaydeder.",
        "Önce send_chk_one ile taze Word alımını doğrular (kopuk kablo bayat RAM'le geçemez), ardından BIT_RAM'deki 32 bitin pulse ve bit sürelerini ACT_PULSE / ACT_BIT pencereleriyle karşılaştırır.",
        "Loopback kablosu kopuk (WORD_CNT artmadı), sürücü/alıcı tPHL–tPLH gecikme asimetrisi nedeniyle pulse daralması/genişlemesi, yanlış saat frekansı veya aşırı hat gürültüsü.",
    ),
    "logger": TestDoc(
        "logger", "Logger Kontrolü (ENABLE / FREEZE / GLOBAL_FREEZE)",
        "Kanal logger'ının ENABLE=0 iken kayıt almadığını, FREEZE=1 ve GLOBAL_FREEZE=1 iken gelen Word'leri RAM'e yazmayıp DROP_CNT sayacını artırdığını ve normal moda dönüşünü doğrular.",
        "ENABLE=0 → WORD+0, DROP+0; FREEZE=1 → WORD+0, DROP+1; GLOBAL_FREEZE=1 → WORD+0, DROP+1; normale dönüşte WORD+1.",
        "Logger enable/freeze sinyalleri bağlı değil, DROP_CNT artmıyor, GLOBAL_FREEZE kanallara ulaşmıyor veya kablo kopuk.",
    ),
    "custom": TestDoc(
        "custom", "Config Sekmesi Custom Config ile Alım",
        "Config sekmesinde hesaplanan Custom TX ve Custom RX zamanlama register'larını karta yazıp geri okuyarak özel ayarlarla veri bütünlüğü ve bit zamanlamasını doğrular.",
        "Custom yazma + geri okuma doğrulaması, ardından HS desen ve Bit Diagnostic testlerinin geçmesi.",
        "Config sekmesindeki özel zamanlama değerleri donanım sınırları dışında veya Custom APPLY darbesi uygulanmıyor.",
    ),
    # ---- Ballard Dış Doğrulama testleri ----
    "bb_init": TestDoc(
        "bb_init", "Ballard Cihaz Bağlantısı ve Kanal Açılışı",
        "BTICARD64.DLL / BTI42964.DLL üzerinden Ballard BusBox/OmniBusBox cihazını açıp seçilen RX ve TX kanallarını başlatır.",
        "CardOpen, CoreOpen, kanal tip kontrolü ve cihaz seri numarası / model bilgisini doğrular.",
        "Ballard USB/PCIe bağlantısı yok, DLL bulunamadı/64-bit uyumsuz, cihaz başka bir uygulama tarafından kilitli.",
    ),
    "tx_single": TestDoc(
        "tx_single", "Kart TX → Ballard RX: Tek Word ve Bit Sırası",
        "Kart TX'in ürettiği ARINC 429 Word'ünü bağımsız Ballard alıcısında doğrulayarak Label bit sırası, SDI, Data, SSM ve Odd Parity doğruluğunu kanıtlar.",
        "Ballard RX tarafında tam 1 Word, 0 hata ve bit-birebir veri eşleşmesi.",
        "Kart TX → Ballard RX kablosu kopuk veya A/B ters, yanlış Ballard RX kanal numarası seçili, kart TX sürücüsü arızalı.",
    ),
    "tx_pattern": TestDoc(
        "tx_pattern", "Kart TX → Ballard RX: Veri Bütünlüğü Deseni",
        "Kart TX'ten uç desenler ve walking-1 Word'leri gönderip bağımsız Ballard alıcısında tek-bit bozulma olmadığını doğrular.",
        "Gönderilen tüm desen Word'lerinin Ballard RX'te eksiksiz ve bire bir alındığını kontrol eder.",
        "Kart TX sinyal bütünlüğü bozuk, A/B polarite ters, empedans uyumsuzluğu veya ara bit hatası.",
    ),
    "tx_period": TestDoc(
        "tx_period", "Kart TX → Ballard RX: Bağımsız Saat Sapması ve Periyot",
        "Kart TX Scheduler'ın gönderdiği periyodik mesajları Ballard'ın bağımsız osilatörlü zaman damgasıyla ölçerek FPGA saat sapmasını (ppm) tespit eder.",
        "Ballard timestamp farklarının beklenen periyotla eşleşmesini ve saat sapmasının ARINC 429 toleransı içinde kalmasını doğrular.",
        "FPGA kristal/PLL saat frekansı hatalı veya kaymış, CLK_HZ ayarı gerçek kart saatiyle uyuşmuyor.",
    ),
    "tx_burst": TestDoc(
        "tx_burst", "Kart TX → Ballard RX: Minimum Gap Burst",
        "Kart TX'in minimum 4-bit gap ile gönderdiği art arda Word'lerin bağımsız Ballard alıcısında kayıpsız alındığını doğrular.",
        "Gönderilen tüm burst Word'lerinin Ballard RX'te eksiksiz ve hatasız sayıldığını kontrol eder.",
        "Kart TX minimum 4-bit gap süresi standarttan kısa, sürücü toparlanma gecikmesi veya paket kaybı.",
    ),
    "tx_parity_err": TestDoc(
        "tx_parity_err", "Kart TX → BusBox RX: Hatalı Parity Üretimi",
        "Kart TX'ten bilerek Even parity'li Word gönderip bağımsız Ballard alıcısının bunu parity hatası olarak yakaladığını doğrular.",
        "Ballard RX hata bayrağının (parity) tetiklendiğini ve ardından normal Word ile alımın sürdüğünü kontrol eder.",
        "Kart TX parity biti üretimi hatalı veya Ballard RX parity denetimi kapalı.",
    ),
    "tx_switch": TestDoc(
        "tx_switch", "Kart TX → BusBox RX: HS ↔ LS Geçişi (Sürücü SLP)",
        "Kart TX hızını HS ↔ LS arasında değiştirip sürücü entegresinin SLP pini geçişinin bağımsız Ballard alıcısında temiz alındığını doğrular.",
        "Her hız geçişinde gönderilen Word'lerin Ballard RX'te eksiksiz ve sıfır hatayla alındığını kontrol eder.",
        "Sürücü SLP pini bağlı değil/ters, hız geçişinde ilk Word düşüyor veya preset zamanlaması hatalı.",
    ),
    "rx_single": TestDoc(
        "rx_single", "BusBox TX → Kart RX: Tek Word Alımı",
        "Referans Ballard vericisinden gönderilen Word'ün seçili tüm Kart RX kanallarında hatasız alındığını doğrular.",
        "Seçili her Kart RX kanalında WORD_CNT +1, ERR_CNT +0 ve LAST_WORD bire bir eşleşme.",
        "Ballard TX → Kart RX kablosu kopuk veya A/B ters, yanlış Ballard TX kanalı seçili, Kart RX alıcı entegre arızalı.",
    ),
    "rx_pattern": TestDoc(
        "rx_pattern", "BusBox TX → Kart RX: Veri Bütünlüğü Deseni",
        "Ballard referans vericisinden uç desenler gönderip Kart RX alıcılarının tüm bit pozisyonlarını hatasız çözdüğünü doğrular.",
        "Tüm seçili Kart RX kanallarında eksiksiz ve hatasız Word eşleşmesi.",
        "Kart RX alıcı eşiği/gürültü bağışıklığı sorunu, kablo temassızlığı veya polarite hatası.",
    ),
    "rx_bittime": TestDoc(
        "rx_bittime", "BusBox TX → Kart RX: Bağımsız Bit Zamanlaması",
        "Referans Ballard sinyalinin Kart RX Bit Diagnostic birimiyle ölçülen pulse/bit sürelerini kontrol ederek Kart RX zamanlama doğruluğunu kanıtlar.",
        "Tüm seçili Kart RX kanallarında ölçülen pulse ve bit sürelerinin aktif kabul penceresi içinde olduğunu doğrular.",
        "FPGA saat frekansı sapması, Kart RX alıcı gecikme asimetrisi veya aşırı hat gürültüsü.",
    ),
    "rx_burst": TestDoc(
        "rx_burst", "BusBox TX → Kart RX: Minimum Gap Burst",
        "Ballard'dan art arda minimum aralıklı mesajlar gönderip Kart RX kanallarının kayıpsız alımını doğrular.",
        "Her Kart RX kanalında gönderilen tüm Word'lerin WORD_CNT +N, ERR_CNT +0, DROP_CNT +0 ile yakalandığını kontrol eder.",
        "Kart RX min-gap toparlanması veya logger/RAM kayıt hızı sorunu.",
    ),
    "rx_parity_err": TestDoc(
        "rx_parity_err", "BusBox TX → Kart RX: Parity Hatası Enjeksiyonu",
        "Ballard'dan bilerek hatalı parity'li Word gönderip Kart RX'in bunu reddedip Error RAM'e Parity Error yazdığını doğrular.",
        "WORD_CNT +0, ERR_CNT >= 1 ve Error RAM'de Parity Error kodu; ardından doğru Word ile toparlanma.",
        "Kart RX parity detektörü kapalı veya hata sonrası toparlanma sorunu.",
    ),
    "rx_mismatch": TestDoc(
        "rx_mismatch", "BusBox TX → Kart RX: Hız Uyuşmazlığı Reddi",
        "Ballard ve Kart RX farklı hızlarda (HS↔LS) iken hiçbir hatalı Word'ün kabul edilmediğini doğrular.",
        "Her iki hız uyuşmazlığı yönünde WORD_CNT +0 ve beklenen hata kaydı.",
        "Kart RX hız/pencere ayarları fazla gevşek veya config uygulanmıyor.",
    ),
    "rx_switch": TestDoc(
        "rx_switch", "BusBox TX → Kart RX: HS ↔ LS Geçişi",
        "Ballard TX ve Kart RX hızları HS ↔ LS arasında değiştirilerek Kart RX'in her geçiş sonrası ilk Word'ü kayıpsız yakaladığını doğrular.",
        "Her hız geçişinde tüm seçili Kart RX kanallarında WORD_CNT +1, ERR_CNT +0 ve LAST_WORD eşleşmesi.",
        "Kart RX config geçişinde kilitlenme, alıcı eşik/filtre oturma gecikmesi veya ilk Word kaybı.",
    ),
    "duplex": TestDoc(
        "duplex", "Eşzamanlı Çift Yönlü (Full-Duplex) Aktarım",
        "Kart TX → Ballard RX ve Ballard TX → Kart RX yönlerini aynı anda çalıştırarak kart üzerindeki sürücü ve alıcılar arasında çapraz karışma (crosstalk) olmadığını doğrular.",
        "Her iki yönde aynı anda gönderilen tüm Word'lerin eksiksiz ve sıfır hatayla alındığını kontrol eder.",
        "PCB üzerinde TX→RX çapraz kuplaj/gürültü, ortak besleme düşümü veya topraklama sorunu.",
    ),
}


def get_test_doc(tid: str, fallback_title: str = "", fallback_hint: str = "") -> TestDoc:
    if tid in TEST_DOCS:
        return TEST_DOCS[tid]
    return TestDoc(
        tid,
        fallback_title or tid,
        "Bu test seçili ARINC 429 donanım yolunun beklenen protokol davranışını doğrular.",
        "Register sayaçları, alınan veri ve hata kodları üzerinden doğrulama yapılır.",
        fallback_hint or "Kablolama, hız/preset uyuşmazlığı veya sürücü/alıcı entegre hatası.",
    )


def format_test_info_html(doc: TestDoc, fail_detail: str = "") -> str:
    esc = _html.escape
    parts = [
        f"<h3 style='margin:0 0 8px 0;'>{esc(doc.title)}</h3>",
        f"<p><b>Ne test eder?</b><br>{esc(doc.what)}</p>",
        f"<p><b>Neyi kontrol eder?</b><br>{esc(doc.checks)}</p>",
        f"<p><b>Kalırsa olası kök nedenler:</b><br>{esc(doc.causes)}</p>",
    ]
    if fail_detail:
        parts.append(
            "<div style='margin-top:10px;padding:8px 10px;border-radius:6px;"
            "background:rgba(198,40,40,0.12);border:1px solid rgba(198,40,40,0.45);'>"
            f"<b>Bu oturumdaki kayıtlı hata:</b><br><span style='font-family:monospace;'>{esc(fail_detail)}</span>"
            "</div>"
        )
    return "".join(parts)


# =====================================================================================
# Tek-dosya zengin HTML test raporu (PCS, Loopback ve Ballard için)
# =====================================================================================
_HTML_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f4f6fa; color: #1b2430; margin: 0; padding: 24px; line-height: 1.45; }
.wrap { max-width: 1120px; margin: 0 auto; background: #fff; border: 1px solid #d7dfeb;
        border-radius: 10px; padding: 24px 28px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
h1 { margin: 0 0 4px 0; font-size: 20px; color: #0f295c; }
.sub { color: #5a6475; font-size: 13px; margin-bottom: 18px; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 20px 0; }
.card { background: #f6f8fc; border: 1px solid #d7dfeb; border-radius: 8px; padding: 10px 14px; min-width: 130px; }
.card .k { font-size: 11px; color: #5a6475; text-transform: uppercase; letter-spacing: 0.4px; }
.card .v { font-size: 18px; font-weight: 700; margin-top: 2px; font-family: ui-monospace, Consolas, monospace; }
.ok { color: #1b7a34; } .err { color: #c62828; } .warn { color: #c46b00; } .muted { color: #5a6475; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.b-ok { background: #e6f4ea; color: #1b7a34; }
.b-err { background: #fdecea; color: #c62828; }
.b-warn { background: #fff4e5; color: #b25e00; }
.b-muted { background: #eef1f7; color: #5a6475; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 20px 0; font-size: 13px; }
th { text-align: left; background: #eef2f8; color: #24324a; padding: 8px 10px; border-bottom: 2px solid #cfd8e6; }
td { padding: 8px 10px; border-bottom: 1px solid #e7ecf3; vertical-align: top; }
tr:nth-child(even) td { background: #fafbfd; }
.desc { font-size: 11.5px; color: #5a6475; margin-top: 3px; }
.cause { font-size: 11.5px; color: #9a2020; margin-top: 3px; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
.logbox { background: #121721; color: #e2e8f0; padding: 12px 14px; border-radius: 8px;
          font-family: ui-monospace, Consolas, monospace; font-size: 12px; white-space: pre-wrap;
          max-height: 360px; overflow: auto; }
.log-err { color: #ff7b72; } .log-ok { color: #7ee787; } .log-warn { color: #f2cc60; } .log-info { color: #9bb1cf; }
h2 { font-size: 15px; color: #1b2f57; margin: 20px 0 8px 0; border-bottom: 1px solid #e4eaf3; padding-bottom: 4px; }
"""


def build_html_report(report: dict, log_entries: list[tuple[str, str]] | None = None) -> str:
    """PCS, Loopback veya Ballard rapor sözlüğünü tek-dosya zengin HTML raporuna dönüştürür."""
    esc = _html.escape
    mode = report.get("mode", "loopback")
    ts = esc(str(report.get("timestamp") or report.get("started") or ""))

    if mode == "pcs":
        st_cls = "b-err" if report.get("pcs_err") or report.get("last_round_failed") else (
            "b-ok" if report.get("total_rounds", 0) > 0 and report.get("fail_rounds", 0) == 0 else "b-warn"
        )
        st_txt = "PCS HATA" if report.get("pcs_err") else (
            "GEÇTİ" if report.get("passed") else (
                "HATA İLE DURDU" if report.get("run_state") == "HATA İLE DURDU"
                else ("KALDI" if report.get("fail_rounds") else report.get("run_state", ""))
            )
        )
        total = int(report.get("total_rounds", 0))
        passed_n = int(report.get("pass_rounds", 0))
        failed_n = int(report.get("fail_rounds", 0))
        rate = f"{(100.0 * passed_n / total):.2f}%" if total else "—"
        streak = int(report.get("consec_pass", 0))
        body = [
            f"<h1>ARINC 429 Otonom Periyodik Test Raporu (AXIL Studio PCS) "
            f"<span class='badge {st_cls}'>{esc(st_txt)}</span></h1>",
            f"<div class='sub'>Tarih: {ts} · PCS: 0x{report['pcs_base']:08X} ({esc(report['pcs_state'])}, "
            f"PC={report['pcs_pc']}, {report['imem_cnt']}/{report['imem_size']} komut) · "
            f"IP: 0x{report['ip_base']:08X} · Saat: {report['clk_hz']/1e6:g} MHz · Aralık: {report['gap_ms']} ms</div>",
            "<div class='cards'>"
            f"<div class='card'><div class='k'>Toplam Tur</div><div class='v'>{total}</div></div>"
            f"<div class='card'><div class='k'>Hatasız Tur</div><div class='v ok'>{passed_n}</div></div>"
            f"<div class='card'><div class='k'>Hatalı Tur</div><div class='v {'err' if failed_n else ''}'>{failed_n}</div></div>"
            f"<div class='card'><div class='k'>Başarı Oranı</div><div class='v'>{rate}</div></div>"
            f"<div class='card'><div class='k'>Son Hatasız Seri</div><div class='v ok'>{streak}</div></div>"
            f"<div class='card'><div class='k'>Son Tur Süresi</div><div class='v'>{report['last_dur_ms']} ms</div></div>"
            f"<div class='card'><div class='k'>Maks. Gürültü</div><div class='v'>{report['max_noise_clk']} clk</div></div>"
            "</div>",
            "<h2>Test Sonuçları ve Teknik Açıklamalar</h2>"
            "<table><thead><tr><th>Son Tur</th><th>Test ve Açıklama</th><th>Hatalı / Toplam</th>"
            "<th>Kalan Hat(lar)</th><th>Kök Neden / Not</th></tr></thead><tbody>",
        ]
        for x in report.get("tests", []):
            doc = get_test_doc(x["tid"], x["title"], x.get("hint", ""))
            fch = ", ".join(x.get("fail_channels") or ()) or "—"
            if total == 0:
                b = "<span class='badge b-muted'>BEKLİYOR</span>"
            elif x.get("last_failed"):
                b = "<span class='badge b-err'>KALDI</span>"
            else:
                b = "<span class='badge b-ok'>GEÇTİ</span>"
            cause = f"<div class='cause'>Olası neden: {esc(doc.causes)}</div>" if x["fails"] else "<span class='ok'>Hata yok</span>"
            body.append(
                f"<tr><td>{b}</td>"
                f"<td><b>{esc(x['title'])}</b><div class='desc'>{esc(doc.what)}</div></td>"
                f"<td class='mono {'err' if x['fails'] else 'ok'}'>{x['fails']} / {total}</td>"
                f"<td class='mono'>{esc(fch)}</td>"
                f"<td>{cause}</td></tr>"
            )
        body.append("</tbody></table>")

        if report.get("channels"):
            body.append("<h2>Hat / Kanal Bazlı Kalma Sayaçları</h2><table><thead><tr>"
                        "<th>Hat / Kanal</th><th>Toplam Hata</th><th>Durum</th></tr></thead><tbody>")
            for c in report["channels"]:
                cls = "b-warn" if c["fails"] else "b-ok"
                txt = f"{c['fails']} hata kaydedildi" if c["fails"] else "Temiz"
                body.append(
                    f"<tr><td class='mono'><b>{esc(c['name'])}</b></td>"
                    f"<td class='mono'>{c['fails']}</td>"
                    f"<td><span class='badge {cls}'>{esc(txt)}</span></td></tr>"
                )
            body.append("</tbody></table>")

        for label, key in (("İlk Yakalanan Hata", "first_fail"), ("Son Yakalanan Hata", "last_fail")):
            rec = report.get(key)
            if not rec or (key == "last_fail" and rec == report.get("first_fail")):
                continue
            body.append(
                f"<h2>{label}</h2><div class='card'><div class='mono err'>"
                f"Tur #{rec['round']} · [Hat: {esc(rec['channel'])}] · {esc(rec['test_title'])}<br>"
                f"Neden (Kod {rec['sub_code']}): {esc(rec['reason'])} — "
                f"beklenen 0x{rec['expected']:08X}, okunan 0x{rec['got']:08X}</div></div>"
            )

        if log_entries:
            body.append("<h2>Hata ve Durum Akışı (Log)</h2><div class='logbox'>")
            for level, line in log_entries:
                cls = {"err": "log-err", "ok": "log-ok", "warn": "log-warn"}.get(level, "log-info")
                body.append(f"<div class='{cls}'>{esc(line)}</div>")
            body.append("</div>")
    else:
        mode_name = "Ballard Dış Doğrulama Test Raporu" if mode == "ballard" else "ARINC 429 Loopback Test Raporu"
        counts = report.get("counts", {})
        ok = bool(report.get("passed"))
        st_cls = "b-ok" if ok else ("b-warn" if report.get("aborted") else "b-err")
        st_txt = "GEÇTİ" if ok else ("DURDURULDU" if report.get("aborted") else "KALDI")
        chans = list(report.get("channels") or ())
        if not chans and isinstance(report.get("setup"), dict):
            s = report["setup"]
            chans = list(s.get("rx") or ()) + (["TB"] if s.get("tb") else [])
        extra_sub = ""
        if mode == "ballard" and isinstance(report.get("ballard"), dict):
            bb = report["ballard"]
            extra_sub = f" · Ballard: Kart #{bb.get('card', 0)} Core #{bb.get('core', 0)} {esc(str(bb.get('product', '')))} (RX CH{bb.get('rx_chan')}, TX CH{bb.get('tx_chan')})"
        body = [
            f"<h1>{esc(mode_name)} <span class='badge {st_cls}'>{st_txt}</span></h1>",
            f"<div class='sub'>Tarih: {ts} · Süre: {report.get('duration_s', 0)} s · "
            f"Kanallar: {esc(', '.join(chans) or '—')}{extra_sub}</div>",
            "<div class='cards'>"
            f"<div class='card'><div class='k'>Geçen</div><div class='v ok'>{counts.get('PASS', 0)}</div></div>"
            f"<div class='card'><div class='k'>Kalan</div><div class='v err'>{counts.get('FAIL', 0) + counts.get('ERROR', 0)}</div></div>"
            f"<div class='card'><div class='k'>Atlanan</div><div class='v muted'>{counts.get('SKIP', 0)}</div></div>"
            f"<div class='card'><div class='k'>Süre</div><div class='v'>{report.get('duration_s', 0)} s</div></div>"
            "</div>",
            "<h2>Test Sonuçları ve Ayrıntılı Kontroller</h2>"
            "<table><thead><tr><th>Sonuç</th><th>Test</th><th>Hız</th><th>Süre</th><th>Kontroller & Açıklama</th></tr></thead><tbody>",
        ]
        for r in report.get("results", []):
            is_d = isinstance(r, dict)
            st = r.get("status", "") if is_d else getattr(r, "status", "")
            tid = (r.get("tid") or r.get("id", "")) if is_d else getattr(r, "tid", "")
            title = r.get("title", "") if is_d else getattr(r, "title", "")
            speed = r.get("speed", "") if is_d else getattr(r, "speed", "")
            dur_s = float(r.get("duration_s", 0) if is_d else getattr(r, "duration_s", 0))
            raw_cks = r.get("checks", []) if is_d else getattr(r, "checks", [])
            raw_notes = r.get("notes", []) if is_d else getattr(r, "notes", [])
            bcls = {"PASS": "b-ok", "FAIL": "b-err", "ERROR": "b-err", "SKIP": "b-muted"}.get(st, "b-muted")
            doc = get_test_doc(tid, title)
            cks = []
            for ck in raw_cks:
                ck_d = isinstance(ck, dict)
                ck_ok = ck.get("ok") if ck_d else getattr(ck, "ok", None)
                ck_name = ck.get("name", "") if ck_d else getattr(ck, "name", "")
                ck_det = ck.get("detail", "") if ck_d else getattr(ck, "detail", "")
                mark = "✓" if ck_ok is True else ("✗" if ck_ok is False else "·")
                ccls = "ok" if ck_ok is True else ("err" if ck_ok is False else "muted")
                det = f" — {esc(str(ck_det))}" if ck_det else ""
                cks.append(f"<div class='{ccls}'>{mark} {esc(str(ck_name))}{det}</div>")
            for note in raw_notes:
                cks.append(f"<div class='warn'>! {esc(str(note))}</div>")
            cause = f"<div class='cause'>Olası neden: {esc(doc.causes)}</div>" if st in ("FAIL", "ERROR") else ""
            body.append(
                f"<tr><td><span class='badge {bcls}'>{esc(st)}</span></td>"
                f"<td><b>{esc(title)}</b><div class='desc'>{esc(doc.what)}</div></td>"
                f"<td class='mono'>{esc(speed or '—')}</td>"
                f"<td class='mono'>{dur_s:.2f} s</td>"
                f"<td>{''.join(cks)}{cause}</td></tr>"
            )
        body.append("</tbody></table>")

    return (
        "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>"
        f"<title>ARINC 429 Test Raporu</title><style>{_HTML_CSS}</style></head>"
        f"<body><div class='wrap'>{''.join(body)}</div></body></html>"
    )
