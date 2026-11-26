"""ARINC 429 IP işlemleri (GUI'siz): RX Config gönderme, kanal okuma, TX yazma, reset.

Tüm erişimler AXIL Studio istemcisi (axil_client.AxilClient) veya aynı arayüzü sunan
SimClient üzerinden yapılır.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, asdict

from . import ipmap
from .regs import RegMap, RX_CONFIG_SPECS, channel_label, channel_prefix

DEFAULT_OUT_DIR = os.path.join(os.path.expanduser("~"), "ARINC429_okumalar")
BATCH_RECORDS = 16
CFG_MODE_NAMES = {0: "High Speed (Preset)", 1: "Low Speed (Preset)", 2: "Custom"}


def native_dir(path: str) -> str:
    """Başka işletim sisteminde kaydedilmiş klasör yolunu varsayılana çevirir."""
    if not path:
        return DEFAULT_OUT_DIR
    if os.name == "nt":
        ok = bool(os.path.splitdrive(path)[0])
    else:
        ok = path.startswith("/") and "\\" not in path
    return path if ok else DEFAULT_OUT_DIR


@dataclass
class ReadSettings:
    read_word: str = "all"           # all | last | none
    read_word_n: int = 4
    read_error: str = "all"
    read_error_n: int = 4
    read_bit: str = "all"            # N: Bit Diagnostic verisi okunacak Word sayısı
    read_bit_n: int = 4
    out_dir: str = ""
    auto_txt: bool = True
    auto_write_log: bool = True
    verbose_bridge_log: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "ReadSettings":
        d = dict(d or {})
        fields = ReadSettings.__dataclass_fields__
        return ReadSettings(**{k: v for k, v in d.items() if k in fields})


class IpError(Exception):
    pass


def _record_write(on_write, reg_name: str, offset: int, value: int):
    if on_write:
        on_write(reg_name, offset, int(value) & 0xFFFFFFFF)


def plan_writes(rm: RegMap, writes, current: dict[str, int] | None = None) -> list[tuple[str, int, int]]:
    """Mantıksal yazmaları fiziksel register yazmalarına çevirir: [(register, offset, değer)].

    Ardışık aynı register'a giden alanlar tek yazmada birleşir; sıra korunur (ör. CUST alanları,
    sonra CFG.APPLY). Register'daki yazılmayan RW alanlar ``current`` değerinden korunur, PULSE
    alanları 0 yazılır (yalnızca istenen darbe gider).
    """
    current = dict(current or {})
    ops: list[tuple[str, int, int]] = []
    pend_reg, pend_val = None, 0
    for name, val in writes:
        r = rm.resolve(name)
        if r is None:
            raise IpError(f"Register IP haritasında yok: {name}")
        reg, fe = r
        if pend_reg is not None and reg.name != pend_reg.name:
            ops.append((pend_reg.name, pend_reg.offset, pend_val))
            current[pend_reg.name] = _clear_pulses(pend_reg, pend_val)
            pend_reg = None
        if pend_reg is None:
            pend_reg, pend_val = reg, _clear_pulses(reg, current.get(reg.name, reg.reset))
        pend_val = (int(val) & 0xFFFFFFFF) if fe is None else fe.insert(pend_val, val)
    if pend_reg is not None:
        ops.append((pend_reg.name, pend_reg.offset, pend_val))
    return ops


def bridge_rows(rm: RegMap, writes) -> list[tuple[str, int]]:
    """Debug Bridge config listesi için fiziksel register satırları [(register, 32-bit değer)].

    Alanlar reset değeri üzerine yerleştirilir; liste sırayla yazıldığında aynı sonucu verir.
    """
    return [(n, v) for n, _, v in plan_writes(rm, [(n, int(v)) for n, v in writes])]


def _clear_pulses(reg, value: int) -> int:
    for fe in reg.fields.values():
        if fe.kind == "PULSE":
            value &= ~fe.mask
    return value & 0xFFFFFFFF


def _needs_read(rm: RegMap, writes) -> list[str]:
    """Kısmi yazılan (RW alanı korunacak) fiziksel register'lar."""
    written: dict[str, set] = {}
    regs = {}
    for name, _ in writes:
        r = rm.resolve(name)
        if r is None:
            continue
        reg, fe = r
        regs[reg.name] = reg
        written.setdefault(reg.name, set()).add(None if fe is None else fe.name)
    out = []
    for rn, names in written.items():
        if None in names:
            continue
        keep = [f for f in regs[rn].fields.values() if f.kind == "RW" and f.name not in names]
        if keep:
            out.append(rn)
    return out


def write_fields(bus, rm: RegMap, writes, quiet=False, on_write=None) -> list[tuple[str, int, int]]:
    """Mantıksal adlarla yazar: [(ad, değer)] -> tek batch (gerekirse önce kısmi register'lar okunur)."""
    writes = [(n, int(v)) for n, v in writes]
    rd = _needs_read(rm, writes)
    current = {}
    if rd:
        vals = bus.batch([("read", rm.regs[n].offset) for n in rd], quiet=True)
        current = dict(zip(rd, (int(v or 0) for v in vals)))
    ops = plan_writes(rm, writes, current)
    bus.batch([("write", off, v) for _, off, v in ops], quiet=quiet)
    for rn, off, v in ops:
        _record_write(on_write, rn, off, v)
    return ops


def read_fields(bus, rm: RegMap, names, quiet=True) -> dict[str, int]:
    """Mantıksal adları okur (her fiziksel register bir kez): {ad: değer}."""
    names = list(names)
    phys: list[str] = []
    for n in names:
        r = rm.resolve(n)
        if r is None:
            raise IpError(f"Register IP haritasında yok: {n}")
        if r[0].name not in phys:
            phys.append(r[0].name)
    vals = bus.batch([("read", rm.regs[p].offset) for p in phys], quiet=quiet)
    got = dict(zip(phys, (int(v or 0) for v in vals)))
    return {n: rm.extract(n, got[rm.resolve(n)[0].name]) for n in names}


