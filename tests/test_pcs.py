"""AXIL Studio PCS (cmd_seq v2.0) otonom periyodik IP 2.1.0 loopback test doğrulaması."""
from __future__ import annotations

import json
import pytest

from a429 import ipmap, pcs_test
from a429.regs import RegMap
from a429.selftest import odd_parity
from a429.txlive import build_word

M32 = 0xFFFFFFFF


class FakeIp21:
    """ARINC 429 IP 2.1.0 davranışsal donanım modeli (hata enjeksiyonlu, loopback)."""

    def __init__(self, base: int = 0x00010000, num_rx: int = 2, has_txbit: bool = True, clk_hz: int = 50_000_000):
        self.base = base
        self.clk_hz = clk_hz
        self.ip_dict = ipmap.to_ip_dict(num_rx=num_rx, has_tx=True, has_txbit=has_txbit, clk_hz=clk_hz)
        self.rm = RegMap(self.ip_dict)
        self.rx_chans = [f"RX{i}" for i in range(num_rx)]
        self.chans = self.rx_chans + (["TB"] if has_txbit else [])
        self._regs: dict[int, int] = {}
        self._err_ram: dict[str, list[tuple[int, int]]] = {}
        self._err_ptr: dict[str, int] = {}
        self._bit_ram: dict[str, list[list[tuple[int, int, int, int]]]] = {}
        self._bit_ptr: dict[str, int] = {}
        self._tx_speed = "HS"
        self._rx_speed: dict[str, str] = {}
        self._tb_fifo: list[int] = []
        self._tb_ovf = False

        # Donanım hata enjeksiyon anahtarları
        self.fault_bad_id = False
        self.fault_line_stuck11: set[str] = set()
        self.fault_swapped: set[str] = set()
        self.fault_open: set[str] = set()
        self.fault_bitflip: set[str] = set()
        self.fault_drop_burst: set[str] = set()
        self.fault_ignore_parity = False
        self.fault_ignore_gap = False
        self.fault_bad_pulse: set[str] = set()
        self.fault_noise_clk: dict[str, int] = {}
        self.fault_ignore_freeze = False

        self._reset_all(hard=True)

    def _reset_all(self, hard: bool = False):
        keep = {}
        if not hard and self._regs:
            # SOFT_RESET çekirdeği sıfırlar, AXI4-Lite RW register'larını (arinc429_axil.v) sıfırlamaz
            for off in (pcs_test.OFF_TX_INIT_DLY, pcs_test.OFF_TX_IWG):
                if off in self._regs:
                    keep[off] = self._regs[off]
        self._regs = {r.offset: r.reset for r in self.rm.regs.values()}
        self._regs.update(keep)
        self._tx_speed = "HS"
        self._set_tx_act("HS")
        self._rx_speed = {ch: "HS" for ch in self.chans}
        for ch in self.chans:
            self._set_rx_act(ch, "HS")
        self._err_ram = {ch: [] for ch in self.chans}
        self._err_ptr = {ch: 0 for ch in self.chans}
        self._bit_ram = {ch: [[] for _ in range(8)] for ch in self.chans}
        self._bit_ptr = {ch: 0 for ch in self.chans}
        self._tb_fifo = []
        self._tb_ovf = False
        self._update_tb_status()
        self._update_line_status()

    def _update_tb_status(self):
        if self.rm.has("TB_CHK_STATUS"):
            self._regs[pcs_test.TB_CHK_STATUS] = (len(self._tb_fifo) & 0xF) | (0x10 if self._tb_ovf else 0)

    def _set_tx_act(self, spd: str):
        p = 250 if spd == "HS" else 2000
        g = 2000 if spd == "HS" else 16000
        self._regs[self.rm.offset("TX_ACT_TIMING")] = (p << 16) | p
        self._regs[self.rm.offset("TX_ACT_GAP_DUR")] = g
        self._regs[self.rm.offset("TX_ACT_SLP")] = 1 if spd == "HS" else 0

    def _set_rx_act(self, ch: str, spd: str):
        pre = "TB_" if ch == "TB" else ch + "_"
        if spd == "HS":
            self._regs[self.rm.offset(pre + "ACT_PULSE")] = (325 << 16) | 175
            self._regs[self.rm.offset(pre + "ACT_BIT")] = (550 << 16) | 450
        else:
            self._regs[self.rm.offset(pre + "ACT_PULSE")] = (2600 << 16) | 1400
            self._regs[self.rm.offset(pre + "ACT_BIT")] = (4400 << 16) | 3600

    def _update_line_status(self):
        tx_ctrl = self._regs.get(self.rm.offset("TX_CTRL"), 0)
        tx_en = bool(tx_ctrl & 1)
        line = self._regs.get(self.rm.offset("TX_EXT_LINE"), 0) & 3
        h, lo = (0, 0) if tx_en else (line & 1, (line >> 1) & 1)
        for ch in self.chans:
            pre = "TB_" if ch == "TB" else ch + "_"
            off = self.rm.offset(pre + "STATUS")
            st = self._regs.get(off, 0) & ~0x7000
            if ch in self.fault_line_stuck11:
                ch_h, ch_lo = 1, 1
            elif ch in self.fault_open:
                ch_h, ch_lo = 0, 0
            elif ch in self.fault_swapped:
                ch_h, ch_lo = lo, h
            else:
                ch_h, ch_lo = h, lo
            st |= (ch_h << 12) | (ch_lo << 13)
            self._regs[off] = st

    def _deliver(self, words: list[int], gap_viol: bool = False):
        self._regs[self.rm.offset("TX_WORD_CNT")] = (self._regs[self.rm.offset("TX_WORD_CNT")] + len(words)) & M32
        gfreeze = bool(self._regs.get(self.rm.offset("GLOBAL_FREEZE"), 0) & 1)
        tb_chk_en = bool(self._regs.get(self.rm.offset("TB_CHK_CTRL"), 0) & 1) if self.rm.has("TB_CHK_CTRL") else False

        for w_idx, wd_orig in enumerate(words):
            if "TB" in self.chans and tb_chk_en:
                if len(self._tb_fifo) < 4:
                    self._tb_fifo.append(wd_orig)
                else:
                    self._tb_ovf = True
                self._update_tb_status()

            for ch in self.chans:
                pre = "TB_" if ch == "TB" else ch + "_"
                ctrl = self._regs.get(self.rm.offset(pre + "CTRL"), 0)
                if not (ctrl & 1):
                    # Logger kapalıyken decoder arka planda çalışmaya ve TB_CHK'yi beslemeye devam eder
                    if ch == "TB" and tb_chk_en and self._tb_fifo:
                        exp = self._tb_fifo.pop(0)
                        if wd_orig == exp:
                            self._regs[self.rm.offset("TB_CHK_OK_CNT")] += 1
                        else:
                            self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1
                        self._update_tb_status()
                    continue
                if ch in self.fault_open or ch in self.fault_line_stuck11:
                    if ch == "TB" and tb_chk_en:
                        self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1
                    continue
                if ((ctrl & 2) or gfreeze) and not self.fault_ignore_freeze:
                    self._regs[self.rm.offset(pre + "DROP_CNT")] += 1
                    if ch == "TB" and tb_chk_en and self._tb_fifo:
                        exp = self._tb_fifo.pop(0)
                        if wd_orig == exp:
                            self._regs[self.rm.offset("TB_CHK_OK_CNT")] += 1
                        else:
                            self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1
                        self._update_tb_status()
                    continue

                wd = wd_orig ^ (M32 if ch in self.fault_swapped else 0)
                if ch in self.fault_bitflip:
                    wd ^= 0x00000100

                # Hız uyuşmazlığı
                rspd = self._rx_speed[ch]
                if self._tx_speed != rspd:
                    if self._tx_speed == "LS" and rspd == "HS":
                        self._push_err(ch, pcs_test.ERR_PULSE_STUCK, wd)
                        if ch == "TB" and tb_chk_en and self._tb_fifo:
                            self._tb_fifo.pop(0)
                            self._update_tb_status()
                    continue

                # Gap ihlali (gerçek decoder: ilk 2 Word arasında 1 kez ERR_GAP_VIOL üretir,
                # kalan Word'lerde ST_ERR_RECOVERY'de bekler -> TB_CHK FIFO'dan yalnızca 1 kayıt düşer)
                if gap_viol and not self.fault_ignore_gap:
                    if w_idx == 1:
                        self._push_err(ch, pcs_test.ERR_GAP_VIOL, wd)
                        if ch == "TB" and tb_chk_en and self._tb_fifo:
                            self._tb_fifo.pop(0)
                            self._update_tb_status()
                    continue

                # Odd parity
                if (bin(wd).count("1") % 2 == 0) and not self.fault_ignore_parity:
                    self._push_err(ch, pcs_test.ERR_PARITY, wd)
                    if ch == "TB" and tb_chk_en and self._tb_fifo:
                        self._tb_fifo.pop(0)
                        self._update_tb_status()
                    continue

                # Geçerli Word kabul
                wcnt_off = self.rm.offset(pre + "WORD_CNT")
                widx = self._regs[wcnt_off] & 7
                self._regs[wcnt_off] = (self._regs[wcnt_off] + 1) & M32
                self._regs[self.rm.offset(pre + "LAST_WORD")] = wd

                p_dur = (400 if ch in self.fault_bad_pulse else 250) if rspd == "HS" else 2000
                n_dur = 250 if rspd == "HS" else 2000
                noise = self.fault_noise_clk.get(ch, 0)
                self._bit_ram[ch][widx] = [(p_dur, noise if b == 5 else 0, n_dur, 0) for b in range(32)]

                if ch == "TB" and tb_chk_en:
                    if self._tb_fifo:
                        exp = self._tb_fifo.pop(0)
                        if wd == exp:
                            self._regs[self.rm.offset("TB_CHK_OK_CNT")] += 1
                        else:
                            self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1
                    else:
                        self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1
                    self._update_tb_status()

    def _push_err(self, ch: str, code: int, data: int):
        pre = "TB_" if ch == "TB" else ch + "_"
        self._err_ram[ch].append((code & 0xFFFF, data & M32))
        self._regs[self.rm.offset(pre + "ERR_CNT")] = len(self._err_ram[ch])

    def _build_word_from_reg(self) -> int:
        w = self._regs.get(self.rm.offset("TX_WORD"), 0)
        return build_word(w & 0xFF, (w >> 8) & 3, (w >> 10) & 0x7FFFF, (w >> 29) & 3, odd=bool((w >> 31) & 1))

    def read(self, addr: int) -> tuple[int, int]:
        off = (addr - self.base) & 0xFFFF
        if off == 0x0000 and self.fault_bad_id:
            return 0xDEADBEEF, 0
        # Error / Bit RAM read side-effects
        for ch in self.chans:
            cbase = 0x0800 if ch == "TB" else 0x4000 + int(ch[2:]) * 0x400
            if off == cbase + pcs_test.CH_ERR_RD_INFO:
                lst = self._err_ram[ch]
                ptr = self._err_ptr[ch]
                code = lst[ptr][0] if 0 <= ptr < len(lst) else 0
                return code, 0
            if off == cbase + pcs_test.CH_ERR_RD_DATA:
                lst = self._err_ram[ch]
                ptr = self._err_ptr[ch]
                data = lst[ptr][1] if 0 <= ptr < len(lst) else 0
                self._err_ptr[ch] = (ptr + 1) & 0xFF
                return data, 0
            if off == cbase + pcs_test.CH_BIT_RD_PULSE:
                widx, bidx = (self._bit_ptr[ch] >> 5) & 7, self._bit_ptr[ch] & 31
                rec = self._bit_ram[ch][widx]
                if not rec:
                    return 0, 0
                pd, pe, _, _ = rec[bidx]
                return ((pe & 0xFFFF) << 16) | (pd & 0xFFFF), 0
            if off == cbase + pcs_test.CH_BIT_RD_NULL:
                widx, bidx = (self._bit_ptr[ch] >> 5) & 7, self._bit_ptr[ch] & 31
                rec = self._bit_ram[ch][widx]
                self._bit_ptr[ch] = (self._bit_ptr[ch] + 1) & 0xFF
                if not rec:
                    return 0, 0
                _, _, nd, ne = rec[bidx]
                return ((ne & 0xFFFF) << 16) | (nd & 0xFFFF), 0
        return self._regs.get(off, 0), 0

    def write(self, addr: int, val: int) -> int:
        off = (addr - self.base) & 0xFFFF
        val &= M32
        if off == pcs_test.OFF_SOFT_RESET and (val & 1):
            self._reset_all(hard=False)
            return 0
        self._regs[off] = val

        if off in (pcs_test.OFF_TX_CTRL, pcs_test.OFF_TX_EXT_LINE):
            self._update_line_status()
            # Scheduler start (SCHED_EN & MSG_SCHED_EN & TRANSMITTER_EN)
            if off == pcs_test.OFF_TX_CTRL and (val & 0x0B) == 0x0B:
                n = self._regs.get(pcs_test.OFF_TX_SCHED_CNT, 0) or 1
                wd = self._regs.get(pcs_test.OFF_TX_EXT_DATA, 0)
                iwg = max(1, self._regs.get(pcs_test.OFF_TX_IWG, 1))
                act_gap = self._regs.get(self.rm.offset("TX_ACT_GAP_DUR"), 2000)
                gap_viol = (self._regs.get(pcs_test.OFF_TX_ACT_TIM, 0) != 0 and (act_gap + iwg) < 1500)
                send_list = [wd] * n
                if self.fault_drop_burst and not gap_viol:
                    # 1 Word düşürerek burst kaybını simüle et
                    orig_open = set(self.fault_open)
                    self._deliver(send_list[:-1], gap_viol=gap_viol)
                    self.fault_open |= self.fault_drop_burst
                    self._deliver(send_list[-1:], gap_viol=gap_viol)
                    self.fault_open = orig_open
                else:
                    self._deliver(send_list, gap_viol=gap_viol)
                self._regs[pcs_test.OFF_TX_STATUS] |= 0x10  # SCHED_DONE
            elif off == pcs_test.OFF_TX_CTRL and not (val & 0x08):
                self._regs[pcs_test.OFF_TX_STATUS] &= ~0x10
            return 0

        if off == pcs_test.OFF_TX_SEND and (val & 1):
            ctrl = self._regs.get(pcs_test.OFF_TX_CTRL, 0)
            wd = self._build_word_from_reg() if (ctrl & 4) else self._regs.get(pcs_test.OFF_TX_EXT_DATA, 0)
            self._deliver([wd], gap_viol=False)
            return 0

        if off == pcs_test.OFF_TX_CFG and (val & 0x10):
            sel = val & 3
            if sel == 0:
                self._tx_speed = "HS"
                self._set_tx_act("HS")
            elif sel == 1:
                self._tx_speed = "LS"
                self._set_tx_act("LS")
            else:
                self._tx_speed = "HS"
                self._regs[pcs_test.OFF_TX_ACT_TIM] = self._regs.get(pcs_test.OFF_TX_CUST_TIM, 0)
                self._regs[self.rm.offset("TX_ACT_GAP_DUR")] = self._regs.get(pcs_test.OFF_TX_CUST_GAP, 0)
            return 0

        if self.rm.has("TB_CHK_CTRL") and off == pcs_test.TB_CHK_CTRL and (val & 2):
            self._tb_fifo.clear()
            self._tb_ovf = False
            self._update_tb_status()
            self._regs[pcs_test.TB_CHK_CTRL] = val & 1
            return 0

        for ch in self.chans:
            cbase = 0x0800 if ch == "TB" else 0x4000 + int(ch[2:]) * 0x400
            pre = "TB_" if ch == "TB" else ch + "_"
            if off == cbase + pcs_test.CH_CTRL and (val & 4):
                self._regs[self.rm.offset(pre + "WORD_CNT")] = 0
                self._regs[self.rm.offset(pre + "ERR_CNT")] = 0
                self._regs[self.rm.offset(pre + "DROP_CNT")] = 0
                self._err_ram[ch] = []
                self._regs[off] = val & 3
                return 0
            if off == cbase + pcs_test.CH_CFG and (val & 0x10):
                spd = "LS" if (val & 3) == 1 else "HS"
                self._rx_speed[ch] = spd
                self._set_rx_act(ch, spd)
                return 0
            if off == cbase + pcs_test.CH_ERR_RADDR:
                self._err_ptr[ch] = val & 0xFF
                return 0
            if off == cbase + pcs_test.CH_BIT_RADDR:
                widx = (val >> 8) & 7
                bidx = val & 31
                self._bit_ptr[ch] = (widx << 5) | bidx
                return 0
        return 0


