"""Dış doğrulama testi: Ballard BusBox / OmniBusBox (BTIDriver) ile ARINC 429 IP + entegre testi (GUI'siz).

Loopback testinden farkı:
- Kart TX + sürücü entegresi (line driver) bağımsız referans alıcıya (Ballard RX) karşı test edilir.
- Alıcı entegresi (line receiver) + kart RX bağımsız referans vericiye (Ballard TX) karşı test edilir.
- FPGA saat / PLL kayması, ARINC 429 bit/label sırası, arıza yönü izolasyonu (TX mi RX mi?) ve
  alıcı entegresinin gerçek gecikme asimetrisi (tPLH - tPHL) bağımsız olarak ölçülür.

Sonuç yapısı (TestResult / Check / raporlama) ``a429/selftest.py`` ile birebir aynıdır.
"""
from __future__ import annotations

import threading
import time

from . import ipmap, selftest
from .ballard import BallardError, BallardSession, CardInfo, RxRecord
from .ip import send_rx_config
from .regs import RegMap, channel_label, channel_prefix
from .selftest import Check, Ctx, SPEEDS, TestAborted, TestResult, _scheduler_run, odd_parity, pattern_words, restore
from .txlive import build_word

NOM_PULSE_US = {"HS": 5.0, "LS": 40.0}
NOM_BIT_US = {"HS": 10.0, "LS": 80.0}


class ExtCtx(Ctx):
    """Dış doğrulama bağlamı: IP bus erişimi + Ballard BusBox oturumu."""

    def __init__(
        self,
        bus,
        rm: RegMap,
        ballard,
        rx_channels: list[str],
        use_tb: bool = False,
        test_tx: bool = True,
        test_rx: bool = True,
        bb_rx_chan: int | None = None,
        bb_tx_chan: int | None = None,
        pattern_len: int = 35,
        burst_words: int = 40,
        custom: dict | None = None,
        log=None,
        stop: threading.Event | None = None,
    ):
        # RX testleri kapalıysa kart RX kanallarını izlemeye gerek yok; TX BIT seçiliyse TX testlerinde izlenir
        ip_rx = list(rx_channels) if test_rx else []
        super().__init__(bus, rm, ip_rx, use_tb=use_tb, pattern_len=pattern_len, burst_words=burst_words,
                         custom=custom, log=log, stop=stop)
        self.bb = ballard
        self.bb_info: CardInfo | None = None
        self.test_tx = bool(test_tx and bb_rx_chan is not None)
        self.test_rx = bool(test_rx and bb_tx_chan is not None and bool(ip_rx))
        self.bb_rx = bb_rx_chan if self.test_tx else None
        self.bb_tx = bb_tx_chan if self.test_rx else None
        self._bb_cfg_key: tuple | None = None

    def bb_setup(self, rx_speed: str = "HS", tx_speed: str = "HS", rx_parity: str = "odd",
                 tx_raw_parity: bool = True, force: bool = False):
        key = (self.bb_rx, self.bb_tx, rx_speed, tx_speed, rx_parity, tx_raw_parity)
        if not force and self._bb_cfg_key == key:
            self.bb.drain_rx()
            return
        self.bb.configure(
            rx_chan=self.bb_rx,
            tx_chan=self.bb_tx,
            rx_speed=rx_speed,
            tx_speed=tx_speed,
            rx_parity=rx_parity,
            tx_raw_parity=tx_raw_parity,
        )
        self._bb_cfg_key = key
        # Hız / kanal yeniden yapılandırma sonrası hattın sakinleşmesi
        self.wait_us(5000)
        self.bb.drain_rx()

    def bb_expect_rx(self, expected_n: int, speed: str, extra_s: float = 0.25) -> list[RxRecord]:
        word_s = 0.0004 if speed == "HS" else 0.0032
        timeout_s = max(0.15, expected_n * word_s * 3.0 + extra_s)
        quiet_s = 0.015 if speed == "HS" else 0.045
        return self.bb.read_rx(
            chan=self.bb_rx,
            timeout_s=timeout_s,
            min_count=expected_n,
            quiet_gap_s=quiet_s,
            stop=self.stop,
        )

    def bb_send(self, words: list[int], speed: str):
        word_s = 0.0004 if speed == "HS" else 0.0032
        budget = max(1.0, len(words) * word_s * 4.0 + 1.0)
        self.bb.send_words(words, wait_done_s=budget, stop=self.stop)
        self.settle()

    def ip_rx_chans(self) -> list[str]:
        return list(self.rx)

    def _expect_ip_rx_rejected(self, R: TestResult, s0, s1, what: str, err_bit: str | None, strict_err: bool):
        for ch in self.ip_rx_chans():
            lab = channel_label(ch)
            dw, de = self.delta(s0, s1, ch, "word"), self.delta(s0, s1, ch, "err")
            R.add(f"{lab}: {what} Word kabul edilmedi", dw == 0, f"WORD +{dw}")
            names = sorted({n for e in self.last_errors(ch, min(de, 256)) for n in e["names"]}) if de else []
            if err_bit:
                ok = de > 0 and err_bit in names
                R.add(f"{lab}: {err_bit} hatası raporlandı", ok if strict_err else (True if ok else None),
                      f"ERR +{de}: {', '.join(names) or '—'}"
                      + ("" if ok or strict_err else " (hat sinyali glitch filtresinde elendi)"))


# =====================================================================================
# Yardımcılar
# =====================================================================================
def _bb_rx_diagnose(recs: list[RxRecord], expected: list[int], bb_rx: int | None) -> str:
    if not recs:
        return (f"Ballard RX CH{bb_rx}'te sinyal yok: Kart TX → BusBox RX kablosu, sürücü entegre beslemesi "
                "veya seçili BusBox RX kanalı kontrol edilmeli")
    got = [r.word for r in recs]
    if len(got) == len(expected) and all(a == (b ^ 0xFFFFFFFF) for a, b in zip(got, expected)):
        return "tüm bitler ters: A/B hattı ters bağlı (TXA↔TXB)"
    errs = sorted({f for r in recs for f in r.error_flags})
    if errs:
        return "Ballard hata bayrakları: " + ", ".join(errs)
    return f"beklenen {len(expected)}, alınan {len(recs)} Word"