def verify_fields(bus, rm: RegMap, expected: list[tuple[str, int]], log=None, what="") -> None:
    """[(ad, beklenen)] geri okuma doğrulaması; uyuşmazlıkta IpError."""
    if not expected:
        return
    got = read_fields(bus, rm, [n for n, _ in expected], quiet=True)
    bad = []
    for n, exp in expected:
        fe = rm.resolve(n)[1]
        mask = 0xFFFFFFFF if fe is None else (1 << fe.width) - 1
        if got[n] != (int(exp) & mask):
            bad.append(f"{n} ({rm.location(n)}): yazılan {int(exp) & mask}, okunan {got[n]}")
    if bad:
        if log:
            for b in bad:
                log(f"  -> UYUŞMADI: {b}")
        raise IpError(f"{what} geri okuma doğrulaması başarısız ({len(bad)} alan uyuşmadı): " + "; ".join(bad[:3]))


class RecordReader:
    """RAM kaydı okuma planı: mantıksal alanlar -> fiziksel register'lar (offset sırasında).

    Son fiziksel register rd_strobe'ludur (okununca donanım pointer'ı +1 ilerler); gruplanmış
    haritada ERR_RD_INFO (CODE|ADDR) ve BIT_RD_PULSE/NULL (DUR|ERR) birer okumadır.
    """

    def __init__(self, rm: RegMap, names: list[str]):
        self.rm = rm
        self.names = names
        self.phys: list[str] = []
        for n in names:
            reg = rm.resolve(n)[0]
            if reg.name not in self.phys:
                self.phys.append(reg.name)
        self.offsets = [rm.regs[p].offset for p in self.phys]
        self.index = [self.phys.index(rm.resolve(n)[0].name) for n in names]

    def __len__(self):
        return len(self.phys)

    def decode(self, raw: list[int]) -> list[int]:
        return [self.rm.extract(n, raw[i]) for n, i in zip(self.names, self.index)]


def set_field(bus, rm: RegMap, reg_name: str, field_name: str, value: int, quiet=True, on_write=None):
    """Tek bir bit alanını yazar. Yalnız PULSE register'a doğrudan, RW alan içeren register'a read-modify-write uygular."""
    off = rm.offset(reg_name)
    entry = rm.get(reg_name)
    fe = rm.field(reg_name, field_name)
    if fe is None:
        v = int(value) & 0xFFFFFFFF
        bus.write(off, v, quiet=quiet)
        _record_write(on_write, reg_name, off, v)
        return
    if fe.kind == "PULSE" and (entry is None or entry.is_pulse_only()):
        v = fe.insert(0, value)
        bus.write(off, v, quiet=quiet)
        _record_write(on_write, reg_name, off, v)
        return
    cur = bus.read(off, quiet=quiet)
    nxt = fe.insert(cur, value)
    bus.write(off, nxt, quiet=quiet)
    _record_write(on_write, reg_name, off, nxt)


def read_caps(bus, rm: RegMap, quiet=True) -> dict:
    """CAPS / CAPS_MEM / CLK_HZ register'larını okur; haritada yoksa varsayılan döner."""
    info = {
        "wdepth": 256,
        "edepth": 256,
        "bit_words": 8,
        "num_rx": None,
        "has_tx": None,
        "has_txbit": None,
        "has_bitdiag": True,
        "clk_hz": None,
    }
    to_read = []
    for name in ("CAPS", "CAPS_MEM", "CLK_HZ"):
        if rm.has(name):
            to_read.append((name, rm.offset(name)))
    if not to_read:
        return info
    vals = bus.batch([("read", off) for _, off in to_read], quiet=quiet)
    got = dict(zip([n for n, _ in to_read], vals))
    if "CAPS" in got and got["CAPS"] is not None:
        c = got["CAPS"]
        info["num_rx"] = rm.field("CAPS", "NUM_RX").extract(c)
        info["has_tx"] = bool(rm.field("CAPS", "TX").extract(c))
        info["has_txbit"] = bool(rm.field("CAPS", "TXBIT").extract(c))
        info["has_bitdiag"] = bool(rm.field("CAPS", "BITDIAG").extract(c))
    if "CAPS_MEM" in got and got["CAPS_MEM"] is not None:
        cm = got["CAPS_MEM"]
        wlog = rm.field("CAPS_MEM", "WORD_DEPTH_LOG2").extract(cm)
        elog = rm.field("CAPS_MEM", "ERR_DEPTH_LOG2").extract(cm)
        blog = rm.field("CAPS_MEM", "BITDIAG_WORDS_LOG2").extract(cm)
        if 1 <= wlog <= 16:
            info["wdepth"] = 1 << wlog
        if 1 <= elog <= 16:
            info["edepth"] = 1 << elog
        if 1 <= blog <= 10:
            info["bit_words"] = 1 << blog
    if "CLK_HZ" in got and got["CLK_HZ"]:
        info["clk_hz"] = int(got["CLK_HZ"])
    return info


def send_rx_config(bus, rm: RegMap, ch: str, values: dict[str, int], verify=True, quiet=False, log=None, on_write=None):
    """Seçili RX (veya TB) kanalına Custom Config yazar ve ACT_* register'larından doğrular.

    values: {"CUST_GLITCH_FILTER_SIZE": int, ...}
    """
    miss = rm.missing_for_rx_config(ch)
    if miss:
        raise IpError("RX Config için eksik register'lar: " + ", ".join(miss))
    p = channel_prefix(ch)
    if log:
        log(f"[RX Config · {ch}] Gönderiliyor ({len(values)} parametre)…")

    writes = [(p + "CFG_SEL", 2)]                                     # 2 = Custom
    writes += [(p + suffix, int(val)) for suffix, val in values.items()]
    writes.append((p + "CFG_APPLY", 1))
    write_fields(bus, rm, writes, quiet=quiet, on_write=on_write)

    if verify:
        check = []
        for suffix, expected in values.items():
            act_name = p + "ACT_" + suffix[5:] if suffix.startswith("CUST_") else p + suffix
            check.append((act_name if rm.has(act_name) else (p + suffix), expected))
        verify_fields(bus, rm, check, log=log, what="RX Config")
        if log:
            log(f"[RX Config · {ch}] Geri okuma ile doğrulandı.")