class FakePcsSystem:
    """Gerçek cmd_seq v2.0 ISA yürütücüsü + AXIL Studio AxilClient taklidi."""

    def __init__(self, ip: FakeIp21, pcs_base: int = 0x00000000, imem_aw: int = 9, dmem_aw: int = 8):
        self.ip = ip
        self.pcs_base = pcs_base
        self.imem_aw = imem_aw
        self.dmem_aw = dmem_aw
        self.self_id = (pcs_base >> 16) & 0xFF
        self.imem = [0] * (1 << imem_aw)
        self.dmem = [0] * (1 << dmem_aw)
        self.R = [0] * 16
        self.pc = 0
        self.entry = 0
        self.stack: list[int] = []
        self.max_stack_depth = 0
        self.z = self.n = self.c = self.v = self.ferr = 0
        self.busy = self.done = self.err = self.paused = False
        self.err_code = self.err_pc = self.err_addr = 0
        self.imem_ptr = self.imem_phase = self.imem_cnt = self.imem_sum = 0
        self._imem_lo = 0
        self.dmem_ptr = 0
        self.imem_data_writes = 0
        self.timer = 1000
        self.ip_host_writes = 0  # PC'nin doğrudan ARINC 429 IP'ye yaptığı yazma sayısı

    # ---- AxilClient arayüzü
    def address_map(self):
        return [
            {"name": "PCS_A429", "kind": "cmd_seq", "ip": "cmd_seq", "base": self.pcs_base,
             "window": 0x100000, "parent": "", "registers": []},
            {"name": "ARINC429_0", "kind": "ip", "ip": "arinc429_axil", "base": self.ip.base,
             "window": 0x10000, "parent": "PCS_A429", "registers": []},
        ]

    def _status_word(self) -> int:
        return (
            int(self.busy)
            | (int(self.done) << 1)
            | (int(self.err) << 2)
            | (int(self.paused) << 3)
            | (int(self.imem_phase) << 4)
            | ((self.pc & 0xFFFF) << 16)
        )

    def read(self, offset=0, addr=None, quiet=False) -> int:
        a = (self.ip.base + offset) if addr is None else (addr & M32)
        if ((a >> 16) & 0xFF) == self.self_id:
            off = a & 0xFFFF
            if off == pcs_test.REG_ID:
                return 0x5EC00200
            if off == pcs_test.REG_CAPS:
                return self.imem_aw | (self.dmem_aw << 8) | (16 << 16) | (self.self_id << 24)
            if off == pcs_test.REG_STATUS:
                return self._status_word()
            if off == pcs_test.REG_ERR_CODE:
                return self.err_code
            if off == pcs_test.REG_ERR_PC:
                return self.err_pc
            if off == pcs_test.REG_ERR_ADDR:
                return self.err_addr
            if off == pcs_test.REG_IMEM_CNT:
                return self.imem_cnt
            if off == pcs_test.REG_IMEM_SUM:
                return self.imem_sum
            if off == pcs_test.REG_TIMER:
                return self.timer & M32
            if pcs_test.REG_DMEM_BASE <= off < pcs_test.REG_DMEM_BASE + (1 << self.dmem_aw) * 4:
                return self.dmem[(off - pcs_test.REG_DMEM_BASE) >> 2]
            return 0
        data, _ = self.ip.read(a)
        return data

    def write(self, offset=0, value=0, addr=None, quiet=False):
        a = (self.ip.base + offset) if addr is None else (addr & M32)
        v = int(value) & M32
        if ((a >> 16) & 0xFF) == self.self_id:
            off = a & 0xFFFF
            if off == pcs_test.REG_CTRL:
                if v & pcs_test.CTRL_STOP:
                    self.busy = False
                    self.paused = True
                if v & pcs_test.CTRL_RESET:
                    self.busy = self.done = self.err = self.paused = False
                    self.R = [0] * 16
                    self.pc = 0
                    self.stack = []
                if v & pcs_test.CTRL_RUN:
                    self.busy = True
                    self.paused = self.done = self.err = False
                    self.pc = self.entry
            elif off == pcs_test.REG_ENTRY:
                self.entry = v
            elif off == pcs_test.REG_IMEM_PTR:
                self.imem_ptr = v
                self.imem_phase = 0
                self.imem_cnt = 0
                self.imem_sum = 0
            elif off == pcs_test.REG_IMEM_DATA:
                self.imem_data_writes += 1
                self.imem_sum = (self.imem_sum + v) & M32
                if self.imem_phase == 0:
                    self._imem_lo = v
                    self.imem_phase = 1
                else:
                    self.imem[self.imem_ptr] = self._imem_lo | (v << 32)
                    self.imem_ptr += 1
                    self.imem_cnt += 1
                    self.imem_phase = 0
            elif off == pcs_test.REG_DMEM_PTR:
                self.dmem_ptr = v & ((1 << self.dmem_aw) - 1)
            elif off == pcs_test.REG_DMEM_DATA:
                self.dmem[self.dmem_ptr] = v
                self.dmem_ptr = (self.dmem_ptr + 1) & ((1 << self.dmem_aw) - 1)
            elif pcs_test.REG_DMEM_BASE <= off < pcs_test.REG_DMEM_BASE + (1 << self.dmem_aw) * 4:
                self.dmem[(off - pcs_test.REG_DMEM_BASE) >> 2] = v
            return
        self.ip_host_writes += 1
        self.ip.write(a, v)

    def batch(self, ops, quiet=False):
        out = []
        for st in ops:
            if st["op"] == "read":
                out.append(self.read(addr=st.get("addr"), offset=st.get("offset", 0), quiet=quiet))
            else:
                self.write(addr=st.get("addr"), offset=st.get("offset", 0), value=st["value"], quiet=quiet)
                out.append(None)
        return out

    # ---- cmd_seq v2.0 komut yürütücüsü (seqmodel.py ile birebir)
    def step(self):
        if not self.busy or self.err or self.done:
            return
        w = self.imem[self.pc]
        f = pcs_test.decode_fields(w)
        op, ra, rb, mod, d, imm = f["op"], f["ra"], f["rb"], f["mod"], f["d"], f["imm"]
        name = pcs_test.OPNAME.get(op)
        a = self.R[ra]
        b = imm if (mod & 1) else self.R[rb]
        didx = d + ((self.R[ra] if op == pcs_test.OPS["RD"] else self.R[rb]) if (mod & 1) else 0)
        self.timer = (self.timer + 3 + f["dly"]) & M32

        def setr(r, val):
            if r:
                self.R[r] = val & M32

        def fail(code):
            self.err = True
            self.busy = False
            self.err_code = code
            self.err_pc = self.pc

        if name in ("NOP", "FENCE"):
            self.pc += 1
        elif name == "END":
            self.done = True
            self.busy = False
        elif name in ("WR", "RD"):
            addr = (self.R[rb] + imm) & M32
            if ((addr >> 16) & 0xFF) == self.self_id:
                self.err_addr = addr
                fail(3)
                return
            if name == "WR":
                self.ip.write(addr, a)
            else:
                data, _ = self.ip.read(addr)
                if mod & 2:
                    if didx >= (1 << self.dmem_aw):
                        fail(7)
                        return
                    self.dmem[didx] = data & M32
                else:
                    setr(ra, data)
            self.pc += 1
        elif name == "LDI":
            setr(ra, imm)
            self.pc += 1
        elif name == "MOV":
            setr(ra, b)
            self.pc += 1
        elif name == "LDD":
            if didx >= (1 << self.dmem_aw):
                fail(7)
                return
            setr(ra, self.dmem[didx])
            self.pc += 1
        elif name == "STD":
            if didx >= (1 << self.dmem_aw):
                fail(7)
                return
            self.dmem[didx] = a & M32
            self.pc += 1
        elif name in pcs_test.ALU_OPS:
            if name == "ADD":
                full = a + b
                res, c = full & M32, full >> 32
                v = int((a >> 31) == (b >> 31) and (res >> 31) != (a >> 31))
            elif name in ("SUB", "CMP"):
                res = (a - b) & M32
                c = int(a >= b)
                v = int((a >> 31) != (b >> 31) and (res >> 31) != (a >> 31))
            else:
                c = v = 0
                sh = b & 31
                res = {"AND": a & b, "OR": a | b, "XOR": a ^ b, "SHL": (a << sh) & M32, "SHR": a >> sh}[name]
            self.z, self.n, self.c, self.v = int(res == 0), res >> 31, c, v
            if name != "CMP":
                setr(ra, res)
            self.pc += 1
        elif name == "JMP":
            self.pc = imm
        elif name == "BR":
            lt = self.n ^ self.v
            cond = {0: 1, 1: self.z, 2: 1 - self.z, 3: lt, 4: 1 - lt, 5: self.ferr,
                    6: 1 - self.c, 7: self.c, 8: self.n, 9: 1 - self.n}[d]
            self.pc = imm if cond else self.pc + 1
        elif name == "LOOP":
            assert ra != 0
            self.R[ra] = (a - 1) & M32
            self.pc = imm if a != 1 else self.pc + 1
        elif name == "CALL":
            if len(self.stack) == 4:
                fail(4)
                return
            self.stack.append(self.pc + 1)
            self.max_stack_depth = max(self.max_stack_depth, len(self.stack))
            self.pc = imm
        elif name == "RET":
            if not self.stack:
                fail(4)
                return
            self.pc = self.stack.pop()
        elif name == "WAIT":
            self.timer = (self.timer + b) & M32
            self.pc += 1
        elif name == "TMR":
            setr(ra, self.timer)
            self.pc += 1
        else:
            fail(1)

    def run_until_rounds(self, target_rounds: int, max_steps: int = 200_000):
        for _ in range(max_steps):
            self.step()
            assert not self.err, f"PCS runtime error: code={self.err_code} pc={self.err_pc} addr=0x{self.err_addr:08X}"
            if self.dmem[pcs_test.M_TOTAL_ROUNDS] >= target_rounds and self.dmem[pcs_test.M_SEQ_BEGIN] == self.dmem[pcs_test.M_TOTAL_ROUNDS]:
                return
        raise AssertionError(f"Hedef {target_rounds} tura ulaşılamadı (mevcut {self.dmem[pcs_test.M_TOTAL_ROUNDS]})")


