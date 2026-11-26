"""ARINC 429 IP + hat entegreleri otomatik loopback testi (GUI'siz).

Kurulum: kartın ARINC TX çıkışı (line driver) dışarıdan seçilen RX girişlerine (line receiver) bağlanır.
TX BIT (TB) kanalı TX hattını kart üzerindeki kendi alıcısıyla dinler. Test, TX'ten Word gönderip TB'yi ve
bağlı RX'leri karşılaştırır; HS / LS, art arda gönderim, gap ölçümü, bit zamanlaması, hat polaritesi ve
hata tespiti (hız uyuşmazlığı, parity, gap ihlali) senaryolarını otomatik koşar.

Zaman: kartta gerçek bekleme (time.sleep), RTL eş-simülasyonunda (a429.cosim) ``bus.advance_us``.
Beklentiler RTL davranışından alınmıştır (DESIGN.md / vhdl/rtl), ``tests/test_selftest.py`` RTL'e karşı koşar.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field

from . import ipmap
from .decode import ERR_NAMES
from .ip import IpError, ReadSettings, read_channel, read_fields, send_rx_config, write_fields
from .regs import RegMap, channel_label, channel_prefix
from .txlive import build_word

SPEEDS = {"HS": (0, "High Speed (100 kbps)"), "LS": (1, "Low Speed (12.5 kbps)")}
ERR = {n: i for i, n in enumerate(ERR_NAMES)}


class TestAborted(Exception):
    pass


@dataclass
class Check:
    name: str
    ok: bool | None            # None: bilgi (sonucu etkilemez)
    detail: str = ""


@dataclass
class TestResult:
    tid: str
    title: str
    speed: str = ""
    status: str = "PASS"       # PASS | FAIL | SKIP | ERROR
    checks: list = field(default_factory=list)
    measurements: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    duration_s: float = 0.0

    def add(self, name, ok, detail=""):
        self.checks.append(Check(name, ok, detail))
        if ok is False and self.status == "PASS":
            self.status = "FAIL"
        return ok

    @property
    def summary(self) -> str:
        bad = [c for c in self.checks if c.ok is False]
        if self.status == "SKIP":
            return self.notes[0] if self.notes else "Atlandı"
        if self.status == "ERROR":
            return self.notes[-1] if self.notes else "Hata"
        if bad:
            return f"{len(bad)} kontrol başarısız: {bad[0].name}" + (f" ({bad[0].detail})" if bad[0].detail else "")
        n = sum(1 for c in self.checks if c.ok)
        return f"{n} kontrol geçti"

    def to_dict(self):
        d = asdict(self)
        d["summary"] = self.summary
        return d


def odd_parity(word31: int) -> int:
    """Bit 1..31'e göre Odd parity (bit 32) eklenmiş Word."""
    w = word31 & 0x7FFFFFFF
    return w | ((bin(w).count("1") % 2 == 0) << 31)


def err_names(code: int) -> list[str]:
    return [n for i, n in enumerate(ERR_NAMES) if (code >> i) & 1]