def send_tx_config(bus, rm: RegMap, writes: list[tuple[str, int]], verify=True, quiet=False, log=None, on_write=None):
    """TX Config register'larını sırayla yazar ve RW / ACT_* değerlerini doğrular."""
    miss = rm.missing([r for r, _ in writes])
    if miss:
        raise IpError("TX Config için eksik register'lar: " + ", ".join(miss))
    if log:
        log(f"[TX Config] Gönderiliyor ({len(writes)} register)…")
    write_fields(bus, rm, writes, quiet=quiet, on_write=on_write)

    if verify:
        last: dict[str, int] = {}
        for rname, val in writes:
            if rm.is_pulse(rname):
                continue
            if rname.startswith("TX_CUST_"):
                act = "TX_ACT_" + rname[8:]
                rname = act if rm.has(act) else rname
            last[rname] = val
        if last:
            verify_fields(bus, rm, list(last.items()), log=log, what="TX Config")
            if log:
                log("[TX Config] Geri okuma ile doğrulandı.")


def tx_write(bus, rm: RegMap, writes: list[tuple[str, int]], verify=True, quiet=False, log=None, on_write=None):
    """TX canlı kontrol yazmaları: [(register_adı, değer)]."""
    miss = rm.missing([r for r, _ in writes])
    if miss:
        raise IpError("Eksik TX register'ları: " + ", ".join(miss))

    # SEND_CMD varsa önce TX_STATUS.BUSY = 0 bekle
    if any(r == "TX_SEND_CMD" for r, _ in writes) and rm.has("TX_STATUS"):
        busy_fe = rm.field("TX_STATUS", "BUSY")
        if busy_fe is not None:
            bus.read_until(rm.offset("TX_STATUS"), busy_fe.mask, 0, max_reads=64, quiet=True)

    write_fields(bus, rm, writes, quiet=quiet, on_write=on_write)

    if verify:
        last = {r: v for r, v in writes if not rm.is_pulse(r)}
        verify_fields(bus, rm, list(last.items()), what="TX")


def soft_reset(bus, rm: RegMap, target: str = "ALL", log=None, on_write=None):
    """SOFT_RESET register'ına ilgili hedef bitini (ALL, TX, TXBIT, RX0..) yazar."""
    if not rm.has("SOFT_RESET"):
        raise IpError("IP haritasında SOFT_RESET register'ı yok.")
    set_field(bus, rm, "SOFT_RESET", target, 1, quiet=False, on_write=on_write)
    if log:
        log(f"[Reset] SOFT_RESET.{target} darbesi gönderildi.")


def read_channel_status(bus, rm: RegMap, ch: str, quiet: bool = True) -> dict:
    """Seçili kanalın canlı sayaçlarını ve CTRL durumunu tek batch'te okur."""
    p = channel_prefix(ch)
    names = [r for r in (p + "CTRL", p + "STATUS", p + "WORD_CNT", p + "ERR_CNT", p + "DROP_CNT", p + "LAST_WORD")
             if rm.has(r)]
    if not names:
        raise IpError(f"{ch} durum register'ları IP haritasında yok.")
    vals = bus.batch([("read", rm.offset(r)) for r in names], quiet=quiet)
    got = dict(zip(names, vals))
    ctrl = got.get(p + "CTRL", 0)
    en_fe = rm.field(p + "CTRL", "ENABLE")
    fr_fe = rm.field(p + "CTRL", "FREEZE")
    st = got.get(p + "STATUS")
    diag = {}
    for key, fname in (("line_high", "LINE_HIGH"), ("line_low", "LINE_LOW"), ("sync_wait", "SYNC_WAIT")):
        fe = rm.field(p + "STATUS", fname) if st is not None else None
        diag[key] = bool(fe.extract(st)) if fe is not None and fe.name == fname else None
    return {
        **diag,
        "enable": bool(en_fe.extract(ctrl)) if en_fe else bool(ctrl & 1),
        "freeze": bool(fr_fe.extract(ctrl)) if fr_fe else bool(ctrl & 2),
        "word_cnt": got.get(p + "WORD_CNT"),
        "err_cnt": got.get(p + "ERR_CNT"),
        "drop_cnt": got.get(p + "DROP_CNT"),
        "last_word": got.get(p + "LAST_WORD"),
    }


def set_channel_enable(bus, rm: RegMap, ch: str, enable: bool, log=None, on_write=None):
    """Seçili kanalın CTRL.ENABLE bitini ayarlar."""
    p = channel_prefix(ch)
    set_field(bus, rm, p + "CTRL", "ENABLE", 1 if enable else 0, quiet=False, on_write=on_write)
    if log:
        log(f"[{ch}] Logger Enable = {1 if enable else 0}")


def clear_channel(bus, rm: RegMap, ch: str, log=None, on_write=None):
    """Seçili kanalın CTRL.CLEAR darbesini gönderir (sayaçlar ve RAM işaretçileri sıfırlanır)."""
    p = channel_prefix(ch)
    set_field(bus, rm, p + "CTRL", "CLEAR", 1, quiet=False, on_write=on_write)
    if log:
        log(f"[{ch}] Kanal sayaçları temizlendi (CTRL.CLEAR).")


