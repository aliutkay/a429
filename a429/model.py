"""ARINC 429 RX test IP – config hesap motoru (Excel 'Config' sayfasının birebir karşılığı)."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field, asdict

from .regs import RX_CONFIG_SPECS, RegMap, channel_prefix
from .txlive import default_tx_live

HB_ARINC = "ARINC (Rise → Fall başlangıcı)"
LEGACY_HB_ARINC = "ARINC (rise başı → fall başı)"   # eski proje dosyaları
HB_50 = "%50 – %50"
NOM_AMP = 10.0                          # nominal ARINC diferansiyel genliği (V)
ROW_PULSE = "FPGA'da görülen Pulse süresi (µs)"
ROW_BIT = "Receiver çıkışı Bit Time (µs)"
ROW_NULL = "Receiver çıkışı Null süresi (µs)"
DEFAULT_FPGA = [("LVCMOS33", 0.8, 2.0), ("LVTTL", 0.8, 2.0), ("Custom", 0.8, 1.7)]
# TX FPGA çıkış standartları: (ad, VOH_min V, VOL_max V, VCC V, tr ns, tf ns)
DEFAULT_TX_FPGA = [
    ("LVCMOS33", 2.4, 0.4, 3.3, 3.0, 3.0),
    ("LVTTL", 2.4, 0.4, 3.3, 3.0, 3.0),
    ("Custom", 2.4, 0.4, 3.3, 5.0, 5.0),
]
# Register formüllerinde kullanılabilen hesaplanan değişkenler (clock sayısı; clk_mhz hariç)
VARIABLES = [
    ("glitch_filter_size", "Glitch Filter Size"),
    ("min_pulse", "Min Pulse"), ("max_pulse", "Max Pulse"),
    ("min_bit", "Min Bit"), ("max_bit", "Max Bit"),
    ("min_null", "Min Null"), ("max_null", "Max Null"),
    ("nom_pulse", "Nominal Pulse"), ("nom_bit", "Nominal Bit Time"), ("nom_null", "Nominal Null"),
    ("word_gap_base", "Word Gap referansı (4 × Min Bit)"),
    ("pulse_glitch_base", "Pulse Glitch referansı"), ("null_glitch_base", "Null Glitch referansı"),
    ("max_gap_glitch_error", "Word Gap Glitch Error limiti"),
    ("max_null_glitch_error", "Null Glitch Error limiti"),
    ("max_pulse_glitch_error", "Pulse Glitch Error limiti"),
    ("clk_mhz", "System Clock (MHz)"),
]


@dataclass
class SpecProfile:
    name: str
    rate_min: float      # kbps
    rate_nom: float
    rate_max: float
    rate_tol: float      # oran (0.01 = %1) – bilgi: ±2.5% bit toleransının içinde kalır, hesaba eklenmez
    bit_tol: float
    half_tol: float
    rise_nom: float      # µs
    rise_tol: float
    fall_nom: float
    fall_tol: float
    amp_min: float       # V (alıcı girişi)
    amp_max: float
    k: float = 0.8       # 10→90 % ölçüm aralığı


DEFAULT_PROFILES = [
    SpecProfile("High Speed (100k)", 100, 100, 100, 0.01, 0.025, 0.05, 1.5, 0.5, 1.5, 0.5, 6.5, 13),
    SpecProfile("Low Speed (12-14.5k)", 12, 12.5, 14.5, 0.01, 0.025, 0.05, 10, 5, 10, 5, 6.5, 13),
    SpecProfile("Low Speed (12.5k)", 12.5, 12.5, 12.5, 0.01, 0.025, 0.05, 10, 5, 10, 5, 6.5, 13),
    SpecProfile("Custom", 50, 50, 50, 0.01, 0.025, 0.05, 3, 1, 3, 1, 6.5, 13),
]


@dataclass
class ICParams:
    """Alıcı entegre parametreleri: (min, nom, max)."""
    v_one: tuple = (5.5, 6.0, 6.5)      # V
    v_null: tuple = (2.5, 3.3, 4.0)     # V
    tplh: tuple = (0, 600, 1000)        # ns
    tphl: tuple = (0, 600, 1000)        # ns
    trr: tuple = (0, 15, 50)            # ns, çıkış %10→%90
    tfr: tuple = (0, 15, 50)            # ns
    vcc: tuple = (2.97, 3.3, 3.63)      # V, entegre VCC = çıkış salınımı
    voh_min: float = 2.4                # V
    vol_max: float = 0.4                # V
    name: str = "HI-8591"


@dataclass
class TxDriverParams:
    """ARINC 429 Line Driver entegre parametreleri: (min, nom, max)."""
    name: str = "HI-8597"
    vil_max: float = 0.99               # V (HI-8597: 0.3 * 3.3 V)
    vih_min: float = 2.31               # V (HI-8597: 0.7 * 3.3 V)
    tplh: tuple = (200.0, 500.0, 1000.0)   # ns
    tphl: tuple = (200.0, 500.0, 1000.0)   # ns
    skew_max: float = 150.0             # ns, |tPLH - tPHL| max (0 ise bağımsız min/max farkı kullanılır)
    tr_hs: tuple = (1.0, 1.5, 2.0)      # µs, High Speed (%10→%90)
    tf_hs: tuple = (1.0, 1.5, 2.0)      # µs
    tr_ls: tuple = (5.0, 10.0, 15.0)    # µs, Low Speed (%10→%90)
    tf_ls: tuple = (5.0, 10.0, 15.0)    # µs
    vdiff: tuple = (9.0, 10.0, 11.0)    # V, diferansiyel çıkış genliği
    has_slp: bool = True                # Dijital SLP pini (1: 1.5 µs, 0: 10 µs)
    has_hiz: bool = True                # TX1IN=1, TX0IN=1 → HIGH-Z desteği


DEFAULT_TX_DRIVERS = [
    TxDriverParams("HI-8597", 0.99, 2.31, (200, 500, 1000), (200, 500, 1000), 150,
                   (1.0, 1.5, 2.0), (1.0, 1.5, 2.0), (5.0, 10.0, 15.0), (5.0, 10.0, 15.0),
                   (9.0, 10.0, 11.0), True, True),
    TxDriverParams("HI-8585", 0.8, 2.0, (100, 500, 2000), (100, 500, 2000), 200,
                   (1.0, 1.5, 2.0), (1.0, 1.5, 2.0), (5.0, 10.0, 15.0), (5.0, 10.0, 15.0),
                   (9.0, 10.0, 11.0), True, False),
    TxDriverParams("HI-8592", 0.8, 2.0, (50, 250, 500), (50, 250, 500), 150,
                   (1.0, 1.5, 2.0), (1.0, 1.5, 2.0), (5.0, 10.0, 15.0), (5.0, 10.0, 15.0),
                   (9.0, 10.0, 11.0), True, False),
    TxDriverParams("HS-3182", 0.5, 2.0, (500, 1500, 3300), (500, 1500, 3300), 300,
                   (1.0, 1.5, 2.0), (1.0, 1.5, 2.0), (3.0, 6.0, 9.0), (3.0, 6.0, 9.0),
                   (9.0, 10.0, 11.0), False, False),
]


@dataclass
class ConfigInputs:
    clk_mhz: float = 50.0
    ppm: float = 50.0                   # sistem clock toleransı (±ppm)
    fpga_std: str = "LVCMOS33"
    fpga_table: list = field(default_factory=lambda: [list(x) for x in DEFAULT_FPGA])
    profile: str = "High Speed (100k)"     # RX ARINC profili
    tx_profile: str = "High Speed (100k)"  # TX ARINC profili (aynı profil listesinden)
    err: float = 0.05
    half_ref: str = HB_ARINC
    gf_mode: str = "ratio"              # "ratio" | "clock"
    gf_ref: str = "Min Pulse"           # "Min Pulse" | "Min Null" | "Min Bit"
    gf_ratio: float = 0.25
    gf_clock: int = 50
    pulse_glitch_pct: float = 0.10
    null_glitch_pct: float = 0.10
    gap_glitch_pct: float = 0.10
    glitch_base: str = "MIN"            # MIN | NOM | MAX
    tx_live: dict = field(default_factory=default_tx_live)
    profiles: list = field(default_factory=lambda: copy.deepcopy(DEFAULT_PROFILES))
    ic_profiles: list = field(default_factory=lambda: [ICParams()])
    ic_profile: str = "HI-8591"
    tx_drivers: list = field(default_factory=lambda: copy.deepcopy(DEFAULT_TX_DRIVERS))
    tx_driver: str = "HI-8597"
    tx_fpga_std: str = "LVCMOS33"
    tx_fpga_table: list = field(default_factory=lambda: [list(x) for x in DEFAULT_TX_FPGA])
    tx_comp_delay: bool = False         # Line Driver tPHL-tPLH farkını TX_CUST_PULSE_DUR'da telafi et
    tx_gap_margin: bool = False         # Word Gap'e +ppm güvenlik marjı ekle

    # ---- (de)serialisation
    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d, link=None):
        d = dict(d)
        d.pop("regmap", None)           # eski dosyalardaki komut/register şablonu artık kullanılmıyor
        if d.get("half_ref") == LEGACY_HB_ARINC:
            d["half_ref"] = HB_ARINC
        prof = [SpecProfile(**p) for p in d.pop("profiles", [])] or copy.deepcopy(DEFAULT_PROFILES)
        make_ic = lambda x: ICParams(**{k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in x.items()
                                        if k in ICParams.__dataclass_fields__})
        old_ic = d.pop("ic", {})                # eski dosyalar: tek entegre
        ics = [make_ic(x) for x in d.pop("ic_profiles", [])] or [make_ic(old_ic)]
        make_drv = lambda x: TxDriverParams(**{k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in x.items()
                                               if k in TxDriverParams.__dataclass_fields__})
        drvs = [make_drv(x) for x in d.pop("tx_drivers", [])] or copy.deepcopy(DEFAULT_TX_DRIVERS)
        ci = ConfigInputs(**{k: v for k, v in d.items() if k in ConfigInputs.__dataclass_fields__})
        ci.profiles, ci.ic_profiles, ci.tx_drivers = prof, ics, drvs
        ci.tx_live = {**default_tx_live(), **ci.tx_live}
        if "tx_profile" not in d:               # eski dosyalar: TX, RX ile aynı başlar
            ci.tx_profile = ci.profile
        return ci

    def get_fpga(self):
        for n, vil, vih in self.fpga_table:
            if n == self.fpga_std:
                return float(vil), float(vih)
        return float(self.fpga_table[0][1]), float(self.fpga_table[0][2])

    def get_tx_fpga(self):
        """(voh_min, vol_max, vcc, tr_ns, tf_ns)"""
        for r in self.tx_fpga_table:
            if r[0] == self.tx_fpga_std:
                return tuple(float(x) for x in r[1:6])
        return tuple(float(x) for x in self.tx_fpga_table[0][1:6])

    @property
    def ic(self) -> ICParams:
        return next((x for x in self.ic_profiles if x.name == self.ic_profile), self.ic_profiles[0])

    @property
    def driver(self) -> TxDriverParams:
        return next((x for x in self.tx_drivers if x.name == self.tx_driver), self.tx_drivers[0])

    def get_profile(self) -> SpecProfile:
        for p in self.profiles:
            if p.name == self.profile:
                return p
        return self.profiles[0]


def _floor(x):   # Excel ROUNDDOWN(x,0), kayan nokta toleranslı
    return int(math.floor(x + 1e-9))


def _ceil(x):    # Excel ROUNDUP(x,0)
    return int(math.ceil(x - 1e-9))


@dataclass
class Result:
    rows: dict              # ara hesaplar: ad -> (min, nom, max)
    dur: dict               # test toleransı eklenmiş süreler: ad -> (µs, clk)
    regs: list              # [(görünen ad, Studio register adı, offset, değer, değer_hex, hata)]
    checks: list            # [(ad, ok)]
    single: dict            # tek bit analizi: "MIN"/"NOM"/"MAX" -> dict
    vars: dict = field(default_factory=dict)   # hesaplanan değişkenler (çözümleme limitleri)
    nom_clk: tuple = (0, 0, 0)   # nominal (pulse, bit, null) clk – örnek grafik / word dalga formu
    rx_values: dict = field(default_factory=dict)  # {CUST_* soneki: int}


def compute(ci: ConfigInputs, rm: RegMap | None = None, channel: str = "RX0") -> Result:
    p, ic, mhz = ci.get_profile(), ci.ic, ci.clk_mhz
    for value, name in ((mhz, "System Clock"), (p.rate_min, "Bit Rate MIN"), (p.rate_nom, "Bit Rate NOM"), (p.rate_max, "Bit Rate MAX"),
                        (p.k, "k"), (p.amp_min, "Receiver genliği MIN"), (p.amp_max, "Receiver genliği MAX"),
                        (ic.vcc[0], "VCC MIN"), (ic.vcc[1], "VCC NOM"), (ic.vcc[2], "VCC MAX")):
        if value <= 0:
            raise ValueError(f"{name} sıfırdan büyük olmalı.")
    # ARINC: Y = Z ±bit_tol, X = Z/2 ±half_tol (Z = 1000/R, R seçili hız). ±1% hız toleransı ortalamadır → eklenmez.
    rate = (p.rate_min, p.rate_nom, p.rate_max)
    tbit = (1000 / rate[2] * (1 - p.bit_tol), 1000 / rate[1], 1000 / rate[0] * (1 + p.bit_tol))
    thalf = (1000 / rate[2] / 2 * (1 - p.half_tol), tbit[1] / 2, 1000 / rate[0] / 2 * (1 + p.half_tol))
    rise = (p.rise_nom - p.rise_tol, p.rise_nom, p.rise_nom + p.rise_tol)
    fall = (p.fall_nom - p.fall_tol, p.fall_nom, p.fall_nom + p.fall_tol)
    amin, amax, k = p.amp_min, p.amp_max, p.k
    arinc = ci.half_ref == HB_ARINC
    cr, cf = (0.0, 1.0) if arinc else (0.5, 0.5)
    x1 = ic.v_one[2] / amin - cr; x2 = ic.v_one[0] / amax - cr
    y1 = cf - ic.v_null[2] / amin; y2 = cf - ic.v_null[0] / amax
    xn = ic.v_one[1] / NOM_AMP - cr; yn = cf - ic.v_null[1] / NOM_AMP
    redge = (min(-x1 * rise[0] / k, -x1 * rise[2] / k), -xn * rise[1] / k, max(-x2 * rise[0] / k, -x2 * rise[2] / k))
    fedge = (min(y1 * fall[0] / k, y1 * fall[2] / k), yn * fall[1] / k, max(y2 * fall[0] / k, y2 * fall[2] / k))
    vil, vih = ci.get_fpga()
    fv = (vil / ic.vcc[2], (vil + vih) / 2 / ic.vcc[1], vih / ic.vcc[0])
    drise, dfall = edge_delays(ic, fv)
    pulse = (thalf[0] + redge[0] + fedge[0] + dfall[0] - drise[0],
             thalf[1] + redge[1] + fedge[1] + dfall[1] - drise[1],
             thalf[2] + redge[2] + fedge[2] + dfall[2] - drise[2])
    bit = tbit
    null = (max(0.0, bit[0] - pulse[2]), bit[1] - pulse[1], bit[2] - pulse[0])
    rows = {"Bit Rate (kbps)": rate, "1 Bit Time (µs)": tbit, "½ Bit Time (µs)": thalf,
            "Rise Time (µs)": rise, "Fall Time (µs)": fall, "Receiver giriş genliği A (V)": (amin, None, amax),
            "Rising Edge eşik etkisi (µs)": redge, "Falling Edge eşik etkisi (µs)": fedge,
            "FPGA giriş eşiği v = Vt / VCC (alt / NOM / üst)": fv,
            "Rising Edge gecikmesi: Receiver giriş eşiği → FPGA (µs)": drise,
            "Falling Edge gecikmesi: Receiver giriş eşiği → FPGA (µs)": dfall,
            ROW_PULSE: pulse, ROW_BIT: bit, ROW_NULL: null}

    e = ci.err
    minp = pulse[0] * (1 - e); maxp = pulse[2] * (1 + e)
    minb = bit[0] * (1 - e); maxb = bit[2] * (1 + e)
    minn = null[0] * (1 - e); maxn = null[2] * (1 + e)
    flo, fhi = mhz * (1 - ci.ppm / 1e6), mhz * (1 + ci.ppm / 1e6)
    c = {"minp": _floor(minp * flo), "maxp": _ceil(maxp * fhi), "minb": _floor(minb * flo),
         "maxb": _ceil(maxb * fhi), "minn": _floor(minn * flo), "maxn": _ceil(maxn * fhi)}
    c["gap"] = 4 * c["minb"]
    if ci.gf_mode == "clock":
        c["gf"] = int(ci.gf_clock)
    else:
        ref = {"Min Pulse": c["minp"], "Min Null": c["minn"], "Min Bit": c["minb"]}[ci.gf_ref]
        c["gf"] = max(1, _floor(ref * ci.gf_ratio))
    c["pbase"] = {"MIN": c["minp"], "MAX": c["maxp"]}.get(ci.glitch_base, round(pulse[1] * mhz))
    c["nbase"] = {"MIN": c["minn"], "MAX": c["maxn"]}.get(ci.glitch_base, round(null[1] * mhz))
    dur = {"Min Pulse": (minp, c["minp"]), "Max Pulse": (maxp, c["maxp"]), "Min Bit": (minb, c["minb"]),
           "Max Bit": (maxb, c["maxb"]), "Min Null": (minn, c["minn"]), "Max Null": (maxn, c["maxn"]),
           "Word Gap referans süresi (4 × Min Bit)": (c["gap"] / mhz, c["gap"]),
           "Glitch Filter Size": (c["gf"] / mhz, c["gf"]),
           "Pulse Glitch referans süresi": (c["pbase"] / mhz, c["pbase"]),
           "Null Glitch referans süresi": (c["nbase"] / mhz, c["nbase"])}
    cvars = dict(glitch_filter_size=c["gf"], min_pulse=c["minp"], max_pulse=c["maxp"], min_bit=c["minb"], max_bit=c["maxb"],
                 min_null=c["minn"], max_null=c["maxn"], word_gap_base=c["gap"], pulse_glitch_base=c["pbase"],
                 null_glitch_base=c["nbase"], max_gap_glitch_error=_floor(c["gap"] * ci.gap_glitch_pct),
                 max_null_glitch_error=_floor(c["nbase"] * ci.null_glitch_pct),
                 max_pulse_glitch_error=_floor(c["pbase"] * ci.pulse_glitch_pct), clk_mhz=mhz)

    checks = [
        ("One/Zero eşiği MAX ≤ Receiver giriş genliği MIN", ic.v_one[2] <= amin),
        ("Null eşiği MAX < One/Zero eşiği MIN", ic.v_null[2] < ic.v_one[0]),
        ("Pulse tepesinde düz bölge var", (thalf[0] - rise[2] / k) > 0 if arinc else (thalf[0] - (rise[2] + fall[2]) / (2 * k)) > 0),
        ("Min Pulse > 0", minp > 0),
        ("Glitch Filter Size < Min Pulse", c["gf"] < c["minp"]),
        ("Glitch Filter Size < Min Null", c["gf"] < c["minn"]),
        ("Max Pulse < Min Bit", maxp < minb),
        ("Receiver VOH MIN ≥ FPGA VIH MIN", ic.voh_min >= vih),
        ("Receiver VOL MAX ≤ FPGA VIL MAX", ic.vol_max <= vil),
        ("FPGA VIL MAX < VIH MIN", vil < vih),
        ("Bit Rate MIN ≤ NOM ≤ MAX", rate[0] <= rate[1] <= rate[2]),
        ("Rise Time ve Fall Time MIN > 0", rise[0] > 0 and fall[0] > 0),
        ("k oranı 1'den büyük değil", k <= 1),
        ("Receiver genliği MIN ≤ MAX", amin <= amax),
        ("Receiver parametrelerinde MIN ≤ NOM ≤ MAX", all(t[0] <= t[1] <= t[2] for t in (ic.v_one, ic.v_null, ic.tplh, ic.tphl, ic.trr, ic.tfr, ic.vcc))),
    ]
    single = _single_bit(ci, p, rise, fall, thalf, tbit, arinc, cr, cf, fv, drise, dfall)
    nom = (round(pulse[1] * mhz), round(bit[1] * mhz))
    nom_clk = (nom[0], nom[1], nom[1] - nom[0])
    cvars.update(nom_pulse=nom_clk[0], nom_bit=nom_clk[1], nom_null=nom_clk[2])
    regs = []
    rx_values = {}
    prefix = channel_prefix(channel)
    loaded = rm is not None and rm.is_loaded()
    for disp_name, suffix, var_key, bits in RX_CONFIG_SPECS:
        full_name = prefix + suffix
        v = int(cvars[var_key])
        err = None
        if v < 0:
            err = f"Negatif değer: {v}"
            val, val_hex = None, "HATA"
        elif v >= (1 << bits):
            err = f"{v} değeri {bits} bit alana sığmıyor (en fazla {(1 << bits) - 1})."
            val, val_hex = None, "HATA"
        else:
            val, val_hex = v, f"0x{v:08X}"
            rx_values[suffix] = v
        off_str = rm.offset_hex(full_name) if loaded else "—"
        if loaded and not rm.has(full_name) and err is None:
            err = "IP haritasında yok"
        regs.append((disp_name, full_name, off_str, val, val_hex, err))
        if err and err != "IP haritasında yok":
            checks.append((f"{disp_name}: {err}", False))
    return Result(rows, dur, regs, checks, single, cvars, nom_clk, rx_values)


def _edge(tp, t, v, rising):
    """FPGA'da algılanan kenar gecikmesi (ns), giriş eşik anından itibaren.
    Datasheet tP: giriş %50 → çıkış %50. Çıkış kenarı giriş eşik anından önce başlayamaz → etkin tP ≥ ½·t/0.8.
    FPGA eşiği v·VCC: yükselen kenar (v−0.5)·t/0.8, düşen kenar (0.5−v)·t/0.8 kayar."""
    off = (v - 0.5) * t / 0.8 if rising else (0.5 - v) * t / 0.8
    return max(tp, 0.5 * t / 0.8) + off


def _median(a, b, c):
    return sorted((a, b, c))[1]


def edge_delays(ic, fv):
    """(MIN pulse, NOM, MAX pulse) için yükselen/düşen kenar gecikmeleri (µs). Excel ile birebir.
    Fonksiyon t'ye göre konveks → max uç noktalarda, min uç noktalarda veya kırılma noktasında (t = 1.6·tP)."""
    vmin, vnom, vmax = fv
    tr, tf = ic.trr, ic.tfr
    r_min = max(_edge(ic.tplh[2], t, vmax, True) for t in (tr[0], tr[2]))
    f_min = min(_edge(ic.tphl[0], t, vmax, False) for t in (tf[0], tf[2], _median(tf[0], tf[2], 1.6 * ic.tphl[0])))
    r_max = min(_edge(ic.tplh[0], t, vmin, True) for t in (tr[0], tr[2], _median(tr[0], tr[2], 1.6 * ic.tplh[0])))
    f_max = max(_edge(ic.tphl[2], t, vmin, False) for t in (tf[0], tf[2]))
    r_nom, f_nom = _edge(ic.tplh[1], tr[1], vnom, True), _edge(ic.tphl[1], tf[1], vnom, False)
    return (r_min / 1000, r_nom / 1000, r_max / 1000), (f_min / 1000, f_nom / 1000, f_max / 1000)




