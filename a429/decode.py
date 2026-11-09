"""Okunan word / error / bit diagnostik verilerinin çözümlenmesi (Excel 'Okuma_*' sayfalarının karşılığı)."""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

UNITS = ["clk", "ns", "µs", "ms", "s"]
ERR_NAMES = ["Bus Fault", "Noise Violation", "Gap Violation", "Bit Early",
             "Pulse Glitch", "Pulse Stuck", "Bit Timeout", "Parity Error"]


@dataclass
class DecodeSettings:
    parity_odd: bool = True
    ts_tol: float = 0.01                 # timestamp tutarlılık toleransı (oran)
    ts_at_word_end: bool = True          # timestamp word bitince mi alınıyor
    label_fmt: str = "oct"               # dalga formu alan formatları
    sdi_fmt: str = "dec"
    data_fmt: str = "hex"
    ssm_fmt: str = "dec"

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return DecodeSettings(**{k: v for k, v in d.items() if k in DecodeSettings.__dataclass_fields__})


@dataclass
class Limits:
    mhz: float
    minp: int
    maxp: int
    minb: int
    maxb: int
    gap_err: int
    null_err: int
    pulse_err: int

    @staticmethod
    def from_result(res, mhz):
        v = res.vars
        return Limits(mhz, v["min_pulse"], v["max_pulse"], v["min_bit"], v["max_bit"],
                      v["max_gap_glitch_error"], v["max_null_glitch_error"], v["max_pulse_glitch_error"])


    def for_clock(self, mhz):
        """Aynı süre limitlerini okumanın clock'una çevirir."""
        if mhz == self.mhz:
            return self
        f = mhz / self.mhz
        return Limits(mhz, math.floor(self.minp * f), math.ceil(self.maxp * f), math.floor(self.minb * f), math.ceil(self.maxb * f),
                      math.floor(self.gap_err * f), math.floor(self.null_err * f), math.floor(self.pulse_err * f))


def session_mhz(session, default):
    """Okumanın kayıtlı clock'u; eski okumalarda kopyalanan ayarlardan alınır."""
    return session.get("clk_mhz") or session.get("settings", {}).get("config", {}).get("clk_mhz") or default


# ---------------------------------------------------------------- yardımcılar
def conv(clk, unit, mhz):
    """clock → birim"""
    if clk is None:
        return None
    return {"clk": clk, "ns": clk * 1000 / mhz, "µs": clk / mhz, "ms": clk / mhz / 1000, "s": clk / mhz / 1e6}[unit]


def ft(clk, unit, mhz, with_unit=True):
    v = conv(clk, unit, mhz)
    if v is None:
        return ""
    s = f"{v:,.0f}" if unit == "clk" else (f"{v:,.6f}" if unit == "s" else f"{v:,.3f}")
    return f"{s} {unit}" if with_unit else s


def fmt_val(v, kind, width=None):
    if v is None:
        return "?"
    if kind == "oct":
        return f"o'{v:o}"
    if kind == "hex":
        return f"h'{v:0{width or 1}X}"
    return f"d'{v}"


def word_fields(wd):
    return {"label": wd & 0xFF, "sdi": (wd >> 8) & 3, "data": (wd >> 10) & 0x7FFFF,
            "ssm": (wd >> 29) & 3, "p": (wd >> 31) & 1}


def rx_bits(wd):
    """Alım sırası (bit 1 → 32): label MSB önce (word_data[7..0]), sonra word_data[8..31]."""
    return [(wd >> (7 - i)) & 1 for i in range(8)] + [(wd >> n) & 1 for n in range(8, 32)]


def rx_binary(wd, sep="-"):
    b = "".join(map(str, rx_bits(wd)))
    return sep.join([b[0:8], b[8:10], b[10:29], b[29:31], b[31]])


def parity_ok(wd, odd=True):
    return (bin(wd).count("1") % 2 == 1) == odd


def pf(ok):
    return "PASS" if ok else "FAIL"


# ---------------------------------------------------------------- çözümleme
def ts_of(w):
    if w[0] is None or w[1] is None:
        return None
    return (w[0] << 32) | w[1]


def bits_by_word(session):
    d = {}
    for b in session.get("bits", []):
        d.setdefault(b["word"], {})[b["bit"]] = b
    return d


def decode_bits(session, lim: Limits):
    rows = []
    for b in session.get("bits", []):
        p, pe, n, ne = (x if x is not None else 0 for x in b["w"])
        rows.append(dict(word=b["word"], bit=b["bit"], pulse=p, null=n, bitlen=p + n, perr=pe, nerr=ne,
                         ok_pulse=lim.minp <= p <= lim.maxp, ok_bit=lim.minb <= p + n <= lim.maxb,
                         ok_perr=pe <= lim.pulse_err, ok_nerr=ne <= lim.null_err,
                         ok_pad=all(x < 65536 for x in (p, pe, n, ne)), raw=b["w"]))
    return rows