def read_tx_bit_status(bus, rm: RegMap, quiet: bool = True) -> dict:
    """TX ve TX BIT (TB_) Checker durum ve sayaçlarını tek batch'te okur."""
    candidates = [
        "TX_STATUS", "TX_WORD_CNT",
        "TB_WORD_CNT", "TB_ERR_CNT",
        "TB_CHK_CTRL", "TB_CHK_TIMEOUT", "TB_CHK_OK_CNT", "TB_CHK_ERR_CNT", "TB_CHK_STATUS",
    ]
    names = [r for r in candidates if rm.has(r)]
    if not names:
        raise IpError("TX / TX BIT durum register'ları IP haritasında yok.")
    vals = bus.batch([("read", rm.offset(r)) for r in names], quiet=quiet)
    got = dict(zip(names, vals))
    tx_st = got.get("TX_STATUS", 0)
    chk_ctrl = got.get("TB_CHK_CTRL", 0)
    chk_st = got.get("TB_CHK_STATUS", 0)
    return {
        "tx_busy": bool(rm.field("TX_STATUS", "BUSY").extract(tx_st)) if "TX_STATUS" in got else None,
        "tx_sched_active": bool(rm.field("TX_STATUS", "SCHED_ACTIVE").extract(tx_st)) if "TX_STATUS" in got else None,
        "tx_word_cnt": got.get("TX_WORD_CNT"),
        "tb_word_cnt": got.get("TB_WORD_CNT"),
        "tb_err_cnt": got.get("TB_ERR_CNT"),
        "has_checker": "TB_CHK_CTRL" in got,
        "chk_en": bool(rm.field("TB_CHK_CTRL", "ENABLE").extract(chk_ctrl)) if "TB_CHK_CTRL" in got else False,
        "chk_timeout": got.get("TB_CHK_TIMEOUT"),
        "chk_ok_cnt": got.get("TB_CHK_OK_CNT"),
        "chk_err_cnt": got.get("TB_CHK_ERR_CNT"),
        "chk_fifo_level": rm.field("TB_CHK_STATUS", "FIFO_LEVEL").extract(chk_st) if "TB_CHK_STATUS" in got else None,
        "chk_fifo_ovf": bool(rm.field("TB_CHK_STATUS", "FIFO_OVF").extract(chk_st)) if "TB_CHK_STATUS" in got else False,
    }


def set_tx_checker(bus, rm: RegMap, enable: bool, timeout_clk: int, log=None, on_write=None):
    """TX BIT Checker timeout ve enable ayarlarını yazar."""
    if not rm.has("TB_CHK_CTRL"):
        raise IpError("IP haritasında TB_CHK_CTRL register'ı yok.")
    if rm.has("TB_CHK_TIMEOUT"):
        off = rm.offset("TB_CHK_TIMEOUT")
        v = int(timeout_clk) & 0xFFFFFFFF
        bus.write(off, v, quiet=False)
        _record_write(on_write, "TB_CHK_TIMEOUT", off, v)
    set_field(bus, rm, "TB_CHK_CTRL", "ENABLE", 1 if enable else 0, quiet=False, on_write=on_write)
    if log:
        log(f"[TX BIT] Checker Enable={1 if enable else 0}, Timeout={int(timeout_clk):,} clk")


def clear_tx_checker_fifo(bus, rm: RegMap, log=None, on_write=None):
    """TX BIT Checker FIFO'sunu temizler (TB_CHK_CTRL.CLEAR darbesi)."""
    if not rm.has("TB_CHK_CTRL"):
        raise IpError("IP haritasında TB_CHK_CTRL register'ı yok.")
    set_field(bus, rm, "TB_CHK_CTRL", "CLEAR", 1, quiet=False, on_write=on_write)
    if log:
        log("[TX BIT] Checker FIFO temizlendi.")


def read_rx_active_config(bus, rm: RegMap, ch: str, expected: dict[str, int] | None = None, quiet: bool = True) -> dict:
    """Seçili RX/TB kanalının karttaki aktif config'ini (STATUS.ACT_CFG + ACT_*) okur ve arayüzdeki değerlerle karşılaştırır."""
    p = channel_prefix(ch)
    to_read: list[str] = []
    status_reg = p + "STATUS"
    if rm.has(status_reg):
        to_read.append(status_reg)
    spec_regs: list[tuple[str, str, str]] = []   # (görünen ad, CUST soneki, okunacak register)
    for disp, cust_suf, _, _ in RX_CONFIG_SPECS:
        act_name = p + "ACT_" + cust_suf[5:]
        rname = act_name if rm.has(act_name) else (p + cust_suf)
        if rm.has(rname):
            spec_regs.append((disp, cust_suf, rname))
            to_read.append(rname)
    parity_reg = p + "ACT_PARITY_MODE"
    if rm.has(parity_reg):
        to_read.append(parity_reg)
    if not to_read:
        raise IpError(f"{ch} aktif config register'ları IP haritasında yok.")

    got = read_fields(bus, rm, to_read, quiet=quiet)

    mode = None
    if status_reg in got:
        fe = rm.field(status_reg, "ACT_CFG")
        mode = fe.extract(got[status_reg]) if fe else ((got[status_reg] >> 8) & 3)
    mode_name = CFG_MODE_NAMES.get(mode, f"Bilinmeyen ({mode})") if mode is not None else "Bilinmiyor"

    rows = []
    mismatch = 0
    for disp, cust_suf, rname in spec_regs:
        actual = got[rname]
        exp = expected.get(cust_suf) if expected else None
        match = (actual == exp) if exp is not None else None
        if match is False:
            mismatch += 1
        rows.append((disp, rname, actual, exp, match))
    if parity_reg in got:
        pnames = {0: "0 (Kapalı)", 1: "1 (Odd)", 2: "2 (Even)"}
        rows.append(("Parity Modu", parity_reg, pnames.get(got[parity_reg], str(got[parity_reg])), None, None))

    return {
        "channel": ch,
        "mode": mode,
        "mode_name": mode_name,
        "rows": rows,
        "cust_keys": [cust_suf for _, cust_suf, _ in spec_regs],
        "mismatch": mismatch,
        "all_match": mismatch == 0 and bool(spec_regs),
    }