# =====================================================================================
# Birim ve entegrasyon testleri
# =====================================================================================
def test_all_15_tests_fit_in_512_imem():
    comp = pcs_test.build_program(0x00010000, ["RX0", "RX1"], use_tb=True, imem_aw=9)
    assert comp.insn_count <= 512, f"{comp.insn_count} > 512"
    assert len(comp.selected_tests) == 15
    assert comp.dmem_init[pcs_test.M_SIGNATURE] == pcs_test.SIGNATURE


def test_pcs_discover_load_and_3_clean_rounds():
    ip = FakeIp21(num_rx=2, has_txbit=True)
    sys_pcs = FakePcsSystem(ip)

    found = pcs_test.discover_pcs(sys_pcs, ip_base=ip.base)
    assert len(found) == 1
    assert found[0].is_ip_parent and found[0].imem_size == 512

    comp = pcs_test.build_program(ip.base, ["RX0", "RX1"], use_tb=True, max_rounds=3, gap_ms=10)
    pcs_test.load_and_start(sys_pcs, found[0].base, comp)
    assert sys_pcs.ip_host_writes == 0  # PC ARINC 429 IP'ye hiç yazmadı!

    sys_pcs.run_until_rounds(3)
    # 3. turdan sonra STATE==2 (TAMAMLANDI) durumuna geçmesi için birkaç adım daha
    for _ in range(20):
        sys_pcs.step()
    assert sys_pcs.max_stack_depth <= 4

    t = pcs_test.read_telemetry(sys_pcs, found[0].base)
    assert sys_pcs.ip_host_writes == 0  # Okumada da ARINC 429 IP'ye dokunulmadı!
    assert t["recognized"] and t["passed"]
    assert t["total_rounds"] == 3 and t["pass_rounds"] == 3 and t["fail_rounds"] == 0
    assert t["run_state"] == "TAMAMLANDI"
    assert all(x["fails"] == 0 for x in t["tests"])
    assert all(ch["fails"] == 0 for ch in t["channels"])
    assert t["first_fail"] is None
    assert "GEÇTİ" in pcs_test.report_text(t)
    assert json.loads(pcs_test.report_json(t))["total_rounds"] == 3

    # AGAIN ile 2 tur daha koştur
    pcs_test.restart_rounds(sys_pcs, found[0].base, max_rounds=2)
    for _ in range(500):
        sys_pcs.step()
        if sys_pcs.dmem[pcs_test.M_STATE] == 1:
            break
    assert sys_pcs.dmem[pcs_test.M_STATE] == 1 and sys_pcs.dmem[pcs_test.M_TOTAL_ROUNDS] == 0
    sys_pcs.run_until_rounds(2)
    t2 = pcs_test.read_telemetry(sys_pcs, found[0].base)
    assert t2["total_rounds"] == 2 and t2["fail_rounds"] == 0