def decode_words(session, lim: Limits, ds: DecodeSettings):
    bmap = {}
    for r in decode_bits(session, lim):
        bmap.setdefault(r["word"], []).append(r)
    words = session.get("words", [])
    rows = []
    for i, w in enumerate(words):
        ts, wd, gap, gerr = ts_of(w["w"]), w["w"][2], w["w"][3], w["w"][4]
        r = dict(no=w["no"], addr=w.get("addr"), ts=ts, wd=wd, gap=gap, gerr=gerr, raw=w["w"])
        if wd is not None:
            r.update(word_fields(wd)); r["parity_ok"] = parity_ok(wd, ds.parity_odd); r["bin"] = rx_binary(wd)
        r["gap_ok"] = gap is not None and gap >= 4 * lim.minb
        r["gerr_ok"] = gerr is not None and gerr <= lim.gap_err
        r["pad_ok"] = gerr is not None and gerr < 65536
        # önceki word (word no − 1): liste en yeni önce olduğu için bir sonraki satır
        prev = words[i + 1] if i + 1 < len(words) else None
        r["dt"] = ts - ts_of(prev["w"]) if prev and ts is not None and ts_of(prev["w"]) is not None else None
        if prev and ts is not None and ts_of(prev["w"]) is not None:
            r["ts_order_ok"] = ts > ts_of(prev["w"])
        bl = bmap.get(w["no"], [])
        r["nbits"] = len(bl)
        if bl:
            r["minp"] = min(b["pulse"] for b in bl); r["maxp"] = max(b["pulse"] for b in bl)
            r["minb"] = min(b["bitlen"] for b in bl); r["maxb"] = max(b["bitlen"] for b in bl)
            r["sum_perr"] = sum(b["perr"] for b in bl); r["sum_nerr"] = sum(b["nerr"] for b in bl)
            r["fail_list"] = [b["bit"] + 1 for b in bl if not (b["ok_pulse"] and b["ok_bit"] and b["ok_perr"] and b["ok_nerr"])]
            r["fail_bits"] = len(r["fail_list"])
            r["bit_lens"] = {b["bit"]: b["bitlen"] for b in bl}
        if len(bl) >= 32 and gap is not None:
            r["tot_bits"] = sum(b["bitlen"] for b in bl)
            r["bits_gap"] = r["tot_bits"] + gap
            if prev and prev["no"] == w["no"] - 1 and r["dt"] is not None:
                r["dts"] = r["dt"]
                r["diff"] = r["dt"] - r["bits_gap"]
                r["ts_ok"] = abs(r["diff"]) <= ds.ts_tol * r["dt"]
        rows.append(r)
    return rows


def decode_errors(session):
    errs = session.get("errors", [])
    rows = []
    for i, e in enumerate(errs):
        ts, code, addr, data = ts_of(e["w"]), e["w"][2], e["w"][3], e["w"][4]
        prev = errs[i + 1] if i + 1 < len(errs) else None
        flags = [((code or 0) >> k) & 1 for k in range(8)]
        rows.append(dict(ts=ts, code=code, addr=addr, data=data, flags=flags,
                         active="(okunamadı)" if code is None else (", ".join(n for n, f in zip(ERR_NAMES, flags) if f) or "(yok)"),
                         code_ok=code is not None,
                         dt=ts - ts_of(prev["w"]) if prev and ts is not None and ts_of(prev["w"]) is not None else None,
                         pad_ok=code is not None and code < 256 and addr is not None and addr < 65536, raw=e["w"]))
    return rows