def read_tx_active_config(bus, rm: RegMap, expected: dict[str, int] | None = None, quiet: bool = True) -> dict:
    """TX kanalının karttaki aktif config'ini (TX_STATUS.ACT_CFG + TX_ACT_*) okur ve arayüzle karşılaştırır."""
    specs = [
        ("Pulse süresi (clk)", "TX_CUST_PULSE_DUR", "TX_ACT_PULSE_DUR"),
        ("Null süresi (clk)", "TX_CUST_NULL_DUR", "TX_ACT_NULL_DUR"),
        ("Word Gap süresi (clk)", "TX_CUST_GAP_DUR", "TX_ACT_GAP_DUR"),
        ("SLP hız seçimi", "TX_CUST_SLP", "TX_ACT_SLP"),
    ]
    to_read: list[str] = []
    if rm.has("TX_STATUS"):
        to_read.append("TX_STATUS")
    present: list[tuple[str, str, str]] = []
    for disp, cust_name, act_name in specs:
        rname = act_name if rm.has(act_name) else cust_name
        if rm.has(rname):
            present.append((disp, cust_name, rname))
            to_read.append(rname)
    if not to_read:
        raise IpError("TX aktif config register'ları IP haritasında yok.")

    got = read_fields(bus, rm, to_read, quiet=quiet)

    mode = None
    if "TX_STATUS" in got:
        fe = rm.field("TX_STATUS", "ACT_CFG")
        mode = fe.extract(got["TX_STATUS"]) if fe else ((got["TX_STATUS"] >> 2) & 3)
    mode_name = CFG_MODE_NAMES.get(mode, f"Bilinmeyen ({mode})") if mode is not None else "Bilinmiyor"

    rows = []
    mismatch = 0
    for disp, cust_name, rname in present:
        actual = got[rname]
        exp = expected.get(cust_name) if expected else None
        match = (actual == exp) if exp is not None else None
        if match is False:
            mismatch += 1
        rows.append((disp, rname, actual, exp, match))

    return {
        "channel": "TX",
        "mode": mode,
        "mode_name": mode_name,
        "rows": rows,
        "cust_keys": [cust_name for _, cust_name, _ in present],
        "mismatch": mismatch,
        "all_match": mismatch == 0 and bool(present),
    }


def recompare_active_config(info: dict, expected: dict[str, int] | None) -> dict:
    """Önceden karttan okunmuş aktif config sonucunu güncel arayüz değerleriyle yeniden karşılaştırır."""
    cust_keys = info.get("cust_keys") or []
    new_rows = []
    mismatch = 0
    checked = 0
    for idx, (disp, rname, actual, _old_exp, _old_match) in enumerate(info.get("rows", [])):
        if idx < len(cust_keys):
            exp = expected.get(cust_keys[idx]) if expected else None
            match = (actual == exp) if exp is not None else None
            if match is not None:
                checked += 1
            if match is False:
                mismatch += 1
            new_rows.append((disp, rname, actual, exp, match))
        else:
            new_rows.append((disp, rname, actual, None, None))
    return {
        **info,
        "rows": new_rows,
        "mismatch": mismatch,
        "all_match": mismatch == 0 and checked > 0,
    }


def _limit(available: int, mode: str, n: int) -> int:
    if mode == "all":
        return available
    if mode == "none":
        return 0
    return min(available, max(0, int(n)))