def test_pcs_clear_stats_while_running():
    ip = FakeIp21(num_rx=1, has_txbit=True)
    sys_pcs = FakePcsSystem(ip)
    comp = pcs_test.build_program(ip.base, ["RX0"], use_tb=True, max_rounds=0, gap_ms=1)
    pcs_test.load_and_start(sys_pcs, 0x00000000, comp)
    sys_pcs.run_until_rounds(2)
    assert pcs_test.read_telemetry(sys_pcs, 0x00000000)["total_rounds"] == 2

    pcs_test.clear_stats(sys_pcs, 0x00000000)
    # Sonraki turun başında sayaçlar sıfırlanıp 1. tur tamamlanır
    for _ in range(100_000):
        sys_pcs.step()
        if sys_pcs.dmem[pcs_test.M_CLEAR_REQ] == 0 and sys_pcs.dmem[pcs_test.M_TOTAL_ROUNDS] == 1:
            break
    t = pcs_test.read_telemetry(sys_pcs, 0x00000000)
    assert t["total_rounds"] == 1 and t["fail_rounds"] == 0


@pytest.mark.parametrize("fault_setup,expected_tid,expected_chan_sub", [
    (lambda ip: setattr(ip, "fault_bad_id", True),                "ident",      "TX"),
    (lambda ip: ip.fault_line_stuck11.add("RX0"),                 "idle",       "RX0"),
    (lambda ip: ip.fault_swapped.add("RX1"),                      "polarity",   "RX1"),
    (lambda ip: ip.fault_open.add("RX1"),                         "polarity",   "RX1"),
    (lambda ip: ip.fault_bitflip.add("RX1"),                      "single_hs",  "RX1"),
    (lambda ip: ip.fault_drop_burst.add("RX0"),                   "burst_hs",   "RX0"),
    (lambda ip: setattr(ip, "fault_ignore_parity", True),         "parity",     "RX0"),
    (lambda ip: setattr(ip, "fault_ignore_gap", True),            "gapviol",    "RX0"),
    (lambda ip: ip.fault_bad_pulse.add("RX0"),                    "bittime",    "RX0"),
    (lambda ip: setattr(ip, "fault_ignore_freeze", True),         "logger",     "RX0"),
])
def test_pcs_catches_every_board_fault(fault_setup, expected_tid, expected_chan_sub):
    ip = FakeIp21(num_rx=2, has_txbit=True)
    fault_setup(ip)
    sys_pcs = FakePcsSystem(ip)
    comp = pcs_test.build_program(ip.base, ["RX0", "RX1"], use_tb=True, max_rounds=2, gap_ms=1)
    pcs_test.load_and_start(sys_pcs, 0x00000000, comp)
    sys_pcs.run_until_rounds(2)

    t = pcs_test.read_telemetry(sys_pcs, 0x00000000)
    assert not t["passed"]
    assert t["total_rounds"] == 2 and t["fail_rounds"] == 2
    by_tid = {x["tid"]: x for x in t["tests"]}
    assert by_tid[expected_tid]["fails"] == 2, f"{expected_tid} beklenen 2 kalma, gelen {by_tid[expected_tid]}"
    assert t["first_fail"] is not None
    assert t["first_fail"]["round"] == 1
    assert expected_chan_sub in t["first_fail"]["channel"] or expected_tid in ("parity", "gapviol", "logger")