# =====================================================================================
class Ctx:
    """Test bağlamı: bus erişimi, zaman, kanallar ve ortak yardımcılar."""

    def __init__(self, bus, rm: RegMap, rx_channels: list[str], use_tb: bool = True, pattern_len: int = 35,
                 burst_words: int = 40, custom: dict | None = None, log=None, stop: threading.Event | None = None):
        self.bus = bus
        self.rm = rm
        self.rx = list(rx_channels)
        self.use_tb = use_tb and rm.has("TB_CTRL")
        self.chans = self.rx + (["TB"] if self.use_tb else [])
        self.pattern_len = max(4, int(pattern_len))
        self.burst_words = max(4, int(burst_words))
        self.custom = custom
        self._log = log or (lambda s: None)
        self.stop = stop or threading.Event()
        self.clk_hz = 50_000_000
        self.sim = hasattr(bus, "advance_us")

    # ---- temel
    def log(self, s):
        self._log(s)

    def check_stop(self):
        if self.stop.is_set():
            raise TestAborted("Kullanıcı durdurdu")

    def wait_us(self, us: float):
        self.check_stop()
        if us <= 0:
            return
        if self.sim:
            self.bus.advance_us(us)
        else:
            time.sleep(us / 1e6)

    def r(self, names) -> dict:
        return read_fields(self.bus, self.rm, [n for n in names if self.rm.has(n)], quiet=True)

    def w(self, writes):
        write_fields(self.bus, self.rm, writes, quiet=True)

    def us(self, clk: float) -> float:
        return clk * 1e6 / self.clk_hz

    # ---- zamanlama
    def tx_timing(self) -> dict:
        v = self.r(["TX_ACT_PULSE_DUR", "TX_ACT_NULL_DUR", "TX_ACT_GAP_DUR"])
        p, n, g = v["TX_ACT_PULSE_DUR"] or 1, v["TX_ACT_NULL_DUR"] or 1, v["TX_ACT_GAP_DUR"] or 1
        return {"pulse": p, "null": n, "gap": g, "bit": p + n, "word": 32 * (p + n) + g}

    def rx_window(self, ch) -> dict:
        p = channel_prefix(ch)
        v = self.r([p + s for s in ("ACT_MIN_PULSE", "ACT_MAX_PULSE", "ACT_MIN_BIT", "ACT_MAX_BIT")])
        return {"min_pulse": v[p + "ACT_MIN_PULSE"], "max_pulse": v[p + "ACT_MAX_PULSE"],
                "min_bit": v[p + "ACT_MIN_BIT"], "max_bit": v[p + "ACT_MAX_BIT"]}

    def settle(self):
        """Decoder'ların hata sonrası hat senkronunu (4 x min_bit temiz NULL) alması için bekler."""
        mb = max([self.rx_window(c)["min_bit"] for c in self.chans] + [500])
        self.wait_us(self.us(6 * mb) + 20)

    # ---- konfigürasyon
    def set_speed(self, tx: str | None = None, rx: str | None = None, chans=None):
        writes = []
        if tx:
            writes += [("TX_CFG_SEL", SPEEDS[tx][0]), ("TX_CFG_APPLY", 1)]
        if rx:
            for ch in (chans or self.chans):
                p = channel_prefix(ch)
                writes += [(p + "CFG_SEL", SPEEDS[rx][0]), (p + "CFG_APPLY", 1)]
        self.w(writes)

    def baseline(self):
        """TX: Word Transmitter, tek gönderim (SEND_CMD), EXT_DATA kaynağı, override kapalı."""
        self.w([("TX_EXT_HIGH", 0), ("TX_EXT_LOW", 0), ("TX_SCHED_EN", 0), ("TX_MSG_SCHED_EN", 0),
                ("TX_TRANSMITTER_EN", 1), ("TX_BUILDER_EN", 0), ("TX_INITIAL_DELAY", 0), ("TX_INTER_WORD_GAP", 1),
                ("GLOBAL_FREEZE", 0)])
        for ch in self.chans:
            self.w([(channel_prefix(ch) + "CTRL", 1)])                 # ENABLE=1, FREEZE=0
        self.chk_clear()

    def chk_clear(self):
        if self.use_tb and self.rm.has("TB_CHK_CTRL"):
            self.w([("TB_CHK_CTRL", 0b11)])                            # ENABLE + CLEAR (FIFO)

    # ---- gönderim
    def wait_tx_idle(self, timeout_us: float):
        busy = self.rm.field("TX_STATUS", "BUSY")
        off = self.rm.offset("TX_STATUS")
        end_sim = timeout_us
        t0 = time.monotonic()
        step = 20.0
        while True:
            self.check_stop()
            if not busy.extract(self.bus.read(off, quiet=True)):
                return True
            if self.sim:
                if end_sim <= 0:
                    return False
                self.bus.advance_us(step)
                end_sim -= step
            else:
                if (time.monotonic() - t0) * 1e6 > timeout_us:
                    return False
                time.sleep(0.0005)

    def send_words(self, words: list[int], tim: dict | None = None):
        """EXT_DATA ile Word'leri sırayla gönderir; son Word'ün RX'te kabulüne (gap tespiti) kadar bekler."""
        tim = tim or self.tx_timing()
        word_us = self.us(tim["word"])
        for wd in words:
            if not self.wait_tx_idle(word_us * 3 + 2000):
                raise IpError("TX_STATUS.BUSY düşmedi (TX takılı)")
            self.w([("TX_EXT_DATA", wd), ("TX_SEND_CMD", 1)])
            if self.sim:
                self.wait_us(word_us)
        self.wait_tx_idle(word_us * 3 + 2000)
        self.settle()

    def snap(self) -> dict:
        names = ["TX_WORD_CNT"]
        for ch in self.chans:
            p = channel_prefix(ch)
            names += [p + "WORD_CNT", p + "ERR_CNT", p + "DROP_CNT", p + "LAST_WORD"]
        if self.use_tb:
            names += ["TB_CHK_OK_CNT", "TB_CHK_ERR_CNT"]
        v = self.r(names)
        out = {"tx": v["TX_WORD_CNT"], "chk_ok": v.get("TB_CHK_OK_CNT", 0), "chk_err": v.get("TB_CHK_ERR_CNT", 0)}
        for ch in self.chans:
            p = channel_prefix(ch)
            out[ch] = {"word": v[p + "WORD_CNT"], "err": v[p + "ERR_CNT"], "drop": v[p + "DROP_CNT"],
                       "last": v[p + "LAST_WORD"]}
        return out

    @staticmethod
    def delta(a: dict, b: dict, ch: str, key: str) -> int:
        return (b[ch][key] - a[ch][key]) & 0xFFFFFFFF

    # ---- RAM okuma
    def _read(self, ch, words=0, errors=0, bits=0) -> dict:
        rs = ReadSettings(read_word="last" if words else "none", read_word_n=words or 1,
                          read_error="last" if errors else "none", read_error_n=errors or 1,
                          read_bit="last" if bits else "none", read_bit_n=bits or 1)
        return read_channel(self.bus, self.rm, ch, rs)

    def last_words(self, ch, n) -> list[dict]:
        """Son n Word kaydı, eskiden yeniye: {"data", "ts", "gap", "gap_err"}."""
        d = self._read(ch, words=n)
        out = [{"ts": (r["w"][0] << 32) | r["w"][1], "data": r["w"][2], "gap": r["w"][3], "gap_err": r["w"][4]}
               for r in d["words"]]
        return list(reversed(out))

    def last_errors(self, ch, n) -> list[dict]:
        d = self._read(ch, errors=n)
        return [{"code": r["w"][2], "addr": r["w"][3], "data": r["w"][4], "names": err_names(r["w"][2])}
                for r in reversed(d["errors"])]

    def last_bits(self, ch, nwords) -> list[dict]:
        d = self._read(ch, bits=nwords)
        return [{"word": b["word"], "bit": b["bit"], "pulse": b["w"][0], "perr": b["w"][1], "null": b["w"][2],
                 "nerr": b["w"][3]} for b in d["bits"]]

    # ---- teşhis
    def diagnose(self, ch) -> str:
        """Kanal Word almıyorsa olası nedeni hat durumundan ve son hatalardan çıkarır."""
        p = channel_prefix(ch)
        hints = []
        ctrl = self.r([p + "CTRL"])[p + "CTRL"]
        if not ctrl & 1:
            hints.append("logger kapalı (CTRL.ENABLE=0)")
        if ctrl & 2:
            hints.append("kanal donmuş (FREEZE=1)")
        fe = {n: self.rm.field(p + "STATUS", n) for n in ("LINE_HIGH", "LINE_LOW", "SYNC_WAIT")}
        if all(f is not None and f.name == n for n, f in fe.items()):
            st = [self.bus.read(self.rm.offset(p + "STATUS"), quiet=True) for _ in range(8)]
            lines = {(fe["LINE_HIGH"].extract(s), fe["LINE_LOW"].extract(s)) for s in st}
            if lines == {(1, 1)}:
                hints.append("hat sürekli 11: alıcı çıkışı ters / pull-up / alıcı beslemesi yok")
            elif any(fe["SYNC_WAIT"].extract(s) for s in st):
                hints.append("decoder hat senkronu bekliyor (SYNC_WAIT=1)")
        e = self.r([p + "ERR_CNT"])[p + "ERR_CNT"]
        if e:
            names = sorted({n for x in self.last_errors(ch, min(e, 4)) for n in x["names"]})
            if names:
                hints.append("son hatalar: " + ", ".join(names))
        if not hints:
            hints.append("hatta sinyal yok: TX→RX kablosu, alıcı beslemesi / pinleri, rx_high/rx_low bağlantısı")
        return "; ".join(hints)


