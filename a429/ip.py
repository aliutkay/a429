"""ARINC 429 IP işlemleri (GUI'siz): RX Config gönderme, kanal okuma, TX yazma, reset.

Tüm erişimler AXIL Studio istemcisi (axil_client.AxilClient) veya aynı arayüzü sunan
SimClient üzerinden yapılır.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, asdict

from .regs import RegMap, RX_CONFIG_SPECS, channel_prefix

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

    writes: list[tuple[str, int, int]] = []
    writes.append((p + "CFG_SEL", rm.offset(p + "CFG_SEL"), 2))     # 2 = Custom
    for suffix, val in values.items():
        rname = p + suffix
        writes.append((rname, rm.offset(rname), int(val) & 0xFFFFFFFF))
    writes.append((p + "CFG_APPLY", rm.offset(p + "CFG_APPLY"), 1))

    bus.batch([("write", off, v) for _, off, v in writes], quiet=quiet)
    for rname, off, v in writes:
        _record_write(on_write, rname, off, v)

    if verify:
        check_regs = []
        for suffix, expected in values.items():
            act_name = p + "ACT_" + suffix[5:] if suffix.startswith("CUST_") else p + suffix
            rname = act_name if rm.has(act_name) else (p + suffix)
            check_regs.append((rname, rm.offset(rname), int(expected) & 0xFFFFFFFF))
        got = bus.batch([("read", off) for _, off, _ in check_regs], quiet=True)
        bad = []
        for (rname, _, exp), actual in zip(check_regs, got):
            if actual != exp:
                bad.append(f"{rname}: yazılan {exp}, okunan {actual}")
        if bad:
            if log:
                for b in bad:
                    log(f"  -> UYUŞMADI: {b}")
            raise IpError(f"RX Config geri okuma doğrulaması başarısız ({len(bad)} register uyuşmadı).")
        if log:
            log(f"[RX Config · {ch}] Geri okuma ile doğrulandı.")


def send_tx_config(bus, rm: RegMap, writes: list[tuple[str, int]], verify=True, quiet=False, log=None, on_write=None):
    """TX Config register'larını sırayla yazar ve RW / ACT_* değerlerini doğrular."""
    miss = rm.missing([r for r, _ in writes])
    if miss:
        raise IpError("TX Config için eksik register'lar: " + ", ".join(miss))
    if log:
        log(f"[TX Config] Gönderiliyor ({len(writes)} register)…")
    ops = []
    for rname, val in writes:
        off = rm.offset(rname)
        v = int(val) & 0xFFFFFFFF
        ops.append(("write", off, v))
    bus.batch(ops, quiet=quiet)
    for rname, val in writes:
        _record_write(on_write, rname, rm.offset(rname), val)

    if verify:
        check_list = []
        for rname, val in writes:
            entry = rm.get(rname)
            if entry is None or entry.is_pulse_only():
                continue
            if rname.startswith("TX_CUST_"):
                act = "TX_ACT_" + rname[8:]
                target = act if rm.has(act) else rname
            else:
                target = rname
            check_list.append((target, rm.offset(target), int(val) & 0xFFFFFFFF))
        if check_list:
            got = bus.batch([("read", off) for _, off, _ in check_list], quiet=True)
            bad = [f"{r}: yazılan {exp}, okunan {act}" for (r, _, exp), act in zip(check_list, got) if act != exp]
            if bad:
                if log:
                    for b in bad:
                        log(f"  -> UYUŞMADI: {b}")
                raise IpError(f"TX Config geri okuma doğrulaması başarısız ({len(bad)} register uyuşmadı).")
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

    ops = [("write", rm.offset(r), int(v) & 0xFFFFFFFF) for r, v in writes]
    bus.batch(ops, quiet=quiet)
    for r, v in writes:
        _record_write(on_write, r, rm.offset(r), v)

    if verify:
        check = []
        for r, v in writes:
            entry = rm.get(r)
            if entry is not None and not entry.is_pulse_only():
                check.append((r, rm.offset(r), int(v) & 0xFFFFFFFF))
        if check:
            got = bus.batch([("read", off) for _, off, _ in check], quiet=True)
            bad = [f"{r}: yazılan {exp}, okunan {act}" for (r, _, exp), act in zip(check, got) if act != exp]
            if bad:
                raise IpError("Geri okuma uyuşmadı: " + "; ".join(bad))


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
    names = [r for r in (p + "CTRL", p + "WORD_CNT", p + "ERR_CNT", p + "DROP_CNT", p + "LAST_WORD") if rm.has(r)]
    if not names:
        raise IpError(f"{ch} durum register'ları IP haritasında yok.")
    vals = bus.batch([("read", rm.offset(r)) for r in names], quiet=quiet)
    got = dict(zip(names, vals))
    ctrl = got.get(p + "CTRL", 0)
    en_fe = rm.field(p + "CTRL", "ENABLE")
    fr_fe = rm.field(p + "CTRL", "FREEZE")
    return {
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

    vals = bus.batch([("read", rm.offset(r)) for r in to_read], quiet=quiet)
    got = dict(zip(to_read, vals))

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

    vals = bus.batch([("read", rm.offset(r)) for r in to_read], quiet=quiet)
    got = dict(zip(to_read, vals))

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

        # --- Word RAM
        w_raddr = rm.offset(p + "WORD_RADDR")
        w_rds = [rm.offset(p + s) for s in ("WORD_RD_TS_MSB", "WORD_RD_TS_LSB", "WORD_RD_DATA", "WORD_RD_GAP", "WORD_RD_GAP_ERR")]
        for base_i in range(0, wn, BATCH_RECORDS):
            check_stop()
            chunk = list(range(base_i, min(wn, base_i + BATCH_RECORDS)))
            ops = []
            meta = []
            for i in chunk:
                addr = (wstart + wfull - 1 - i) % wdepth
                ops.append(("write", w_raddr, addr))
                for r in w_rds:
                    ops.append(("read", r))
                meta.append((wtot - 1 - i, addr))
            res = bus.batch(ops, quiet=quiet)
            for idx, (wno, addr) in enumerate(meta):
                sl = res[idx * 6 + 1 : idx * 6 + 6]
                words.append({"no": wno, "addr": addr, "w": list(sl)})
            done += len(chunk)
            prog(done, total, f"{ch} Word {done}/{wn}")

        # --- Error RAM
        e_raddr = rm.offset(p + "ERR_RADDR")
        e_rds = [rm.offset(p + s) for s in ("ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_CODE", "ERR_RD_ADDR", "ERR_RD_DATA")]
        for base_i in range(0, en, BATCH_RECORDS):
            check_stop()
            chunk = list(range(base_i, min(en, base_i + BATCH_RECORDS)))
            ops = []
            addrs = []
            for i in chunk:
                addr = (estart + efull - 1 - i) % edepth
                ops.append(("write", e_raddr, addr))
                for r in e_rds:
                    ops.append(("read", r))
                addrs.append(addr)
            res = bus.batch(ops, quiet=quiet)
            for idx, addr in enumerate(addrs):
                sl = res[idx * 6 + 1 : idx * 6 + 6]
                errors.append({"addr": addr, "w": list(sl)})
            done += len(chunk)
            prog(done, total, f"{ch} Error {len(errors)}/{en}")

        # --- Bit Diagnostic RAM
        b_raddr = rm.offset(p + "BIT_RADDR")
        b_rds = [rm.offset(p + s) for s in ("BIT_RD_PULSE", "BIT_RD_PULSE_ERR", "BIT_RD_NULL", "BIT_RD_NULL_ERR")]
        bit_fe = rm.field(p + "BIT_RADDR", "BIT")
        word_fe = rm.field(p + "BIT_RADDR", "WORD")
        bit_lsb = bit_fe.lsb if bit_fe else 0
        word_lsb = word_fe.lsb if word_fe else 8

        total_bits = bn * 32
        for base_kb in range(0, total_bits, BATCH_RECORDS * 2):
            check_stop()
            chunk = list(range(base_kb, min(total_bits, base_kb + BATCH_RECORDS * 2)))
            ops = []
            meta = []
            for kb in chunk:
                wno, bno = wtot - 1 - kb // 32, kb % 32
                widx = wno % bit_words
                addr_val = (widx << word_lsb) | (bno << bit_lsb)
                ops.append(("write", b_raddr, addr_val))
                for r in b_rds:
                    ops.append(("read", r))
                meta.append((wno, bno))
            res = bus.batch(ops, quiet=quiet)
            for idx, (wno, bno) in enumerate(meta):
                sl = res[idx * 5 + 1 : idx * 5 + 5]
                bits.append({"word": wno, "bit": bno, "w": list(sl)})
            done += len(chunk)
            last_w, last_b = meta[-1]
            prog(done, total, f"{ch} Bit Diagnostic: Word {last_w}, Bit {last_b + 1}")

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
