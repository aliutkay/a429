"""Komut yapısı ve Register haritası (IP'ye yeni özellik eklenince yalnızca buradaki tablo değişir).

Komutlar şablonla tanımlanır:  C3 00 {IP} {REG} {DATA32}
  {IP} / {IP16}                                  hedef IP portu (Bağlantı sekmesinden)
  {REG} / {REG8} / {REG16} / {REG32}             Register adresi
  {DATA} (=32 bit) / {DATA8} / {DATA16} / {DATA32} / {DATA64}   veri
  diğer parçalar sabit hex Byte'lardır.

Yazma Register'larının değeri, hesaplanan değişkenlerden (Config sonuçları) formülle üretilir.
"""
from __future__ import annotations

import ast
import copy
import math
import operator
import re
from dataclasses import dataclass, field, asdict

_TOKEN = re.compile(r"\{(IP|REG|DATA)(8|16|32|64)?\}")


class FrameError(ValueError):
    pass


class FormulaError(ValueError):
    pass


# ------------------------------------------------------------------ komut şablonları
def parse_frame(text):
    """Şablonu [("byte", 1, değer) | ("REG", n, None) | ("DATA", n, None)] listesine çevirir."""
    tokens = []
    for part in text.split():
        m = _TOKEN.fullmatch(part.upper())
        if m:
            bits = int(m.group(2) or (32 if m.group(1) == "DATA" else 8))
            tokens.append((m.group(1), bits // 8, None))
        elif re.fullmatch(r"[0-9A-Fa-f]{2}", part):
            tokens.append(("byte", 1, int(part, 16)))
        else:
            raise FrameError(f"Geçersiz parça: '{part}'. İki haneli hex Byte, {{IP}}, {{REG}} veya {{DATA}} kullanın.")
    if not tokens:
        raise FrameError("Komut şablonu boş.")
    return tokens


def _count(tokens, kind):
    return sum(1 for t in tokens if t[0] == kind)


def _expect(text, title, regs, datas):
    tokens = parse_frame(text)
    if _count(tokens, "REG") != regs or _count(tokens, "DATA") != datas:
        raise FrameError(f"{title}: {regs} adet {{REG}} ve {datas} adet {{DATA}} olmalı.")
    return tokens


def _int_bytes(value, n, endian, what):
    try:
        return int(value).to_bytes(n, endian)
    except OverflowError:
        raise FrameError(f"{what} değeri ({value}) {n * 8} bit alana sığmıyor.") from None


def build_frame(text, reg=None, data=None, endian="big", ip=None):
    out = bytearray()
    for kind, n, val in parse_frame(text):
        if kind == "byte":
            out.append(val)
        elif kind == "REG":
            out += _int_bytes(reg, n, endian, "Register adresi")
        elif kind == "IP":
            out += _int_bytes(ip, n, endian, "IP portu")
        else:
            out += _int_bytes(data, n, endian, "Data")
    return bytes(out)


def parse_values(text, frame, endian="big"):
    """Tam uzunluktaki çerçeveyi şablona göre çözer: {"REG": .., "DATA": ..}, uymuyorsa None."""
    tokens = parse_frame(text)
    if len(frame) != sum(t[1] for t in tokens):
        return None
    out, i = {}, 0
    for kind, n, val in tokens:
        chunk = frame[i:i + n]; i += n
        if kind == "byte":
            if chunk[0] != val:
                return None
        else:
            out[kind] = int.from_bytes(chunk, endian)
    return out


def hexstr(b):
    return " ".join(f"{x:02X}" for x in b)


# ------------------------------------------------------------------ formüller
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.BitAnd: operator.and_, ast.BitOr: operator.or_,
        ast.BitXor: operator.xor, ast.LShift: operator.lshift, ast.RShift: operator.rshift}
_FUNC = {"floor": math.floor, "ceil": math.ceil, "round": round, "min": min, "max": max, "abs": abs}


def evaluate(formula, variables):
    """Güvenli formül hesabı: yalnızca sayılar, değişkenler, + - * / // % & | ^ << >> ve _FUNC işlevleri."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in variables:
                raise FormulaError(f"Bilinmeyen değişken: {n.id}")
            return variables[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.LShift) and not 0 <= b <= 64:
                raise FormulaError("Kaydırma miktarı 0–64 arasında olmalı.")
            return _BIN[type(n.op)](a, b)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNC and not n.keywords:
            return _FUNC[n.func.id](*[ev(a) for a in n.args])
        raise FormulaError("Formülde izin verilmeyen ifade var.")

    text = formula.strip()
    if not text:
        raise FormulaError("Formül boş.")
    try:
        value = ev(ast.parse(text, mode="eval"))
        return int(math.floor(value + 1e-9))
    except FormulaError:
        raise
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError, OverflowError) as e:
        raise FormulaError(f"Formül hesaplanamadı: {e}") from None


# ------------------------------------------------------------------ Register haritası
@dataclass
class WriteReg:
    name: str
    addr: str
    formula: str
    enabled: bool = True
    bits: int = 32              # IP'deki alan genişliği


@dataclass
class ReadReg:
    name: str
    addr: str
    fmt: str = "hex"            # hex | dec


# TX ve kontrol Register'ları (IP adres haritası 00–1F). Adresi boş Register'a yazma yapılmaz.
TX_REGISTERS = [
    ("ip_reset", "IP reset (cfg_reset)"),
    ("tx_transmitter_en", "Word Transmitter enable (0: hat ext_high/ext_low ile sürülür)"),
    ("tx_msg_sched_en", "Message Scheduler modu (1: Scheduler, 0: ext_data_valid tetiği)"),
    ("tx_builder_en", "Word Builder enable (1: alanlar, 0: ext_data)"),
    ("tx_label", "Label"), ("tx_sdi", "SDI"), ("tx_data", "Data"), ("tx_ssm", "SSM"),
    ("tx_parity_type", "Parity tipi (1: Odd, 0: Even)"),
    ("sched_enable", "Scheduler enable (başlat/durdur)"),
    ("sched_delay", "Initial delay (clk)"), ("sched_gap", "Inter word gap (clk)"),
    ("tx_pulse_dur", "Pulse süresi (clk)"), ("tx_null_dur", "Null süresi (clk)"), ("tx_gap_dur", "Word Gap süresi (clk)"),
    ("tx_slp", "SLP hız seçimi (1: 1.5 µs, 0: 10 µs)"),
    ("tx_ext_valid", "ext_data_valid (gönderim tetiği, kenar)"), ("tx_ext_data", "ext_data (32-bit Word)"),
    ("tx_ext_high", "ext_high"), ("tx_ext_low", "ext_low"),
    ("rx_read_mode", "RX read mode (okuma sırasında kayıtları dondurur)"),
]
DEFAULT_TX_ADDR = dict(zip([k for k, _ in TX_REGISTERS], [f"{i:02X}" for i in range(0x14)] + ["1C"]))
MAP_VERSION = 2


def default_tx_regs():
    return dict(DEFAULT_TX_ADDR)


DEFAULT_WRITE_REGS = [
    ("CFG Glitch Filter Size", "14", "glitch_filter_size", True, 16),
    ("CFG Min Pulse Duration", "15", "min_pulse", True, 16),
    ("CFG Max Pulse Duration", "16", "max_pulse", True, 16),
    ("CFG Min Bit Duration", "17", "min_bit", True, 16),
    ("CFG Max Bit Duration", "18", "max_bit", True, 16),
    ("CFG Max Gap Glitch Error", "19", "max_gap_glitch_error", True, 16),
    ("CFG Max Null Glitch Error", "1A", "max_null_glitch_error", True, 16),
    ("CFG Max Pulse Glitch Error", "1B", "max_pulse_glitch_error", True, 16),
]
OLD_RX_ADDR = {f"{0x11 + i:02X}": f"{0x14 + i:02X}" for i in range(8)}      # harita sürüm 1 → 2


def _migrate_v1(rm):
    """Sürüm 1 haritası: RX Config 11–18 → 14–1B, 16 bit; TX yer tutucuları yerine yeni TX haritası."""
    names = {r[0] for r in DEFAULT_WRITE_REGS}
    for r in rm.write_regs:
        r.addr = OLD_RX_ADDR.get(r.addr, r.addr)
        if r.name in names:
            r.bits = 16
    rm.tx_regs = default_tx_regs()
    return rm


def norm_addr(a):
    a = str(a).strip().upper()
    int(a, 16)
    return a.zfill(2)


@dataclass
class RegisterMap:
    write_cmd: str = "C3 00 {IP} {REG} {DATA32}"
    read_cmd: str = "CF 00 {IP} {REG}"
    ip_port: str = "01"
    read_rsp: str = "AB {DATA32} CD"
    endian: str = "big"
    write_regs: list = field(default_factory=lambda: [WriteReg(*r) for r in DEFAULT_WRITE_REGS])
    extra_read: list = field(default_factory=list)
    tx_regs: dict = field(default_factory=default_tx_regs)
    map_version: int = MAP_VERSION

    @staticmethod
    def from_dict(d):
        rm = RegisterMap(**{k: v for k, v in d.items() if k in ("write_cmd", "read_cmd", "read_rsp", "endian", "ip_port")})
        if "ip_port" not in d:              # IP portu sabit Byte olarak yazılmış eski şablonlar
            w = re.fullmatch(r"(\S\S \S\S) (\S\S) (\{REG.*)", rm.write_cmd.strip())
            r = re.fullmatch(r"(\S\S \S\S) (\S\S) (\{REG.*)", rm.read_cmd.strip())
            if w and r and w.group(2) == r.group(2):
                rm.ip_port = w.group(2).upper()
                rm.write_cmd = f"{w.group(1)} {{IP}} {w.group(3)}"
                rm.read_cmd = f"{r.group(1)} {{IP}} {r.group(3)}"
        rm.write_regs = [WriteReg(**r) for r in d.get("write_regs", [])]
        rm.extra_read = [ReadReg(**r) for r in d.get("extra_read", [])]
        rm.tx_regs = {**default_tx_regs(), **{k: v for k, v in d.get("tx_regs", {}).items() if k in DEFAULT_TX_ADDR}}
        return _migrate_v1(rm) if d.get("map_version", 1) < MAP_VERSION else rm

    @staticmethod
    def from_legacy(config, link=None):
        """Eski dosyalardaki sabit Byte alanlarından harita üretir."""
        link = link or {}
        h = lambda s: str(s).strip().upper().zfill(2)
        b0, b1, port = h(config.get("cmd_b0", "C3")), h(config.get("cmd_b1", "00")), h(config.get("cmd_port", "01"))
        rm = RegisterMap(ip_port=port, write_cmd=f"{b0} {b1} {{IP}} {{REG}} {{DATA32}}",
                         read_cmd=f"{h(link.get('rd_hdr', 'CF'))} {b1} {{IP}} {{REG}}",
                         read_rsp=f"{h(link.get('rsp_start', 'AB'))} {{DATA32}} {h(link.get('rsp_end', 'CD'))}")
        for r, a in zip(rm.write_regs, config.get("reg_addr", [])):
            r.addr = h(a)
        return _migrate_v1(rm)

    def copy(self):
        return copy.deepcopy(self)

    def to_dict(self):
        return asdict(self)

    # --- çerçeveler
    def ip(self):
        return int(self.ip_port, 16)

    def build_write(self, addr, value):
        return build_frame(self.write_cmd, int(addr, 16), value, self.endian, self.ip())

    def build_read(self, addr):
        return build_frame(self.read_cmd, int(addr, 16), None, self.endian, self.ip())

    def build_response(self, value):
        return build_frame(self.read_rsp, 0, value, self.endian, self.ip())

    def find_response(self, buf, addr):
        """Tampon içinde cevap çerçevesini arar; bulursa DATA değerini döndürür."""
        n = sum(t[1] for t in parse_frame(self.read_rsp))
        for u in range(0, len(buf) - n + 1):
            got = parse_values(self.read_rsp, bytes(buf[u:u + n]), self.endian)
            if got is not None and got.get("REG", int(addr, 16)) == int(addr, 16):
                return got["DATA"]
        return None

    def data_bytes(self):
        return next(t[1] for t in parse_frame(self.write_cmd) if t[0] == "DATA")

    def addr_bytes(self):
        return next(t[1] for t in parse_frame(self.write_cmd) if t[0] == "REG")

    def resolve(self, reg, variables):
        """(değer, değer_hex, komut_hex, hata) – hata varsa değer None."""
        try:
            v = evaluate(reg.formula, variables)
            if v < 0:
                raise FrameError(f"Negatif değer: {v}")
            if v >= 1 << getattr(reg, "bits", 32):
                raise FrameError(f"{v} değeri {reg.bits} bit alana sığmıyor (en fazla {(1 << reg.bits) - 1}).")
            value_hex = hexstr(_int_bytes(v, self.data_bytes(), self.endian, "Data"))
            return v, value_hex, hexstr(self.build_write(reg.addr, v)), None
        except (FormulaError, FrameError, ValueError) as e:
            return None, "HATA", "", str(e)

    def validate(self):
        _expect(self.write_cmd, "Yazma komutu", 1, 1)
        _expect(self.read_cmd, "Okuma komutu", 1, 0)
        tokens = _expect(self.read_rsp, "Okuma cevabı", _count(parse_frame(self.read_rsp), "REG"), 1)
        if _count(tokens, "REG") > 1:
            raise FrameError("Okuma cevabı: en fazla 1 adet {REG} olabilir.")
        for text in (self.write_cmd, self.read_cmd, self.read_rsp):
            n = [t[1] for t in parse_frame(text) if t[0] == "IP"]
            if len(n) > 1:
                raise FrameError("Bir şablonda en fazla 1 adet {IP} olabilir.")
            if n:
                _int_bytes(self.ip(), n[0], self.endian, "IP portu")
        if self.endian not in ("big", "little"):
            raise FrameError("Byte sırası geçersiz.")
