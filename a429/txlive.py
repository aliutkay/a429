"""TX canlı kontrol hesapları: ARINC 429 Word oluşturma, Parity ve Scheduler süreleri."""
from __future__ import annotations

OVERRIDE_CODES = {"Kapalı": 0, "HIGH": 1, "NULL": 2, "LOW": 3, "HIGH-Z": 4}


def default_tx_live():
    return dict(source="builder", label="310", sdi="0", data="00000", ssm="0", parity="Odd", word="00000000",
                send_mode="scheduler", delay_us="0", delay_unit="µs", gap_mode="period", period_us="1000", period_unit="µs",
                gap_us="0", gap_unit="µs", manual_period="100", manual_unit="ms")


TIME_UNITS = ["clk", "ns", "µs", "ms"]


def to_clk(value, unit, mhz):
    """Süreyi clock sayısına çevirir (ondalıklı)."""
    return {"clk": value, "ns": value * mhz / 1000, "µs": value * mhz, "ms": value * mhz * 1000}[unit]


def parity_bit(word, odd=True):
    """Bit 1–31'e göre Parity biti (bit 32)."""
    ones = bin(word & 0x7FFFFFFF).count("1")
    return int(ones % 2 == 0) if odd else int(ones % 2 == 1)


def build_word(label, sdi, data, ssm, odd=True):
    if not 0 <= label <= 0xFF:
        raise ValueError("Label 000–377 (octal) aralığında olmalı.")
    if not 0 <= sdi <= 3:
        raise ValueError("SDI 0–3 aralığında olmalı.")
    if not 0 <= data <= 0x7FFFF:
        raise ValueError("Data 19 bit olmalı (00000–7FFFF hex).")
    if not 0 <= ssm <= 3:
        raise ValueError("SSM 0–3 aralığında olmalı.")
    word = label | (sdi << 8) | (data << 10) | (ssm << 29)
    return word | (parity_bit(word, odd) << 31)


def parse_builder(cfg):
    """Word oluşturucu alanlarını sayıya çevirir: (label, sdi, data, ssm, odd)."""
    def num(text, base, name):
        try:
            return int(text.strip(), base)
        except ValueError:
            raise ValueError(f"{name} değeri geçersiz.") from None
    return (num(cfg["label"], 8, "Label"), num(cfg["sdi"], 10, "SDI"), num(cfg["data"], 16, "Data"),
            num(cfg["ssm"], 10, "SSM"), cfg["parity"] == "Odd")


def parse_hex_word(text):
    try:
        value = int(text.strip().replace(" ", ""), 16)
    except ValueError:
        raise ValueError("Word hex değeri geçersiz.") from None
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("Word 32 bit olmalı.")
    return value


def parse_bin_word(text):
    bits = text.replace(" ", "")
    if len(bits) != 32 or set(bits) - {"0", "1"}:
        raise ValueError("Binary değer tam 32 bit olmalı.")
    return int(bits, 2)


def fmt_binary(word):
    """Bit 32'den 1'e: Parity, SSM, Data, SDI, Label."""
    b = f"{word:032b}"
    return " ".join((b[0], b[1:3], b[3:22], b[22:24], b[24:]))


def word_fields_text(word):
    return (f"Label {word & 0xFF:03o} · SDI {(word >> 8) & 3} · Data {(word >> 10) & 0x7FFFF:05X} · "
            f"SSM {(word >> 29) & 3} · Parity {(word >> 31) & 1}")


def gap_from_period(period_us, tbit_us):
    """Interword gap = periyot − (32 Bit Word süresi + 4 Bit gap süresi). (gap_µs, word_µs, sabit_gap_µs)"""
    word_us, fixed_us = 32 * tbit_us, 4 * tbit_us
    return period_us - word_us - fixed_us, word_us, fixed_us