def read_channel(
    bus,
    rm: RegMap,
    ch: str,
    opts: ReadSettings,
    progress=None,
    stop_flag: threading.Event | None = None,
    log=None,
    on_write=None,
) -> dict:
    """Seçili kanalın Word, Error ve Bit Diagnostic RAM'lerini okur.

    Okuma boyunca Debug Bridge kilitlenir (bus.lock) ve kanal FREEZE=1 tutulur.
    """
    miss = rm.missing_for_rx_read(ch)
    if miss:
        raise IpError(f"{ch} okuması için eksik register'lar: " + ", ".join(miss))

    p = channel_prefix(ch)
    quiet = not opts.verbose_bridge_log
    prog = progress or (lambda done, total, msg: None)
    stopped = lambda: stop_flag is not None and stop_flag.is_set()

    def check_stop():
        if stopped():
            raise IpError("Kullanıcı durdurdu.")

    bus.lock()
    frozen = False
    try:
        if log:
            log(f"[RX Okuma · {ch}] Başlıyor…")
        set_field(bus, rm, p + "CTRL", "FREEZE", 1, quiet=quiet, on_write=on_write)
        frozen = True

        caps = read_caps(bus, rm, quiet=True)
        wdepth, edepth, bit_words = caps["wdepth"], caps["edepth"], caps["bit_words"]

        head_regs = [p + "WORD_CNT", p + "ERR_CNT", "TS_LSB", "TS_MSB"]
        has_drop = rm.has(p + "DROP_CNT")
        if has_drop:
            head_regs.append(p + "DROP_CNT")
        hvals = bus.batch([("read", rm.offset(r)) for r in head_regs], quiet=quiet)
        wtot, etot, lsb, msb = hvals[0], hvals[1], hvals[2], hvals[3]
        drop_cnt = hvals[4] if has_drop else None

        wfull = min(wtot, wdepth)
        wstart = wtot % wdepth if wtot > wdepth else 0
        efull = min(etot, edepth)
        estart = etot % edepth if etot > edepth else 0

        wn = _limit(wfull, opts.read_word, opts.read_word_n)
        en = _limit(efull, opts.read_error, opts.read_error_n)
        bn = _limit(min(wtot, max(0, bit_words - 1)), opts.read_bit, opts.read_bit_n) if caps["has_bitdiag"] else 0

        total = max(1, wn + en + bn * 32)
        done = 0
        words, errors, bits = [], [], []

        # --- Word RAM (1 kez başlangıç WORD_RADDR yazılır, WORD_RD_GAP_ERR rd_strobe ile +1 ilerler)
        w_raddr = rm.offset(p + "WORD_RADDR")
        w_rec = RecordReader(rm, [p + s for s in ("WORD_RD_TS_MSB", "WORD_RD_TS_LSB", "WORD_RD_DATA", "WORD_RD_GAP", "WORD_RD_GAP_ERR")])
        if wn > 0:
            first_waddr = (wstart + wfull - wn) % wdepth
            bus.write(w_raddr, first_waddr, quiet=quiet)
            k = len(w_rec)
            for base_j in range(0, wn, BATCH_RECORDS):
                check_stop()
                chunk = list(range(base_j, min(wn, base_j + BATCH_RECORDS)))
                ops = [("read", r) for _ in chunk for r in w_rec.offsets]
                res = bus.batch(ops, quiet=quiet)
                for idx, j in enumerate(chunk):
                    wno = wtot - wn + j
                    addr = (first_waddr + j) % wdepth
                    words.append({"no": wno, "addr": addr, "w": w_rec.decode(res[idx * k : idx * k + k])})
                done += len(chunk)
                prog(done, total, f"{ch} Word {done}/{wn}")
            words.reverse()

        # --- Error RAM (1 kez başlangıç ERR_RADDR yazılır, ERR_RD_DATA rd_strobe ile +1 ilerler)
        e_raddr = rm.offset(p + "ERR_RADDR")
        e_rec = RecordReader(rm, [p + s for s in ("ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_CODE", "ERR_RD_ADDR", "ERR_RD_DATA")])
        if en > 0:
            first_eaddr = (estart + efull - en) % edepth
            bus.write(e_raddr, first_eaddr, quiet=quiet)
            k = len(e_rec)
            for base_j in range(0, en, BATCH_RECORDS):
                check_stop()
                chunk = list(range(base_j, min(en, base_j + BATCH_RECORDS)))
                ops = [("read", r) for _ in chunk for r in e_rec.offsets]
                res = bus.batch(ops, quiet=quiet)
                for idx, j in enumerate(chunk):
                    addr = (first_eaddr + j) % edepth
                    errors.append({"addr": addr, "w": e_rec.decode(res[idx * k : idx * k + k])})
                done += len(chunk)
                prog(done, total, f"{ch} Error {len(errors)}/{en}")
            errors.reverse()

        # --- Bit Diagnostic RAM (1 kez başlangıç BIT_RADDR yazılır, BIT_RD_NULL_ERR rd_strobe ile +1 ilerler)
        b_raddr = rm.offset(p + "BIT_RADDR")
        b_rec = RecordReader(rm, [p + s for s in ("BIT_RD_PULSE", "BIT_RD_PULSE_ERR", "BIT_RD_NULL", "BIT_RD_NULL_ERR")])
        bit_fe = rm.field(p + "BIT_RADDR", "BIT")
        word_fe = rm.field(p + "BIT_RADDR", "WORD")
        bit_lsb = bit_fe.lsb if bit_fe else 0
        word_lsb = word_fe.lsb if word_fe else 8

        total_bits = bn * 32
        if total_bits > 0:
            first_wno = wtot - bn
            first_widx = first_wno % bit_words
            bus.write(b_raddr, (first_widx << word_lsb) | (0 << bit_lsb), quiet=quiet)
            raw_bits = []
            k = len(b_rec)
            for base_kb in range(0, total_bits, BATCH_RECORDS * 2):
                check_stop()
                chunk = list(range(base_kb, min(total_bits, base_kb + BATCH_RECORDS * 2)))
                ops = [("read", r) for _ in chunk for r in b_rec.offsets]
                res = bus.batch(ops, quiet=quiet)
                for idx, kb in enumerate(chunk):
                    wno, bno = first_wno + kb // 32, kb % 32
                    raw_bits.append({"word": wno, "bit": bno, "w": b_rec.decode(res[idx * k : idx * k + k])})
                done += len(chunk)
                last_b = raw_bits[-1]
                prog(done, total, f"{ch} Bit Diagnostic: Word {last_b['word']}, Bit {last_b['bit'] + 1}")
            # En yeni Word önce, her Word içinde bit 0..31 sırasıyla
            for wi in range(bn - 1, -1, -1):
                bits.extend(raw_bits[wi * 32 : (wi + 1) * 32])

        wend, eend = bus.batch([("read", rm.offset(p + "WORD_CNT")), ("read", rm.offset(p + "ERR_CNT"))], quiet=quiet)
        if wend != wtot or eend != etot:
            if log:
                log(f"UYARI: Okuma sırasında sayaç değişti (Word {wtot} → {wend}, Error {etot} → {eend}).")
        if log:
            log(f"[RX Okuma · {ch}] Tamamlandı: {wn} Word, {en} Error, {bn} Word Bit Diagnostic.")

        summary = {
            "total_word_cnt": wtot,
            "total_error_cnt": etot,
            "ts_msb": msb,
            "ts_lsb": lsb,
            "extra": [],
            "wcnt_end": wend,
            "ecnt_end": eend,
            "read_scope": {"word": opts.read_word, "error": opts.read_error, "bit": opts.read_bit},
        }
        if drop_cnt is not None:
            summary["drop_cnt"] = drop_cnt
        return {
            "summary": summary,
            "words": words,
            "errors": errors,
            "bits": bits,
            "channel": ch,
            "ip": {"name": rm.name, "base": rm.base},
            "wdepth": wdepth,
            "edepth": edepth,
            "bit_words": bit_words,
        }
    finally:
        if frozen:
            try:
                set_field(bus, rm, p + "CTRL", "FREEZE", 0, quiet=True, on_write=on_write)
            except Exception as e:
                if log:
                    log(f"UYARI: {ch} FREEZE kapatılamadı: {e}")
        try:
            bus.unlock()
        except Exception:
            pass