def stats(session, lim: Limits, wdepth=256, edepth=256, bit_words=8):
    s = session.get("summary", {})
    wt, et = s.get("total_word_cnt") or 0, s.get("total_error_cnt") or 0
    now = ((s.get("ts_msb") or 0) << 32) | (s.get("ts_lsb") or 0)
    words = session.get("words", [])
    errs = session.get("errors", [])
    w_kept, e_kept = min(wt, wdepth), min(et, edepth)
    last_w = max((ts_of(w["w"]) for w in words if ts_of(w["w"]) is not None), default=None)
    last_e = max((ts_of(e["w"]) for e in errs if ts_of(e["w"]) is not None), default=None)
    bit_nos = {b["word"] for b in session.get("bits", [])}
    partial = s.get("read_scope", {}).get("word", "all") != "all"
    res = [
        ("Toplam alınan Word", f"{wt:,}", "Reset'ten beri alınan tüm Word'ler."),
        ("Toplam Error", f"{et:,}", "Reset'ten beri oluşan tüm Error kayıtları."),
        ("Error oranı", f"{(et / wt * 100) if wt else 0:.2f} %", "Toplam Error / toplam Word."),
        ("Sistem çalışma süresi", ft(now, "s", lim.mhz), "Okuma anındaki timestamp."),
        ("Ortalama Word hızı", f"{(wt / (now / lim.mhz / 1e6)) if now else 0:,.2f} word/s", "Toplam Word / sistem çalışma süresi."),
        ("Word Buffer'daki kayıt sayısı", f"{w_kept}", "Buffer'da tutulan Word sayısı."),
        ("Okunan Word sayısı", f"{len(words)}", "Bu okumada karttan alınan Word sayısı."),
        ("Üzerine yazılan (kaybolan) Word", f"{max(0, wt - wdepth)}", "Buffer dolduğu için üzerine yazılan en eski Word'ler."),
        ("En yeni / en eski Word No", f"{wt - 1} … {wt - w_kept}" if wt else "-", "Liste en yeni üstte."),
        ("En eski Word'ün BRAM adresi", f"{(wt % wdepth) if wt > wdepth else 0}", "Circular Buffer başlangıcı."),
        ("Error Buffer'daki kayıt sayısı", f"{e_kept}", "Buffer'da tutulan Error sayısı."),
        ("Okunan Error sayısı", f"{len(errs)}", "Bu okumada karttan alınan Error sayısı."),
        ("Üzerine yazılan (kaybolan) Error", f"{max(0, et - edepth)}", ""),
        ("Bit Diagnostic verisi okunan Word'ler", f"{max(bit_nos)} … {min(bit_nos)}" if bit_nos else "-",
         "En eski kaydın üzerine yazılmış olabileceği için son (BRAM derinliği − 1) Word okunur."),
    ]
    for x in s.get("extra", []):
        val = "okunamadı" if x["value"] is None else (f"0x{x['value']:08X}" if x["fmt"] == "hex" else f"{x['value']:,}")
        res.append((x["name"], val, f"Ek okuma Register'ı, adres {x['addr']}."))
    wend, eend = s.get("wcnt_end"), s.get("ecnt_end")
    checks = [
        ("Okuma sırasında Word/Error sayacı değişmedi", "-" if "wcnt_end" not in s else pf(wend == wt and eend == et)),
        ("System Timestamp ≥ son Word Timestamp", "-" if last_w is None else pf(now >= last_w)),
        ("System Timestamp ≥ son Error Timestamp", "-" if last_e is None else pf(now >= last_e)),
        ("Son Word'den bu yana geçen süre", "-" if last_w is None else ft(now - last_w, "ms", lim.mhz)),
        ("Okunan Word sayısı = Buffer'daki kayıt sayısı", "-" if not wt or partial else pf(len(words) == w_kept)),
    ]
    return res, checks


# ---------------------------------------------------------------- TTL/Excel uyumlu dışa aktarma
def export_txt(session):
    h = lambda v: "XXXXXXXX" if v is None else f"{v:08X}"
    words = "\n".join(f"{w['no']}\t" + "\t".join(h(x) for x in w["w"]) for w in session.get("words", []))
    errors = "\n".join("\t".join(h(x) for x in e["w"]) for e in session.get("errors", []))
    bits = "\n".join(f"{b['word']}\t{b['bit']}\t" + "\t".join(h(x) for x in b["w"]) for b in session.get("bits", []))
    s = session.get("summary", {})
    summ = "\n".join([f"total_word_cnt\t{h(s.get('total_word_cnt'))}", f"total_error_cnt\t{h(s.get('total_error_cnt'))}",
                      f"timestamp_msb\t{h(s.get('ts_msb'))}", f"timestamp_lsb\t{h(s.get('ts_lsb'))}"])
    return {"a429_words.txt": words, "a429_errors.txt": errors, "a429_bits.txt": bits, "a429_summary.txt": summ}


def import_txt(words_txt="", errors_txt="", bits_txt="", summary_txt=""):
    """TTL makrosunun ürettiği txt dosyalarından oturum oluştur (eski okumaları açmak için)."""
    hv = lambda x: None if x.strip().upper().startswith("X") else int(x.strip(), 16)
    sess = {"summary": {}, "words": [], "errors": [], "bits": []}
    for ln in words_txt.splitlines():
        p = ln.split("\t")
        if len(p) >= 6:
            sess["words"].append({"no": int(p[0]), "w": [hv(x) for x in p[1:6]]})
    for ln in errors_txt.splitlines():
        p = ln.split("\t")
        if len(p) >= 5:
            sess["errors"].append({"w": [hv(x) for x in p[:5]]})
    for ln in bits_txt.splitlines():
        p = ln.split("\t")
        if len(p) >= 6:
            sess["bits"].append({"word": int(p[0]), "bit": int(p[1]), "w": [hv(x) for x in p[2:6]]})
    keys = {"total_word_cnt": "total_word_cnt", "total_error_cnt": "total_error_cnt",
            "timestamp_msb": "ts_msb", "timestamp_lsb": "ts_lsb"}
    for ln in summary_txt.splitlines():
        p = ln.split("\t")
        if len(p) >= 2 and p[0] in keys:
            sess["summary"][keys[p[0]]] = hv(p[1])
    return sess
