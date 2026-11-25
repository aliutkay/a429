"""AXIL Studio IP register haritası çözümleyicisi (arinc429_ip).

Register ve alan adları DESIGN.md sözleşmesine göre sabit tanımlıdır; offset ve bit alanları
AXIL Studio'nun gönderdiği client.ip["registers"] listesinden adla bulunur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class MissingRegisterError(KeyError):
    """İstenen register IP haritasında bulunamadığında fırlatılır."""


def channel_prefix(ch: str) -> str:
    return "TB_" if ch == "TB" else f"{ch}_"


def channel_label(ch: str) -> str:
    return "TX BIT" if ch == "TB" else ch


# RX Config hesap değişkenleri → kanal register sonekleri (DESIGN.md §7.1)
# (görünen ad, register soneki, model.py cvars anahtarı, bit genişliği)
RX_CONFIG_SPECS = [
    ("Glitch Filter Size", "CUST_GLITCH_FILTER_SIZE", "glitch_filter_size", 16),
    ("Min Pulse Duration", "CUST_MIN_PULSE", "min_pulse", 16),
    ("Max Pulse Duration", "CUST_MAX_PULSE", "max_pulse", 16),
    ("Min Bit Duration", "CUST_MIN_BIT", "min_bit", 16),
    ("Max Bit Duration", "CUST_MAX_BIT", "max_bit", 16),
    ("Max Pulse Glitch Error", "CUST_MAX_PULSE_ERR", "max_pulse_glitch_error", 16),
    ("Max Null Glitch Error", "CUST_MAX_NULL_ERR", "max_null_glitch_error", 16),
    ("Max Gap Glitch Error", "CUST_MAX_GAP_ERR", "max_gap_glitch_error", 16),
]

# TX register görünen adları (DESIGN.md §6.1)
TX_REG_NAMES = {
    "TX_TRANSMITTER_EN": "Word Transmitter enable",
    "TX_MSG_SCHED_EN": "Message Scheduler modu",
    "TX_BUILDER_EN": "Word Builder enable",
    "TX_LABEL": "Label",
    "TX_SDI": "SDI",
    "TX_DATA": "Data",
    "TX_SSM": "SSM",
    "TX_PARITY_TYPE": "Parity tipi (1: Odd, 0: Even)",
    "TX_SCHED_EN": "Scheduler enable",
    "TX_INITIAL_DELAY": "Initial delay (clk)",
    "TX_INTER_WORD_GAP": "Inter word gap (clk)",
    "TX_SEND_CMD": "Tek gönderim tetiği (SEND_CMD)",
    "TX_EXT_DATA": "Hazır 32-bit Word (EXT_DATA)",
    "TX_EXT_HIGH": "Override ext_high",
    "TX_EXT_LOW": "Override ext_low",
    "TX_CFG_SEL": "TX Config seçimi (2: Custom)",
    "TX_CFG_APPLY": "TX Config uygula (CFG_APPLY)",
    "TX_CUST_PULSE_DUR": "Custom Pulse süresi (clk)",
    "TX_CUST_NULL_DUR": "Custom Null süresi (clk)",
    "TX_CUST_GAP_DUR": "Custom Word Gap süresi (clk)",
    "TX_CUST_SLP": "Custom SLP (1: 1.5 µs, 0: 10 µs)",
    "TX_ACT_PULSE_DUR": "Etkin Pulse süresi",
    "TX_ACT_NULL_DUR": "Etkin Null süresi",
    "TX_ACT_GAP_DUR": "Etkin Word Gap süresi",
    "TX_ACT_SLP": "Etkin SLP",
    "TX_STATUS": "TX durumu",
    "TX_WORD_CNT": "Gönderilen Word sayısı",
}

TX_CONFIG_ORDER = [
    "TX_TRANSMITTER_EN",
    "TX_MSG_SCHED_EN",
    "TX_BUILDER_EN",
    "TX_LABEL",
    "TX_SDI",
    "TX_DATA",
    "TX_SSM",
    "TX_PARITY_TYPE",
    "TX_INITIAL_DELAY",
    "TX_INTER_WORD_GAP",
    "TX_CFG_SEL",
    "TX_CUST_PULSE_DUR",
    "TX_CUST_NULL_DUR",
    "TX_CUST_GAP_DUR",
    "TX_CUST_SLP",
    "TX_CFG_APPLY",
    "TX_EXT_DATA",
    "TX_EXT_HIGH",
    "TX_EXT_LOW",
    "TX_SCHED_EN",
]

# PULSE (yazınca 1 clk darbe, geri okunup doğrulanmaz) register sonekleri / adları
PULSE_REGS = {"SOFT_RESET", "TX_SEND_CMD", "TX_CFG_APPLY"}
PULSE_SUFFIXES = ("_CFG_APPLY",)

# Kanal okuma için zorunlu register sonekleri
RX_READ_REQUIRED = [
    "CTRL",
    "WORD_CNT", "ERR_CNT",
    "WORD_RADDR", "WORD_RD_TS_MSB", "WORD_RD_TS_LSB", "WORD_RD_DATA", "WORD_RD_GAP", "WORD_RD_GAP_ERR",
    "ERR_RADDR", "ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_CODE", "ERR_RD_ADDR", "ERR_RD_DATA",
    "BIT_RADDR", "BIT_RD_PULSE", "BIT_RD_PULSE_ERR", "BIT_RD_NULL", "BIT_RD_NULL_ERR",
]

GLOBAL_READ_REQUIRED = ["TS_LSB", "TS_MSB"]

# Register haritasında bit alanları tek tek tanımlanmamışsa DESIGN.md varsayılan bit konumları
DEFAULT_FIELDS: dict[str, dict[str, tuple[int, int, str]]] = {
    "CTRL": {"ENABLE": (0, 1, "RW"), "FREEZE": (1, 1, "RW"), "CLEAR": (2, 1, "PULSE")},
    "STATUS": {"FROZEN": (4, 1, "RO"), "WORD_WRAP": (5, 1, "RO"), "ERR_WRAP": (6, 1, "RO"), "ACT_CFG": (8, 2, "RO")},
    "BIT_RADDR": {"BIT": (0, 5, "RW"), "WORD": (8, 5, "RW")},
    "TX_STATUS": {"BUSY": (0, 1, "RO"), "SCHED_ACTIVE": (1, 1, "RO"), "ACT_CFG": (2, 2, "RO")},
    "CAPS": {"NUM_RX": (0, 5, "RO"), "TX": (8, 1, "RO"), "TXBIT": (9, 1, "RO"), "RX_TEST": (10, 1, "RO"), "BITDIAG": (11, 1, "RO")},
    "CAPS_MEM": {"WORD_DEPTH_LOG2": (0, 8, "RO"), "ERR_DEPTH_LOG2": (8, 8, "RO"), "BITDIAG_WORDS_LOG2": (16, 8, "RO")},
    "SOFT_RESET": {"ALL": (0, 1, "PULSE"), "TX": (1, 1, "PULSE"), "TXBIT": (2, 1, "PULSE")},
}


@dataclass(frozen=True)
class FieldEntry:
    name: str
    lsb: int
    width: int = 1
    kind: str = "RW"

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.lsb

    def extract(self, word: int) -> int:
        return (word >> self.lsb) & ((1 << self.width) - 1)

    def insert(self, word: int, value: int) -> int:
        v = (int(value) & ((1 << self.width) - 1)) << self.lsb
        return (word & ~self.mask) | v


@dataclass
class RegEntry:
    name: str
    offset: int
    access: str = "RW"
    reset: int = 0
    desc: str = ""
    fields: dict[str, FieldEntry] = field(default_factory=dict)

    def is_pulse_only(self) -> bool:
        if self.name in PULSE_REGS or any(self.name.endswith(s) for s in PULSE_SUFFIXES):
            return True
        if self.fields and all(f.kind == "PULSE" for f in self.fields.values()):
            return True
        return self.access == "WO"


def _parse_int(v) -> int:
    if isinstance(v, int):
        return v
    return int(str(v).strip(), 0)


class RegMap:
    """AXIL Studio'dan gelen tek bir IP tanımının register haritası."""

    def __init__(self, ip: dict | None = None):
        self.ip = ip or {}
        self.name: str = self.ip.get("name", "")
        self.base: int = _parse_int(self.ip.get("base", 0)) if self.ip else 0
        self.regs: dict[str, RegEntry] = {}
        for r in self.ip.get("registers", []):
            fields = {}
            for f in r.get("fields", []):
                fe = FieldEntry(
                    name=str(f["name"]),
                    lsb=int(f.get("lsb", 0)),
                    width=int(f.get("width", 1)),
                    kind=str(f.get("kind", "") or r.get("access", "RW")).upper(),
                )
                fields[fe.name] = fe
            entry = RegEntry(
                name=str(r["name"]),
                offset=_parse_int(r["offset"]),
                access=str(r.get("access", "RW")).upper(),
                reset=_parse_int(r.get("reset", 0)),
                desc=str(r.get("desc", "")),
                fields=fields,
            )
            self.regs[entry.name] = entry

    @classmethod
    def empty(cls) -> "RegMap":
        return cls(None)

    def is_loaded(self) -> bool:
        return bool(self.regs)

    def has(self, name: str) -> bool:
        return name in self.regs

    def get(self, name: str) -> RegEntry | None:
        return self.regs.get(name)

    def offset(self, name: str) -> int:
        r = self.regs.get(name)
        if r is None:
            raise MissingRegisterError(f"Register IP haritasında yok: {name}")
        return r.offset

    def offset_hex(self, name: str) -> str:
        r = self.regs.get(name)
        return f"0x{r.offset:04X}" if r is not None else "—"

    def field(self, reg_name: str, field_name: str) -> FieldEntry | None:
        r = self.regs.get(reg_name)
        if r is not None and field_name in r.fields:
            return r.fields[field_name]
        # DESIGN.md varsayılan bit konumları (alanlar Studio'da ayrı girilmemişse)
        if reg_name == "SOFT_RESET":
            m = re.fullmatch(r"RX(\d+)", field_name)
            if m:
                return FieldEntry(field_name, 16 + int(m.group(1)), 1, "PULSE")
        key = reg_name
        if key not in DEFAULT_FIELDS:
            # RX0_CTRL -> CTRL, TB_BIT_RADDR -> BIT_RADDR
            m = re.match(r"^(?:RX\d+|TB)_(.+)$", reg_name)
            if m:
                key = m.group(1)
        spec = DEFAULT_FIELDS.get(key, {}).get(field_name)
        if spec is not None:
            return FieldEntry(field_name, spec[0], spec[1], spec[2])
        return None

    def channels(self) -> list[str]:
        """Haritada bulunan RX kanalları (sayısal sırada) + varsa TB."""
        rx_nums = []
        for name in self.regs:
            m = re.fullmatch(r"RX(\d+)_CTRL", name)
            if m:
                rx_nums.append(int(m.group(1)))
        out = [f"RX{n}" for n in sorted(set(rx_nums))]
        if "TB_CTRL" in self.regs:
            out.append("TB")
        return out or ["RX0"]

    def has_tx(self) -> bool:
        return "TX_TRANSMITTER_EN" in self.regs or "TX_CFG_SEL" in self.regs

    def missing(self, names) -> list[str]:
        return [n for n in names if n not in self.regs]

    def missing_for_rx_config(self, ch: str) -> list[str]:
        p = channel_prefix(ch)
        req = [p + "CFG_SEL", p + "CFG_APPLY"] + [p + s for _, s, _, _ in RX_CONFIG_SPECS]
        return self.missing(req)

    def missing_for_rx_read(self, ch: str) -> list[str]:
        p = channel_prefix(ch)
        req = GLOBAL_READ_REQUIRED + [p + s for s in RX_READ_REQUIRED]
        return self.missing(req)

    def missing_for_tx_config(self) -> list[str]:
        return self.missing(TX_CONFIG_ORDER)

    def missing_for_tx_live(self) -> list[str]:
        req = [
            "TX_TRANSMITTER_EN", "TX_MSG_SCHED_EN", "TX_BUILDER_EN",
            "TX_LABEL", "TX_SDI", "TX_DATA", "TX_SSM", "TX_PARITY_TYPE",
            "TX_SCHED_EN", "TX_INITIAL_DELAY", "TX_INTER_WORD_GAP",
            "TX_SEND_CMD", "TX_EXT_DATA", "TX_EXT_HIGH", "TX_EXT_LOW",
        ]
        return self.missing(req)

    def missing_for_reset(self) -> list[str]:
        return self.missing(["SOFT_RESET"])