# =====================================================================================
# IP durum kontrolü (sağlık): RX/TB'nin sessizce hiçbir şey kaydetmemesine yol açan ayarlar
# ve hat sorunları. Her bulgu: {"level": ok|info|warn|error, "area", "title", "detail", "fix"}
# "fix" varsa apply_fix(bus, rm, fix) ile tek tıkla düzeltilir.
# =====================================================================================
LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2, "ok": 3}
FIX_TEXT = {
    "enable": "Logger'ı aç (CTRL.ENABLE=1)",
    "unfreeze": "Freeze'i kaldır (CTRL.FREEZE=0)",
    "global_unfreeze": "GLOBAL_FREEZE=0",
    "ts_enable": "Timestamp'i aç (TS_CTRL.ENABLE=1)",
    "tx_transmitter": "Word Transmitter'ı aç (TX_TRANSMITTER_EN=1, override kapalı)",
    "tb_enable_for_chk": "TX BIT logger'ını aç (TB_CTRL.ENABLE=1)",
}


def _finding(level, area, title, detail="", fix=None):
    return {"level": level, "area": area, "title": title, "detail": detail, "fix": fix}


def check_ip(bus, rm: RegMap, clk_hz: int | None = None, line_samples: int = 16, quiet: bool = True) -> dict:
    """IP'yi uygulamanın beklentisine göre kontrol eder; bulgu listesi ve özet döner."""
    F: list[dict] = []

    def rd(names):
        names = [n for n in names if rm.has(n)]
        return read_fields(bus, rm, names, quiet=quiet) if names else {}

    g = rd(["IP_ID", "IP_VERSION", "CLK_HZ", "GLOBAL_FREEZE", "TS_CTRL"])
    if "IP_ID" in g and g["IP_ID"] != ipmap.IP_ID_WORD:
        F.append(_finding("error", "IP", f"IP kimliği beklenmiyor: 0x{g['IP_ID']:08X} ('A429' = 0x41343239)",
                          "Debug Bridge'deki IP base adresi yanlış olabilir ya da bu bir ARINC 429 IP'si değil."))
    if "IP_VERSION" in g:
        v = g["IP_VERSION"]
        hw = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
        hw_s = "%d.%d.%d" % hw
        if hw[0] != ipmap.IP_VERSION[0]:
            F.append(_finding("warn", "IP", f"IP sürümü {hw_s}, uygulama {ipmap.IP_VERSION_STR} haritası için",
                              "Karttaki bitstream ile AXIL Studio'daki register haritası aynı sürümden olmalı. "
                              + ("Uygulama eski (gruplanmamış) haritayla uyumluluk modunda çalışıyor."
                                 if not rm.grouped() else "Kartı yeni bitstream ile güncelleyin.")))
        else:
            F.append(_finding("ok", "IP", f"IP sürümü {hw_s}"))
    if clk_hz and "CLK_HZ" in g and g["CLK_HZ"] and g["CLK_HZ"] != int(clk_hz):
        F.append(_finding("warn", "IP", f"IP saati {g['CLK_HZ'] / 1e6:g} MHz, Config sekmesi {clk_hz / 1e6:g} MHz",
                          "Hesaplanan clk değerleri karttaki saatle uyuşmaz; Config sekmesindeki saat değerini düzeltin."))
    if g.get("GLOBAL_FREEZE"):
        F.append(_finding("warn", "IP", "GLOBAL_FREEZE=1: tüm kanallar donduruldu",
                          "Gelen Word ve hatalar RAM'e yazılmaz, yalnızca DROP_CNT artar.", ("global_unfreeze",)))
    if "TS_CTRL" in g:
        fe = rm.field("TS_CTRL", "ENABLE")
        if fe is not None and not fe.extract(g["TS_CTRL"]):
            F.append(_finding("warn", "IP", "Timestamp sayacı kapalı (TS_CTRL.ENABLE=0)",
                              "Kayıtların zaman damgası ilerlemez.", ("ts_enable",)))

    # ---- TX
    tx = rd(["TX_TRANSMITTER_EN", "TX_EXT_HIGH", "TX_EXT_LOW", "TX_ACT_PULSE_DUR", "TX_ACT_NULL_DUR", "TX_STATUS"])
    tx_bit = None
    if tx:
        if "TX_ACT_PULSE_DUR" in tx and "TX_ACT_NULL_DUR" in tx:
            tx_bit = tx["TX_ACT_PULSE_DUR"] + tx["TX_ACT_NULL_DUR"]
        if tx.get("TX_TRANSMITTER_EN") == 0:
            lines = {(0, 0): "NULL", (1, 0): "HIGH", (0, 1): "LOW", (1, 1): "HIGH-Z"}
            ln = lines.get((tx.get("TX_EXT_HIGH", 0), tx.get("TX_EXT_LOW", 0)), "?")
            F.append(_finding("info", "TX", f"TX hat override modunda (hat sabit {ln})",
                              "TX_TRANSMITTER_EN=0 iken Word gönderilmez; hat EXT_HIGH/EXT_LOW ile sürülür.",
                              ("tx_transmitter",)))

    # ---- Kanallar
    for ch in rm.channels():
        p = channel_prefix(ch)
        lab = channel_label(ch)
        if not rm.has(p + "CTRL"):
            continue
        c = rd([p + "CTRL", p + "WORD_CNT", p + "ERR_CNT", p + "DROP_CNT",
                p + "ACT_MIN_BIT", p + "ACT_MAX_BIT"])
        ctrl = c.get(p + "CTRL", 0)
        en = rm.field(p + "CTRL", "ENABLE").extract(ctrl)
        fr = rm.field(p + "CTRL", "FREEZE").extract(ctrl)
        if not en:
            F.append(_finding("error" if ch != "TB" else "warn", lab,
                              "Logger kapalı (CTRL.ENABLE=0): Word ve hata KAYDEDİLMEZ",
                              "Hatta veri olsa bile WORD_CNT / ERR_CNT artmaz. Reset sonrası varsayılan kapalıdır.",
                              ("enable", ch)))
        if fr:
            F.append(_finding("warn", lab, "Kanal donduruldu (CTRL.FREEZE=1)",
                              "Gelen kayıtlar RAM'e yazılmaz, DROP_CNT artar.", ("unfreeze", ch)))
        if c.get(p + "DROP_CNT"):
            F.append(_finding("info", lab, f"{c[p + 'DROP_CNT']:,} kayıt freeze sırasında atıldı (DROP_CNT)"))

        # Hat teşhisi: STATUS.LINE_HIGH/LINE_LOW/SYNC_WAIT örneklemesi (IP 2.x)
        st_fe = {n: rm.field(p + "STATUS", n) for n in ("LINE_HIGH", "LINE_LOW", "SYNC_WAIT")}
        if all(fe is not None and fe.name == n for n, fe in st_fe.items()):
            off = rm.offset(p + "STATUS")
            samples = bus.batch([("read", off)] * max(1, line_samples), quiet=True)
            states = [(st_fe["LINE_HIGH"].extract(s), st_fe["LINE_LOW"].extract(s)) for s in samples]
            waits = [st_fe["SYNC_WAIT"].extract(s) for s in samples]
            n11 = states.count((1, 1))
            active = sum(1 for s in states if s in ((1, 0), (0, 1)))
            if n11 == len(states):
                F.append(_finding("error", lab, "Hat sürekli 11 (HIGH ve LOW aynı anda 1)",
                                  "Alıcı çıkışları ters (aktif-düşük) / pull-up ile 1'e çekili / alıcı beslemesi yok. "
                                  "Decoder 4 bit temiz NULL bekler ve hiçbir şey kaydetmez (SYNC_WAIT=1)."))
            elif all(waits):
                F.append(_finding("warn", lab, "Decoder hat senkronu bekliyor (STATUS.SYNC_WAIT=1)",
                                  "Word'ler arasında en az 4 bit süresi temiz NULL (00) görülmedi: sürekli aktivite, "
                                  "11 durumu ya da çok kısa gap."))
            elif n11:
                F.append(_finding("warn", lab, f"Hatta 11 durumu görüldü ({n11}/{len(states)} örnek)",
                                  "Alıcı çıkışlarında çakışma: bağlantı / test pinleri kontrol edilmeli."))
            elif not active and not c.get(p + "WORD_CNT") and en:
                F.append(_finding("info", lab, "Hatta aktivite görülmedi (anlık örnekleme, 00)",
                                  "Kaynak gönderim yapmıyor olabilir ya da rx_high/rx_low pinleri bağlı değil "
                                  "(HDL Designer'da bağlanmamış port '0' kalır)."))
            else:
                F.append(_finding("ok", lab, "Hat durumu normal"))

        # Hız uyumu (TB kendi TX'ini dinler; RX için bilgi)
        if tx_bit and (p + "ACT_MIN_BIT") in c and (p + "ACT_MAX_BIT") in c:
            lo, hi = c[p + "ACT_MIN_BIT"], c[p + "ACT_MAX_BIT"]
            if lo and hi and not (lo <= tx_bit <= hi):
                F.append(_finding("warn" if ch == "TB" else "info", lab,
                                  f"TX bit süresi {tx_bit} clk, {lab} kabul aralığı {lo}–{hi} clk",
                                  "TX ve RX farklı hız config'inde (HS/LS) olabilir; bu durumda her bit hata olur."))
        if en and not fr and c.get(p + "ERR_CNT"):
            F.append(_finding("info", lab, f"{c[p + 'ERR_CNT']:,} hata kaydı var",
                              "Ayrıntılar için RX Verilerini Oku → Error RAM."))
        if en and not fr and c.get(p + "WORD_CNT"):
            F.append(_finding("ok", lab, f"{c[p + 'WORD_CNT']:,} Word alındı"))

    if rm.has("TB_CHK_CTRL") and rm.has("TB_CTRL"):
        t = rd(["TB_CHK_CTRL", "TB_CTRL"])
        if rm.field("TB_CHK_CTRL", "ENABLE").extract(t["TB_CHK_CTRL"]) and \
                not rm.field("TB_CTRL", "ENABLE").extract(t["TB_CTRL"]):
            F.append(_finding("warn", "TX BIT", "Checker açık ama TX BIT logger kapalı",
                              "Checker yankıyı görür ama Word/hata kaydı tutulmaz.", ("tb_enable_for_chk",)))

    F.sort(key=lambda f: LEVEL_ORDER[f["level"]])
    counts = {lv: sum(1 for f in F if f["level"] == lv) for lv in LEVEL_ORDER}
    worst = next((lv for lv in ("error", "warn", "info") if counts[lv]), "ok")
    return {"findings": F, "counts": counts, "worst": worst}


