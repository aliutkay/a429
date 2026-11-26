"""AXIL Studio olmadan test ve --sim modu için sahte AxilClient + arinc429_ip simülatörü."""
from __future__ import annotations

import random
import time

from .regs import channel_prefix


def _reg(name: str, offset: int, access: str = "RW", reset: int = 0, fields=None, desc: str = "") -> dict:
    return {
        "name": name,
        "offset": f"0x{offset:08X}",
        "access": access,
        "reset": f"0x{reset:08X}",
        "desc": desc,
        "fields": fields or [],
    }


def _fld(name: str, lsb: int, width: int = 1, kind: str = "RW") -> dict:
    return {"name": name, "lsb": lsb, "width": width, "kind": kind}


def build_sim_ip_dict(num_rx: int = 1, has_tx: bool = True, has_txbit: bool = True, base: int = 0x40000000) -> dict:
    """DESIGN.md haritasına uygun örnek AXIL Studio IP sözlüğü üretir."""
    regs = [
        _reg("IP_ID", 0x0000, "RO", 0x41343239),
        _reg("IP_VERSION", 0x0004, "RO", 0x00010000),
        _reg("CAPS", 0x0008, "RO", 0, [
            _fld("NUM_RX", 0, 5, "RO"), _fld("TX", 8, 1, "RO"), _fld("TXBIT", 9, 1, "RO"),
            _fld("RX_TEST", 10, 1, "RO"), _fld("BITDIAG", 11, 1, "RO"),
        ]),
        _reg("CAPS_MEM", 0x000C, "RO", 0, [
            _fld("WORD_DEPTH_LOG2", 0, 8, "RO"), _fld("ERR_DEPTH_LOG2", 8, 8, "RO"),
            _fld("BITDIAG_WORDS_LOG2", 16, 8, "RO"),
        ]),
        _reg("CLK_HZ", 0x0010, "RO", 50_000_000),
        _reg("SOFT_RESET", 0x0020, "WO", 0, [
            _fld("ALL", 0, 1, "PULSE"), _fld("TX", 1, 1, "PULSE"), _fld("TXBIT", 2, 1, "PULSE"),
        ] + [_fld(f"RX{n}", 16 + n, 1, "PULSE") for n in range(num_rx)]),
        _reg("GLOBAL_FREEZE", 0x0024, "RW", 0),
        _reg("TS_CTRL", 0x0028, "RW", 1),
        _reg("TS_LSB", 0x002C, "RO", 0),
        _reg("TS_MSB", 0x0030, "RO", 0),
        _reg("ROUTE_CTRL", 0x0040, "RW", 0),
        _reg("ROUTE_TEST_MASK", 0x0044, "RW", 0),
    ]

    if has_tx:
        tx_base = 0x0400
        tx_defs = [
            ("TX_TRANSMITTER_EN", 0x00, "RW", 0, None),
            ("TX_MSG_SCHED_EN", 0x04, "RW", 0, None),
            ("TX_BUILDER_EN", 0x08, "RW", 0, None),
            ("TX_LABEL", 0x0C, "RW", 0, None),
            ("TX_SDI", 0x10, "RW", 0, None),
            ("TX_DATA", 0x14, "RW", 0, None),
            ("TX_SSM", 0x18, "RW", 0, None),
            ("TX_PARITY_TYPE", 0x1C, "RW", 1, None),
            ("TX_SCHED_EN", 0x20, "RW", 0, None),
            ("TX_INITIAL_DELAY", 0x24, "RW", 0, None),
            ("TX_INTER_WORD_GAP", 0x28, "RW", 1, None),
            ("TX_SEND_CMD", 0x2C, "WO", 0, [_fld("SEND", 0, 1, "PULSE")]),
            ("TX_EXT_DATA", 0x30, "RW", 0, None),
            ("TX_EXT_HIGH", 0x34, "RW", 0, None),
            ("TX_EXT_LOW", 0x38, "RW", 0, None),
            ("TX_CFG_SEL", 0x40, "RW", 0, None),
            ("TX_CFG_APPLY", 0x44, "WO", 0, [_fld("APPLY", 0, 1, "PULSE")]),
            ("TX_CUST_PULSE_DUR", 0x48, "RW", 0, None),
            ("TX_CUST_NULL_DUR", 0x4C, "RW", 0, None),
            ("TX_CUST_GAP_DUR", 0x50, "RW", 0, None),
            ("TX_CUST_SLP", 0x54, "RW", 0, None),
            ("TX_ACT_PULSE_DUR", 0x60, "RO", 0, None),
            ("TX_ACT_NULL_DUR", 0x64, "RO", 0, None),
            ("TX_ACT_GAP_DUR", 0x68, "RO", 0, None),
            ("TX_ACT_SLP", 0x6C, "RO", 0, None),
            ("TX_STATUS", 0x80, "RO", 0, [_fld("BUSY", 0, 1, "RO"), _fld("SCHED_ACTIVE", 1, 1, "RO"), _fld("ACT_CFG", 2, 2, "RO")]),
            ("TX_WORD_CNT", 0x84, "RO", 0, None),
        ]
        for name, off, acc, rst, flds in tx_defs:
            regs.append(_reg(name, tx_base + off, acc, rst, flds))

    def add_rx_page(prefix: str, page_base: int, has_checker: bool = False):
        ch_defs = [
            ("CTRL", 0x00, "RW", 0, [_fld("ENABLE", 0, 1, "RW"), _fld("FREEZE", 1, 1, "RW"), _fld("CLEAR", 2, 1, "PULSE")]),
            ("STATUS", 0x04, "RO", 0, [_fld("FROZEN", 4, 1, "RO"), _fld("WORD_WRAP", 5, 1, "RO"), _fld("ERR_WRAP", 6, 1, "RO"), _fld("ACT_CFG", 8, 2, "RO")]),
            ("CFG_SEL", 0x08, "RW", 0, None),
            ("CFG_APPLY", 0x0C, "WO", 0, [_fld("APPLY", 0, 1, "PULSE")]),
            ("CUST_GLITCH_FILTER_SIZE", 0x40, "RW", 0, None),
            ("CUST_MIN_PULSE", 0x44, "RW", 0, None),
            ("CUST_MAX_PULSE", 0x48, "RW", 0, None),
            ("CUST_MIN_BIT", 0x4C, "RW", 0, None),
            ("CUST_MAX_BIT", 0x50, "RW", 0, None),
            ("CUST_MAX_PULSE_ERR", 0x54, "RW", 0, None),
            ("CUST_MAX_NULL_ERR", 0x58, "RW", 0, None),
            ("CUST_MAX_GAP_ERR", 0x5C, "RW", 0, None),
            ("CUST_PARITY_MODE", 0x60, "RW", 1, None),
            ("ACT_GLITCH_FILTER_SIZE", 0xA0, "RO", 0, None),
            ("ACT_MIN_PULSE", 0xA4, "RO", 0, None),
            ("ACT_MAX_PULSE", 0xA8, "RO", 0, None),
            ("ACT_MIN_BIT", 0xAC, "RO", 0, None),
            ("ACT_MAX_BIT", 0xB0, "RO", 0, None),
            ("ACT_MAX_PULSE_ERR", 0xB4, "RO", 0, None),
            ("ACT_MAX_NULL_ERR", 0xB8, "RO", 0, None),
            ("ACT_MAX_GAP_ERR", 0xBC, "RO", 0, None),
            ("ACT_PARITY_MODE", 0xC0, "RO", 1, None),
            ("WORD_CNT", 0xE0, "RO", 0, None),
            ("ERR_CNT", 0xE4, "RO", 0, None),
            ("DROP_CNT", 0xE8, "RO", 0, None),
            ("LAST_WORD", 0xEC, "RO", 0, None),
            ("WORD_RADDR", 0x100, "RW", 0, None),
            ("WORD_RD_TS_MSB", 0x104, "RO", 0, None),
            ("WORD_RD_TS_LSB", 0x108, "RO", 0, None),
            ("WORD_RD_DATA", 0x10C, "RO", 0, None),
            ("WORD_RD_GAP", 0x110, "RO", 0, None),
            ("WORD_RD_GAP_ERR", 0x114, "RO", 0, None),
            ("ERR_RADDR", 0x120, "RW", 0, None),
            ("ERR_RD_TS_MSB", 0x124, "RO", 0, None),
            ("ERR_RD_TS_LSB", 0x128, "RO", 0, None),
            ("ERR_RD_CODE", 0x12C, "RO", 0, None),
            ("ERR_RD_ADDR", 0x130, "RO", 0, None),
            ("ERR_RD_DATA", 0x134, "RO", 0, None),
            ("BIT_RADDR", 0x140, "RW", 0, [_fld("BIT", 0, 5, "RW"), _fld("WORD", 8, 5, "RW")]),
            ("BIT_RD_PULSE", 0x144, "RO", 0, None),
            ("BIT_RD_PULSE_ERR", 0x148, "RO", 0, None),
            ("BIT_RD_NULL", 0x14C, "RO", 0, None),
            ("BIT_RD_NULL_ERR", 0x150, "RO", 0, None),
        ]
        if has_checker:
            ch_defs += [
                ("CHK_CTRL", 0x1C0, "RW", 0, [_fld("ENABLE", 0, 1, "RW"), _fld("CLEAR", 1, 1, "PULSE")]),
                ("CHK_TIMEOUT", 0x1C4, "RW", 0, None),
                ("CHK_OK_CNT", 0x1C8, "RO", 0, None),
                ("CHK_ERR_CNT", 0x1CC, "RO", 0, None),
                ("CHK_STATUS", 0x1D0, "RO", 0, [_fld("FIFO_LEVEL", 0, 4, "RO"), _fld("FIFO_OVF", 4, 1, "RO")]),
            ]
        for suf, off, acc, rst, flds in ch_defs:
            regs.append(_reg(prefix + suf, page_base + off, acc, rst, flds))

    if has_txbit:
        add_rx_page("TB_", 0x0800, has_checker=True)
    for n in range(num_rx):
        add_rx_page(f"RX{n}_", 0x4000 + n * 0x400, has_checker=False)

    return {
        "name": "arinc429_sim",
        "base": base,
        "panel": "arinc429",
        "desc": "Simüle edilmiş ARINC 429 IP (DESIGN.md haritası)",
        "registers": regs,
    }