def _check_tb_echo(c: ExtCtx, R: TestResult, s0, s1, n: int, label: str = ""):
    if not c.use_tb:
        return
    dw, de = c.delta(s0, s1, "TB", "word"), c.delta(s0, s1, "TB", "err")
    dok = (s1["chk_ok"] - s0["chk_ok"]) & 0xFFFFFFFF
    derr = (s1["chk_err"] - s0["chk_err"]) & 0xFFFFFFFF
    R.add(f"{label}TX BIT (TB) yankısı ve Checker: {n} eşleşme, 0 hata",
          dw == n and de == 0 and dok == n and derr == 0,
          f"TB W+{dw} E+{de}, CHK OK+{dok} ERR+{derr}")


# =====================================================================================
# Testler
# =====================================================================================
def t_ident(c: ExtCtx, R: TestResult):
    v = c.r(["IP_ID", "IP_VERSION", "CAPS", "CLK_HZ"])
    R.add("IP_ID = 'A429'", v.get("IP_ID") == ipmap.IP_ID_WORD, f"0x{v.get('IP_ID', 0):08X}")
    ver = v.get("IP_VERSION", 0)
    R.add(f"IP sürümü {ipmap.IP_VERSION[0]}.x", (ver >> 16) & 0xFF == ipmap.IP_VERSION[0],
          f"{(ver >> 16) & 0xFF}.{(ver >> 8) & 0xFF}.{ver & 0xFF}")
    caps = v.get("CAPS", 0)
    nrx = c.rm.field("CAPS", "NUM_RX").extract(caps)
    if c.test_tx:
        R.add("IP TX kanalı var (CAPS.TX)", bool(c.rm.field("CAPS", "TX").extract(caps)))
    if c.use_tb:
        R.add("IP TX BIT kanalı var (CAPS.TXBIT)", bool(c.rm.field("CAPS", "TXBIT").extract(caps)))
    if c.test_rx:
        need = max([int(ch[2:]) + 1 for ch in c.rx] + [0])
        R.add(f"Seçilen Kart RX kanalları IP'de var (NUM_RX={nrx})", nrx >= need, ", ".join(c.rx))
    if v.get("CLK_HZ"):
        c.clk_hz = v["CLK_HZ"]
    R.measurements["clk_mhz"] = c.clk_hz / 1e6
    R.add(f"IP saati {c.clk_hz / 1e6:g} MHz", None)

    info = c.bb.open()
    c.bb_info = info
    R.add(f"Ballard cihazı açıldı: {info.display_label()}", True)
    R.measurements["ballard"] = {
        "card": info.card_num, "core": info.core_num, "product": info.product,
        "type": info.card_type, "rx_channels": info.rx_channels, "tx_channels": info.tx_channels,
        "parametric": info.parametric,
    }
    if c.test_tx:
        R.add(f"Ballard RX CH{c.bb_rx} mevcut", c.bb_rx in info.rx_channels,
              f"mevcut RX: {info.rx_channels}")
    if c.test_rx:
        R.add(f"Ballard TX CH{c.bb_tx} mevcut", c.bb_tx in info.tx_channels,
              f"mevcut TX: {info.tx_channels}")
    ok_st, msg_st = c.bb.self_test()
    R.add("Ballard donanım öz-testi (CardTest)", ok_st, msg_st)


def t_prep(c: ExtCtx, R: TestResult):
    c.w([("SOFT_RESET", 1)])
    c.wait_us(5)
    c.w([("TS_CTRL", 1)])
    c.baseline()
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 0b101)])  # ENABLE + CLEAR
    if c.use_tb:
        tim_ls = 32 * 4000 + 16000
        c.w([("TB_CHK_TIMEOUT", 3 * tim_ls)])
    c.settle()
    s = c.snap()
    for ch in c.chans:
        R.add(f"{channel_label(ch)}: logger açık, sayaçlar sıfır", s[ch]["word"] == 0 and s[ch]["err"] == 0,
              f"WORD={s[ch]['word']} ERR={s[ch]['err']}")
    c.bb_setup("HS", "HS", rx_parity="odd", tx_raw_parity=True, force=True)
    R.add("Ballard BusBox HS + 1 µs zaman damgası + Sequential Monitor hazır", True)


