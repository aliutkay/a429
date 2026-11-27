"""AXIL Studio PCS (cmd_seq v2.0) otonom periyodik ARINC 429 IP 2.1.0 loopback testi.

Bu modül harici araç gerektirmeden:
  1. ``client.address_map()`` ile projedeki ``cmd_seq`` (PCS) bloğunu keşfeder,
  2. IP 2.1.0 (``TX_SCHED_COUNT`` + gruplanmış register'lar) için en kapsamlı
     donanım / hat / entegre hata yakalama test takımını dinamik olarak PCS
     assembly'sine derler (``cmd_seq`` v2.0 64-bit ISA — 15 testin tamamı
     varsayılan 512 komutluk ``IMEM_AW=9`` I-mem'e sığar),
  3. Programı ``IMEM_PTR`` / ``IMEM_DATA`` üzerinden yükleyip ``IMEM_CNT`` ve
     ``IMEM_SUM`` ile doğrular, D-mem tablosunu ve ayarları yazar, PCS'yi başlatır,
  4. PC'den ARINC 429 IP'ye hiçbir test komutu göndermeden yalnızca PCS D-mem'den
     toplam tur, başarılı/başarısız tur, test bazlı ve kanal bazlı kalma
     sayaçları ile ilk yakalanan hatanın ayrıntılarını okur.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from . import ipmap
from .regs import channel_label
from .txlive import build_word

# =====================================================================================
# cmd_seq v2.0 donanım sabitleri (aliutkay/axil-studio hdl/cmd_seq/README.md)
# =====================================================================================
PCS_ID_MASK = 0xFFFF0000
PCS_ID_SIG = 0x5EC00000

# PCS kendi pencere offset'leri (PCS_BASE + off)
REG_ID = 0x0000
REG_CAPS = 0x0004
REG_CTRL = 0x0008
REG_STATUS = 0x000C
REG_ENTRY = 0x0010
REG_ERR_CODE = 0x0014
REG_ERR_PC = 0x0018
REG_ERR_ADDR = 0x001C
REG_IMEM_PTR = 0x0020
REG_IMEM_DATA = 0x0024
REG_IMEM_CNT = 0x0028
REG_IMEM_SUM = 0x002C
REG_DMEM_PTR = 0x0030
REG_DMEM_DATA = 0x0034
REG_SNAP_CNT = 0x0038
REG_TIMER = 0x003C
REG_IRQ_STAT = 0x0040
REG_DMEM_BASE = 0x0400

CTRL_RUN = 0x01
CTRL_STOP = 0x02
CTRL_RESET = 0x04
CTRL_STEP = 0x08
CTRL_SNAP_EN = 0x10
CTRL_PT_WR_RUN = 0x20
CTRL_ERR_HALT = 0x40
CTRL_IRQ_EN = 0x80

LOAD_CHUNK = 64  # Her batch isteğinde yüklenen 64-bit komut sayısı

PCS_ERR_TEXT = {
    1: "geçersiz komut (illegal instruction)",
    2: "AXI bus hata cevabı (SLVERR/DECERR)",
    3: "kendi penceresine erişim (own window)",
    4: "çağrı yığını taşması/boşalması (call stack)",
    5: "AXI bus zaman aşımı (bus timeout)",
    6: "PC I-mem dışına çıktı",
    7: "D-mem indeksi sınır dışı",
}

# =====================================================================================
# cmd_seq v2.0 64-bit assembler (seqasm.py ile bit-birebir uyumlu)
# =====================================================================================
OPS = {
    "NOP": 0x00, "END": 0x01, "KILL": 0x02,
    "WR": 0x08, "RD": 0x09,
    "LDI": 0x10, "LDD": 0x11, "STD": 0x12, "MOV": 0x13,
    "ADD": 0x18, "SUB": 0x19, "AND": 0x1A, "OR": 0x1B,
    "XOR": 0x1C, "SHL": 0x1D, "SHR": 0x1E, "CMP": 0x1F,
    "JMP": 0x20, "BR": 0x21, "LOOP": 0x22, "CALL": 0x23, "RET": 0x24,
    "WAIT": 0x28, "WAITT": 0x29, "TMR": 0x2A,
    "SNAP": 0x30, "FENCE": 0x31, "SEV": 0x32, "WFE": 0x33, "IRQ": 0x34,
}
OPNAME = {v: k for k, v in OPS.items()}
CONDS = {"AL": 0, "Z": 1, "NZ": 2, "LT": 3, "GE": 4, "ERR": 5, "LO": 6, "HS": 7, "MI": 8, "PL": 9}
COND_ALIASES = {"EQ": "Z", "NE": "NZ"}
ALU_OPS = {"ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "CMP"}
NO_OPERAND = ("NOP", "END", "RET", "SNAP", "FENCE", "IRQ")
KILL_MIN = 0x10


class PcsError(Exception):
    """PCS keşif, derleme, yükleme veya okuma hatası."""


def encode_insn(op: int, ra: int = 0, rb: int = 0, mod: int = 0, d: int = 0, dly: int = 0, imm: int = 0) -> int:
    return (
        ((op & 0x3F) << 58)
        | ((ra & 0xF) << 54)
        | ((rb & 0xF) << 50)
        | ((mod & 0x3) << 48)
        | ((d & 0xFF) << 40)
        | ((dly & 0xFF) << 32)
        | (imm & 0xFFFFFFFF)
    )


def decode_fields(w: int) -> dict[str, int]:
    return {
        "op": (w >> 58) & 0x3F,
        "ra": (w >> 54) & 0xF,
        "rb": (w >> 50) & 0xF,
        "mod": (w >> 48) & 3,
        "d": (w >> 40) & 0xFF,
        "dly": (w >> 32) & 0xFF,
        "imm": w & 0xFFFFFFFF,
    }


def words32(prog: list[tuple[int, int, str]]) -> list[int]:
    out: list[int] = []
    for _, w, _ in prog:
        out.append(w & 0xFFFFFFFF)
        out.append((w >> 32) & 0xFFFFFFFF)
    return out


def imem_sum(prog: list[tuple[int, int, str]]) -> int:
    return sum(words32(prog)) & 0xFFFFFFFF


class Assembler:
    """cmd_seq v2.0 assembly derleyicisi."""

    def __init__(self, imem_aw: int = 9, dmem_aw: int = 8, symbols: dict[str, int] | None = None):
        self.imem_size = 1 << imem_aw
        self.dmem_size = 1 << dmem_aw
        self.syms: dict[str, int] = dict(symbols or {})
        self.entry: tuple[str, str] | None = None
        self.pc_line: dict[int, int] = {}

    def _value(self, tok: str, loc: str) -> int:
        tok = tok.strip()
        if not tok:
            raise PcsError(f"{loc}: boş ifade")
        parts = re.split(r"(?<=[^+\-])([+\-])", tok)
        total, sign = 0, 1
        for p in parts:
            p = p.strip()
            if p == "+":
                sign = 1
                continue
            if p == "-":
                sign = -1
                continue
            total += sign * self._atom(p, loc)
        return total

    def _atom(self, t: str, loc: str) -> int:
        if re.fullmatch(r"-?(0x[0-9a-fA-F_]+|0b[01_]+|\d[\d_]*)", t):
            t = t.replace("_", "")
        try:
            return int(t, 0)
        except ValueError:
            pass
        if t in self.syms:
            return self.syms[t]
        raise PcsError(f"{loc}: tanımsız sembol '{t}'")

    @staticmethod
    def _is_reg(t: str) -> bool:
        return re.fullmatch(r"[Rr](\d+)", t.strip()) is not None

    @staticmethod
    def _reg(t: str, loc: str) -> int:
        m = re.fullmatch(r"[Rr](\d+)", t.strip())
        if not m or int(m.group(1)) > 15:
            raise PcsError(f"{loc}: R0..R15 bekleniyor, gelen '{t}'")
        return int(m.group(1))

    def _dref(self, t: str, loc: str) -> tuple[int, int | None]:
        m = re.fullmatch(r"[Dd]\[(.+)\]", t.strip())
        if not m:
            raise PcsError(f"{loc}: D[n] bekleniyor, gelen '{t}'")
        inner = m.group(1).strip()
        reg = None
        m2 = re.fullmatch(r"([Rr]\d+)\s*(?:\+\s*(.+))?", inner) or re.fullmatch(r"(.+?)\s*\+\s*([Rr]\d+)", inner)
        if m2 and self._is_reg(m2.group(1)):
            reg, rest = self._reg(m2.group(1), loc), m2.group(2)
        elif m2 and m2.lastindex == 2 and self._is_reg(m2.group(2)):
            reg, rest = self._reg(m2.group(2), loc), m2.group(1)
        else:
            rest = inner
        n = self._value(rest, loc) if rest else 0
        if reg is None and not 0 <= n < min(self.dmem_size, 256):
            raise PcsError(f"{loc}: D indeksi sınır dışı ({n})")
        if not 0 <= n < 256:
            raise PcsError(f"{loc}: D ofseti 0..255 olmalı ({n})")
        return n, reg

    def _mem(self, t: str, loc: str) -> tuple[int, int]:
        m = re.fullmatch(r"\[(.+)\]", t.strip())
        if not m:
            raise PcsError(f"{loc}: [adres] bekleniyor, gelen '{t}'")
        inner = m.group(1).strip()
        m2 = re.match(r"([Rr]\d+)\s*(?:([+\-])\s*(.+))?$", inner)
        if m2:
            rb = self._reg(m2.group(1), loc)
            imm = 0
            if m2.group(2):
                imm = self._value(m2.group(3), loc)
                if m2.group(2) == "-":
                    imm = -imm
            return rb, imm
        return 0, self._value(inner, loc)

    def _operand_b(self, t: str, loc: str) -> tuple[int, int, int]:
        if self._is_reg(t):
            return self._reg(t, loc), 0, 0
        return 0, 1, self._value(t, loc)

    def _target(self, t: str, loc: str) -> int:
        v = self._value(t, loc)
        if not 0 <= v < self.imem_size:
            raise PcsError(f"{loc}: atlama hedefi I-mem dışında ({v})")
        return v

    @staticmethod
    def _split_ops(s: str) -> list[str]:
        out, depth, cur = [], 0, ""
        for ch in s:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    def parse(self, src: str) -> tuple[list[tuple[int, int, str]], int]:
        stmts: list[tuple[int, str, str, str]] = []
        pc = 0
        for no, raw in enumerate(src.splitlines(), 1):
            line = re.split(r"[;#]", raw, maxsplit=1)[0].strip()
            loc = f"satır {no}"
            while True:
                m = re.match(r"([A-Za-z_]\w*)\s*:\s*(.*)$", line)
                if not m:
                    break
                if m.group(1) in self.syms:
                    raise PcsError(f"{loc}: '{m.group(1)}' iki kez tanımlandı")
                self.syms[m.group(1)] = pc
                line = m.group(2)
            if not line:
                continue
            low = line.lower()
            if low.startswith(".equ"):
                parts = line.split(None, 2)
                if len(parts) < 3:
                    raise PcsError(f"{loc}: .equ AD değer")
                name = parts[1].rstrip(",")
                if name in self.syms:
                    raise PcsError(f"{loc}: '{name}' iki kez tanımlandı")
                self.syms[name] = self._value(parts[2].lstrip(", "), loc)
                continue
            if low.startswith(".entry"):
                self.entry = (line.split(None, 1)[1].strip(), loc)
                continue
            stmts.append((pc, line, loc, raw.strip()))
            self.pc_line[pc] = no
            pc += 1
        if pc > self.imem_size:
            raise PcsError(f"Program {pc} komut; PCS I-mem kapasitesi {self.imem_size} komut")
        prog = [(p, self._encode_line(line, loc), raw) for p, line, loc, raw in stmts]
        entry = self._target(self.entry[0], self.entry[1]) if self.entry else 0
        return prog, entry

    def _encode_line(self, line: str, loc: str) -> int:
        dly = 0
        m = re.search(r"@\s*(\S+)\s*$", line)
        if m:
            dly = self._value(m.group(1), loc)
            if not 0 <= dly <= 255:
                raise PcsError(f"{loc}: DLY 0..255 olmalı ({dly})")
            line = line[:m.start()].strip()
        parts = line.split(None, 1)
        mn = parts[0].upper()
        ops = self._split_ops(parts[1]) if len(parts) > 1 else []
        if mn not in OPS:
            raise PcsError(f"{loc}: bilinmeyen komut '{parts[0]}'")
        op = OPS[mn]

        def need(n: int):
            if len(ops) != n:
                raise PcsError(f"{loc}: {mn} {n} operand alır, {len(ops)} verildi")

        if mn in NO_OPERAND:
            need(0)
            return encode_insn(op, dly=dly)
        if mn == "KILL":
            need(1)
            code = self._value(ops[0], loc)
            if not KILL_MIN <= code <= 0xFF:
                raise PcsError(f"{loc}: KILL kodu 0x10..0xFF olmalı")
            return encode_insn(op, d=code, dly=dly)
        if mn == "WR":
            need(2)
            rb, imm = self._mem(ops[0], loc)
            return encode_insn(op, ra=self._reg(ops[1], loc), rb=rb, dly=dly, imm=imm)
        if mn == "RD":
            need(2)
            rb, imm = self._mem(ops[1], loc)
            if ops[0].strip().upper().startswith("D["):
                n, x = self._dref(ops[0], loc)
                return encode_insn(op, ra=x or 0, rb=rb, mod=2 | int(x is not None), d=n, dly=dly, imm=imm)
            return encode_insn(op, ra=self._reg(ops[0], loc), rb=rb, dly=dly, imm=imm)
        if mn == "LDI":
            need(2)
            return encode_insn(op, ra=self._reg(ops[0], loc), mod=1, dly=dly, imm=self._value(ops[1], loc))
        if mn == "LDD":
            need(2)
            n, x = self._dref(ops[1], loc)
            return encode_insn(op, ra=self._reg(ops[0], loc), rb=x or 0, mod=int(x is not None), d=n, dly=dly)
        if mn == "STD":
            need(2)
            n, x = self._dref(ops[0], loc)
            return encode_insn(op, ra=self._reg(ops[1], loc), rb=x or 0, mod=int(x is not None), d=n, dly=dly)
        if mn == "MOV" or mn in ALU_OPS:
            need(2)
            rb, mb, imm = self._operand_b(ops[1], loc)
            return encode_insn(op, ra=self._reg(ops[0], loc), rb=rb, mod=mb, dly=dly, imm=imm)
        if mn in ("JMP", "CALL"):
            need(1)
            return encode_insn(op, dly=dly, imm=self._target(ops[0], loc))
        if mn == "BR":
            need(2)
            c = COND_ALIASES.get(ops[0].strip().upper(), ops[0].strip().upper())
            if c not in CONDS:
                raise PcsError(f"{loc}: bilinmeyen koşul '{ops[0]}'")
            return encode_insn(op, d=CONDS[c], dly=dly, imm=self._target(ops[1], loc))
        if mn == "LOOP":
            need(2)
            ra = self._reg(ops[0], loc)
            if ra == 0:
                raise PcsError(f"{loc}: LOOP için R0 dışı sayaç gerekir")
            return encode_insn(op, ra=ra, dly=dly, imm=self._target(ops[1], loc))
        if mn in ("WAIT", "WAITT"):
            need(1)
            rb, mb, imm = self._operand_b(ops[0], loc)
            return encode_insn(op, rb=rb, mod=mb, dly=dly, imm=imm)
        if mn == "TMR":
            need(1)
            return encode_insn(op, ra=self._reg(ops[0], loc), dly=dly)
        if mn in ("SEV", "WFE"):
            need(1)
            n = self._value(ops[0], loc)
            if not 0 <= n <= 7:
                raise PcsError(f"{loc}: olay numarası 0..7 olmalı")
            return encode_insn(op, d=n, dly=dly)
        raise PcsError(f"{loc}: kodlanamayan komut '{mn}'")


def assemble(src: str, imem_aw: int = 9, dmem_aw: int = 8, symbols: dict[str, int] | None = None):
    return Assembler(imem_aw, dmem_aw, symbols).parse(src)


# =====================================================================================
# PCS durum ve yetenek çözümü
# =====================================================================================
def decode_caps(v: int) -> tuple[int, int, int, int]:
    """CAPS -> (imem_aw, dmem_aw, nregs, self_id)."""
    return v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF


def pcs_err_text(code: int) -> str:
    if code >= KILL_MIN:
        return f"KILL 0x{code:02X}"
    return PCS_ERR_TEXT.get(code, f"kod {code}")


class PcsStatus:
    def __init__(self, v: int):
        self.value = int(v) & 0xFFFFFFFF
        self.busy = bool(v & 1)
        self.done = bool((v >> 1) & 1)
        self.err = bool((v >> 2) & 1)
        self.paused = bool((v >> 3) & 1)
        self.imem_phase = bool((v >> 4) & 1)
        self.wr_drain = bool((v >> 5) & 1)
        self.rd_drain = bool((v >> 6) & 1)
        self.pc = (v >> 16) & 0xFFFF

    @property
    def state(self) -> str:
        if self.err:
            return "ERROR"
        if self.done:
            return "DONE"
        if self.paused:
            return "PAUSED"
        if self.busy:
            return "RUNNING"
        return "IDLE"


@dataclass
class PcsInfo:
    name: str
    base: int
    parent: str = ""
    is_ip_parent: bool = False
    pcs_id: int = 0
    imem_aw: int = 9
    dmem_aw: int = 8
    self_id: int = 0
    status: int = 0
    running_a429: bool = False

    @property
    def imem_size(self) -> int:
        return 1 << self.imem_aw

    @property
    def dmem_size(self) -> int:
        return 1 << self.dmem_aw

    def display_label(self) -> str:
        tag = " · bağlı IP üstü" if self.is_ip_parent else ""
        run = " · A429 TESTİ KOŞUYOR" if self.running_a429 else ""
        return f"{self.name} @ 0x{self.base:08X} ({self.imem_size} komut / {self.dmem_size} D-mem{tag}{run})"


# =====================================================================================
# A429 IP 2.1.0 PCS Test Kataloğu & D-mem Haritası
# =====================================================================================
SIGNATURE = 0xA4292101  # A429 IP 2.1 PCS loopback v1

# Test kimlikleri (idx = D[D_TEST_FAIL + idx] kalma sayacı indeksi)
TESTS: list[tuple[int, str, str, str]] = [
    (0,  "ident",      "IP kimliği (IP_ID = 'A429')",                     "IP erişim / bus hatası"),
    (1,  "idle",       "Hat boşta seviyesi (NULL 00, SYNC_WAIT=0)",        "Alıcı ters / pull-up / hat kilitli / besleme yok"),
    (2,  "polarity",   "Hat polaritesi (Override HIGH / LOW / NULL)",      "Kablo kopuk / A-B ters / sürücü-alıcı ölü"),
    (3,  "single_hs",  "HS Tek Word (Word Builder + Odd Parity + TB)",     "HS 100 kbps yol / bit sırası / TB Checker hatası"),
    (4,  "single_ls",  "LS Tek Word (Word Builder + SLP + TB)",            "LS 12.5 kbps yol / sürücü SLP pini hatası"),
    (5,  "pattern_hs", "HS Veri bütünlüğü (uç desenler + xorshift32)",     "HS tek-bit bozulma / stuck-bit / crosstalk"),
    (6,  "pattern_ls", "LS Veri bütünlüğü (uç desenler + xorshift32)",     "LS tek-bit bozulma / stuck-bit"),
    (7,  "burst_hs",   "HS Minimum 4-bit gap burst (TX_SCHED_COUNT)",      "HS min-gap toparlanma / FIFO / TB Checker taşması"),
    (8,  "burst_ls",   "LS Minimum 4-bit gap burst (TX_SCHED_COUNT)",      "LS min-gap toparlanma / paket kaybı"),
    (9,  "switch",     "HS ↔ LS hız geçişi (sürücü SLP + alıcı)",          "Hız geçişinde kilitlenme / ilk Word kaybı"),
    (10, "parity",     "Parity hatası tespiti (Even → ERR + toparlanma)",  "Parity detektörü veya hata sonrası toparlanma hatası"),
    (11, "mismatch",   "Hız uyuşmazlığı tespiti (HS/LS ↔ LS/HS)",          "Pulse Glitch / Pulse Stuck tespiti hatası"),
    (12, "gapviol",    "Gap ihlali tespiti (2-bit gap → Gap Violation)",   "Gap detektörü veya Custom TX sonrası toparlanma hatası"),
    (13, "bittime",    "Bit zamanlaması & hat gürültüsü (Bit Diagnostic)", "Sürücü/alıcı pulse-bit süre kayması veya aşırı glitch"),
    (14, "logger",     "Logger kontrolü (ENABLE / FREEZE / GLOBAL_FREEZE)","Logger enable/freeze veya DROP_CNT mekanizması hatası"),
]
TEST_BY_ID = {tid: (idx, title, hint) for idx, tid, title, hint in TESTS}
TEST_BY_IDX = {idx: (tid, title, hint) for idx, tid, title, hint in TESTS}
ALL_TEST_IDS = [tid for _, tid, _, _ in TESTS]

# İlk hata alt-neden kodları (D[M_FIRST_FAIL_INFO][31:16])
SUB_REASON = {
    1: "IP_ID uyuşmadı",
    2: "Hat boşta NULL/senkron değil (STATUS & 0x7000)",
    3: "Polarite HIGH uyuşmadı (STATUS & 0x3000)",
    4: "Polarite LOW uyuşmadı (STATUS & 0x3000)",
    5: "Polarite NULL uyuşmadı (STATUS & 0x3000)",
    6: "TX zaman aşımı (TX_STATUS.BUSY / SCHED_DONE)",
    7: "TX_WORD_CNT beklenen kadar artmadı",
    8: "RX/TB WORD_CNT beklenen kadar artmadı",
    9: "RX/TB ERR_CNT beklenmedik hata kaydetti",
    10: "RX/TB LAST_WORD beklenen veriyle uyuşmadı",
    11: "TX BIT Checker OK/ERR/OVF hatası",
    12: "Hatalı Word yanlışlıkla kabul edildi (WORD_CNT > 0)",
    13: "Beklenen hata kodu raporlanmadı (ERR_RD_INFO)",
    14: "Bit Diagnostic pulse süresi pencere dışında",
    15: "Bit Diagnostic bit süresi pencere dışında",
    16: "Logger DROP_CNT beklenen kadar artmadı",
}

# =====================================================================================
# D-mem bellek haritası (256 × 32-bit, DMEM_AW >= 8)
# D[0..15]  : Sabit yapılandırma ve canlı kontrol (clear_stats bunlara dokunmaz)
# D[16..64] : Bitişik istatistik bloğu (49 kelime: tek döngüde sıfırlanır)
# =====================================================================================
M_STATE = 0
M_CFG_MASK = 1
M_TEST_MASK = 2
M_GAP_CLK = 3
M_MAX_ROUNDS = 4
M_AGAIN = 5
M_CLEAR_REQ = 6
M_PRNG = 7
M_N_CHANS = 8
M_TB_IDX = 9
M_BURST_HS = 10
M_BURST_LS = 11
M_CLK_HZ = 12
M_IP_BASE = 13
M_ROUND_T0 = 14

# ---- D[16..80]: Clearable stats block (65 words: 16..80 inclusive)
STATS_START = 16
STATS_COUNT = 65
M_SEQ_BEGIN = 16
M_TOTAL_ROUNDS = 17
M_FAIL_ROUNDS = 18
M_LAST_FAIL_MASK = 19
M_CUM_FAIL_MASK = 20
M_LAST_DUR_CLK = 21
M_FIRST_FAIL_ROUND = 22
M_FIRST_FAIL_INFO = 23
M_FIRST_FAIL_EXP = 24
M_FIRST_FAIL_GOT = 25
M_MAX_NOISE = 26
M_LAST_FAIL_ROUND = 27
M_LAST_FAIL_INFO = 28
M_LAST_FAIL_EXP = 29
M_LAST_FAIL_GOT = 30
D_TEST_FAIL = 32   # 32..46 (15 test kalma sayacı; D[47]=global/TX kalma sayacı)
D_CHAN_FAIL = 48   # 48..64 (17 kanal kalma sayacı)
D_TEST_CH = 65     # 65..80 (16 test için son kalma hat bitmask'i: bit0=TX/Genel, bit(i+1)=ch[i])

# ---- D[81..181]: Kanal adres/kod tabloları, snapshot ve geçici hücreler
D_CH_ADDR = 81     # 81..97 (17 kanal mutlak taban adresi)
D_CH_CODE = 99     # 98=global(255), 99..115 (17 kanal mantıksal kodu: 0..15=RXn, 16=TB)
D_SNAP_W = 116     # 116..132
D_SNAP_E = 133     # 133..149
D_SNAP_D = 150     # 150..166
M_SNAP_TX = 167
M_SNAP_CHKO = 168
M_SNAP_CHKE = 169
M_TMP0 = 170
M_TMP1 = 171
D_PATTERNS = 176   # 176..181 (6 sabit odd-parity uç desen)
M_SIGNATURE = 255  # +0x7FC: SIGNATURE

# ARINC 429 IP 2.1.0 sabit register ofsetleri (a429/ipmap.py)
OFF_IP_ID = 0x0000
OFF_SOFT_RESET = 0x0020
OFF_GLOBAL_FREEZE = 0x0024
OFF_TS_CTRL = 0x0028

OFF_TX_CTRL = 0x0400
OFF_TX_WORD = 0x0404
OFF_TX_SEND = 0x0408
OFF_TX_EXT_DATA = 0x040C
OFF_TX_EXT_LINE = 0x0410
OFF_TX_INIT_DLY = 0x0420
OFF_TX_IWG = 0x0424
OFF_TX_SCHED_CNT = 0x0428
OFF_TX_CFG = 0x0440
OFF_TX_CUST_TIM = 0x0444
OFF_TX_CUST_GAP = 0x0448
OFF_TX_CUST_SLP = 0x044C
OFF_TX_ACT_TIM = 0x0460
OFF_TX_ACT_GAP = 0x0464
OFF_TX_STATUS = 0x0480
OFF_TX_WORD_CNT = 0x0484

CH_CTRL = 0x00
CH_STATUS = 0x04
CH_CFG = 0x08
CH_ACT_PULSE = 0x60
CH_ACT_BIT = 0x64
CH_WORD_CNT = 0xE0
CH_ERR_CNT = 0xE4
CH_DROP_CNT = 0xE8
CH_LAST_WORD = 0xEC
CH_ERR_RADDR = 0x120
CH_ERR_RD_INFO = 0x12C
CH_ERR_RD_DATA = 0x130
CH_BIT_RADDR = 0x140
CH_BIT_RD_PULSE = 0x144
CH_BIT_RD_NULL = 0x148

TB_BASE_OFF = 0x0800
TB_CHK_CTRL = 0x09C0
TB_CHK_TIMEOUT = 0x09C4
TB_CHK_OK_CNT = 0x09C8
TB_CHK_ERR_CNT = 0x09CC
TB_CHK_STATUS = 0x09D0

# ERR_RD_INFO.CODE bit maskeleri (a429/decode.py ERR_NAMES)
ERR_GAP_VIOL = 0x004     # bit 2
ERR_PULSE_STUCK = 0x020  # bit 5
ERR_PARITY = 0x080       # bit 7

SINGLE_TX_WORD = (0o310) | (2 << 8) | (0x5A5A5 << 10) | (1 << 29) | (1 << 31)
SINGLE_EXP_WORD = build_word(0o310, 2, 0x5A5A5, 1, odd=True)


def _odd(w31: int) -> int:
    w = w31 & 0x7FFFFFFF
    return w | ((bin(w).count("1") % 2 == 0) << 31)


PATTERN_FIXED = [_odd(w) for w in (0x00000000, 0x7FFFFFFF, 0x55555555, 0x2AAAAAAA, 0x0F0F0F0F, 0x70F0F0F0)]
PARITY_GOOD_WORD = _odd(0x0ABC123)
PARITY_BAD_WORD = PARITY_GOOD_WORD ^ 0x80000000


# =====================================================================================
# Dinamik PCS assembly üreteci (IP 2.1.0, tüm 15 test <= 512 komut)
# =====================================================================================
@dataclass
class CompiledProgram:
    asm: str
    prog: list[tuple[int, int, str]]
    entry: int
    imem_sum: int
    dmem_init: dict[int, int]
    selected_tests: list[str]
    rx_channels: list[str]
    use_tb: bool
    ip_base: int
    clk_hz: int

    @property
    def insn_count(self) -> int:
        return len(self.prog)


def build_program(
    ip_base: int,
    rx_channels: list[str],
    *,
    use_tb: bool = True,
    selected: list[str] | None = None,
    clk_hz: int = 50_000_000,
    gap_ms: int = 500,
    max_rounds: int = 0,
    burst_hs: int = 24,
    burst_ls: int = 6,
    bitdiag_words: int = 8,
    err_depth: int = 256,
    imem_aw: int = 9,
    dmem_aw: int = 8,
) -> CompiledProgram:
    """Seçili test ve kanallar için IP 2.1.0 PCS assembly'sini üretip 64-bit makine koduna derler."""
    sel_set = set(selected if selected is not None else ALL_TEST_IDS)
    sel_list = [tid for _, tid, _, _ in TESTS if tid in sel_set]
    if not sel_list:
        raise PcsError("En az bir PCS testi seçilmelidir.")

    chans = [c for c in rx_channels if c.startswith("RX")]
    if use_tb:
        chans.append("TB")
    if not chans:
        raise PcsError("En az bir RX kanalı veya TX BIT (TB) seçilmelidir.")

    clk_hz = max(1_000_000, int(clk_hz))
    clk_us = max(1, clk_hz // 1_000_000)
    gap_clk = max(100, int(round(max(0, gap_ms) * (clk_hz / 1000.0))))
    burst_hs = max(4, min(128, int(burst_hs)))
    burst_ls = max(4, min(64, int(burst_ls)))

    w_5us = 5 * clk_us
    w_30us = 30 * clk_us
    w_settle_hs = 90 * clk_us
    w_settle_ls = 520 * clk_us
    w_tx_to = 12_000 * clk_us
    w_sched_to = max(50_000 * clk_us, burst_ls * 4_500 * clk_us)
    tb_timeout_clk = 3 * (32 * 80 + 320) * clk_us

    cfg_mask = 0
    for c in rx_channels:
        if c.startswith("RX") and c[2:].isdigit():
            cfg_mask |= 1 << int(c[2:])
    if use_tb:
        cfg_mask |= 1 << 16
    if sel_set & {"single_hs", "pattern_hs", "burst_hs", "switch", "parity", "mismatch", "gapviol", "bittime", "logger"}:
        cfg_mask |= 1 << 17
    if sel_set & {"single_ls", "pattern_ls", "burst_ls", "switch", "mismatch"}:
        cfg_mask |= 1 << 18

    test_mask = 0
    for idx, tid, _, _ in TESTS:
        if tid in sel_set:
            test_mask |= 1 << idx

    tb_idx = chans.index("TB") if use_tb else 0xFF
    err_mask = max(1, err_depth) - 1
    bit_wmask = max(1, bitdiag_words) - 1

    # D-mem başlangıç tablosu
    dmem_init: dict[int, int] = {
        M_STATE: 0,
        M_CFG_MASK: cfg_mask,
        M_TEST_MASK: test_mask,
        M_GAP_CLK: gap_clk,
        M_MAX_ROUNDS: max(0, int(max_rounds)),
        M_AGAIN: 0,
        M_CLEAR_REQ: 0,
        M_PRNG: 0x2545F491,
        M_N_CHANS: len(chans),
        M_TB_IDX: tb_idx,
        M_BURST_HS: burst_hs,
        M_BURST_LS: burst_ls,
        M_CLK_HZ: clk_hz,
        M_IP_BASE: ip_base & 0xFFFFFFFF,
        M_ROUND_T0: 0,
        M_SEQ_BEGIN: 0,
        M_TOTAL_ROUNDS: 0,
        M_SIGNATURE: SIGNATURE,
    }
    # D[16..64] istatistik bloğu start: başında PCS tarafından clear_stats ile sıfırlanır (47 UART yazması tasarrufu)
    # D_CH_CODE - 1 = 255: R8=0 (global/TX) için tek LDD ile kanal kodu çözümü
    dmem_init[D_CH_CODE - 1] = 255
    for i, ch in enumerate(chans):
        if ch == "TB":
            dmem_init[D_CH_ADDR + i] = (ip_base + TB_BASE_OFF) & 0xFFFFFFFF
            dmem_init[D_CH_CODE + i] = 16
        else:
            n = int(ch[2:])
            dmem_init[D_CH_ADDR + i] = (ip_base + 0x4000 + n * 0x400) & 0xFFFFFFFF
            dmem_init[D_CH_CODE + i] = n
    for i, w in enumerate(PATTERN_FIXED):
        dmem_init[D_PATTERNS + i] = w

    need_chk_line = bool(sel_set & {"idle", "polarity"})
    need_send_one = bool(sel_set & {"pattern_hs", "pattern_ls", "switch", "parity", "mismatch", "gapviol", "bittime", "logger"})
    need_pattern = bool(sel_set & {"pattern_hs", "pattern_ls"})
    need_burst = bool(sel_set & {"burst_hs", "burst_ls"})
    need_sched = need_burst or ("gapviol" in sel_set)
    need_check_ok = bool(sel_set & {"single_hs", "single_ls", "pattern_hs", "pattern_ls", "burst_hs", "burst_ls", "switch", "parity", "gapviol", "bittime", "logger"})
    need_check_rej = bool(sel_set & {"parity", "mismatch", "gapviol"})
    need_set_speed = bool(sel_set & {"idle", "single_hs", "single_ls", "pattern_hs", "pattern_ls", "burst_hs", "burst_ls", "switch", "parity", "mismatch", "gapviol", "bittime", "logger"})
    need_single = bool(sel_set & {"single_hs", "single_ls"})
    need_send_chk_one = bool(sel_set & {"switch", "parity", "gapviol", "bittime", "logger"})

    # 1-tabanlı LOOP indeksleme ofsetleri: D[BASE_M1 + R8], R8 = N_CHANS..1
    ch_addr_m1 = D_CH_ADDR - 1
    ch_code_m1 = D_CH_CODE - 1
    ch_fail_m1 = D_CHAN_FAIL - 1
    snap_w_m1 = D_SNAP_W - 1
    snap_e_m1 = D_SNAP_E - 1
    snap_d_m1 = D_SNAP_D - 1

    L: list[str] = [
        "; ARINC 429 IP 2.1.0 — Otonom Periyodik Loopback Testi (AXIL Studio PCS / cmd_seq v2.0)",
        f"; IP_BASE=0x{ip_base:08X}  CLK={clk_hz} Hz  Kanallar={','.join(chans)}  Testler={','.join(sel_list)}",
        "",
        f".equ IP_BASE          0x{ip_base & 0xFFFFFFFF:08X}",
        f".equ IP_ID_EXP        0x{ipmap.IP_ID_WORD:08X}",
        f".equ OFF_IP_ID        0x{OFF_IP_ID:04X}",
        f".equ OFF_SOFT_RESET   0x{OFF_SOFT_RESET:04X}",
        f".equ OFF_GLOB_FREEZE  0x{OFF_GLOBAL_FREEZE:04X}",
        f".equ OFF_TS_CTRL      0x{OFF_TS_CTRL:04X}",
        f".equ OFF_TX_CTRL      0x{OFF_TX_CTRL:04X}",
        f".equ OFF_TX_WORD      0x{OFF_TX_WORD:04X}",
        f".equ OFF_TX_SEND      0x{OFF_TX_SEND:04X}",
        f".equ OFF_TX_EXT_DATA  0x{OFF_TX_EXT_DATA:04X}",
        f".equ OFF_TX_EXT_LINE  0x{OFF_TX_EXT_LINE:04X}",
        f".equ OFF_TX_INIT_DLY  0x{OFF_TX_INIT_DLY:04X}",
        f".equ OFF_TX_IWG       0x{OFF_TX_IWG:04X}",
        f".equ OFF_TX_SCHED_CNT 0x{OFF_TX_SCHED_CNT:04X}",
        f".equ OFF_TX_CFG       0x{OFF_TX_CFG:04X}",
        f".equ OFF_TX_CUST_TIM  0x{OFF_TX_CUST_TIM:04X}",
        f".equ OFF_TX_CUST_GAP  0x{OFF_TX_CUST_GAP:04X}",
        f".equ OFF_TX_CUST_SLP  0x{OFF_TX_CUST_SLP:04X}",
        f".equ OFF_TX_ACT_TIM   0x{OFF_TX_ACT_TIM:04X}",
        f".equ OFF_TX_ACT_GAP   0x{OFF_TX_ACT_GAP:04X}",
        f".equ OFF_TX_STATUS    0x{OFF_TX_STATUS:04X}",
        f".equ OFF_TX_WORD_CNT  0x{OFF_TX_WORD_CNT:04X}",
        f".equ CH_CTRL          0x{CH_CTRL:04X}",
        f".equ CH_STATUS        0x{CH_STATUS:04X}",
        f".equ CH_CFG           0x{CH_CFG:04X}",
        f".equ CH_ACT_PULSE     0x{CH_ACT_PULSE:04X}",
        f".equ CH_ACT_BIT       0x{CH_ACT_BIT:04X}",
        f".equ CH_WORD_CNT      0x{CH_WORD_CNT:04X}",
        f".equ CH_ERR_CNT       0x{CH_ERR_CNT:04X}",
        f".equ CH_DROP_CNT      0x{CH_DROP_CNT:04X}",
        f".equ CH_LAST_WORD     0x{CH_LAST_WORD:04X}",
        f".equ CH_ERR_RADDR     0x{CH_ERR_RADDR:04X}",
        f".equ CH_ERR_RD_INFO   0x{CH_ERR_RD_INFO:04X}",
        f".equ CH_ERR_RD_DATA   0x{CH_ERR_RD_DATA:04X}",
        f".equ CH_BIT_RADDR     0x{CH_BIT_RADDR:04X}",
        f".equ CH_BIT_RD_PULSE  0x{CH_BIT_RD_PULSE:04X}",
        f".equ CH_BIT_RD_NULL   0x{CH_BIT_RD_NULL:04X}",
        f".equ TB_CHK_CTRL      0x{TB_CHK_CTRL:04X}",
        f".equ TB_CHK_TIMEOUT   0x{TB_CHK_TIMEOUT:04X}",
        f".equ TB_CHK_OK_CNT    0x{TB_CHK_OK_CNT:04X}",
        f".equ TB_CHK_ERR_CNT   0x{TB_CHK_ERR_CNT:04X}",
        f".equ TB_CHK_STATUS    0x{TB_CHK_STATUS:04X}",
        f".equ SINGLE_TXW       0x{SINGLE_TX_WORD:08X}",
        f".equ SINGLE_EXP       0x{SINGLE_EXP_WORD:08X}",
        f".equ W_5US            {w_5us}",
        f".equ W_30US           {w_30us}",
        f".equ W_SETTLE_HS      {w_settle_hs}",
        f".equ W_SETTLE_LS      {w_settle_ls}",
        f".equ W_TX_TO          {w_tx_to}",
        f".equ W_SCHED_TO       {w_sched_to}",
        f".equ TB_TO_CLK        {tb_timeout_clk}",
        f".equ ERR_MASK         0x{err_mask:X}",
        f".equ BIT_WMASK        0x{bit_wmask:X}",
        f".equ N_CHANS          {len(chans)}",
        "",
        "; ---- Başlangıç: IP reset, logger + checker kurulumu ----",
        "start:",
        "        LDI   R6, IP_BASE",
        "        CALL  clear_stats",
        f"        LDD   R13, D[{M_PRNG}]",
        "        LDI   R1, 1",
        "        WR    [R6+OFF_SOFT_RESET], R1",
        "        WAIT  W_5US",
        "        WR    [R6+OFF_TS_CTRL], R1",
        "        WR    [R6+OFF_TX_CTRL], R1",
        "        WR    [R6+OFF_TX_INIT_DLY], R0",     # eski scheduler gecikmesini sıfırla
        "        WR    [R6+OFF_TX_IWG], R1",          # 1 clk min inter-word gap
        "        LDI   R1, 5",                       # ENABLE + CLEAR
        "        CALL  all_ch_ctrl",
    ]
    if use_tb:
        L += [
            "        LDI   R1, TB_TO_CLK",
            "        WR    [R6+TB_CHK_TIMEOUT], R1",
            "        LDI   R1, 3",
            "        WR    [R6+TB_CHK_CTRL], R1",
        ]
    L += [
        "set_run:",
        "        LDI   R1, 1",
        f"        STD   D[{M_STATE}], R1",
        "",
        "; ---- Ana periyodik test turu ----",
        "round:",
        f"        LDD   R1, D[{M_CLEAR_REQ}]",
        "        CMP   R1, 0",
        "        BR    Z, no_clr",
        "        CALL  clear_stats",
        "no_clr:",
        "        TMR   R1",
        f"        STD   D[{M_ROUND_T0}], R1",
        "        LDI   R10, 0",                      # round_fail_mask = 0
    ]

    # ---- Test 0: ident
    if "ident" in sel_set:
        L += [
            "t_ident:",
            "        LDI   R9, 0",
            "        RD    R1, [R6+OFF_IP_ID]",
            "        CMP   R1, IP_ID_EXP",
            "        BR    Z, t_ident_ok",
            "        LDI   R2, IP_ID_EXP",
            "        LDI   R8, 0",
            "        LDI   R3, 1",
            "        CALL  rec_fail",
            "t_ident_ok:",
        ]

    # ---- Test 1: idle
    if "idle" in sel_set:
        L += [
            "t_idle:",
            "        LDI   R9, 1",
            "        CALL  set_hs",
            "        LDI   R11, 0x7000",             # LINE_HIGH | LINE_LOW | SYNC_WAIT
            "        LDI   R12, 0",
            "        LDI   R15, 2",
            "        CALL  chk_line_now",
        ]

    # ---- Test 2: polarity (LOW=2->0x2000, HIGH=1->0x1000, NULL=0->0x0000)
    if "polarity" in sel_set:
        L += [
            "t_pol:",
            "        LDI   R9, 2",
            "        WR    [R6+OFF_TX_CTRL], R0",    # TRANSMITTER_EN=0
            "        LDI   R11, 0x3000",
            "        LDI   R15, 3",
            "        LDI   R14, 3",
            "pol_lp:",
            "        MOV   R1, R14",
            "        SUB   R1, 1",                   # 2 (LOW), 1 (HIGH), 0 (NULL)
            "        CALL  chk_pol",
            "        LOOP  R14, pol_lp",
            "        LDI   R1, 1",
            "        WR    [R6+OFF_TX_CTRL], R1",
            "        WAIT  W_SETTLE_HS",
            "        LDI   R1, 5",                   # override PULSE_STUCK temizle
            "        CALL  all_ch_ctrl",
        ]

    # ---- Test 3 & 4: single_hs / single_ls
    if "single_hs" in sel_set:
        L += ["t_s_hs:", "        LDI   R9, 3", "        LDI   R1, 0x10", "        CALL  run_single"]
    if "single_ls" in sel_set:
        L += ["t_s_ls:", "        LDI   R9, 4", "        LDI   R1, 0x11", "        CALL  run_single"]

    # ---- Test 5 & 6: pattern_hs / pattern_ls
    if "pattern_hs" in sel_set:
        L += ["t_p_hs:", "        LDI   R9, 5", "        LDI   R1, 0x10", "        LDI   R15, 10", "        CALL  run_pattern"]
    if "pattern_ls" in sel_set:
        L += ["t_p_ls:", "        LDI   R9, 6", "        LDI   R1, 0x11", "        LDI   R15, 6", "        CALL  run_pattern"]

    # ---- Test 7 & 8: burst_hs / burst_ls (IP 2.1.0 TX_SCHED_COUNT)
    if "burst_hs" in sel_set:
        L += ["t_b_hs:", "        LDI   R9, 7", "        LDI   R1, 0x10", f"        LDD   R12, D[{M_BURST_HS}]", "        CALL  run_burst"]
    if "burst_ls" in sel_set:
        L += ["t_b_ls:", "        LDI   R9, 8", "        LDI   R1, 0x11", f"        LDD   R12, D[{M_BURST_LS}]", "        CALL  run_burst"]

    # ---- Test 9: switch (HS <-> LS 2 tur)
    if "switch" in sel_set:
        L += [
            "t_sw:",
            "        LDI   R9, 9",
            "        LDI   R14, 2",
            "sw_lp:",
            "        LDI   R1, 0x11",
            "        CALL  set_speed_all",
            "        LDI   R11, 0x80112233",
            "        CALL  send_chk_one",
            "        CALL  set_hs",
            "        LDI   R11, 0x80445566",
            "        CALL  send_chk_one",
            "        LOOP  R14, sw_lp",
        ]

    # ---- Test 10: parity
    if "parity" in sel_set:
        L += [
            "t_par:",
            "        LDI   R9, 10",
        ]
        if "switch" not in sel_set:
            L += ["        CALL  set_hs"]
        L += [
            f"        LDI   R11, 0x{PARITY_BAD_WORD:08X}",  # Even parity
            f"        LDI   R12, 0x{ERR_PARITY:X}",
            "        CALL  send_chk_rej",
            f"        LDI   R11, 0x{PARITY_GOOD_WORD:08X}", # Odd parity recovery
            "        CALL  send_chk_one",
        ]

    # ---- Test 11: mismatch
    if "mismatch" in sel_set:
        L += [
            "t_mis:",
            "        LDI   R9, 11",
            "        LDI   R11, 0x81ABCDEF",
            "        LDI   R1, 0x10",                # TX HS / RX LS
            "        WR    [R6+OFF_TX_CFG], R1",
            "        LDI   R1, 0x11",
            "        CALL  set_rx_speed",
            "        LDI   R12, 0",
            "        CALL  send_chk_rej",
            "        LDI   R1, 0x11",                # TX LS / RX HS
            "        WR    [R6+OFF_TX_CFG], R1",
            "        LDI   R1, 0x10",
            "        CALL  set_rx_speed",
            f"        LDI   R12, 0x{ERR_PULSE_STUCK:X}",
            "        CALL  send_chk_rej",
            "        CALL  set_hs",
        ]

    # ---- Test 12: gapviol (IP 2.1.0 TX_SCHED_COUNT=3 + TX_CUST_GAP_DUR = ACT_GAP/2)
    if "gapviol" in sel_set:
        L += [
            "t_gap:",
            "        LDI   R9, 12",
        ]
        if "mismatch" not in sel_set:
            L += ["        CALL  set_hs"]
        L += [
            "        RD    R1, [R6+OFF_TX_ACT_TIM]",
            "        WR    [R6+OFF_TX_CUST_TIM], R1",
            "        RD    R1, [R6+OFF_TX_ACT_GAP]",
            "        SHR   R1, 1",                   # 4-bit gap / 2 = 2-bit gap (< 4-bit min)
            "        WR    [R6+OFF_TX_CUST_GAP], R1",
            "        LDI   R1, 1",
            "        WR    [R6+OFF_TX_CUST_SLP], R1",
            "        LDI   R1, 0x12",                # Custom + APPLY
            "        WR    [R6+OFF_TX_CFG], R1",
            "        CALL  snap_all",
            "        LDI   R11, 0x80C0FFEE",
            "        LDI   R12, 3",                  # 3 Word: W1->W2 GAP_VIOL, depth-4 TB_CHK taşmaz
            "        CALL  sched_run",
            "        CALL  set_hs",                  # HS'e dön + TB_CHK FIFO/OVF temizle + settle
            f"        LDI   R12, 0x{ERR_GAP_VIOL:X}",
            "        CALL  check_rej",
            "        CALL  send_chk_one",            # toparlanma (R11=0x80C0FFEE)
        ]

    # ---- Test 13: bittime (Bit Diagnostic: 32 bit pulse/bit unsigned-range + gürültü)
    if "bittime" in sel_set:
        L += [
            "t_bt:",
            "        LDI   R9, 13",
        ]
        if "gapviol" not in sel_set:
            L += ["        CALL  set_hs"]
        L += [
            "        LDI   R11, 0xD5555555",
            "        CALL  send_chk_one",            # hat kopuksa WORD_CNT artışı doğrulanır, bayat BRAM geçmez
            "        LDI   R8, N_CHANS",
            "bt_ch:",
            f"        LDD   R7, D[{ch_addr_m1}+R8]",
            "        RD    R1, [R7+CH_WORD_CNT]",
            f"        LDD   R2, D[{snap_w_m1}+R8]",
            "        CMP   R1, R2",                  # bu turda Word almadıysa bayat BIT_RAM okuma
            "        BR    Z, bt_nx",
            "        SUB   R1, 1",
            "        AND   R1, BIT_WMASK",
            "        SHL   R1, 8",
            "        WR    [R7+CH_BIT_RADDR], R1",
            "        RD    R15, [R7+CH_ACT_PULSE]",
            "        MOV   R12, R15",
            "        AND   R12, 0xFFFF",             # min_p
            "        SHR   R15, 16",
            "        SUB   R15, R12",                # max_p - min_p
            "        RD    R1, [R7+CH_ACT_BIT]",
            "        MOV   R2, R1",
            "        AND   R2, 0xFFFF",
            f"        STD   D[{M_TMP0}], R2",        # min_b
            "        SHR   R1, 16",
            "        SUB   R1, R2",
            f"        STD   D[{M_TMP1}], R1",        # max_b - min_b
            "        LDI   R14, 32",
            "bt_lp:",
            "        RD    R1, [R7+CH_BIT_RD_PULSE]",
            "        RD    R4, [R7+CH_BIT_RD_NULL]",
            "        ADD   R4, R1",                  # [15:0]=pulse+null, [31:16]=perr+nerr
            "        MOV   R2, R4",
            "        SHR   R2, 16",
            f"        LDD   R3, D[{M_MAX_NOISE}]",
            "        CMP   R3, R2",
            "        BR    HS, bt_n_ok",
            f"        STD   D[{M_MAX_NOISE}], R2",
            "bt_n_ok:",
            "        AND   R1, 0xFFFF",
            "        MOV   R2, R1",
            "        SUB   R2, R12",
            "        CMP   R15, R2",                 # max_p - min_p < dur_p - min_p -> aralık dışı
            "        BR    LO, bt_pf",
            "        CMP   R14, 1",                  # bit 31'de bit süresi kontrol edilmez
            "        BR    Z, bt_blp",
            "        AND   R4, 0xFFFF",
            "        MOV   R2, R4",
            f"        LDD   R3, D[{M_TMP0}]",
            "        SUB   R2, R3",
            f"        LDD   R3, D[{M_TMP1}]",
            "        CMP   R3, R2",
            "        BR    LO, bt_bf",
            "bt_blp:",
            "        LOOP  R14, bt_lp",
            "        JMP   bt_nx",
            "bt_pf:",
            "        MOV   R2, R12",
            "        LDI   R3, 14",
            "        JMP   bt_fail",
            "bt_bf:",
            "        MOV   R1, R4",
            f"        LDD   R2, D[{M_TMP0}]",
            "        LDI   R3, 15",
            "bt_fail:",
            "        CALL  rec_fail",
            "bt_nx:",
            "        LOOP  R8, bt_ch",
        ]

    # ---- Test 14: logger (ENABLE=0, FREEZE=1, GLOBAL_FREEZE=1)
    if "logger" in sel_set:
        L += [
            "t_log:",
            "        LDI   R9, 14",
        ]
        if "bittime" not in sel_set:
            L += ["        CALL  set_hs"]
        L += [
            "        LDI   R11, 0x80555AAA",
            "        LDI   R1, 0",                   # ENABLE=0 -> DROP+0
            "        LDI   R12, 0",
            "        CALL  log_step",
            "        LDI   R1, 3",                   # ENABLE+FREEZE -> DROP+1
            "        LDI   R12, 1",
            "        CALL  log_step",
            "        LDI   R1, 1",                   # ENABLE=1, GLOBAL_FREEZE=1 -> DROP+1
            "        WR    [R6+OFF_GLOB_FREEZE], R1",
            "        CALL  log_step",
            "        WR    [R6+OFF_GLOB_FREEZE], R0",
            "        CALL  send_chk_one",            # normal moda dönüş
        ]

    # ---- Tur sonu istatistik güncellemesi (seqlock: M_SEQ_BEGIN .. M_TOTAL_ROUNDS)
    L += [
        "",
        "round_end:",
        f"        STD   D[{M_PRNG}], R13",
        f"        LDD   R1, D[{M_TOTAL_ROUNDS}]",
        "        ADD   R1, 1",
        f"        STD   D[{M_SEQ_BEGIN}], R1",
        "        TMR   R2",
        f"        LDD   R3, D[{M_ROUND_T0}]",
        "        SUB   R2, R3",
        f"        STD   D[{M_LAST_DUR_CLK}], R2",
        f"        STD   D[{M_LAST_FAIL_MASK}], R10",
        f"        LDD   R2, D[{M_CUM_FAIL_MASK}]",
        "        OR    R2, R10",
        f"        STD   D[{M_CUM_FAIL_MASK}], R2",
        "        CMP   R10, 0",
        "        BR    Z, r_pub",
        f"        LDD   R2, D[{M_FAIL_ROUNDS}]",
        "        ADD   R2, 1",
        f"        STD   D[{M_FAIL_ROUNDS}], R2",
        "r_pub:",
        f"        STD   D[{M_TOTAL_ROUNDS}], R1",
        f"        LDD   R2, D[{M_MAX_ROUNDS}]",
        "        CMP   R2, 0",
        "        BR    Z, r_wait",
        "        CMP   R1, R2",
        "        BR    HS, finished",
        "r_wait:",
        f"        LDD   R1, D[{M_GAP_CLK}]",
        "        WAIT  R1",
        "        JMP   round",
        "",
        "finished:",
        "        LDI   R1, 2",
        f"        STD   D[{M_STATE}], R1",
        "fin_lp:",
        f"        LDD   R1, D[{M_AGAIN}] @50",
        "        CMP   R1, 0",
        "        BR    Z, fin_lp",
        f"        STD   D[{M_AGAIN}], R0",
        "        CALL  clear_stats",
        "        JMP   set_run",
        "",
        "; ============================================================================",
        "; Ortak alt-yordamlar (maks. çağrı derinliği <= 4)",
        "; ============================================================================",
        "all_ch_ctrl:",
        "        LDI   R2, N_CHANS",
        "acc_lp:",
        f"        LDD   R3, D[{ch_addr_m1}+R2]",
        "        WR    [R3+CH_CTRL], R1",
        "        LOOP  R2, acc_lp",
        "        RET",
        "",
        "clear_stats:",
        f"        STD   D[{M_CLEAR_REQ}], R0",
        f"        LDI   R2, {STATS_COUNT}",
        "cs_lp:",
        f"        STD   D[{STATS_START - 1}+R2], R0",
        "        LOOP  R2, cs_lp",
        "        RET",
        "",
        "; rec_fail: R9=test_id, R8=ch_idx (1..N, 0=global), R3=sub_code, R2=exp, R1=got",
        "rec_fail:",
        "        LDI   R4, 1",
        "        SHL   R4, R9",
        "        MOV   R5, R10",
        "        AND   R5, R4",
        "        BR    NZ, rf_ch",
        "        OR    R10, R4",
        f"        LDD   R5, D[{D_TEST_FAIL}+R9]",
        "        ADD   R5, 1",
        f"        STD   D[{D_TEST_FAIL}+R9], R5",
        f"        STD   D[{D_TEST_CH}+R9], R0",      # bu turdaki ilk hata: hat maskesini sıfırla
        "rf_ch:",
        "        LDI   R4, 1",
        "        SHL   R4, R8",                      # bit0=TX/Genel, bit(i+1)=ch[i]
        f"        LDD   R5, D[{D_TEST_CH}+R9]",
        "        OR    R5, R4",
        f"        STD   D[{D_TEST_CH}+R9], R5",
        f"        LDD   R5, D[{ch_fail_m1}+R8]",     # R8=0 -> D[47] global, R8=1..N -> D[48..]
        "        ADD   R5, 1",
        f"        STD   D[{ch_fail_m1}+R8], R5",
        f"        LDD   R5, D[{M_TOTAL_ROUNDS}]",
        "        ADD   R5, 1",
        f"        LDD   R4, D[{ch_code_m1}+R8]",
        "        SHL   R4, 8",
        "        OR    R4, R9",
        "        SHL   R3, 16",
        "        OR    R4, R3",
        f"        STD   D[{M_LAST_FAIL_ROUND}], R5",
        f"        STD   D[{M_LAST_FAIL_INFO}], R4",
        f"        STD   D[{M_LAST_FAIL_EXP}], R2",
        f"        STD   D[{M_LAST_FAIL_GOT}], R1",
        f"        LDD   R3, D[{M_FIRST_FAIL_ROUND}]",
        "        CMP   R3, 0",
        "        BR    NZ, rf_ret",
        f"        STD   D[{M_FIRST_FAIL_ROUND}], R5",
        f"        STD   D[{M_FIRST_FAIL_INFO}], R4",
        f"        STD   D[{M_FIRST_FAIL_EXP}], R2",
        f"        STD   D[{M_FIRST_FAIL_GOT}], R1",
        "rf_ret:",
        "        RET",
    ]

    if need_chk_line:
        L += [
            "",
            "; chk_pol: R1=TX_EXT_LINE (1->0x1000, 2->0x2000, 0->0), R11=mask, R15=sub_code",
            "chk_pol:",
            "        MOV   R12, R1",
            "        SHL   R12, 12",
            "        WR    [R6+OFF_TX_EXT_LINE], R1",
            "        WAIT  W_30US",
            "chk_line_now:",
            "        LDI   R8, N_CHANS",
            "cl_lp:",
            f"        LDD   R7, D[{ch_addr_m1}+R8]",
            "        RD    R1, [R7+CH_STATUS]",
            "        AND   R1, R11",
            "        CMP   R1, R12",
            "        BR    Z, cl_nx",
            "        MOV   R2, R12",
            "        MOV   R3, R15",
            "        CALL  rec_fail",
            "cl_nx:",
            "        LOOP  R8, cl_lp",
            "        RET",
        ]

    if need_set_speed:
        L += [
            "",
            "; set_hs / set_speed_all / set_rx_speed: R1 = 0x10 (HS) veya 0x11 (LS)",
            "set_hs:",
            "        LDI   R1, 0x10",
            "set_speed_all:",
            "        WR    [R6+OFF_TX_CFG], R1",
            "set_rx_speed:",
            "        LDI   R2, N_CHANS",
            "srs_lp:",
            f"        LDD   R3, D[{ch_addr_m1}+R2]",
            "        WR    [R3+CH_CFG], R1",
            "        LOOP  R2, srs_lp",
        ]
        if use_tb:
            L += ["        LDI   R2, 3", "        WR    [R6+TB_CHK_CTRL], R2"]
        L += [
            "        CMP   R1, 0x10",
            "        BR    Z, srs_hs",
            "        WAIT  W_SETTLE_LS",
            "        RET",
            "srs_hs:",
            "        WAIT  W_SETTLE_HS",
            "        RET",
        ]

    if need_check_ok or need_check_rej or ("logger" in sel_set):
        L += [
            "",
            "snap_all:",
            f"        RD    D[{M_SNAP_TX}], [R6+OFF_TX_WORD_CNT]",
            "        LDI   R2, N_CHANS",
            "sn_lp:",
            f"        LDD   R3, D[{ch_addr_m1}+R2]",
            f"        RD    D[{snap_w_m1}+R2], [R3+CH_WORD_CNT]",
            f"        RD    D[{snap_e_m1}+R2], [R3+CH_ERR_CNT]",
            f"        RD    D[{snap_d_m1}+R2], [R3+CH_DROP_CNT]",
            "        LOOP  R2, sn_lp",
        ]
        if use_tb:
            L += [
                f"        RD    D[{M_SNAP_CHKO}], [R6+TB_CHK_OK_CNT]",
                f"        RD    D[{M_SNAP_CHKE}], [R6+TB_CHK_ERR_CNT]",
            ]
        L += ["        RET"]

    if need_send_one or need_single or need_sched:
        L += [
            "",
            "wait_tx_idle:",
            "        TMR   R3",
            "        ADD   R3, W_TX_TO",
            "wti_lp:",
            "        RD    R1, [R6+OFF_TX_STATUS]",
            "        AND   R1, 1",
            "        BR    Z, wti_ok",
            "        TMR   R2",
            "        SUB   R2, R3",
            "        BR    MI, wti_lp",
            "        LDI   R8, 0",
            "        LDI   R2, 0",
            "        LDI   R3, 6",
            "        CALL  rec_fail",
            "wti_ok:",
            "        WAIT  W_SETTLE_HS",
            "        RET",
        ]

    if need_send_one:
        L += [
            "",
            "send_one:",
            "        WR    [R6+OFF_TX_EXT_DATA], R11",
            "        LDI   R1, 1",
            "        WR    [R6+OFF_TX_SEND], R1",
            "        JMP   wait_tx_idle",             # tail-call (yığın derinliği harcamaz)
        ]

    if need_check_ok:
        L += [
            "",
            "; check_ok: R12=beklenen Word adedi, R11=beklenen son Word",
            "check_ok:",
            "        RD    R1, [R6+OFF_TX_WORD_CNT]",
            f"        LDD   R2, D[{M_SNAP_TX}]",
            "        SUB   R1, R2",
            "        CMP   R1, R12",
            "        BR    Z, co_ch",
            "        MOV   R2, R12",
            "        LDI   R8, 0",
            "        LDI   R3, 7",
            "        CALL  rec_fail",
            "co_ch:",
            "        LDI   R8, N_CHANS",
            "co_lp:",
            f"        LDD   R7, D[{ch_addr_m1}+R8]",
            "        RD    R1, [R7+CH_WORD_CNT]",
            f"        LDD   R2, D[{snap_w_m1}+R8]",
            "        SUB   R1, R2",
            "        MOV   R2, R12",
            "        LDI   R3, 8",
            "        CMP   R1, R12",
            "        BR    NZ, co_f",
            "        RD    R1, [R7+CH_ERR_CNT]",
            f"        LDD   R2, D[{snap_e_m1}+R8]",
            "        SUB   R1, R2",
            "        LDI   R2, 0",
            "        LDI   R3, 9",
            "        BR    NZ, co_f",
            "        RD    R1, [R7+CH_LAST_WORD]",
            "        MOV   R2, R11",
            "        LDI   R3, 10",
            "        CMP   R1, R11",
            "        BR    Z, co_nx",
            "co_f:",
            "        CALL  rec_fail",
            "co_nx:",
            "        LOOP  R8, co_lp",
        ]
        if use_tb:
            L += [
                "        RD    R1, [R6+TB_CHK_OK_CNT]",
                f"        LDD   R2, D[{M_SNAP_CHKO}]",
                "        SUB   R1, R2",
                "        CMP   R1, R12",
                "        BR    NZ, co_tbf",
                "        RD    R1, [R6+TB_CHK_ERR_CNT]",
                f"        LDD   R2, D[{M_SNAP_CHKE}]",
                "        SUB   R1, R2",
                "        RD    R2, [R6+TB_CHK_STATUS]",
                "        AND   R2, 0x10",
                "        OR    R1, R2",
                "        BR    Z, co_ret",
                "co_tbf:",
                f"        LDI   R8, {tb_idx + 1}",
                "        MOV   R2, R12",
                "        LDI   R3, 11",
                "        CALL  rec_fail",
                "co_ret:",
            ]
        L += ["        RET"]

    if need_send_chk_one or need_pattern:
        L += [
            "",
            "send_chk_one:",
            "        CALL  snap_all",
            "        CALL  send_one",
            "chk_one:",
            "        LDI   R12, 1",
            "        JMP   check_ok",
        ]

    if need_single:
        L += [
            "",
            "run_single:",
            "        CALL  set_speed_all",
            "        CALL  snap_all",
            "        LDI   R1, SINGLE_TXW",
            "        WR    [R6+OFF_TX_WORD], R1",
            "        LDI   R1, 5",
            "        WR    [R6+OFF_TX_CTRL], R1",
            "        WR    [R6+OFF_TX_SEND], R1",     # bit0=1 (5 & 1 = 1)
            "        CALL  wait_tx_idle",
            "        LDI   R1, 1",
            "        WR    [R6+OFF_TX_CTRL], R1",
            "        LDI   R11, SINGLE_EXP",
        ]
        if need_send_chk_one or need_pattern:
            L += ["        JMP   chk_one"]
        else:
            L += ["        LDI   R12, 1", "        JMP   check_ok"]

    if need_pattern:
        L += [
            "",
            "; run_pattern: R1=hız, R15=toplam Word (6 sabit + kalanı xorshift32)",
            "run_pattern:",
            "        CALL  set_speed_all",
            "        LDI   R14, 0",
            "rp_lp:",
            "        CMP   R14, 6",
            "        BR    HS, rp_rnd",
            f"        LDD   R11, D[{D_PATTERNS}+R14]",
            "        JMP   rp_go",
            "rp_rnd:",
            "        MOV   R1, R13",                 # xorshift32
            "        SHL   R1, 13",
            "        XOR   R13, R1",
            "        MOV   R1, R13",
            "        SHR   R1, 17",
            "        XOR   R13, R1",
            "        MOV   R1, R13",
            "        SHL   R1, 5",
            "        XOR   R13, R1",
            "        MOV   R11, R13",
            "        AND   R11, 0x7FFFFFFF",         # odd_par (0x6996 tablosu)
            "        MOV   R1, R11",
            "        SHR   R1, 16",
            "        XOR   R1, R11",
            "        MOV   R2, R1",
            "        SHR   R2, 8",
            "        XOR   R1, R2",
            "        MOV   R2, R1",
            "        SHR   R2, 4",
            "        XOR   R1, R2",
            "        AND   R1, 0xF",
            "        LDI   R2, 0x6996",
            "        SHR   R2, R1",
            "        AND   R2, 1",
            "        BR    NZ, rp_go",
            "        OR    R11, 0x80000000",
            "rp_go:",
            "        CALL  send_chk_one",
            "        ADD   R14, 1",
            "        CMP   R14, R15",
            "        BR    LO, rp_lp",
            "        RET",
        ]

    if need_sched:
        L += [
            "",
            "; sched_run (IP 2.1.0): R11=Word, R12=TX_SCHED_COUNT",
            "sched_run:",
            "        WR    [R6+OFF_TX_EXT_DATA], R11",
            "        WR    [R6+OFF_TX_SCHED_CNT], R12",
            "        LDI   R1, 0x0B",
            "        WR    [R6+OFF_TX_CTRL], R1",
            "        TMR   R3",
            "        ADD   R3, W_SCHED_TO",
            "sr_lp:",
            "        RD    R1, [R6+OFF_TX_STATUS]",
            "        AND   R1, 0x10",                # SCHED_DONE
            "        BR    NZ, sr_done",
            "        TMR   R2",
            "        SUB   R2, R3",
            "        BR    MI, sr_lp",
            "        LDI   R8, 0",
            "        LDI   R2, 0x10",
            "        LDI   R3, 6",
            "        CALL  rec_fail",
            "sr_done:",
            "        LDI   R1, 1",
            "        WR    [R6+OFF_TX_CTRL], R1",
            "        WR    [R6+OFF_TX_SCHED_CNT], R0",
            "        JMP   wait_tx_idle",
        ]

    if need_burst:
        L += [
            "",
            "run_burst:",
            "        CALL  set_speed_all",
            "        CALL  snap_all",
            "        LDI   R11, 0x82468ACE",
            "        CALL  sched_run",
            "        JMP   check_ok",
        ]

    if need_check_rej:
        if sel_set & {"parity", "mismatch"}:
            L += [
                "",
                "send_chk_rej:",
                "        CALL  snap_all",
                "        CALL  send_one",
            ]
        L += [
            "check_rej:",
            "        LDI   R8, N_CHANS",
            "cr_lp:",
            f"        LDD   R7, D[{ch_addr_m1}+R8]",
            "        RD    R1, [R7+CH_WORD_CNT]",
            f"        LDD   R2, D[{snap_w_m1}+R8]",
            "        SUB   R1, R2",
            "        LDI   R2, 0",
            "        LDI   R3, 12",
            "        BR    NZ, cr_f",
            "        CMP   R12, 0",
            "        BR    Z, cr_nx",
            "        RD    R4, [R7+CH_ERR_CNT]",
            f"        LDD   R2, D[{snap_e_m1}+R8]",
            "        SUB   R4, R2",
            "        LDI   R5, 0",
            "        BR    Z, cr_efail",
            "        AND   R2, ERR_MASK",
            "        WR    [R7+CH_ERR_RADDR], R2",
            "cr_scan:",
            "        RD    R1, [R7+CH_ERR_RD_INFO]",
            "        OR    R5, R1",
            "        RD    R1, [R7+CH_ERR_RD_DATA]",
            "        LOOP  R4, cr_scan",
            "        AND   R5, R12",
            "        BR    NZ, cr_nx",
            "cr_efail:",
            "        MOV   R1, R5",
            "        MOV   R2, R12",
            "        LDI   R3, 13",
            "cr_f:",
            "        CALL  rec_fail",
            "cr_nx:",
            "        LOOP  R8, cr_lp",
            "        RET",
        ]

    if "logger" in sel_set:
        L += [
            "",
            "log_step:",
            "        CALL  all_ch_ctrl",
            "        CALL  snap_all",
            "        CALL  send_one",
            "check_drop:",
            "        LDI   R8, N_CHANS",
            "cd_lp:",
            f"        LDD   R7, D[{ch_addr_m1}+R8]",
            "        RD    R1, [R7+CH_WORD_CNT]",
            f"        LDD   R2, D[{snap_w_m1}+R8]",
            "        SUB   R1, R2",
            "        LDI   R2, 0",
            "        LDI   R3, 12",
            "        BR    NZ, cd_f",
            "        RD    R1, [R7+CH_DROP_CNT]",
            f"        LDD   R2, D[{snap_d_m1}+R8]",
            "        SUB   R1, R2",
            "        MOV   R2, R12",
            "        LDI   R3, 16",
            "        CMP   R1, R12",
            "        BR    Z, cd_nx",
            "cd_f:",
            "        CALL  rec_fail",
            "cd_nx:",
            "        LOOP  R8, cd_lp",
            "        RET",
        ]

    asm_text = "\n".join(L) + "\n"
    prog, entry = assemble(asm_text, imem_aw=imem_aw, dmem_aw=dmem_aw)
    return CompiledProgram(
        asm=asm_text,
        prog=prog,
        entry=entry,
        imem_sum=imem_sum(prog),
        dmem_init=dmem_init,
        selected_tests=sel_list,
        rx_channels=[c for c in rx_channels if c.startswith("RX")],
        use_tb=use_tb,
        ip_base=ip_base & 0xFFFFFFFF,
        clk_hz=clk_hz,
    )


# =====================================================================================
# PCS keşfi, yükleme, kontrol ve telemetri okuma (AxilClient üzerinden)
# =====================================================================================
def _abs_batch(client, ops: list[tuple], quiet: bool = True) -> list:
    """Mutlak adresli batch erişimi: [("read", addr) | ("write", addr, val)]."""
    if hasattr(client, "batch"):
        steps = [
            {"op": "read", "addr": st[1]} if st[0] == "read"
            else {"op": "write", "addr": st[1], "value": int(st[2]) & 0xFFFFFFFF}
            for st in ops
        ]
        return client.batch(steps, quiet=quiet)
    out = []
    for st in ops:
        if st[0] == "read":
            out.append(client.read(addr=st[1], quiet=quiet))
        else:
            client.write(addr=st[1], value=int(st[2]) & 0xFFFFFFFF, quiet=quiet)
            out.append(None)
    return out


def probe_pcs_at(client, base: int, name: str = "PCS", parent: str = "", is_ip_parent: bool = False) -> PcsInfo:
    """Verilen taban adresteki bloğun cmd_seq v2.0 olduğunu doğrulayıp yeteneklerini okur."""
    vals = _abs_batch(client, [
        ("read", base + REG_ID),
        ("read", base + REG_CAPS),
        ("read", base + REG_STATUS),
        ("read", base + REG_DMEM_BASE + M_SIGNATURE * 4),
    ])
    pid, caps_v, status_v, sig = vals
    if (pid & PCS_ID_MASK) != PCS_ID_SIG:
        raise PcsError(f"0x{base:08X} adresinde cmd_seq (PCS) bulunamadı (ID=0x{pid:08X}, beklenen 0x5EC0xxxx)")
    imem_aw, dmem_aw, _nregs, self_id = decode_caps(caps_v)
    return PcsInfo(
        name=name,
        base=base & 0xFFFFFFFF,
        parent=parent,
        is_ip_parent=is_ip_parent,
        pcs_id=pid,
        imem_aw=imem_aw,
        dmem_aw=dmem_aw,
        self_id=self_id,
        status=status_v,
        running_a429=(sig == SIGNATURE and PcsStatus(status_v).busy),
    )


def discover_pcs(client, ip_base: int | None = None) -> list[PcsInfo]:
    """AXIL Studio address_map() üzerinden projedeki tüm cmd_seq (PCS) bloklarını bulur."""
    amap_fn = getattr(client, "address_map", None)
    if amap_fn is None:
        return []
    entries = amap_fn() or []
    ip_parent = ""
    if ip_base is not None:
        for e in entries:
            if int(e.get("base", -1)) == (ip_base & 0xFFFFFFFF) and e.get("kind") != "cmd_seq":
                ip_parent = str(e.get("parent") or "")
                break
    out: list[PcsInfo] = []
    for e in entries:
        if e.get("kind") != "cmd_seq":
            continue
        base = int(e["base"]) & 0xFFFFFFFF
        name = str(e.get("name") or f"PCS_0x{base:08X}")
        parent = str(e.get("parent") or "")
        is_p = bool(ip_parent and name == ip_parent)
        try:
            out.append(probe_pcs_at(client, base, name=name, parent=parent, is_ip_parent=is_p))
        except Exception:  # noqa: BLE001
            out.append(PcsInfo(name=name, base=base, parent=parent, is_ip_parent=is_p))
    out.sort(key=lambda x: (not x.is_ip_parent, x.base))
    return out


def _dmem_stream_ops(base: int, dmem_init: dict[int, int]) -> list[tuple]:
    """Bitişik D-mem alanlarını DMEM_PTR + DMEM_DATA (tek adres) yazmalarına dönüştürür."""
    idxs = sorted(dmem_init)
    ops: list[tuple] = []
    i = 0
    while i < len(idxs):
        j = i
        while j + 1 < len(idxs) and idxs[j + 1] == idxs[j] + 1:
            j += 1
        if j - i >= 1:
            ops.append(("write", base + REG_DMEM_PTR, idxs[i]))
            for k in range(i, j + 1):
                ops.append(("write", base + REG_DMEM_DATA, dmem_init[idxs[k]]))
        else:
            idx = idxs[i]
            ops.append(("write", base + REG_DMEM_BASE + idx * 4, dmem_init[idx]))
        i = j + 1
    return ops


def load_and_start(
    client,
    pcs_base: int,
    compiled: CompiledProgram,
    log=None,
    progress=None,
    force_reload: bool = False,
) -> PcsInfo:
    """Derlenmiş programı PCS I-mem'e yükler (aynıysa atlar), doğrular, D-mem'i yazar ve başlatır."""
    base = pcs_base & 0xFFFFFFFF
    prog_cb = progress or (lambda _d, _t, _m: None)
    info = probe_pcs_at(client, base)
    if compiled.insn_count > info.imem_size:
        raise PcsError(f"Program {compiled.insn_count} komut; bu PCS en fazla {info.imem_size} komut alır.")
    if info.dmem_size < 256:
        raise PcsError(f"PCS D-mem boyu en az 256 word olmalı (mevcut {info.dmem_size}).")

    lock = getattr(client, "lock", None)
    if lock:
        client.lock()
    try:
        # Önce durdur + resetle (I-mem, IMEM_CNT ve IMEM_SUM korunur)
        _abs_batch(client, [
            ("write", base + REG_CTRL, CTRL_ERR_HALT | CTRL_STOP),
            ("write", base + REG_CTRL, CTRL_ERR_HALT | CTRL_RESET),
        ])
        cur_cnt, cur_sum, cur_st_v = _abs_batch(client, [
            ("read", base + REG_IMEM_CNT),
            ("read", base + REG_IMEM_SUM),
            ("read", base + REG_STATUS),
        ])
        cur_st = PcsStatus(cur_st_v)
        already_loaded = (
            not force_reload
            and cur_cnt == compiled.insn_count
            and cur_sum == compiled.imem_sum
            and not cur_st.imem_phase
        )

        if already_loaded:
            prog_cb(compiled.insn_count, compiled.insn_count, "Aynı program I-mem'de zaten yüklü — D-mem güncelleniyor…")
        else:
            _abs_batch(client, [("write", base + REG_IMEM_PTR, 0)])
            w32 = words32(compiled.prog)
            step = 2 * LOAD_CHUNK
            total_insns = compiled.insn_count
            for i in range(0, len(w32), step):
                chunk = [("write", base + REG_IMEM_DATA, w) for w in w32[i:i + step]]
                _abs_batch(client, chunk)
                done = min(total_insns, (i + len(chunk)) // 2)
                prog_cb(done, total_insns, f"PCS I-mem yükleniyor: {done} / {total_insns} komut…")

            cnt, total, st_v = _abs_batch(client, [
                ("read", base + REG_IMEM_CNT),
                ("read", base + REG_IMEM_SUM),
                ("read", base + REG_STATUS),
            ])
            st = PcsStatus(st_v)
            if cnt != compiled.insn_count or total != compiled.imem_sum or st.imem_phase:
                raise PcsError(
                    f"PCS I-mem yükleme doğrulama hatası: CNT={cnt}/{compiled.insn_count}, "
                    f"SUM=0x{total:08X}/0x{compiled.imem_sum:08X}, PHASE={int(st.imem_phase)}"
                )

        dmem_ops = _dmem_stream_ops(base, compiled.dmem_init)
        for i in range(0, len(dmem_ops), 64):
            _abs_batch(client, dmem_ops[i:i + 64])

        _abs_batch(client, [
            ("write", base + REG_ENTRY, compiled.entry),
            ("write", base + REG_CTRL, CTRL_ERR_HALT | CTRL_RUN),
        ])
        prog_cb(compiled.insn_count, compiled.insn_count, "PCS başlatıldı")
        if log:
            if already_loaded:
                log(f"[PCS] 0x{base:08X}: aynı program zaten yüklü ({compiled.insn_count} komut, "
                    f"SUM 0x{compiled.imem_sum:08X}) — I-mem atlandı, D-mem güncellenip başlatıldı.")
            else:
                log(f"[PCS] 0x{base:08X}: {compiled.insn_count}/{info.imem_size} komut yüklendi "
                    f"(SUM 0x{compiled.imem_sum:08X}) ve başlatıldı.")
        return probe_pcs_at(client, base, name=info.name, parent=info.parent, is_ip_parent=info.is_ip_parent)
    finally:
        if lock:
            try:
                client.unlock()
            except Exception:  # noqa: BLE001
                pass


def stop_pcs(client, pcs_base: int):
    base = pcs_base & 0xFFFFFFFF
    _abs_batch(client, [("write", base + REG_CTRL, CTRL_ERR_HALT | CTRL_STOP)])


def clear_stats(client, pcs_base: int):
    """Çalışan PCS'ye istatistik sıfırlama isteği gönderir; durmuşsa D-mem'i doğrudan sıfırlar."""
    base = pcs_base & 0xFFFFFFFF
    st = PcsStatus(_abs_batch(client, [("read", base + REG_STATUS)])[0])
    if st.busy:
        _abs_batch(client, [("write", base + REG_DMEM_BASE + M_CLEAR_REQ * 4, 1)])
    else:
        ops = [("write", base + REG_DMEM_BASE + (STATS_START + i) * 4, 0) for i in range(STATS_COUNT)]
        _abs_batch(client, ops)


def update_gap(client, pcs_base: int, gap_ms: int, clk_hz: int = 50_000_000):
    base = pcs_base & 0xFFFFFFFF
    gap_clk = max(100, int(round(max(0, gap_ms) * (clk_hz / 1000.0))))
    _abs_batch(client, [("write", base + REG_DMEM_BASE + M_GAP_CLK * 4, gap_clk)])


def restart_rounds(client, pcs_base: int, max_rounds: int):
    base = pcs_base & 0xFFFFFFFF
    _abs_batch(client, [
        ("write", base + REG_DMEM_BASE + M_MAX_ROUNDS * 4, max(0, int(max_rounds))),
        ("write", base + REG_DMEM_BASE + M_AGAIN * 4, 1),
    ])


def _chan_name(code: int) -> str:
    if code == 16:
        return channel_label("TB")
    if 0 <= code < 16:
        return channel_label(f"RX{code}")
    if code == 255:
        return "TX / Genel"
    return f"CH#{code}"


def read_telemetry(client, pcs_base: int) -> dict:
    """PCS durumunu ve D-mem sayaçlarını ARINC 429 IP'ye dokunmadan atomik (seqlock) okur."""
    base = pcs_base & 0xFFFFFFFF
    csr_addrs = [
        base + REG_ID, base + REG_CAPS, base + REG_STATUS, base + REG_ERR_CODE,
        base + REG_ERR_PC, base + REG_ERR_ADDR, base + REG_IMEM_CNT,
    ]
    dmem_idxs = list(range(0, 81)) + list(range(D_CH_CODE, D_CH_CODE + 17)) + [M_SIGNATURE]
    dmem_addrs = [base + REG_DMEM_BASE + i * 4 for i in dmem_idxs]

    vals = None
    for _ in range(3):
        raw = _abs_batch(client, [("read", a) for a in csr_addrs + dmem_addrs])
        csrs = raw[:len(csr_addrs)]
        dm = dict(zip(dmem_idxs, raw[len(csr_addrs):]))
        if dm[M_SIGNATURE] != SIGNATURE or dm[M_SEQ_BEGIN] == dm[M_TOTAL_ROUNDS]:
            vals = (csrs, dm)
            break
        vals = (csrs, dm)
    assert vals is not None
    csrs, dm = vals
    pid, caps_v, st_v, err_code, err_pc, err_addr, imem_cnt = csrs
    st = PcsStatus(st_v)
    imem_aw, dmem_aw, _, _ = decode_caps(caps_v)
    recognized = (dm[M_SIGNATURE] == SIGNATURE)

    clk_hz = dm[M_CLK_HZ] or 50_000_000
    n_chans = min(17, dm[M_N_CHANS]) if recognized else 0
    test_mask = dm[M_TEST_MASK] if recognized else 0
    last_mask = dm[M_LAST_FAIL_MASK] if recognized else 0
    cum_mask = dm[M_CUM_FAIL_MASK] if recognized else 0

    chans_out = []
    for i in range(n_chans):
        code = int(dm[D_CH_CODE + i])
        chans_out.append({
            "idx": i,
            "code": code,
            "name": _chan_name(code),
            "fails": int(dm[D_CHAN_FAIL + i]),
        })

    tests_out = []
    for idx, tid, title, hint in TESTS:
        if not ((test_mask >> idx) & 1):
            continue
        ch_mask = int(dm[D_TEST_CH + idx]) if recognized else 0
        fail_chans: list[str] = []
        if ch_mask & 1:
            fail_chans.append("TX / Genel")
        for i in range(n_chans):
            if (ch_mask >> (i + 1)) & 1:
                fail_chans.append(chans_out[i]["name"])
        tests_out.append({
            "idx": idx,
            "tid": tid,
            "title": title,
            "hint": hint,
            "fails": int(dm[D_TEST_FAIL + idx]),
            "last_failed": bool((last_mask >> idx) & 1),
            "ever_failed": bool((cum_mask >> idx) & 1),
            "fail_channels": fail_chans,
        })

    def _decode_fail(r_idx: int, i_idx: int, e_idx: int, g_idx: int) -> dict | None:
        if not recognized or not dm[r_idx]:
            return None
        info_w = int(dm[i_idx])
        f_tid_idx = info_w & 0xFF
        f_ch_code = (info_w >> 8) & 0xFF
        f_sub = (info_w >> 16) & 0xFFFF
        t_entry = TEST_BY_IDX.get(f_tid_idx, (f"test#{f_tid_idx}", f"Test #{f_tid_idx}", ""))
        return {
            "round": int(dm[r_idx]),
            "test_idx": f_tid_idx,
            "test_id": t_entry[0],
            "test_title": t_entry[1],
            "channel": _chan_name(f_ch_code),
            "channel_code": f_ch_code,
            "sub_code": f_sub,
            "reason": SUB_REASON.get(f_sub, f"alt kod {f_sub}"),
            "expected": int(dm[e_idx]),
            "got": int(dm[g_idx]),
        }

    first_fail = _decode_fail(M_FIRST_FAIL_ROUND, M_FIRST_FAIL_INFO, M_FIRST_FAIL_EXP, M_FIRST_FAIL_GOT)
    last_fail = _decode_fail(M_LAST_FAIL_ROUND, M_LAST_FAIL_INFO, M_LAST_FAIL_EXP, M_LAST_FAIL_GOT)

    total = int(dm[M_TOTAL_ROUNDS]) if recognized else 0
    failed_n = int(dm[M_FAIL_ROUNDS]) if recognized else 0
    passed_n = max(0, total - failed_n)
    state_code = int(dm[M_STATE]) if recognized else 0

    return {
        "mode": "pcs",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pcs_base": base,
        "pcs_id": pid,
        "imem_size": 1 << imem_aw if imem_aw <= 16 else 512,
        "dmem_size": 1 << dmem_aw if dmem_aw <= 16 else 256,
        "imem_cnt": int(imem_cnt),
        "pcs_state": st.state,
        "pcs_busy": st.busy,
        "pcs_err": st.err,
        "pcs_pc": st.pc,
        "pcs_err_code": int(err_code),
        "pcs_err_text": pcs_err_text(int(err_code)) if st.err else "",
        "pcs_err_pc": int(err_pc),
        "pcs_err_addr": int(err_addr),
        "recognized": recognized,
        "signature": int(dm[M_SIGNATURE]),
        "run_state": {0: "HAZIRLANIYOR", 1: "KOŞUYOR", 2: "TAMAMLANDI"}.get(state_code, str(state_code)),
        "clk_hz": clk_hz,
        "ip_base": int(dm[M_IP_BASE]) if recognized else 0,
        "gap_ms": round(int(dm[M_GAP_CLK]) * 1000.0 / clk_hz, 1) if recognized else 0.0,
        "max_rounds": int(dm[M_MAX_ROUNDS]) if recognized else 0,
        "total_rounds": total,
        "pass_rounds": passed_n,
        "fail_rounds": failed_n,
        "last_round_failed": bool(last_mask),
        "last_dur_ms": round(int(dm[M_LAST_DUR_CLK]) * 1000.0 / clk_hz, 3) if recognized else 0.0,
        "max_noise_clk": int(dm[M_MAX_NOISE]) if recognized else 0,
        "tests": tests_out,
        "channels": chans_out,
        "first_fail": first_fail,
        "last_fail": last_fail,
        "passed": recognized and not st.err and total > 0 and failed_n == 0,
    }


def _fmt_fail_rec(rec: dict, ch_override: str = "") -> str:
    ch = ch_override or rec["channel"]
    return (
        f"Tur #{rec['round']} · [Hat: {ch}] · {rec['test_title']} · "
        f"{rec['reason']} (beklenen 0x{rec['expected']:08X}, okunan 0x{rec['got']:08X})"
    )


def diff_fail_events(prev: dict | None, cur: dict) -> list[str]:
    """İki PCS telemetri okuması arasındaki yeni hataları hat/kanal bilgisiyle log satırlarına dönüştürür."""
    ts = str(cur.get("timestamp") or "").split(" ")[-1] or time.strftime("%H:%M:%S")
    out: list[str] = []

    if cur.get("pcs_err") and (prev is None or not prev.get("pcs_err")):
        out.append(
            f"[{ts}] PCS HATA · {cur.get('pcs_err_text', '')} "
            f"(PC={cur.get('pcs_pc', 0)}, ERR_CODE={cur.get('pcs_err_code', 0)}, "
            f"ADDR=0x{cur.get('pcs_err_addr', 0):08X})"
        )

    if not cur.get("recognized"):
        return out

    total = int(cur.get("total_rounds", 0))
    fails = int(cur.get("fail_rounds", 0))
    ff = cur.get("first_fail")
    lf = cur.get("last_fail")

    if prev is None:
        if fails > 0:
            if ff:
                out.append(f"[{ts}] İlk hata · {_fmt_fail_rec(ff)}")
            if lf and lf != ff:
                out.append(f"[{ts}] Son hata · {_fmt_fail_rec(lf)}")
            if not ff and not lf:
                for x in cur.get("tests", []):
                    if x.get("fails", 0) > 0:
                        fch = ", ".join(x.get("fail_channels") or ()) or "—"
                        out.append(
                            f"[{ts}] Tur #{total} · [Hat: {fch}] · {x['title']} · "
                            f"{x['fails']}/{total} hata ({x.get('hint', '')})"
                        )
        return out

    prev_total = int(prev.get("total_rounds", 0))
    prev_fails = int(prev.get("fail_rounds", 0))
    if total <= prev_total or fails <= prev_fails:
        return out

    prev_t = {x["tid"]: int(x["fails"]) for x in prev.get("tests", [])}
    prev_c = {c["code"]: int(c["fails"]) for c in prev.get("channels", [])}
    changed_chans = [
        c["name"]
        for c in cur.get("channels", [])
        if int(c["fails"]) > prev_c.get(c["code"], 0)
    ]

    logged_any = False
    for x in cur.get("tests", []):
        dt = int(x["fails"]) - prev_t.get(x["tid"], 0)
        if dt <= 0:
            continue
        logged_any = True
        fch = list(x.get("fail_channels") or ()) or changed_chans
        ch_lbl = ", ".join(fch)
        if lf and lf.get("test_id") == x["tid"]:
            extra = f" (+{dt} tur)" if dt > 1 else ""
            out.append(f"[{ts}] {_fmt_fail_rec(lf, ch_lbl)}{extra} [toplam {x['fails']}/{total}]")
        else:
            hat_part = f"[Hat: {ch_lbl}] · " if ch_lbl else ""
            out.append(
                f"[{ts}] Tur #{total} · {hat_part}{x['title']} · +{dt} hata "
                f"({x.get('hint', '')}) [toplam {x['fails']}/{total}]"
            )

    if not logged_any:
        if lf:
            out.append(f"[{ts}] {_fmt_fail_rec(lf)} [hatalı tur {fails}/{total}]")
        else:
            hat_part = f"[Hat: {', '.join(changed_chans)}] · " if changed_chans else ""
            out.append(f"[{ts}] Tur #{total} · {hat_part}+{fails - prev_fails} hatalı tur [toplam {fails}/{total}]")
    return out


def report_text(t: dict) -> str:
    """PCS otonom test telemetrisini metin raporuna dönüştürür."""
    status = "PCS HATA" if t["pcs_err"] else (
        "GEÇTİ" if t["passed"] else ("KALDI" if t["fail_rounds"] else t["run_state"])
    )
    lines = [
        f"ARINC 429 Otonom Periyodik Test Raporu (AXIL Studio PCS) — {status}",
        f"Tarih     : {t['timestamp']}   PCS: 0x{t['pcs_base']:08X} ({t['pcs_state']}, PC={t['pcs_pc']}, "
        f"{t['imem_cnt']}/{t['imem_size']} komut)",
        f"IP        : 0x{t['ip_base']:08X}   Saat: {t['clk_hz'] / 1e6:g} MHz   Tur aralığı: {t['gap_ms']} ms   "
        f"Son tur süresi: {t['last_dur_ms']} ms",
        f"Turlar    : Toplam {t['total_rounds']} · Geçen {t['pass_rounds']} · Kalan {t['fail_rounds']}"
        + (f" / Hedef {t['max_rounds']}" if t["max_rounds"] else " (sürekli)"),
        f"Gürültü   : Maks. Bit Diagnostic glitch = {t['max_noise_clk']} clk",
        "=" * 78,
        "TEST BAZLI KALMA SAYAÇLARI:",
    ]
    for x in t["tests"]:
        st = "KALDI" if x["fails"] else "GEÇTİ"
        fch = x.get("fail_channels") or []
        hat = f"  [Hat: {', '.join(fch)}]" if fch else ""
        last = " [son turda kaldı]" if x["last_failed"] else ""
        lines.append(f"  [{st:5s}] {x['title']:52s}  Kalma: {x['fails']}/{t['total_rounds']}{hat}{last}")
    if t["channels"]:
        lines.append("-" * 78)
        lines.append("KANAL BAZLI KALMA SAYAÇLARI:")
        for ch in t["channels"]:
            lines.append(f"  {ch['name']:18s}: {ch['fails']} hata")
    if t["first_fail"]:
        ff = t["first_fail"]
        lines.append("-" * 78)
        lines.append(
            f"İLK HATA  : Tur #{ff['round']} · [Hat: {ff['channel']}] · {ff['test_title']}\n"
            f"            Neden: {ff['reason']}  (beklenen 0x{ff['expected']:08X}, okunan 0x{ff['got']:08X})"
        )
    if t.get("last_fail") and t["last_fail"] != t.get("first_fail"):
        lf = t["last_fail"]
        lines.append("-" * 78)
        lines.append(
            f"SON HATA  : Tur #{lf['round']} · [Hat: {lf['channel']}] · {lf['test_title']}\n"
            f"            Neden: {lf['reason']}  (beklenen 0x{lf['expected']:08X}, okunan 0x{lf['got']:08X})"
        )
    if t["pcs_err"]:
        lines.append("-" * 78)
        lines.append(f"PCS HATA  : {t['pcs_err_text']} (PC={t['pcs_err_pc']}, ADDR=0x{t['pcs_err_addr']:08X})")
    return "\n".join(lines) + "\n"


def report_json(t: dict) -> str:
    return json.dumps(t, ensure_ascii=False, indent=2)