class _SimChannel:
    def __init__(self, n_words: int, n_err: int, seed: int):
        rnd = random.Random(seed)
        self.wtot = n_words
        self.etot = n_err
        self.drop = 0
        self.w_ptr = 0
        self.e_ptr = 0
        self.b_ptr = 0
        self.wmem: dict[int, list[int]] = {}
        self.emem: dict[int, list[int]] = {}
        self.bmem: dict[tuple[int, int], list[int]] = {}
        ts = 1_000_000
        for n in range(n_words):
            lab = rnd.choice([0o310, 0o203, 0o206, 0o312])
            data = rnd.randrange(1 << 19)
            wd = lab | (rnd.randrange(4) << 8) | (data << 10) | (rnd.randrange(4) << 29)
            if bin(wd).count("1") % 2 == 0:
                wd |= 1 << 31
            gap = 4 * 500 + rnd.randrange(0, 3000)
            bits = []
            for b in range(32):
                p = 250 + rnd.randint(-3, 3)
                nl = 248 + rnd.randint(-3, 3)
                bits.append((p, rnd.randint(0, 2), nl, rnd.randint(0, 2)))
            self.wmem[n % 256] = [ts >> 32, ts & 0xFFFFFFFF, wd, gap, rnd.randint(0, 3)]
            for b, v in enumerate(bits):
                self.bmem[(n % 8, b)] = list(v)
            ts += gap + sum(x[0] + x[2] for x in bits)
        self.now = ts + 123_456
        for i in range(n_err):
            t = self.wmem[(n_words - n_err + i) % 256][1] + 77
            self.emem[i % 256] = [0, t, 1 << rnd.randrange(12), rnd.randrange(32), self.wmem[i % 256][2]]