# =====================================================================================
# Testler
# =====================================================================================
def t_ident(c: Ctx, R: TestResult):
    v = c.r(["IP_ID", "IP_VERSION", "CAPS", "CLK_HZ"])
    R.add("IP_ID = 'A429'", v.get("IP_ID") == ipmap.IP_ID_WORD, f"0x{v.get('IP_ID', 0):08X}")
    ver = v.get("IP_VERSION", 0)
    R.add(f"IP sürümü {ipmap.IP_VERSION[0]}.x", (ver >> 16) & 0xFF == ipmap.IP_VERSION[0],
          f"{(ver >> 16) & 0xFF}.{(ver >> 8) & 0xFF}.{ver & 0xFF}")
    caps = v.get("CAPS", 0)
    nrx = c.rm.field("CAPS", "NUM_RX").extract(caps)
    R.add("TX kanalı var (CAPS.TX)", bool(c.rm.field("CAPS", "TX").extract(caps)))
    if c.use_tb:
        R.add("TX BIT kanalı var (CAPS.TXBIT)", bool(c.rm.field("CAPS", "TXBIT").extract(caps)))
    need = max([int(ch[2:]) + 1 for ch in c.rx] + [0])
    R.add(f"Seçilen RX kanalları IP'de var (NUM_RX={nrx})", nrx >= need, ", ".join(c.rx) or "RX seçilmedi")
    if v.get("CLK_HZ"):
        c.clk_hz = v["CLK_HZ"]
    R.measurements["clk_mhz"] = c.clk_hz / 1e6
    R.add(f"IP saati {c.clk_hz / 1e6:g} MHz", None)


def t_prep(c: Ctx, R: TestResult):
    c.w([("SOFT_RESET", 1)])                                    # RST_ALL: config'ler HS preset, decoder'lar resetlenir
    c.wait_us(5)
    c.w([("TS_CTRL", 1)])
    c.baseline()
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 0b101)])             # ENABLE + CLEAR
    if c.use_tb:
        tim_ls = 32 * 4000 + 16000
        c.w([("TB_CHK_TIMEOUT", 3 * tim_ls)])
    c.settle()
    s = c.snap()
    for ch in c.chans:
        R.add(f"{channel_label(ch)}: logger açık, sayaçlar sıfır", s[ch]["word"] == 0 and s[ch]["err"] == 0,
              f"WORD={s[ch]['word']} ERR={s[ch]['err']}")
    st = c.r(["TX_STATUS"] + [channel_prefix(ch) + "STATUS" for ch in c.chans])
    R.add("TX config High Speed preset", c.rm.field("TX_STATUS", "ACT_CFG").extract(st["TX_STATUS"]) == 0)
    for ch in c.chans:
        p = channel_prefix(ch)
        R.add(f"{channel_label(ch)} config High Speed preset",
              c.rm.field(p + "STATUS", "ACT_CFG").extract(st[p + "STATUS"]) == 0)


def _line_samples(c: Ctx, ch, n=16):
    p = channel_prefix(ch)
    fe = {k: c.rm.field(p + "STATUS", k) for k in ("LINE_HIGH", "LINE_LOW", "SYNC_WAIT")}
    if not all(f is not None and f.name == k for k, f in fe.items()):
        return None
    off = c.rm.offset(p + "STATUS")
    out = []
    for _ in range(n):
        s = c.bus.read(off, quiet=True)
        out.append((fe["LINE_HIGH"].extract(s), fe["LINE_LOW"].extract(s), fe["SYNC_WAIT"].extract(s)))
    return out


def t_idle(c: Ctx, R: TestResult):
    c.baseline()
    c.wait_tx_idle(20000)
    c.settle()
    for ch in c.chans:
        s = _line_samples(c, ch)
        if s is None:
            R.notes.append("IP 1.x: STATUS hat teşhis bitleri yok")
            R.status = "SKIP"
            return
        lines = {(h, lo) for h, lo, _ in s}
        lab = channel_label(ch)
        if lines == {(0, 0)}:
            R.add(f"{lab}: hat boşta NULL (00)", True)
        else:
            why = ("alıcı çıkışı ters (aktif-düşük) / pull-up / alıcı beslemesi yok" if (1, 1) in lines
                   else "hatta sürekli seviye var: TX override açık ya da hat kısa devre")
            R.add(f"{lab}: hat boşta NULL (00)", False, f"görülen {sorted(lines)}: {why}")
        R.add(f"{lab}: decoder senkron (SYNC_WAIT=0)", not any(w for _, _, w in s))


