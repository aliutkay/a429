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
    """Tek bir bit alanını yazar. PULSE alanına doğrudan, RW alanına read-modify-write uygular."""
    off = rm.offset(reg_name)
    fe = rm.field(reg_name, field_name)
    if fe is None:
        v = int(value) & 0xFFFFFFFF
        bus.write(off, v, quiet=quiet)
        _record_write(on_write, reg_name, off, v)
        return
    if fe.kind == "PULSE":
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