class SimClient:
    """AxilClient arayüzünü taklit eden bellek içi simülatör."""

    def __init__(self, num_rx: int = 1, has_tx: bool = True, has_txbit: bool = True, seed: int = 1):
        self.ip = build_sim_ip_dict(num_rx=num_rx, has_tx=has_tx, has_txbit=has_txbit)
        self.connected = True
        self.port = "SIM"
        self.lang = "tr"
        self.theme = {}
        self.settings: dict = {}
        self.on_event = None
        self.locked = False
        self.bridge_logs: list[str] = []
        self.added_configs: list = []
        self._sched_t0: float | None = None

        self._regs: dict[int, int] = {}
        self._name_by_off: dict[int, str] = {}
        self._off_by_name: dict[str, int] = {}
        for r in self.ip["registers"]:
            off = int(r["offset"], 0)
            self._regs[off] = int(r["reset"], 0)
            self._name_by_off[off] = r["name"]
            self._off_by_name[r["name"]] = off

        caps = (num_rx & 0x1F) | ((1 if has_tx else 0) << 8) | ((1 if has_txbit else 0) << 9) | (1 << 11)
        self._regs[0x0008] = caps
        self._regs[0x000C] = (8) | (8 << 8) | (3 << 16)       # 256 / 256 / 8
        self._regs[0x0010] = 50_000_000

        self._channels: dict[str, _SimChannel] = {}
        if has_txbit:
            tb_sim = _SimChannel(12, 1, seed + 100)
            # Simüle edilmiş TX BIT hata kaydını anlamlı bir WORD_MISMATCH (bit 8) yap
            if 0 in tb_sim.emem:
                tb_sim.emem[0][2] = 1 << 8
            self._channels["TB"] = tb_sim
            if "TX_WORD_CNT" in self._off_by_name:
                self._regs[self._off_by_name["TX_WORD_CNT"]] = 12
            if "TB_CHK_CTRL" in self._off_by_name:
                self._regs[self._off_by_name["TB_CHK_CTRL"]] = 1
                self._regs[self._off_by_name["TB_CHK_TIMEOUT"]] = 50000
                self._regs[self._off_by_name["TB_CHK_OK_CNT"]] = 11
                self._regs[self._off_by_name["TB_CHK_ERR_CNT"]] = 1
                self._regs[self._off_by_name["TB_CHK_STATUS"]] = 0
        for n in range(num_rx):
            self._channels[f"RX{n}"] = _SimChannel(23 - n * 5, 3 + n, seed + n)
        self._apply_tx_preset(0)
        for ch in self._channels:
            self._apply_rx_preset(ch, 0)
        self._now = max((c.now for c in self._channels.values()), default=1_000_000)
        self._latched_msb = self._now >> 32

    def _apply_tx_preset(self, sel: int):
        st_off = self._off_by_name.get("TX_STATUS")
        if st_off is not None:
            self._regs[st_off] = (self._regs.get(st_off, 0) & ~0xC) | ((sel & 3) << 2)
        presets = {
            0: {"PULSE_DUR": 250, "NULL_DUR": 250, "GAP_DUR": 2000, "SLP": 1},     # 50 MHz High Speed
            1: {"PULSE_DUR": 2000, "NULL_DUR": 2000, "GAP_DUR": 16000, "SLP": 0},  # 50 MHz Low Speed
        }
        if sel in presets:
            for s, val in presets[sel].items():
                ao = self._off_by_name.get("TX_ACT_" + s)
                if ao is not None:
                    self._regs[ao] = val
        else:
            for s in ("PULSE_DUR", "NULL_DUR", "GAP_DUR", "SLP"):
                co, ao = self._off_by_name.get("TX_CUST_" + s), self._off_by_name.get("TX_ACT_" + s)
                if co is not None and ao is not None:
                    self._regs[ao] = self._regs.get(co, 0)

    def _apply_rx_preset(self, ch: str, sel: int):
        p = channel_prefix(ch)
        st_off = self._off_by_name.get(p + "STATUS")
        if st_off is not None:
            self._regs[st_off] = (self._regs.get(st_off, 0) & ~0x300) | ((sel & 3) << 8)
        presets = {
            0: {  # 50 MHz High Speed preset
                "GLITCH_FILTER_SIZE": 10, "MIN_PULSE": 150, "MAX_PULSE": 350,
                "MIN_BIT": 400, "MAX_BIT": 600, "MAX_PULSE_ERR": 50,
                "MAX_NULL_ERR": 50, "MAX_GAP_ERR": 200, "PARITY_MODE": 1,
            },
            1: {  # 50 MHz Low Speed preset
                "GLITCH_FILTER_SIZE": 80, "MIN_PULSE": 1200, "MAX_PULSE": 2800,
                "MIN_BIT": 3200, "MAX_BIT": 4800, "MAX_PULSE_ERR": 400,
                "MAX_NULL_ERR": 400, "MAX_GAP_ERR": 1600, "PARITY_MODE": 1,
            },
        }
        if sel in presets:
            for s, val in presets[sel].items():
                ao = self._off_by_name.get(p + "ACT_" + s)
                if ao is not None:
                    self._regs[ao] = val
        else:
            for s in (
                "GLITCH_FILTER_SIZE", "MIN_PULSE", "MAX_PULSE", "MIN_BIT", "MAX_BIT",
                "MAX_PULSE_ERR", "MAX_NULL_ERR", "MAX_GAP_ERR", "PARITY_MODE",
            ):
                co, ao = self._off_by_name.get(p + "CUST_" + s), self._off_by_name.get(p + "ACT_" + s)
                if co is not None and ao is not None:
                    self._regs[ao] = self._regs.get(co, 0)

    def _to_off(self, offset=0, addr=None) -> int:
        if addr is not None:
            return (int(addr) - int(self.ip["base"])) & 0xFFFFFFFF
        return int(offset)

    def read(self, offset=0, addr=None, quiet=False) -> int:
        off = self._to_off(offset, addr)
        name = self._name_by_off.get(off, "")
        if name == "TS_LSB":
            self._latched_msb = (self._now >> 32) & 0xFFFFFFFF
            return self._now & 0xFFFFFFFF
        if name == "TS_MSB":
            return self._latched_msb

        # Kanal okuma register'ları
        for ch, sim in self._channels.items():
            p = channel_prefix(ch)
            if not name.startswith(p):
                continue
            suf = name[len(p):]
            if suf == "WORD_CNT":
                return sim.wtot
            if suf == "ERR_CNT":
                return sim.etot
            if suf == "DROP_CNT":
                return sim.drop
            if suf == "LAST_WORD":
                return sim.wmem.get((sim.wtot - 1) % 256, [0, 0, 0, 0, 0])[2] if sim.wtot else 0
            if suf in ("WORD_RD_TS_MSB", "WORD_RD_TS_LSB", "WORD_RD_DATA", "WORD_RD_GAP", "WORD_RD_GAP_ERR"):
                idx = ("WORD_RD_TS_MSB", "WORD_RD_TS_LSB", "WORD_RD_DATA", "WORD_RD_GAP", "WORD_RD_GAP_ERR").index(suf)
                val = sim.wmem.get(sim.w_ptr, [0] * 5)[idx]
                if suf == "WORD_RD_GAP_ERR":
                    sim.w_ptr = (sim.w_ptr + 1) & 0xFF
                return val
            if suf in ("ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_CODE", "ERR_RD_ADDR", "ERR_RD_DATA"):
                idx = ("ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_CODE", "ERR_RD_ADDR", "ERR_RD_DATA").index(suf)
                val = sim.emem.get(sim.e_ptr, [0] * 5)[idx]
                if suf == "ERR_RD_DATA":
                    sim.e_ptr = (sim.e_ptr + 1) & 0xFF
                return val
            if suf in ("BIT_RD_PULSE", "BIT_RD_PULSE_ERR", "BIT_RD_NULL", "BIT_RD_NULL_ERR"):
                idx = ("BIT_RD_PULSE", "BIT_RD_PULSE_ERR", "BIT_RD_NULL", "BIT_RD_NULL_ERR").index(suf)
                widx, bno = (sim.b_ptr >> 5) & 0x7, sim.b_ptr & 0x1F
                val = sim.bmem.get((widx, bno), [0] * 4)[idx]
                if suf == "BIT_RD_NULL_ERR":
                    sim.b_ptr = (sim.b_ptr + 1) & 0xFF
                return val
        return self._regs.get(off, 0) & 0xFFFFFFFF

    def write(self, offset=0, value=0, addr=None, quiet=False):
        off = self._to_off(offset, addr)
        v = int(value) & 0xFFFFFFFF
        name = self._name_by_off.get(off, "")
        if name == "TX_CFG_APPLY" and (v & 1):
            sel = self._regs.get(self._off_by_name.get("TX_CFG_SEL", -1), 0) & 3
            self._apply_tx_preset(sel)
            return
        if name == "TX_SCHED_EN":
            was_on = bool(self._regs.get(off, 0) & 1)
            now_on = bool(v & 1)
            if not was_on and now_on:
                self._sched_t0 = time.monotonic()
            elif was_on and not now_on and self._sched_t0 is not None:
                sent = max(1, min(10000, round((time.monotonic() - self._sched_t0) * 1000)))
                self._sched_t0 = None
                cnt_off = self._off_by_name.get("TX_WORD_CNT")
                if cnt_off is not None:
                    self._regs[cnt_off] = (self._regs.get(cnt_off, 0) + sent) & 0xFFFFFFFF
                chk_off = self._off_by_name.get("TB_CHK_CTRL")
                ok_off = self._off_by_name.get("TB_CHK_OK_CNT")
                if chk_off is not None and ok_off is not None and (self._regs.get(chk_off, 0) & 1):
                    self._regs[ok_off] = (self._regs.get(ok_off, 0) + sent) & 0xFFFFFFFF
            self._regs[off] = v
            return
        if name == "TX_SEND_CMD" and (v & 1):
            cnt_off = self._off_by_name.get("TX_WORD_CNT")
            if cnt_off is not None:
                self._regs[cnt_off] = (self._regs.get(cnt_off, 0) + 1) & 0xFFFFFFFF
            if "TB" in self._channels:
                chk_off = self._off_by_name.get("TB_CHK_CTRL")
                if chk_off is not None and (self._regs.get(chk_off, 0) & 1):
                    ok_off = self._off_by_name.get("TB_CHK_OK_CNT")
                    if ok_off is not None:
                        self._regs[ok_off] = (self._regs.get(ok_off, 0) + 1) & 0xFFFFFFFF
            return
        if name == "TB_CHK_CTRL":
            if v & 2:       # FIFO CLEAR darbesi
                st_off = self._off_by_name.get("TB_CHK_STATUS")
                if st_off is not None:
                    self._regs[st_off] = 0
            self._regs[off] = v & ~2
            return
        if name == "SOFT_RESET":
            if v & 1:
                self._apply_tx_preset(0)
                for ch in self._channels:
                    self._apply_rx_preset(ch, 0)
            else:
                if v & 2:
                    self._apply_tx_preset(0)
                if (v & 4) and "TB" in self._channels:
                    self._apply_rx_preset("TB", 0)
                for ch in self._channels:
                    if ch.startswith("RX") and (v & (1 << (16 + int(ch[2:])))):
                        self._apply_rx_preset(ch, 0)
            return
        for ch, sim in self._channels.items():
            p = channel_prefix(ch)
            if name == p + "CTRL":
                if v & 4:           # CLEAR darbesi (kendiliğinden 0'a döner)
                    sim.wtot = 0
                    sim.etot = 0
                    sim.drop = 0
                    sim.w_ptr = 0; sim.e_ptr = 0; sim.b_ptr = 0
                    sim.wmem.clear(); sim.emem.clear(); sim.bmem.clear()
                self._regs[off] = v & ~4
                return
            if name == p + "WORD_RADDR":
                self._regs[off] = v & 0xFF
                sim.w_ptr = v & 0xFF
                return
            if name == p + "ERR_RADDR":
                self._regs[off] = v & 0xFF
                sim.e_ptr = v & 0xFF
                return
            if name == p + "BIT_RADDR":
                self._regs[off] = v
                sim.b_ptr = (((v >> 8) & 0x7) << 5) | (v & 0x1F)
                return
            if name == p + "CFG_APPLY" and (v & 1):
                sel = self._regs.get(self._off_by_name.get(p + "CFG_SEL", -1), 0) & 3
                self._apply_rx_preset(ch, sel)
                return
        self._regs[off] = v

    def batch(self, steps, quiet=False):
        out = []
        for st in steps:
            if isinstance(st, dict):
                if st["op"] == "read":
                    out.append(self.read(st.get("offset", 0), st.get("addr"), quiet=quiet))
                else:
                    self.write(st.get("offset", 0), st.get("value", 0), st.get("addr"), quiet=quiet)
                    out.append(None)
            elif st[0] == "read":
                out.append(self.read(st[1], quiet=quiet))
            else:
                self.write(st[1], st[2], quiet=quiet)
                out.append(None)
        return out

    def read_until(self, offset, mask, value, max_reads=256, addr=None, quiet=True):
        out = []
        for _ in range(max_reads):
            w = self.read(offset, addr=addr, quiet=quiet)
            out.append(w)
            if (w & mask) == value:
                break
        return out

    def lock(self):
        self.locked = True

    def unlock(self):
        self.locked = False

    def show_register(self, register=None):
        pass

    def add_config(self, rows):
        self.added_configs.append(list(rows))

    def status(self, text):
        pass

    def log(self, text):
        self.bridge_logs.append(str(text))

    def get_settings(self, ip=None):
        return dict(self.settings)

    def set_settings(self, ip=None, **values):
        self.settings.update(values)
        for k in [k for k, v in values.items() if v is None]:
            self.settings.pop(k, None)

    def close(self):
        pass