def t_polarity(c: Ctx, R: TestResult):
    """Override ile TX hattını HIGH / LOW / NULL'a sabitler, her alıcının seviyesini okur (A/B ters, kopuk hat)."""
    cases = [("HIGH", (1, 0)), ("LOW", (0, 1)), ("NULL", (0, 0))]
    seen = {ch: {} for ch in c.chans}
    try:
        for name, (h, lo) in cases:
            c.w([("TX_EXT_HIGH", h), ("TX_EXT_LOW", lo), ("TX_TRANSMITTER_EN", 0)])
            c.wait_us(30)
            for ch in c.chans:
                s = _line_samples(c, ch, 6)
                if s is None:
                    R.notes.append("IP 1.x: STATUS hat teşhis bitleri yok")
                    R.status = "SKIP"
                    return
                seen[ch][name] = sorted({(a, b) for a, b, _ in s})
        # HIGH-Z (11): sürücü destekliyorsa çıkış yüksek empedans -> alıcı NULL görür (bilgi)
        c.w([("TX_EXT_HIGH", 1), ("TX_EXT_LOW", 1)])
        c.wait_us(30)
        for ch in c.chans:
            s = _line_samples(c, ch, 6)
            R.add(f"{channel_label(ch)}: HIGH-Z (TX1IN=TX0IN=1) iken alıcı {sorted({(a, b) for a, b, _ in s})}", None,
                  "HI-8596/97: Hi-Z → NULL beklenir; HI-8585: 0 V → NULL")
    finally:
        c.w([("TX_EXT_HIGH", 0), ("TX_EXT_LOW", 0), ("TX_TRANSMITTER_EN", 1)])
    for ch in c.chans:
        lab = channel_label(ch)
        got = seen[ch]
        inv = got["NULL"] == [(1, 1)]
        for name, exp in cases:
            ok = got[name] == [exp]
            why = ""
            if not ok:
                if inv:
                    why = "alıcı çıkışları ters (aktif-düşük): boşta 11, HIGH/LOW yer değiştirmiş görünür"
                elif name == "HIGH" and got[name] == [(0, 1)]:
                    why = "HIGH, LOW görüldü: A/B hattı ters bağlı (TXA↔TXB veya RINA↔RINB)"
                elif name == "LOW" and got[name] == [(1, 0)]:
                    why = "LOW, HIGH görüldü: A/B hattı ters bağlı"
                elif got[name] == [(0, 0)]:
                    why = "hiç seviye görülmedi: kablo kopuk / sürücü veya alıcı çalışmıyor"
                elif (1, 1) in got[name]:
                    why = "11 görüldü: alıcı çıkışı ters / pull-up"
            R.add(f"{lab}: TX {name} → alıcı {exp}", ok, why or f"görülen {got[name]}")
    # Override darbeleri RX'lerde PULSE_STUCK üretir; sonraki testler için sayaçları temizle
    c.settle()
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 0b101)])
    c.chk_clear()


def _word_checks(c: Ctx, R: TestResult, s0, s1, sent: list[int], label=""):
    n = len(sent)
    R.add(f"{label}TX_WORD_CNT +{n}", (s1["tx"] - s0["tx"]) & 0xFFFFFFFF == n, f"+{(s1['tx'] - s0['tx']) & 0xFFFFFFFF}")
    ok_all = True
    for ch in c.chans:
        lab = channel_label(ch)
        dw, de = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err")
        good = dw == n and de == 0
        ok_all &= good
        R.add(f"{label}{lab}: {n} Word alındı, hata yok", good,
              f"WORD +{dw}, ERR +{de}" + ("" if good else " → " + c.diagnose(ch)))
        if dw:
            last = s1[ch]["last"]
            why = " → tüm bitler ters: A/B hattı ters bağlı" if last == sent[-1] ^ 0xFFFFFFFF else ""
            R.add(f"{label}{lab}: LAST_WORD = 0x{sent[-1]:08X}", last == sent[-1], f"0x{last:08X}{why}")
    if c.use_tb:
        dok = (s1["chk_ok"] - s0["chk_ok"]) & 0xFFFFFFFF
        derr = (s1["chk_err"] - s0["chk_err"]) & 0xFFFFFFFF
        R.add(f"{label}TX BIT Checker: {n} eşleşme, 0 hata", dok == n and derr == 0, f"OK +{dok}, ERR +{derr}")
    return ok_all


def t_single(c: Ctx, R: TestResult, speed: str):
    """Word Builder yolu: Label/SDI/Data/SSM + IP'nin hesapladığı Odd parity."""
    c.baseline()
    exp = build_word(0o310, 2, 0x5A5A5, 1, odd=True)
    s0 = c.snap()
    c.w([("TX_LABEL", 0o310), ("TX_SDI", 2), ("TX_DATA", 0x5A5A5), ("TX_SSM", 1), ("TX_PARITY_TYPE", 1),
         ("TX_BUILDER_EN", 1), ("TX_SEND_CMD", 1)])
    tim = c.tx_timing()
    c.wait_us(c.us(tim["word"]))
    c.wait_tx_idle(c.us(tim["word"]) * 3 + 2000)
    c.settle()
    s1 = c.snap()
    c.w([("TX_BUILDER_EN", 0)])
    _word_checks(c, R, s0, s1, [exp])
    R.measurements["word"] = f"0x{exp:08X}"