# ---------------------------------------------------------------- Yön 1: Kart TX -> Ballard RX
def t_tx_single(c: ExtCtx, R: TestResult, speed: str):
    """Kart TX Word Builder → Sürücü Entegre → Ballard RX: tek Word ve ARINC 429 bit/label sırası."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(tx=speed, rx=speed if c.use_tb else None, chans=["TB"] if c.use_tb else None)
    c.bb_setup(rx_speed=speed, tx_speed=speed, rx_parity="odd")
    exp = build_word(0o310, 2, 0x5A5A5, 1, odd=True)
    s0 = c.snap()
    c.w([("TX_LABEL", 0o310), ("TX_SDI", 2), ("TX_DATA", 0x5A5A5), ("TX_SSM", 1), ("TX_PARITY_TYPE", 1),
         ("TX_BUILDER_EN", 1), ("TX_SEND_CMD", 1)])
    tim = c.tx_timing()
    c.wait_us(c.us(tim["word"]))
    c.wait_tx_idle(c.us(tim["word"]) * 3 + 2000)
    c.settle()
    c.w([("TX_BUILDER_EN", 0)])
    s1 = c.snap()

    R.add("TX_WORD_CNT +1", (s1["tx"] - s0["tx"]) & 0xFFFFFFFF == 1, f"+{(s1['tx'] - s0['tx']) & 0xFFFFFFFF}")
    recs = c.bb_expect_rx(1, speed)
    ok_cnt = len(recs) == 1 and not recs[0].err
    R.add(f"Ballard RX CH{c.bb_rx}: 1 Word alındı, hata bayrağı yok", ok_cnt,
          f"alınan {len(recs)}" + ("" if ok_cnt else " → " + _bb_rx_diagnose(recs, [exp], c.bb_rx)))
    if recs:
        got = recs[0].word
        why = " → tüm bitler ters: A/B hattı ters bağlı (TXA↔TXB)" if got == (exp ^ 0xFFFFFFFF) else ""
        R.add(f"Ballard RX CH{c.bb_rx}: Word = 0x{exp:08X} (Label 0310, bit sırası uyumlu)",
              got == exp, f"0x{got:08X} (Label {got & 0xFF:03o}){why}")
    _check_tb_echo(c, R, s0, s1, 1)
    R.measurements["word"] = f"0x{exp:08X}"


def t_tx_pattern(c: ExtCtx, R: TestResult, speed: str, n: int | None = None):
    """Kart TX → Ballard RX: walking-1 / 0x55 / 0xAA veri bütünlüğü deseni."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(tx=speed, rx=speed if c.use_tb else None, chans=["TB"] if c.use_tb else None)
    c.bb_setup(rx_speed=speed, tx_speed=speed, rx_parity="odd")
    words = pattern_words(n or (c.pattern_len if speed == "HS" else max(8, c.pattern_len // 3)))
    s0 = c.snap()
    c.send_words(words)
    s1 = c.snap()
    R.add(f"TX_WORD_CNT +{len(words)}", (s1["tx"] - s0["tx"]) & 0xFFFFFFFF == len(words),
          f"+{(s1['tx'] - s0['tx']) & 0xFFFFFFFF}")
    recs = c.bb_expect_rx(len(words), speed)
    err_recs = [r for r in recs if r.err]
    R.add(f"Ballard RX CH{c.bb_rx}: {len(words)} Word alındı, hata yok",
          len(recs) == len(words) and not err_recs,
          f"alınan {len(recs)}, hatalı {len(err_recs)}"
          + ("" if len(recs) == len(words) and not err_recs else " → " + _bb_rx_diagnose(recs, words, c.bb_rx)))
    if len(recs) == len(words):
        got = [r.word for r in recs]
        bad = [i for i, (a, b) in enumerate(zip(got, words)) if a != b]
        R.add(f"Ballard RX CH{c.bb_rx}: sıra ve içerik birebir ({len(words)} Word)",
              not bad,
              "" if not bad else f"{len(bad)} fark, ilki #{bad[0]}: gönderilen 0x{words[bad[0]]:08X}, "
              f"alınan 0x{got[bad[0]]:08X}"
              + (" → tüm bitler ters: A/B hattı ters bağlı"
                 if all(a == (b ^ 0xFFFFFFFF) for a, b in zip(got, words)) else ""))
    _check_tb_echo(c, R, s0, s1, len(words))


def t_tx_period(c: ExtCtx, R: TestResult, speed: str):
    """Kart TX Scheduler → Ballard RX 1 µs timestamp: bağımsız FPGA saat ve periyot doğrulaması."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(tx=speed, rx=speed if c.use_tb else None, chans=["TB"] if c.use_tb else None)
    c.bb_setup(rx_speed=speed, tx_speed=speed, rx_parity="odd")
    tim = c.tx_timing()
    iwg = 10 * tim["bit"]
    c.w([("TX_EXT_DATA", odd_parity(0x1234567))])
    s0 = c.snap()
    period_clk = _scheduler_run(c, 8, iwg, tim)
    s1 = c.snap()
    n = (s1["tx"] - s0["tx"]) & 0xFFFFFFFF
    R.add("TX Scheduler Word gönderdi", n >= 4, f"{n} Word")
    if n < 4:
        return
    recs = c.bb_expect_rx(n, speed)
    if not R.add(f"Ballard RX CH{c.bb_rx}: {n} Word alındı, hata yok",
                 len(recs) == n and not any(r.err for r in recs),
                 f"alınan {len(recs)}" + ("" if len(recs) == n else " → " + _bb_rx_diagnose(recs, [odd_parity(0x1234567)] * n, c.bb_rx))):
        return
    diffs = [b.timestamp_us - a.timestamp_us for a, b in zip(recs, recs[1:])]
    exp_us = c.us(period_clk)
    mean_us = sum(diffs) / len(diffs)
    ppm = (mean_us - exp_us) / exp_us * 1e6
    tol_each = max(6.0, exp_us * 0.025)
    tol_mean = max(3.0, exp_us * 0.015)
    R.measurements["expected_period_us"] = round(exp_us, 3)
    R.measurements["ballard_period_us"] = [min(diffs), round(mean_us, 3), max(diffs)]
    R.measurements["clock_err_ppm"] = round(ppm, 1)
    R.add(
        f"Ballard bağımsız periyot ölçümü: {min(diffs)}…{max(diffs)} µs, ort {mean_us:.2f} µs "
        f"(beklenen {exp_us:.2f} µs, sapma {ppm:+.0f} ppm)",
        abs(mean_us - exp_us) <= tol_mean and all(abs(d - exp_us) <= tol_each for d in diffs),
        "" if abs(mean_us - exp_us) <= tol_mean else "FPGA saati / CLK_HZ veya TX bit zamanlaması kayık olabilir",
    )
    _check_tb_echo(c, R, s0, s1, n)


def t_tx_burst(c: ExtCtx, R: TestResult, speed: str):
    """Kart TX minimum 4-bit gap burst → Ballard RX: kayıpsız ve hatasız sürekli akış."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(tx=speed, rx=speed if c.use_tb else None, chans=["TB"] if c.use_tb else None)
    c.bb_setup(rx_speed=speed, tx_speed=speed, rx_parity="odd")
    tim = c.tx_timing()
    n_req = c.burst_words if speed == "HS" else max(6, c.burst_words // 4)
    wd = odd_parity(0x2468ACE)
    c.w([("TX_EXT_DATA", wd)])
    s0 = c.snap()
    _scheduler_run(c, n_req, 1, tim)
    s1 = c.snap()
    n = (s1["tx"] - s0["tx"]) & 0xFFFFFFFF
    R.measurements["words"] = n
    R.add(f"TX Scheduler {n} Word gönderdi (4-bit min gap = {c.us(tim['gap']):.1f} µs)", n >= n_req // 2)
    recs = c.bb_expect_rx(n, speed)
    errs = [r for r in recs if r.err]
    wrong = [r for r in recs if r.word != wd]
    R.add(f"Ballard RX CH{c.bb_rx}: {n}/{n} Word alındı, hata ve bozulma yok",
          len(recs) == n and not errs and not wrong,
          f"alınan {len(recs)}, hata bayrağı {len(errs)}, veri farkı {len(wrong)}"
          + ("" if len(recs) == n and not errs and not wrong else " → " + _bb_rx_diagnose(recs, [wd] * n, c.bb_rx)))
    _check_tb_echo(c, R, s0, s1, n)


def t_tx_parity_err(c: ExtCtx, R: TestResult):
    """Kart TX'ten bilerek Even parity → Ballard RX'in parity hatasını yakalaması + toparlanma."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(tx="HS", rx="HS" if c.use_tb else None, chans=["TB"] if c.use_tb else None)
    c.bb_setup(rx_speed="HS", tx_speed="HS", rx_parity="odd")
    good = odd_parity(0x0ABC123)
    bad = good ^ 0x80000000

    c.send_words([bad])
    recs = c.bb_expect_rx(1, "HS", extra_s=0.12)
    # Ballard RX: PARODD modunda parity hatalı Word ya MSGACT429_PAR ile işaretlenir ya da filtrelenir
    clean_bad = [r for r in recs if not r.err]
    par_flagged = any(r.parity_err or r.err for r in recs)
    R.add(f"Ballard RX CH{c.bb_rx}: Even parity Word hatasız kabul edilmedi",
          len(clean_bad) == 0,
          "PAR hata bayrağı ile yakalandı" if par_flagged
          else ("reddedildi (kayıt yok)" if not recs else f"HATA: hatasız alındı 0x{clean_bad[0].word:08X}"))

    c.bb.drain_rx()
    c.send_words([good])
    recs2 = c.bb_expect_rx(1, "HS")
    R.add(f"Ballard RX CH{c.bb_rx}: ardından Odd parity Word hatasız alındı",
          len(recs2) == 1 and not recs2[0].err and recs2[0].word == good,
          f"alınan {len(recs2)}" + (f" (0x{recs2[0].word:08X})" if recs2 else ""))
    c.chk_clear()


def t_tx_switch(c: ExtCtx, R: TestResult):
    """Kart TX (ve sürücü entegre SLP pini) HS ↔ LS 3 tur geçiş → Ballard RX doğrulaması."""
    if not c.test_tx:
        R.status = "SKIP"
        R.notes.append("Kart TX → Ballard RX yönü seçili değil")
        return
    c.baseline()
    k = 0
    for cycle in range(3):
        for spd in ("LS", "HS"):
            c.set_speed(tx=spd, rx=spd if c.use_tb else None, chans=["TB"] if c.use_tb else None)
            c.bb_setup(rx_speed=spd, tx_speed=spd, rx_parity="odd")
            words = [odd_parity(0x100000 * (k + 1) + 0x77), odd_parity(0x3000000 + k)]
            k += 1
            c.send_words(words)
            recs = c.bb_expect_rx(2, spd)
            ok = len(recs) == 2 and not any(r.err for r in recs) and [r.word for r in recs] == words
            R.add(f"Geçiş {cycle + 1} → {spd}: Ballard RX CH{c.bb_rx} 2 Word hatasız aldı", ok,
                  "" if ok else _bb_rx_diagnose(recs, words, c.bb_rx))
    c.set_speed(tx="HS", rx="HS" if c.use_tb else None, chans=["TB"] if c.use_tb else None)


# ---------------------------------------------------------------- Yön 2: Ballard TX -> Kart RX
def t_rx_single(c: ExtCtx, R: TestResult, speed: str):
    """Ballard TX → Alıcı Entegre → Kart RX: tek Word ve ARINC 429 bit/label sırası."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(rx=speed, chans=c.ip_rx_chans())
    c.settle()
    c.bb_setup(rx_speed=speed, tx_speed=speed, tx_raw_parity=True)
    exp = build_word(0o310, 2, 0x5A5A5, 1, odd=True)
    s0 = c.snap()
    c.bb_send([exp], speed)
    s1 = c.snap()
    for ch in c.ip_rx_chans():
        lab = channel_label(ch)
        dw, de = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err")
        good = dw == 1 and de == 0
        R.add(f"{lab}: Ballard TX CH{c.bb_tx}'ten 1 Word alındı, hata yok", good,
              f"WORD +{dw}, ERR +{de}" + ("" if good else " → " + c.diagnose(ch)))
        if dw:
            last = s1[ch]["last"]
            why = " → tüm bitler ters: A/B hattı ters bağlı (RINA↔RINB)" if last == (exp ^ 0xFFFFFFFF) else ""
            R.add(f"{lab}: LAST_WORD = 0x{exp:08X} (Label 0310, bit sırası uyumlu)",
                  last == exp, f"0x{last:08X} (Label {last & 0xFF:03o}){why}")
    R.measurements["word"] = f"0x{exp:08X}"


def t_rx_pattern(c: ExtCtx, R: TestResult, speed: str, n: int | None = None):
    """Ballard TX → Kart RX: walking-1 / 0x55 / 0xAA veri bütünlüğü deseni."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(rx=speed, chans=c.ip_rx_chans())
    c.settle()
    c.bb_setup(rx_speed=speed, tx_speed=speed, tx_raw_parity=True)
    words = pattern_words(n or (c.pattern_len if speed == "HS" else max(8, c.pattern_len // 3)))
    s0 = c.snap()
    c.bb_send(words, speed)
    s1 = c.snap()
    for ch in c.ip_rx_chans():
        lab = channel_label(ch)
        dw, de = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err")
        if not R.add(f"{lab}: {len(words)} Word alındı, hata yok", dw == len(words) and de == 0,
                     f"WORD +{dw}, ERR +{de}" + ("" if dw == len(words) and de == 0 else " → " + c.diagnose(ch))):
            continue
        got = [x["data"] for x in c.last_words(ch, len(words))]
        bad = [i for i, (a, b) in enumerate(zip(got, words)) if a != b]
        R.add(f"{lab}: Word RAM sırası ve içeriği ({len(words)} Word)",
              not bad and len(got) == len(words),
              "" if not bad else f"{len(bad)} fark, ilki #{bad[0]}: gönderilen 0x{words[bad[0]]:08X}, "
              f"alınan 0x{got[bad[0]]:08X}"
              + (" → tüm bitler ters: A/B hattı ters bağlı"
                 if all(a == (b ^ 0xFFFFFFFF) for a, b in zip(got, words)) else ""))


def t_rx_bittime(c: ExtCtx, R: TestResult, speed: str):
    """Ballard TX temiz referans sinyali → IP Bit Diagnostic: alıcı entegre zamanlama karakterizasyonu."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(rx=speed, chans=c.ip_rx_chans())
    c.settle()
    c.bb_setup(rx_speed=speed, tx_speed=speed, tx_raw_parity=True)
    words = pattern_words(2)
    c.bb_send(words, speed)
    nom_p = NOM_PULSE_US[speed]
    R.measurements["ref_pulse_us"] = nom_p
    for ch in c.ip_rx_chans():
        lab = channel_label(ch)
        win = c.rx_window(ch)
        bits = c.last_bits(ch, 2)
        if len(bits) < 64:
            R.add(f"{lab}: Bit Diagnostic kaydı", False, f"{len(bits)} bit okundu → " + c.diagnose(ch))
            continue
        pulses = [b["pulse"] for b in bits]
        bitl = [b["pulse"] + b["null"] for b in bits if b["bit"] != 31]
        nulls = [b["null"] for b in bits if b["bit"] != 31]
        noise = sum(b["perr"] + b["nerr"] for b in bits)
        mp, mn = sum(pulses) / len(pulses), sum(nulls) / len(nulls)
        mp_us = c.us(mp)
        R.measurements[ch] = {
            "pulse_us": [round(c.us(min(pulses)), 3), round(mp_us, 3), round(c.us(max(pulses)), 3)],
            "null_us": [round(c.us(min(nulls)), 3), round(c.us(mn), 3), round(c.us(max(nulls)), 3)],
            "bit_us": [round(c.us(min(bitl)), 3), round(c.us(max(bitl)), 3)],
            "rx_ic_skew_us": round(mp_us - nom_p, 3),
            "noise_clk": noise,
        }
        R.add(f"{lab}: pulse {c.us(min(pulses)):.2f}…{c.us(max(pulses)):.2f} µs, kabul {c.us(win['min_pulse']):.2f}…"
              f"{c.us(win['max_pulse']):.2f} µs", win["min_pulse"] <= min(pulses) and max(pulses) <= win["max_pulse"])
        R.add(f"{lab}: bit {c.us(min(bitl)):.2f}…{c.us(max(bitl)):.2f} µs, kabul {c.us(win['min_bit']):.2f}…"
              f"{c.us(win['max_bit']):.2f} µs", win["min_bit"] <= min(bitl) and max(bitl) <= win["max_bit"])
        R.add(f"{lab}: ortalama pulse {mp_us:.3f} µs (referans {nom_p:.1f} µs, fark {mp_us - nom_p:+.3f} µs: "
              "alıcı entegre + hat asimetrisi)", None)
        R.add(f"{lab}: hat gürültüsü (glitch clk toplamı) = {noise}", None,
              "" if noise == 0 else "gürültü var: kablo / topraklama / sonlandırma kontrol edilmeli")


def t_rx_burst(c: ExtCtx, R: TestResult, speed: str):
    """Ballard TX kesintisiz 4-bit gap burst → Kart RX: kayıpsız ve hatasız alım."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(rx=speed, chans=c.ip_rx_chans())
    c.settle()
    c.bb_setup(rx_speed=speed, tx_speed=speed, tx_raw_parity=True)
    n = c.burst_words if speed == "HS" else max(6, c.burst_words // 4)
    words = [odd_parity(((i & 0xFF) | ((i & 0x7FFFF) << 10))) for i in range(n)]
    s0 = c.snap()
    c.bb_send(words, speed)
    s1 = c.snap()
    R.measurements["words"] = n
    for ch in c.ip_rx_chans():
        lab = channel_label(ch)
        dw, de, dd = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err"), c.delta(s0, s1, ch, "drop")
        R.add(f"{lab}: {n}/{n} Word alındı, hata ve kayıp yok", dw == n and de == 0 and dd == 0,
              f"WORD +{dw}, ERR +{de}, DROP +{dd}" + ("" if dw == n else " → " + c.diagnose(ch)))


def t_rx_parity_err(c: ExtCtx, R: TestResult):
    """Ballard TX'ten Even parity enjeksiyonu → Kart RX Parity Error yakalama + toparlanma."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    c.set_speed(rx="HS", chans=c.ip_rx_chans())
    c.settle()
    c.bb_setup(rx_speed="HS", tx_speed="HS", tx_raw_parity=True)
    good = odd_parity(0x0ABC123)
    bad = good ^ 0x80000000
    s0 = c.snap()
    c.bb_send([bad], "HS")
    s1 = c.snap()
    c._expect_ip_rx_rejected(R, s0, s1, "Ballard'dan gelen hatalı parity'li", "Parity Error", strict_err=True)
    for ch in c.ip_rx_chans():
        if c.delta(s0, s1, ch, "err"):
            e = c.last_errors(ch, 1)[-1]
            R.add(f"{channel_label(ch)}: hata kaydında Word = 0x{bad:08X}", e["data"] == bad, f"0x{e['data']:08X}")
    s2 = c.snap()
    c.bb_send([good], "HS")
    s3 = c.snap()
    R.add("Ardından doğru parity'li Word tüm Kart RX kanallarında alındı",
          all(c.delta(s2, s3, ch, "word") == 1 and s3[ch]["last"] == good for ch in c.ip_rx_chans()))


def t_rx_mismatch(c: ExtCtx, R: TestResult):
    """Hız uyuşmazlığı: Ballard HS / Kart RX LS ve Ballard LS / Kart RX HS."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    for tx_spd, rx_spd, err in (("HS", "LS", "Pulse Glitch"), ("LS", "HS", "Pulse Stuck")):
        c.set_speed(rx=rx_spd, chans=c.ip_rx_chans())
        c.settle()
        c.bb_setup(rx_speed=tx_spd, tx_speed=tx_spd, tx_raw_parity=True)
        s0 = c.snap()
        c.bb_send([odd_parity(0x1ABCDEF)], tx_spd)
        s1 = c.snap()
        c._expect_ip_rx_rejected(R, s0, s1, f"Ballard {tx_spd} / Kart RX {rx_spd}:", err, strict_err=(tx_spd == "LS"))
    c.set_speed(rx="HS", chans=c.ip_rx_chans())
    c.settle()


def t_rx_switch(c: ExtCtx, R: TestResult):
    """Ballard TX → Kart RX 3 tur HS ↔ LS geçişi."""
    if not c.test_rx:
        R.status = "SKIP"
        R.notes.append("Ballard TX → Kart RX yönü seçili değil")
        return
    c.baseline()
    k = 0
    for cycle in range(3):
        for spd in ("LS", "HS"):
            c.set_speed(rx=spd, chans=c.ip_rx_chans())
            c.settle()
            c.bb_setup(rx_speed=spd, tx_speed=spd, tx_raw_parity=True)
            words = [odd_parity(0x100000 * (k + 1) + 0x55), odd_parity(0x2000000 + k)]
            k += 1
            s0 = c.snap()
            c.bb_send(words, spd)
            s1 = c.snap()
            ok = all(c.delta(s0, s1, ch, "word") == 2 and c.delta(s0, s1, ch, "err") == 0
                     and s1[ch]["last"] == words[-1] for ch in c.ip_rx_chans())
            R.add(f"Geçiş {cycle + 1} → {spd}: tüm Kart RX kanalları 2 Word aldı", ok,
                  "" if ok else "; ".join(f"{channel_label(ch)} W+{c.delta(s0, s1, ch, 'word')} "
                                          f"E+{c.delta(s0, s1, ch, 'err')}" for ch in c.ip_rx_chans()))
    c.set_speed(rx="HS", chans=c.ip_rx_chans())
    c.settle()


# ---------------------------------------------------------------- Çift yönlü + Custom
def t_duplex(c: ExtCtx, R: TestResult, speed: str):
    """Çift yönlü eşzamanlı stres: Kart TX → Ballard RX ile Ballard TX → Kart RX aynı anda."""
    if not (c.test_tx and c.test_rx):
        R.status = "SKIP"
        R.notes.append("Çift yönlü test için hem Kart TX → Ballard RX hem Ballard TX → Kart RX seçili olmalı")
        return
    c.baseline()
    c.set_speed(tx=speed, rx=speed)
    c.settle()
    c.bb_setup(rx_speed=speed, tx_speed=speed, rx_parity="odd", tx_raw_parity=True)
    n = 16 if speed == "HS" else 6
    tx_wd = build_word(0o310, 1, 0x13579, 2, odd=True)
    rx_words = [build_word(0o250, i & 3, (0x20000 + i * 17) & 0x7FFFF, 1, odd=True) for i in range(n)]

    tim = c.tx_timing()
    c.w([("TX_EXT_DATA", tx_wd)])
    s0 = c.snap()

    # Kart TX Scheduler'ı başlatırken eşzamanlı olarak Ballard TX'ten veri gönder
    tx_err: list[Exception] = []

    def _run_bb_tx():
        try:
            c.bb.send_words(rx_words, wait_done_s=max(2.0, n * 0.02 + 1.0), stop=c.stop)
        except Exception as e:  # noqa: BLE001
            tx_err.append(e)

    th = threading.Thread(target=_run_bb_tx, daemon=True)
    th.start()
    _scheduler_run(c, n, 4 * tim["bit"], tim)
    th.join(timeout=10.0)
    c.settle()
    s1 = c.snap()

    if tx_err:
        raise tx_err[0]

    sent_n = (s1["tx"] - s0["tx"]) & 0xFFFFFFFF
    recs = c.bb_expect_rx(sent_n, speed)
    ok_tx = len(recs) == sent_n and not any(r.err for r in recs) and all(r.word == tx_wd for r in recs)
    R.add(f"Çift yönlü Kart TX → Ballard RX CH{c.bb_rx}: {sent_n}/{sent_n} Word hatasız", ok_tx,
          f"alınan {len(recs)}" + ("" if ok_tx else " → " + _bb_rx_diagnose(recs, [tx_wd] * sent_n, c.bb_rx)))

    for ch in c.ip_rx_chans():
        lab = channel_label(ch)
        dw, de, dd = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err"), c.delta(s0, s1, ch, "drop")
        got = [x["data"] for x in c.last_words(ch, dw)] if dw == n else []
        ok_rx = dw == n and de == 0 and dd == 0 and got == rx_words
        R.add(f"Çift yönlü Ballard TX CH{c.bb_tx} → {lab}: {n}/{n} Word birebir, hatasız", ok_rx,
              f"WORD +{dw}, ERR +{de}, DROP +{dd}" + ("" if ok_rx else " → " + c.diagnose(ch)))
    _check_tb_echo(c, R, s0, s1, sent_n, label="Çift yönlü ")


def _custom_speed_hint(c: ExtCtx) -> str | None:
    """Custom TX/RX config'in hedef hızı HS (100k) ya da LS (12.5k) ile uyumluysa onu döner."""
    if not c.custom:
        return None
    tx_map = dict(c.custom.get("tx", []))
    p = tx_map.get("TX_CUST_PULSE_DUR", 0)
    n = tx_map.get("TX_CUST_NULL_DUR", 0)
    if p and n:
        bit_us = c.us(p + n)
        if 8.5 <= bit_us <= 11.5:
            return "HS"
        if 65.0 <= bit_us <= 95.0:
            return "LS"
        return None
    rx_map = c.custom.get("rx", {})
    mb = rx_map.get("CUST_MIN_BIT", 0)
    xb = rx_map.get("CUST_MAX_BIT", 0)
    if mb and xb:
        mid = c.us((mb + xb) / 2.0)
        if 8.5 <= mid <= 11.5:
            return "HS"
        if 65.0 <= mid <= 95.0:
            return "LS"
    return None


def t_custom(c: ExtCtx, R: TestResult):
    """Config sekmesinde hesaplanan Custom TX / RX ayarlarının Ballard referansıyla doğrulanması."""
    if not c.custom:
        R.status = "SKIP"
        R.notes.append("Config sekmesinden Custom config alınamadı")
        return
    spd = _custom_speed_hint(c)
    if spd is None:
        R.status = "SKIP"
        R.notes.append("Custom config 100 kbps / 12.5 kbps dışı bir hız için hesaplanmış (standart BusBox HS/LS destekler)")
        return
    c.baseline()
    try:
        if c.test_tx and c.custom.get("tx"):
            tx = [(n, v) for n, v in c.custom["tx"] if n.startswith("TX_CUST_") or n == "TX_CFG_SEL"]
            c.w(tx + [("TX_CFG_SEL", 2), ("TX_CFG_APPLY", 1)])
            R.add(f"Custom TX config yazıldı ({spd} uyumlu)", True)
        if c.test_rx and c.custom.get("rx"):
            for ch in c.ip_rx_chans():
                send_rx_config(c.bus, c.rm, ch, c.custom["rx"], verify=True, quiet=True)
            R.add(f"Custom RX config yazıldı ve doğrulandı ({spd} uyumlu)", True)
        c.settle()
        c.bb_setup(rx_speed=spd, tx_speed=spd, rx_parity="odd", tx_raw_parity=True)
        if c.test_tx:
            words = pattern_words(8)
            c.send_words(words)
            recs = c.bb_expect_rx(8, spd)
            ok = len(recs) == 8 and not any(r.err for r in recs) and [r.word for r in recs] == words
            R.add(f"Custom TX → Ballard RX CH{c.bb_rx}: 8 Word desen birebir", ok,
                  "" if ok else _bb_rx_diagnose(recs, words, c.bb_rx))
        if c.test_rx:
            words = pattern_words(8)
            s0 = c.snap()
            c.bb_send(words, spd)
            s1 = c.snap()
            for ch in c.ip_rx_chans():
                dw, de = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err")
                got = [x["data"] for x in c.last_words(ch, dw)] if dw == 8 else []
                R.add(f"Ballard TX CH{c.bb_tx} → Custom {channel_label(ch)}: 8 Word desen birebir",
                      dw == 8 and de == 0 and got == words, f"WORD +{dw}, ERR +{de}")
    finally:
        c.set_speed(tx="HS" if c.test_tx else None, rx="HS" if c.test_rx else None)
        c.settle()


# =====================================================================================
# Katalog ve koşucu
# =====================================================================================
# (id, başlık, fonksiyon, hız parametreli mi, yön: "both" | "tx" | "rx" | "duplex")
CATALOG = [
    ("ident", "Bağlantı, IP kimliği ve Ballard öz-testi", t_ident, False, "both"),
    ("prep", "Hazırlık: IP reset, logger ve BusBox kurulumu", t_prep, False, "both"),
    ("tx_single", "Kart TX → BusBox RX: Tek Word ve bit sırası", t_tx_single, True, "tx"),
    ("tx_pattern", "Kart TX → BusBox RX: Veri bütünlüğü deseni", t_tx_pattern, True, "tx"),
    ("tx_period", "Kart TX → BusBox RX: Bağımsız saat ve periyot ölçümü", t_tx_period, True, "tx"),
    ("tx_burst", "Kart TX → BusBox RX: Minimum gap burst", t_tx_burst, True, "tx"),
    ("tx_parity_err", "Kart TX → BusBox RX: Parity hatası üretimi", t_tx_parity_err, False, "tx"),
    ("tx_switch", "Kart TX → BusBox RX: HS ↔ LS geçişi (sürücü SLP)", t_tx_switch, False, "tx"),
    ("rx_single", "BusBox TX → Kart RX: Tek Word ve bit sırası", t_rx_single, True, "rx"),
    ("rx_pattern", "BusBox TX → Kart RX: Veri bütünlüğü deseni", t_rx_pattern, True, "rx"),
    ("rx_bittime", "BusBox TX → Kart RX: Alıcı entegre bit zamanlaması", t_rx_bittime, True, "rx"),
    ("rx_burst", "BusBox TX → Kart RX: Minimum gap burst", t_rx_burst, True, "rx"),
    ("rx_parity_err", "BusBox TX → Kart RX: Parity hatası enjeksiyonu", t_rx_parity_err, False, "rx"),
    ("rx_mismatch", "BusBox TX → Kart RX: Hız uyuşmazlığı tespiti", t_rx_mismatch, False, "rx"),
    ("rx_switch", "BusBox TX → Kart RX: HS ↔ LS geçişi", t_rx_switch, False, "rx"),
    ("duplex", "Çift yönlü eşzamanlı stres (Full-Duplex)", t_duplex, True, "duplex"),
    ("custom", "Config sekmesi Custom config doğrulaması", t_custom, False, "both"),
]
ALWAYS = ("ident", "prep")


def plan(selected: list[str] | None, speeds=("HS", "LS")) -> list[tuple[str, str, object, str]]:
    sel = set(selected or [t[0] for t in CATALOG]) | set(ALWAYS)
    steps = []
    for tid, title, fn, per_speed, _dir in CATALOG:
        if tid not in sel:
            continue
        if per_speed:
            for sp in speeds:
                steps.append((tid, title, fn, sp))
        else:
            steps.append((tid, title, fn, ""))
    return steps


def run(
    bus,
    rm: RegMap,
    rx_channels: list[str],
    *,
    card_num: int = 0,
    core_num: int = 0,
    dll_dir: str | None = None,
    ballard=None,
    test_tx: bool = True,
    test_rx: bool = True,
    bb_rx_chan: int | None = None,
    bb_tx_chan: int | None = None,
    selected: list[str] | None = None,
    speeds=("HS", "LS"),
    use_tb: bool = False,
    pattern_len: int = 35,
    burst_words: int = 40,
    custom: dict | None = None,
    stop_on_fail: bool = False,
    log=None,
    progress=None,
    on_result=None,
    stop: threading.Event | None = None,
) -> dict:
    """Ballard dış doğrulama test takımını koşar; ``selftest.run`` ile aynı rapor sözlüğünü döner."""
    owned_bb = ballard is None
    bb = ballard if ballard is not None else BallardSession(card_num=card_num, core_num=core_num, dll_dir=dll_dir)
    c = ExtCtx(
        bus, rm, bb, rx_channels,
        use_tb=use_tb, test_tx=test_tx, test_rx=test_rx,
        bb_rx_chan=bb_rx_chan, bb_tx_chan=bb_tx_chan,
        pattern_len=pattern_len, burst_words=burst_words,
        custom=custom, log=log, stop=stop,
    )
    steps = plan(selected, speeds)
    results: list[TestResult] = []
    prog = progress or (lambda d, t, m: None)
    t_start = time.monotonic()
    aborted = False
    lock = getattr(bus, "lock", None)
    if lock:
        bus.lock()
    try:
        for i, (tid, title, fn, sp) in enumerate(steps):
            prog(i, len(steps), f"{title}" + (f" · {sp}" if sp else ""))
            R = TestResult(tid, title, sp)
            t0 = time.monotonic()
            try:
                c.check_stop()
                if sp:
                    fn(c, R, sp)
                else:
                    fn(c, R)
            except TestAborted as e:
                R.status = "SKIP"
                R.notes.append(str(e))
                aborted = True
            except (BallardError, Exception) as e:  # noqa: BLE001
                R.status = "ERROR"
                R.notes.append(f"{type(e).__name__}: {e}")
            R.duration_s = round(time.monotonic() - t0, 3)
            results.append(R)
            if on_result:
                on_result(R)
            if aborted or (stop_on_fail and R.status in ("FAIL", "ERROR")) or (tid == "ident" and R.status != "PASS"):
                break
        restore(c)
    finally:
        if owned_bb:
            try:
                bb.close()
            except Exception:
                pass
        if lock:
            try:
                bus.unlock()
            except Exception:
                pass
    prog(len(steps), len(steps), "Tamamlandı")
    counts = {k: sum(1 for r in results if r.status == k) for k in ("PASS", "FAIL", "ERROR", "SKIP")}
    return {
        "mode": "ballard",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.monotonic() - t_start, 2),
        "aborted": aborted,
        "passed": not aborted and counts["FAIL"] == 0 and counts["ERROR"] == 0 and counts["PASS"] > 0,
        "counts": counts,
        "clk_hz": c.clk_hz,
        "channels": c.chans,
        "ballard": {
            "card": c.bb_info.card_num if c.bb_info else card_num,
            "core": c.bb_info.core_num if c.bb_info else core_num,
            "product": c.bb_info.product if c.bb_info else "",
            "rx_chan": c.bb_rx,
            "tx_chan": c.bb_tx,
        },
        "speeds": list(speeds),
        "results": results,
    }


def report_text(rep: dict) -> str:
    """Dış doğrulama raporunu metin olarak biçimlendirir."""
    bb = rep.get("ballard") or {}
    dur = "DURDURULDU" if rep["aborted"] else ("GEÇTİ" if rep["passed"] else "KALDI")
    c = rep["counts"]
    lines = [
        f"ARINC 429 Dış Doğrulama Test Raporu (Ballard) — {dur}",
        f"Tarih   : {rep['timestamp']}   Süre: {rep['duration_s']} s   Saat: {rep['clk_hz'] / 1e6:g} MHz",
        f"Ballard : Kart #{bb.get('card', 0)} Core #{bb.get('core', 0)} {bb.get('product', '')}"
        f" · RX CH{bb.get('rx_chan')} · TX CH{bb.get('tx_chan')}",
        f"Kart RX : {', '.join(channel_label(x) for x in rep['channels']) or '—'}   Hızlar: {', '.join(rep['speeds'])}",
        f"Özet    : PASS {c['PASS']} · FAIL {c['FAIL']} · ERROR {c['ERROR']} · SKIP {c['SKIP']}",
        "=" * 78,
    ]
    for r in rep["results"]:
        hdr = f"[{r.status:5s}] {r.title}" + (f" ({r.speed})" if r.speed else "") + f"  [{r.duration_s:.2f} s]"
        lines.append(hdr)
        for ck in r.checks:
            mark = {True: "  OK  ", False: " FAIL ", None: " INFO "}[ck.ok]
            lines.append(f"  {mark} {ck.name}" + (f"  —  {ck.detail}" if ck.detail else ""))
        for n in r.notes:
            lines.append(f"  NOT  {n}")
    return "\n".join(lines) + "\n"


def report_json(rep: dict) -> str:
    return selftest.report_json(rep)