def apply_fix(bus, rm: RegMap, fix: tuple, log=None, on_write=None):
    """check_ip bulgusundaki düzeltmeyi uygular."""
    kind = fix[0]
    if kind == "enable":
        set_channel_enable(bus, rm, fix[1], True, log=log, on_write=on_write)
    elif kind == "unfreeze":
        set_field(bus, rm, channel_prefix(fix[1]) + "CTRL", "FREEZE", 0, quiet=False, on_write=on_write)
    elif kind == "global_unfreeze":
        write_fields(bus, rm, [("GLOBAL_FREEZE", 0)], on_write=on_write)
    elif kind == "ts_enable":
        set_field(bus, rm, "TS_CTRL", "ENABLE", 1, quiet=False, on_write=on_write)
    elif kind == "tx_transmitter":
        write_fields(bus, rm, [("TX_EXT_HIGH", 0), ("TX_EXT_LOW", 0), ("TX_TRANSMITTER_EN", 1)], on_write=on_write)
    elif kind == "tb_enable_for_chk":
        set_channel_enable(bus, rm, "TB", True, log=log, on_write=on_write)
    else:
        raise IpError(f"Bilinmeyen düzeltme: {kind}")
    if log:
        log(f"[IP Durumu] Düzeltildi: {FIX_TEXT.get(kind, kind)}" + (f" ({fix[1]})" if len(fix) > 1 else ""))