def pattern_words(n: int) -> list[int]:
    base = [0x00000000, 0x7FFFFFFF, 0x55555555, 0x2AAAAAAA, 0x0F0F0F0F, 0x70F0F0F0]
    walk = [1 << b for b in range(31)]
    seq = (base + walk) * (n // (len(base) + len(walk)) + 1)
    return [odd_parity(w) for w in seq[:n]]


def t_pattern(c: Ctx, R: TestResult, speed: str, n: int | None = None):
    c.baseline()
    words = pattern_words(n or (c.pattern_len if speed == "HS" else max(8, c.pattern_len // 3)))
    s0 = c.snap()
    c.send_words(words)
    s1 = c.snap()
    if not _word_checks(c, R, s0, s1, words):
        return
    for ch in c.chans:
        got = [x["data"] for x in c.last_words(ch, len(words))]
        bad = [i for i, (a, b) in enumerate(zip(got, words)) if a != b]
        R.add(f"{channel_label(ch)}: Word RAM sırası ve içeriği ({len(words)} Word, walking-1 / 0x55.. / 0xAA..)",
              not bad and len(got) == len(words),
              "" if not bad else f"{len(bad)} fark, ilki #{bad[0]}: gönderilen 0x{words[bad[0]]:08X}, alınan 0x{got[bad[0]]:08X}"
              + (" → tüm bitler ters: A/B hattı ters bağlı"
                 if all(a == b ^ 0xFFFFFFFF for a, b in zip(got, words)) else ""))


def t_bittime(c: Ctx, R: TestResult, speed: str):
    """Bit Diagnostic: hattaki pulse / null / bit süreleri (line driver + receiver zamanlaması)."""
    c.baseline()
    words = pattern_words(2)
    c.send_words(words)
    tim = c.tx_timing()
    R.measurements["tx_pulse_us"] = round(c.us(tim["pulse"]), 3)
    R.measurements["tx_null_us"] = round(c.us(tim["null"]), 3)
    for ch in c.chans:
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
        R.measurements[ch] = {
            "pulse_us": [round(c.us(min(pulses)), 3), round(c.us(mp), 3), round(c.us(max(pulses)), 3)],
            "null_us": [round(c.us(min(nulls)), 3), round(c.us(mn), 3), round(c.us(max(nulls)), 3)],
            "bit_us": [round(c.us(min(bitl)), 3), round(c.us(max(bitl)), 3)],
            "pulse_skew_us": round(c.us(mp - tim["pulse"]), 3), "noise": noise,
        }
        R.add(f"{lab}: pulse {c.us(min(pulses)):.2f}…{c.us(max(pulses)):.2f} µs, kabul {c.us(win['min_pulse']):.2f}…"
              f"{c.us(win['max_pulse']):.2f} µs", win["min_pulse"] <= min(pulses) and max(pulses) <= win["max_pulse"])
        R.add(f"{lab}: bit {c.us(min(bitl)):.2f}…{c.us(max(bitl)):.2f} µs, kabul {c.us(win['min_bit']):.2f}…"
              f"{c.us(win['max_bit']):.2f} µs", win["min_bit"] <= min(bitl) and max(bitl) <= win["max_bit"])
        R.add(f"{lab}: ortalama pulse {c.us(mp):.3f} µs (TX {c.us(tim['pulse']):.3f} µs, fark "
              f"{c.us(mp - tim['pulse']):+.3f} µs: sürücü/alıcı gecikme asimetrisi)", None)
        R.add(f"{lab}: hat gürültüsü (glitch sayısı) = {noise}", None,
              "" if noise == 0 else "gürültü var: kablo / topraklama / sonlandırma kontrol edilmeli")


def _scheduler_run(c: Ctx, n_words: int, iwg: int, tim: dict):
    period = tim["word"] + iwg
    c.w([("TX_INITIAL_DELAY", 0), ("TX_INTER_WORD_GAP", iwg), ("TX_MSG_SCHED_EN", 1), ("TX_SCHED_EN", 1)])
    c.wait_us(c.us(period * (n_words - 0.5)))
    c.w([("TX_SCHED_EN", 0)])
    c.wait_tx_idle(c.us(tim["word"]) * 3 + 2000)
    c.w([("TX_MSG_SCHED_EN", 0)])
    c.settle()
    return period


def t_period(c: Ctx, R: TestResult, speed: str):
    """Scheduler periyodu (timestamp farkları) ve Word gap ölçümü."""
    c.baseline()
    tim = c.tx_timing()
    iwg = 10 * tim["bit"]
    c.w([("TX_EXT_DATA", odd_parity(0x1234567))])
    s0 = c.snap()
    period = _scheduler_run(c, 6, iwg, tim)
    s1 = c.snap()
    n = (s1["tx"] - s0["tx"]) & 0xFFFFFFFF
    R.add("Scheduler Word gönderdi", n >= 3, f"{n} Word")
    if n < 3:
        return
    for ch in c.chans:
        lab = channel_label(ch)
        dw = c.delta(s0, s1, ch, "word")
        if not R.add(f"{lab}: {n} Word alındı, hata yok", dw == n and c.delta(s0, s1, ch, "err") == 0,
                     f"WORD +{dw}, ERR +{c.delta(s0, s1, ch, 'err')}" + ("" if dw == n else " → " + c.diagnose(ch))):
            continue
        recs = c.last_words(ch, n)
        diffs = [b["ts"] - a["ts"] for a, b in zip(recs, recs[1:])]
        gaps = [r["gap"] for r in recs[1:]]
        tol = max(20, period // 1000)
        R.measurements[ch] = {"period_us": [round(c.us(min(diffs)), 3), round(c.us(max(diffs)), 3)],
                              "gap_us": [round(c.us(min(gaps)), 3), round(c.us(max(gaps)), 3)]}
        R.add(f"{lab}: Word periyodu {c.us(min(diffs)):.2f}…{c.us(max(diffs)):.2f} µs (beklenen {c.us(period):.2f} µs)",
              all(abs(d - period) <= tol for d in diffs))
        exp_gap = tim["gap"] + iwg
        gtol = tim["bit"] // 2
        R.add(f"{lab}: ölçülen gap {c.us(min(gaps)):.2f}…{c.us(max(gaps)):.2f} µs (TX gap + inter-word gap = "
              f"{c.us(exp_gap):.2f} µs)", all(abs(g - exp_gap) <= gtol for g in gaps))
    if c.use_tb:
        R.add(f"TX BIT Checker: {n} eşleşme", (s1["chk_ok"] - s0["chk_ok"]) & 0xFFFFFFFF == n and s1["chk_err"] == s0["chk_err"],
              f"OK +{(s1['chk_ok'] - s0['chk_ok']) & 0xFFFFFFFF}, ERR +{(s1['chk_err'] - s0['chk_err']) & 0xFFFFFFFF}")


def t_burst(c: Ctx, R: TestResult, speed: str):
    """Art arda gönderim: standart minimum gap (4 bit) + 1 clk, kayıpsız ve hatasız alım."""
    c.baseline()
    tim = c.tx_timing()
    n_req = c.burst_words if speed == "HS" else max(6, c.burst_words // 4)
    c.w([("TX_EXT_DATA", odd_parity(0x2468ACE))])
    s0 = c.snap()
    _scheduler_run(c, n_req, 1, tim)
    s1 = c.snap()
    n = (s1["tx"] - s0["tx"]) & 0xFFFFFFFF
    R.measurements["words"] = n
    R.measurements["word_rate_per_s"] = round(c.clk_hz / (tim["word"] + 1), 1)
    R.add(f"Scheduler {n} Word gönderdi (gap 4 bit = {c.us(tim['gap']):.1f} µs)", n >= n_req // 2)
    for ch in c.chans:
        lab = channel_label(ch)
        dw, de, dd = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err"), c.delta(s0, s1, ch, "drop")
        R.add(f"{lab}: {n}/{n} Word, hata ve kayıp yok", dw == n and de == 0 and dd == 0,
              f"WORD +{dw}, ERR +{de}, DROP +{dd}" + ("" if dw == n else " → " + c.diagnose(ch)))
    if c.use_tb:
        ovf = c.r(["TB_CHK_STATUS"])["TB_CHK_STATUS"] >> 4 & 1
        R.add("TX BIT Checker: tüm Word'ler eşleşti, FIFO taşmadı",
              (s1["chk_ok"] - s0["chk_ok"]) & 0xFFFFFFFF == n and s1["chk_err"] == s0["chk_err"] and not ovf,
              f"OK +{(s1['chk_ok'] - s0['chk_ok']) & 0xFFFFFFFF}, ERR +{(s1['chk_err'] - s0['chk_err']) & 0xFFFFFFFF}, OVF={ovf}")


def t_switch(c: Ctx, R: TestResult):
    """HS ↔ LS art arda geçiş: her geçişten sonra Word'ler doğru alınmalı."""
    c.baseline()
    k = 0
    for cycle in range(3):
        for spd in ("LS", "HS"):
            c.set_speed(tx=spd, rx=spd)
            c.settle()
            words = [odd_parity(0x100000 * (k + 1) + 0x77), odd_parity(0x3000000 + k)]
            k += 1
            s0 = c.snap()
            c.send_words(words)
            s1 = c.snap()
            ok = all(c.delta(s0, s1, ch, "word") == 2 and c.delta(s0, s1, ch, "err") == 0
                     and s1[ch]["last"] == words[-1] for ch in c.chans)
            R.add(f"Geçiş {cycle + 1} → {spd}: tüm kanallar 2 Word aldı", ok,
                  "" if ok else "; ".join(f"{channel_label(ch)} W+{c.delta(s0, s1, ch, 'word')} "
                                          f"E+{c.delta(s0, s1, ch, 'err')}" for ch in c.chans))
    c.set_speed(tx="HS", rx="HS")
    c.settle()


def _expect_rejected(c: Ctx, R: TestResult, s0, s1, what: str, err_bit: str | None, strict_err: bool):
    for ch in c.chans:
        lab = channel_label(ch)
        dw, de = c.delta(s0, s1, ch, "word"), c.delta(s0, s1, ch, "err")
        R.add(f"{lab}: {what} Word kabul edilmedi", dw == 0, f"WORD +{dw}")
        names = sorted({n for e in c.last_errors(ch, min(de, 8)) for n in e["names"]}) if de else []
        if err_bit:
            ok = de > 0 and err_bit in names
            R.add(f"{lab}: {err_bit} hatası raporlandı", ok if strict_err else (True if ok else None),
                  f"ERR +{de}: {', '.join(names) or '—'}" + ("" if ok or strict_err else
                                                             " (hat sinyali glitch filtresinde elendi)"))


def t_mismatch(c: Ctx, R: TestResult):
    """Hız uyuşmazlığı: TX HS / RX LS ve TX LS / RX HS → Word kabul edilmemeli, hata raporlanmalı."""
    c.baseline()
    for tx, rx, err in (("HS", "LS", "Pulse Glitch"), ("LS", "HS", "Pulse Stuck")):
        c.set_speed(tx=tx, rx=rx)
        c.settle()
        c.chk_clear()
        s0 = c.snap()
        c.send_words([odd_parity(0x1ABCDEF)])
        s1 = c.snap()
        _expect_rejected(c, R, s0, s1, f"TX {tx} / RX {rx}:", err, strict_err=(tx == "LS"))
    c.set_speed(tx="HS", rx="HS")
    c.settle()
    c.chk_clear()


def t_parity(c: Ctx, R: TestResult):
    c.baseline()
    good = odd_parity(0x0ABC123)
    bad = good ^ 0x80000000                                    # parity biti ters: Even
    s0 = c.snap()
    c.send_words([bad])
    s1 = c.snap()
    _expect_rejected(c, R, s0, s1, "Hatalı parity'li", "Parity Error", strict_err=True)
    for ch in c.chans:
        if c.delta(s0, s1, ch, "err"):
            e = c.last_errors(ch, 1)[-1]
            R.add(f"{channel_label(ch)}: hata kaydında Word = 0x{bad:08X}", e["data"] == bad, f"0x{e['data']:08X}")
    s2 = c.snap()
    c.send_words([good])
    s3 = c.snap()
    R.add("Ardından doğru parity'li Word tüm kanallarda alındı",
          all(c.delta(s2, s3, ch, "word") == 1 for ch in c.chans))
    c.chk_clear()


def t_gapviol(c: Ctx, R: TestResult):
    """Gap tespiti: Word'ler arası 2 bit gap (< 4 bit) → GAP_VIOLATION, Word kabul edilmemeli."""
    c.baseline()
    hs = c.tx_timing()
    try:
        c.w([("TX_CUST_PULSE_DUR", hs["pulse"]), ("TX_CUST_NULL_DUR", hs["null"]), ("TX_CUST_GAP_DUR", 2 * hs["bit"]),
             ("TX_CUST_SLP", 1), ("TX_CFG_SEL", 2), ("TX_CFG_APPLY", 1)])
        tim = c.tx_timing()
        R.add(f"TX Custom: gap {c.us(tim['gap']):.1f} µs (2 bit) aktif", tim["gap"] == 2 * hs["bit"])
        c.w([("TX_EXT_DATA", odd_parity(0x0C0FFEE))])
        s0 = c.snap()
        _scheduler_run(c, 5, 1, tim)
        s1 = c.snap()
        _expect_rejected(c, R, s0, s1, "2 bit gap'li", "Gap Violation", strict_err=True)
    finally:
        c.set_speed(tx="HS")
    c.settle()
    s2 = c.snap()
    c.send_words([odd_parity(0x0C0FFEE)])
    s3 = c.snap()
    R.add("Standart gap'e dönünce alım devam ediyor", all(c.delta(s2, s3, ch, "word") == 1 for ch in c.chans))
    c.chk_clear()


def t_logger(c: Ctx, R: TestResult):
    c.baseline()
    wd = odd_parity(0x0555AAA)
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 0)])
    s0 = c.snap()
    c.send_words([wd])
    s1 = c.snap()
    R.add("ENABLE=0: Word ve hata kaydedilmedi",
          all(c.delta(s0, s1, ch, "word") == 0 and c.delta(s0, s1, ch, "err") == 0 for ch in c.chans))
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 0b011)])          # ENABLE + FREEZE
    s0 = c.snap()
    c.send_words([wd])
    s1 = c.snap()
    R.add("FREEZE=1: Word RAM'e yazılmadı, DROP_CNT +1",
          all(c.delta(s0, s1, ch, "word") == 0 and c.delta(s0, s1, ch, "drop") == 1 for ch in c.chans),
          "; ".join(f"{channel_label(ch)} W+{c.delta(s0, s1, ch, 'word')} D+{c.delta(s0, s1, ch, 'drop')}" for ch in c.chans))
    for ch in c.chans:
        c.w([(channel_prefix(ch) + "CTRL", 1)])
    c.w([("GLOBAL_FREEZE", 1)])
    s0 = c.snap()
    c.send_words([wd])
    s1 = c.snap()
    c.w([("GLOBAL_FREEZE", 0)])
    R.add("GLOBAL_FREEZE=1: tüm kanallarda DROP_CNT +1",
          all(c.delta(s0, s1, ch, "word") == 0 and c.delta(s0, s1, ch, "drop") == 1 for ch in c.chans))
    s0 = c.snap()
    c.send_words([wd])
    s1 = c.snap()
    R.add("Normal moda dönüş: Word alındı", all(c.delta(s0, s1, ch, "word") == 1 for ch in c.chans))
    c.chk_clear()


def t_custom(c: Ctx, R: TestResult):
    """Config sekmesinde hesaplanan Custom TX / RX config ile alım."""
    if not c.custom:
        R.status = "SKIP"
        R.notes.append("Config sekmesinden Custom config alınamadı")
        return
    c.baseline()
    try:
        tx = [(n, v) for n, v in c.custom.get("tx", []) if n.startswith("TX_CUST_") or n in ("TX_CFG_SEL",)]
        c.w(tx + [("TX_CFG_SEL", 2), ("TX_CFG_APPLY", 1)])
        for ch in c.chans:
            send_rx_config(c.bus, c.rm, ch, c.custom["rx"], verify=True, quiet=True)
        R.add("Custom TX / RX config yazıldı ve geri okundu", True)
        c.settle()
        t_pattern(c, R, "HS", n=8)
        t_bittime(c, R, "HS")
    finally:
        c.set_speed(tx="HS", rx="HS")
        c.settle()


# id, başlık, fonksiyon, hız parametreli mi
CATALOG = [
    ("ident", "Bağlantı ve IP kimliği", t_ident, False),
    ("prep", "Hazırlık: reset, logger, checker", t_prep, False),
    ("idle", "Hat boşta seviyesi (NULL)", t_idle, False),
    ("polarity", "Hat polaritesi (override HIGH / LOW / NULL)", t_polarity, False),
    ("single", "Tek Word (Word Builder + parity)", t_single, True),
    ("pattern", "Veri bütünlüğü deseni", t_pattern, True),
    ("bittime", "Bit zamanlaması (sürücü / alıcı)", t_bittime, True),
    ("period", "Scheduler periyodu ve gap ölçümü", t_period, True),
    ("burst", "Art arda gönderim (minimum gap)", t_burst, True),
    ("switch", "HS ↔ LS art arda geçiş", t_switch, False),
    ("mismatch", "Hız uyuşmazlığı tespiti", t_mismatch, False),
    ("parity", "Parity hatası tespiti", t_parity, False),
    ("gapviol", "Gap ihlali tespiti (gap detection)", t_gapviol, False),
    ("logger", "Logger ENABLE / FREEZE / GLOBAL_FREEZE", t_logger, False),
    ("custom", "Config sekmesi Custom config ile alım", t_custom, False),
]
ALWAYS = ("ident", "prep")


def plan(selected: list[str] | None, speeds=("HS", "LS")) -> list[tuple[str, str, object, str]]:
    """Koşulacak adımlar: (id, başlık, fonksiyon, hız)."""
    sel = set(selected or [t[0] for t in CATALOG]) | set(ALWAYS)
    steps = []
    for tid, title, fn, per_speed in CATALOG:
        if tid not in sel:
            continue
        if per_speed:
            for sp in speeds:
                steps.append((tid, title, fn, sp))
        else:
            steps.append((tid, title, fn, ""))
    return steps


def restore(c: Ctx):
    """Test sonrası kartı kullanılabilir duruma getirir: HS preset, Word Transmitter, scheduler kapalı."""
    try:
        c.set_speed(tx="HS", rx="HS")
        c.w([("TX_EXT_HIGH", 0), ("TX_EXT_LOW", 0), ("TX_SCHED_EN", 0), ("TX_MSG_SCHED_EN", 0),
             ("TX_TRANSMITTER_EN", 1), ("TX_BUILDER_EN", 1), ("TX_INTER_WORD_GAP", 1), ("GLOBAL_FREEZE", 0)])
        for ch in c.chans:
            c.w([(channel_prefix(ch) + "CTRL", 1)])
    except Exception as e:                                       # noqa: BLE001
        c.log(f"UYARI: test sonrası geri yükleme: {e}")


def run(bus, rm: RegMap, rx_channels: list[str], selected: list[str] | None = None, speeds=("HS", "LS"),
        use_tb: bool = True, pattern_len: int = 35, burst_words: int = 40, custom: dict | None = None,
        stop_on_fail: bool = False, log=None, progress=None, on_result=None,
        stop: threading.Event | None = None) -> dict:
    """Test takımını koşar. on_result(TestResult) her adımdan sonra çağrılır."""
    c = Ctx(bus, rm, rx_channels, use_tb, pattern_len, burst_words, custom, log, stop)
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
                    c.set_speed(tx=sp, rx=sp)
                    c.settle()
                    fn(c, R, sp)
                else:
                    fn(c, R)
            except TestAborted as e:
                R.status = "SKIP"
                R.notes.append(str(e))
                aborted = True
            except Exception as e:                               # noqa: BLE001
                R.status = "ERROR"
                R.notes.append(f"{type(e).__name__}: {e}")
            R.duration_s = round(time.monotonic() - t0, 2)
            results.append(R)
            c.log(f"[Test] {R.status:5s} {title}{' · ' + sp if sp else ''}: {R.summary}")
            if on_result:
                on_result(R)
            if aborted or (stop_on_fail and R.status in ("FAIL", "ERROR")) or (tid == "ident" and R.status != "PASS"):
                break
        prog(len(steps), len(steps), "Tamamlandı")
    finally:
        restore(c)
        if lock:
            bus.unlock()
    counts = {k: sum(1 for r in results if r.status == k) for k in ("PASS", "FAIL", "ERROR", "SKIP")}
    sim_info = {"cycles": getattr(bus, "sim_cycles", None)}
    return {
        "results": results,
        "counts": counts,
        "passed": counts["FAIL"] == 0 and counts["ERROR"] == 0 and not aborted and bool(results),
        "aborted": aborted,
        "duration_s": round(time.monotonic() - t_start, 1),
        "setup": {"rx": c.rx, "tb": c.use_tb, "speeds": list(speeds), "clk_hz": c.clk_hz, "ip": rm.name,
                  "base": rm.base},
        "sim": sim_info,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =====================================================================================
def report_text(rep: dict) -> str:
    s = rep["setup"]
    L = ["ARINC 429 IP Loopback Test Raporu", "=" * 34,
         f"Tarih      : {rep['started']}",
         f"IP         : {s['ip']} @ 0x{s['base']:08X}, {s['clk_hz'] / 1e6:g} MHz",
         f"Kurulum    : TX → {', '.join(s['rx']) or '(RX yok)'}" + (" + TX BIT (TB)" if s["tb"] else ""),
         f"Hızlar     : {', '.join(s['speeds'])}",
         f"Sonuç      : {'GEÇTİ' if rep['passed'] else 'KALDI'}  "
         f"(PASS {rep['counts']['PASS']}, FAIL {rep['counts']['FAIL']}, ERROR {rep['counts']['ERROR']}, "
         f"SKIP {rep['counts']['SKIP']}; {rep['duration_s']} s)", ""]
    for r in rep["results"]:
        L.append(f"[{r.status:5s}] {r.title}{' · ' + r.speed if r.speed else ''}  ({r.duration_s} s)")
        for ck in r.checks:
            mark = {True: "  ✓", False: "  ✗", None: "  ·"}[ck.ok]
            L.append(f"{mark} {ck.name}" + (f" — {ck.detail}" if ck.detail else ""))
        for n in r.notes:
            L.append(f"  ! {n}")
        if r.measurements:
            L.append("    ölçümler: " + json.dumps(r.measurements, ensure_ascii=False))
        L.append("")
    return "\n".join(L)


def report_json(rep: dict) -> str:
    d = dict(rep)
    d["results"] = [r.to_dict() for r in rep["results"]]
    return json.dumps(d, ensure_ascii=False, indent=2)