def test_pcs_noise_tracking_and_channel_isolation():
    ip = FakeIp21(num_rx=2, has_txbit=True)
    ip.fault_noise_clk["RX0"] = 17
    ip.fault_bitflip.add("RX1")
    sys_pcs = FakePcsSystem(ip)
    comp = pcs_test.build_program(ip.base, ["RX0", "RX1"], use_tb=True, max_rounds=2, gap_ms=1)
    pcs_test.load_and_start(sys_pcs, 0x00000000, comp)
    sys_pcs.run_until_rounds(2)

    t = pcs_test.read_telemetry(sys_pcs, 0x00000000)
    assert t["max_noise_clk"] == 17
    ch_fails = {c["code"]: c["fails"] for c in t["channels"]}
    assert ch_fails[0] == 0        # RX0 sağlam
    assert ch_fails[1] > 0         # RX1 hatalı
    assert ch_fails[16] == 0       # TB sağlam


def test_pcs_smart_imem_skip_on_relaunch():
    ip = FakeIp21(num_rx=1, has_txbit=True)
    sys_pcs = FakePcsSystem(ip)
    comp1 = pcs_test.build_program(ip.base, ["RX0"], use_tb=True, max_rounds=1, gap_ms=500)
    pcs_test.load_and_start(sys_pcs, 0, comp1)
    first_writes = sys_pcs.imem_data_writes
    assert first_writes == 2 * comp1.insn_count

    # Aynı testlerle sadece gap_ms ve max_rounds değiştirilince I-mem tekrar yazılmamalı!
    comp2 = pcs_test.build_program(ip.base, ["RX0"], use_tb=True, max_rounds=2, gap_ms=100)
    pcs_test.load_and_start(sys_pcs, 0, comp2)
    assert sys_pcs.imem_data_writes == first_writes
    sys_pcs.run_until_rounds(2)
    t = pcs_test.read_telemetry(sys_pcs, 0)
    assert t["passed"] and t["total_rounds"] == 2 and t["gap_ms"] == 100.0