def _single_bit(ci, p, rise, fall, thalf, tbit, arinc, cr, cf, fv, drise, dfall):
    """Tek bit analizi: analog yamuk giriş → eşikler → RX çıkışı (µs)."""
    ic, k = ci.ic, p.k
    out = {}
    x1 = ic.v_one[2] / p.amp_min - cr; x2 = ic.v_one[0] / p.amp_max - cr
    y1 = cf - ic.v_null[2] / p.amp_min; y2 = cf - ic.v_null[0] / p.amp_max
    cases = {
        "MIN": dict(A=p.amp_min, V1=ic.v_one[2], VN=ic.v_null[2], tr=rise[2] if x1 >= 0 else rise[0],
                    tf=fall[0] if y1 >= 0 else fall[2], th=thalf[0],
                    v=fv[2], don=drise[0], doff=dfall[0], tend=tbit[0]),
        "NOM": dict(A=NOM_AMP, V1=ic.v_one[1], VN=ic.v_null[1], tr=rise[1], tf=fall[1], th=thalf[1],
                    v=fv[1], don=drise[1], doff=dfall[1], tend=tbit[1]),
        "MAX": dict(A=p.amp_max, V1=ic.v_one[0], VN=ic.v_null[0], tr=rise[2] if x2 <= 0 else rise[0],
                    tf=fall[2] if y2 >= 0 else fall[0], th=thalf[2],
                    v=fv[0], don=drise[2], doff=dfall[2], tend=tbit[2]),
    }
    for name, d in cases.items():
        d["Tr"], d["Tf"] = d["tr"] / k, d["tf"] / k
        d["fs"] = d["th"] if arinc else d["Tr"] / 2 + d["th"] - d["Tf"] / 2
        d["hs"] = 0.0 if arinc else d["Tr"] / 2
        d["ton"] = d["Tr"] * d["V1"] / d["A"]
        d["toff"] = d["fs"] + d["Tf"] * (1 - d["VN"] / d["A"])
        d["oon"], d["ooff"] = d["ton"] + d["don"], d["toff"] + d["doff"]
        d["ow"] = d["ooff"] - d["oon"]
        out[name] = d
    return out
