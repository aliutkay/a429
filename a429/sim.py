"""AXIL Studio olmadan test ve --sim modu için sahte AxilClient + arinc429_ip simülatörü."""
from __future__ import annotations

import random
import time

from . import ipmap
from .regs import RegMap, channel_prefix


def build_sim_ip_dict(num_rx: int = 1, has_tx: bool = True, has_txbit: bool = True, base: int = 0x40000000) -> dict:
    """Gerçek IP ile aynı (a429/ipmap.py) register haritasından Debug Bridge IP sözlüğü üretir."""
    ip = ipmap.to_ip_dict(name="arinc429_sim", base=base, num_rx=num_rx, has_tx=has_tx, has_txbit=has_txbit)
    ip["desc"] = "Simüle edilmiş " + ip["desc"]
    return ip


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
        self.models_line = False        # ARINC hattını modellemez: Test menüsü için --cosim kullanın
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

        self.rm = RegMap(self.ip)
        self._regs: dict[int, int] = {}
        self._name_by_off: dict[int, str] = {}
        self._off_by_name: dict[str, int] = {}
        for r in self.ip["registers"]:
            off = int(r["offset"], 0)
            self._regs[off] = int(r["reset"], 0)
            self._name_by_off[off] = r["name"]
            self._off_by_name[r["name"]] = off
        # Teşhis: kanal başına simüle hat durumu (LINE_HIGH, LINE_LOW); (1, 1) = ters bağlı alıcı
        self.sim_line: dict[str, tuple[int, int]] = {}

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

    # ---- mantıksal alan erişimi (gruplanmış register'larda alan, eski haritada register)
    def _get(self, name: str) -> int:
        r = self.rm.resolve(name)
        if r is None:
            return 0
        return self.rm.extract(name, self._regs.get(r[0].offset, 0))

    def _set(self, name: str, value: int):
        r = self.rm.resolve(name)
        if r is None:
            return
        reg, fe = r
        cur = self._regs.get(reg.offset, 0)
        self._regs[reg.offset] = (int(value) & 0xFFFFFFFF) if fe is None else fe.insert(cur, value)

    def _apply_tx_preset(self, sel: int):
        st = self.rm.field("TX_STATUS", "ACT_CFG")
        if st is not None and "TX_STATUS" in self._off_by_name:
            off = self._off_by_name["TX_STATUS"]
            self._regs[off] = st.insert(self._regs.get(off, 0), sel & 3)
        presets = {
            0: {"PULSE_DUR": 250, "NULL_DUR": 250, "GAP_DUR": 2000, "SLP": 1},     # 50 MHz High Speed
            1: {"PULSE_DUR": 2000, "NULL_DUR": 2000, "GAP_DUR": 16000, "SLP": 0},  # 50 MHz Low Speed
        }
        for s in ("PULSE_DUR", "NULL_DUR", "GAP_DUR", "SLP"):
            val = presets[sel][s] if sel in presets else self._get("TX_CUST_" + s)
            self._set("TX_ACT_" + s, val)

    def _apply_rx_preset(self, ch: str, sel: int):
        p = channel_prefix(ch)
        fe = self.rm.field(p + "STATUS", "ACT_CFG")
        if fe is not None and (p + "STATUS") in self._off_by_name:
            off = self._off_by_name[p + "STATUS"]
            self._regs[off] = fe.insert(self._regs.get(off, 0), sel & 3)
        presets = {
            0: {  # 50 MHz High Speed preset (a429_presets_pkg.vhd)
                "GLITCH_FILTER_SIZE": 20, "MIN_PULSE": 81, "MAX_PULSE": 408,
                "MIN_BIT": 463, "MAX_BIT": 539, "MAX_PULSE_ERR": 8,
                "MAX_NULL_ERR": 9, "MAX_GAP_ERR": 185, "PARITY_MODE": 1,
            },
            1: {  # 50 MHz Low Speed preset
                "GLITCH_FILTER_SIZE": 245, "MIN_PULSE": 980, "MAX_PULSE": 2915,
                "MIN_BIT": 3704, "MAX_BIT": 4306, "MAX_PULSE_ERR": 98,
                "MAX_NULL_ERR": 106, "MAX_GAP_ERR": 1481, "PARITY_MODE": 1,
            },
        }
        for s in ("GLITCH_FILTER_SIZE", "MIN_PULSE", "MAX_PULSE", "MIN_BIT", "MAX_BIT",
                  "MAX_PULSE_ERR", "MAX_NULL_ERR", "MAX_GAP_ERR", "PARITY_MODE"):
            val = presets[sel][s] if sel in presets else self._get(p + "CUST_" + s)
            self._set(p + "ACT_" + s, val)

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
            if suf in ("ERR_RD_TS_MSB", "ERR_RD_TS_LSB", "ERR_RD_INFO", "ERR_RD_DATA"):
                rec = sim.emem.get(sim.e_ptr, [0] * 5)
                if suf == "ERR_RD_DATA":
                    sim.e_ptr = (sim.e_ptr + 1) & 0xFF
                    return rec[4]
                if suf == "ERR_RD_INFO":
                    return (rec[2] & 0xFFFF) | ((rec[3] & 0xFFFF) << 16)
                return rec[0 if suf == "ERR_RD_TS_MSB" else 1]
            if suf in ("BIT_RD_PULSE", "BIT_RD_NULL"):
                widx, bno = (sim.b_ptr >> 5) & 0x7, sim.b_ptr & 0x1F
                rec = sim.bmem.get((widx, bno), [0] * 4)
                if suf == "BIT_RD_NULL":
                    sim.b_ptr = (sim.b_ptr + 1) & 0xFF
                    return (rec[2] & 0xFFFF) | ((rec[3] & 0xFFFF) << 16)
                return (rec[0] & 0xFFFF) | ((rec[1] & 0xFFFF) << 16)
            if suf == "STATUS":
                val = self._regs.get(off, 0)
                hi, lo = self.sim_line.get(ch, (0, 0))
                for fname, v in (("LINE_HIGH", hi), ("LINE_LOW", lo), ("SYNC_WAIT", int(hi and lo))):
                    fe = self.rm.field(name, fname)
                    if fe is not None and fe.name == fname:
                        val = fe.insert(val, v)
                return val
        return self._regs.get(off, 0) & 0xFFFFFFFF

    def write(self, offset=0, value=0, addr=None, quiet=False):
        off = self._to_off(offset, addr)
        v = int(value) & 0xFFFFFFFF
        name = self._name_by_off.get(off, "")
        if name == "TX_CFG":
            apply = self.rm.field("TX_CFG", "APPLY")
            self._regs[off] = v & ~apply.mask
            if apply.extract(v):
                self._apply_tx_preset(self._get("TX_CFG_SEL"))
            return
        if name == "TX_CTRL":
            sched = self.rm.field("TX_CTRL", "SCHED_EN")
            was_on = bool(sched.extract(self._regs.get(off, 0)))
            now_on = bool(sched.extract(v))
            if not was_on and now_on:
                self._sched_t0 = time.monotonic()
            elif was_on and not now_on and self._sched_t0 is not None:
                sent = max(1, min(10000, round((time.monotonic() - self._sched_t0) * 1000)))
                if "TX_SCHED_COUNT" in self._off_by_name and self._get("TX_SCHED_COUNT"):
                    sent = min(sent, self._get("TX_SCHED_COUNT"))     # 0: sınırsız, N: en fazla N Word
                self._sched_t0 = None
                self._set("TX_WORD_CNT", self._get("TX_WORD_CNT") + sent)
                if self._get("TB_CHK_CTRL") & 1:
                    self._set("TB_CHK_OK_CNT", self._get("TB_CHK_OK_CNT") + sent)
            self._regs[off] = v
            return
        if name == "TX_SEND_CMD" and (v & 1):
            self._set("TX_WORD_CNT", self._get("TX_WORD_CNT") + 1)
            if "TB" in self._channels and (self._get("TB_CHK_CTRL") & 1):
                self._set("TB_CHK_OK_CNT", self._get("TB_CHK_OK_CNT") + 1)
            return
        if name == "TB_CHK_CTRL":
            if v & 2:       # FIFO CLEAR darbesi
                self._set("TB_CHK_STATUS", 0)
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
            if name == p + "CFG":
                apply = self.rm.field(p + "CFG", "APPLY")
                self._regs[off] = v & ~apply.mask
                if apply.extract(v):
                    self._apply_rx_preset(ch, self._get(p + "CFG_SEL"))
                return
        if self.rm.regs.get(name) is not None and self.rm.regs[name].access == "RO":
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