def test_pcs_gapviol_clean_with_depth4_tb_fifo_and_stale_iwg():
    """Eski bir testten yüksek TX_INTER_WORD_GAP kalmış olsa bile ve TB_CHK FIFO
    derinliği 4 iken gapviol testi FIFO taşması yapmadan tüm turları geçer."""
    ip = FakeIp21(num_rx=1, has_txbit=True)
    # Önceki bir t_period / TX Canlı çalıştırmasından kalan büyük IWG ve initial delay
    ip._regs[pcs_test.OFF_TX_IWG] = 5000
    ip._regs[pcs_test.OFF_TX_INIT_DLY] = 1000
    sys_pcs = FakePcsSystem(ip)
    comp = pcs_test.build_program(ip.base, ["RX0"], use_tb=True, max_rounds=4, gap_ms=1)
    pcs_test.load_and_start(sys_pcs, 0, comp)
    sys_pcs.run_until_rounds(4)
    t = pcs_test.read_telemetry(sys_pcs, 0)
    assert t["passed"]
    assert t["total_rounds"] == 4 and t["pass_rounds"] == 4 and t["fail_rounds"] == 0
    assert not t["last_round_failed"]
    assert not ip._tb_ovf
    assert len(ip._tb_fifo) == 0


def test_pcs_transient_fail_recovery_and_diff_fail_events():
    """İlk turda geçici hata oluşup sonraki turlarda düzeldiğinde:
    - last_round_failed True -> False döner (UI testleri geri yeşil yapar),
    - first_fail ve last_fail korunur,
    - diff_fail_events yalnızca hata artışı olduğunda log satırı üretir."""
    ip = FakeIp21(num_rx=1, has_txbit=True)
    ip.fault_ignore_gap = True
    sys_pcs = FakePcsSystem(ip)
    comp = pcs_test.build_program(ip.base, ["RX0"], use_tb=True, max_rounds=0, gap_ms=1)
    pcs_test.load_and_start(sys_pcs, 0, comp)

    # Tur 1: gapviol kalır
    sys_pcs.run_until_rounds(1)
    t1 = pcs_test.read_telemetry(sys_pcs, 0)
    assert t1["total_rounds"] == 1 and t1["fail_rounds"] == 1 and t1["pass_rounds"] == 0
    assert t1["last_round_failed"] is True
    by1 = {x["tid"]: x for x in t1["tests"]}
    assert by1["gapviol"]["last_failed"] is True and by1["gapviol"]["fails"] == 1
    assert t1["first_fail"] is not None and t1["first_fail"]["test_id"] == "gapviol"
    assert t1["last_fail"] is not None and t1["last_fail"]["test_id"] == "gapviol" and t1["last_fail"]["round"] == 1

    ev1 = pcs_test.diff_fail_events(None, t1)
    assert len(ev1) >= 1 and all("Tur #1" in e and "Gap ihlali" in e for e in ev1)

    # Hata düzeldi -> Tur 2 ve Tur 3 temiz geçer
    ip.fault_ignore_gap = False
    sys_pcs.run_until_rounds(3)
    t3 = pcs_test.read_telemetry(sys_pcs, 0)
    assert t3["total_rounds"] == 3 and t3["fail_rounds"] == 1 and t3["pass_rounds"] == 2
    assert t3["last_round_failed"] is False
    by3 = {x["tid"]: x for x in t3["tests"]}
    assert by3["gapviol"]["last_failed"] is False and by3["gapviol"]["fails"] == 1
    # Yeni hata olmadığından log akışına satır eklenmez
    assert pcs_test.diff_fail_events(t1, t3) == []

    # Tur 4'te farklı bir hata (parity) oluşursa yeni log satırı eklenir ve last_fail güncellenir
    ip.fault_ignore_parity = True
    sys_pcs.run_until_rounds(4)
    t4 = pcs_test.read_telemetry(sys_pcs, 0)
    assert t4["total_rounds"] == 4 and t4["fail_rounds"] == 2 and t4["pass_rounds"] == 2
    assert t4["last_round_failed"] is True
    assert t4["first_fail"]["test_id"] == "gapviol" and t4["first_fail"]["round"] == 1
    assert t4["last_fail"]["test_id"] == "parity" and t4["last_fail"]["round"] == 4
    ev4 = pcs_test.diff_fail_events(t3, t4)
    assert len(ev4) == 1 and "Tur #4" in ev4[0] and "Parity" in ev4[0] and "toplam 1/4" in ev4[0]


