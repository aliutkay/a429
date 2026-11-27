"""Ballard BTIDriver sarmalayıcı (a429/ballard.py) ve dış doğrulama testi (a429/busbox_test.py) testleri."""
from __future__ import annotations

import ctypes
import threading

import pytest

from a429 import ballard, busbox_test, ipmap, selftest
from a429.decode import ERR_NAMES
from a429.regs import RegMap, channel_prefix
from a429.txlive import build_word

ERR_BIT = {n: 1 << i for i, n in enumerate(ERR_NAMES)}


# =====================================================================================
# 1. Ballard ABI / struct / sarmalayıcı testleri
# =====================================================================================
def test_seqrecord429_layout():
    assert ctypes.sizeof(ballard.SEQRECORD429) == 20
    rec = ballard.SEQRECORD429(
        type=ballard.SEQTYPE_429 | ballard.SEQVER_1,
        count=10,
        timestamp=0x12345678,
        activity=(3 << ballard.MSGACT429_CHSHIFT) | ballard.MSGACT429_SPD | ballard.MSGACT429_PAR | ballard.MSGACT429_ERR | ballard.MSGACT429_HIT,
        decgap=4,
        data=0x801234C8,
        timestamph=0x00000002,
    )
    rx = ballard.BallardSession._to_rx_record(rec)
    assert rx.word == 0x801234C8
    assert rx.timestamp_us == (2 << 32) | 0x12345678
    assert rx.channel == 3
    assert rx.decgap == 4
    assert rx.speed_hs is True
    assert rx.err is True
    assert rx.parity_err is True
    assert rx.error_flags == ["PAR"]


def test_ballard_session_ctypes_call_sequence():
    """Gerçek WinDLL olmadan BTIDriver bağlamasını ve BallardSession çağrı sırasını doğrular."""
    calls: list[tuple] = []
    seq_records: list[ballard.SEQRECORD429] = []
    sent_words: list[int] = []

    class FakeCardDLL:
        def BTICard_CardOpen(self, lph, cardnum):
            calls.append(("CardOpen", cardnum))
            lph._obj.value = 0x1001
            return 0

        def BTICard_CardClose(self, hcard):
            calls.append(("CardClose", hcard))
            return 0

        def BTICard_CoreOpen(self, lph, corenum, hcard):
            calls.append(("CoreOpen", corenum))
            lph._obj.value = 0x2002
            return 0

        def BTICard_CardReset(self, hcore):
            calls.append(("CardReset",))

        def BTICard_CardStart(self, hcore):
            calls.append(("CardStart",))
            return 0

        def BTICard_CardStop(self, hcore):
            calls.append(("CardStop",))
            return 1

        def BTICard_CardGetInfo(self, itype, ch, hcore):
            if itype == ballard.INFOTYPE_SERIALNUM:
                return 112099
            return 0

        def BTICard_CardProductStr(self, hcore):
            return b"BUSBox BB1120"

        def BTICard_CardTypeStr(self, hcore):
            return b"BUSBOX"

        def BTICard_ErrDescStr(self, err, hcore):
            return b"OK"

        def BTICard_CardTest(self, lvl, hcore):
            calls.append(("CardTest", lvl))
            return 0

        def BTICard_TimerResolution(self, resol, hcore):
            calls.append(("TimerResolution", resol))
            return 0

        def BTICard_SeqConfig(self, cfg, hcore):
            calls.append(("SeqConfig", cfg))
            return 0

        def BTICard_SeqBlkRd(self, buf, bufcount, pblk, hcore):
            pblk._obj.value = len(seq_records)
            return len(seq_records) * 10

        def BTICard_SeqFindInit(self, buf, seqcount, psf):
            self._idx = 0
            return 0

        def BTICard_SeqFindNext429Ex(self, prec, recsz, psf):
            if self._idx >= len(seq_records):
                return -1
            src = seq_records[self._idx]
            self._idx += 1
            dst = prec._obj
            for field_name, _ in ballard.SEQRECORD429._fields_:
                setattr(dst, field_name, getattr(src, field_name))
            return 0

    class Fake429DLL:
        def BTI429_ChIsRcv(self, ch, hcore):
            return 1 if ch in (0, 1) else 0

        def BTI429_ChIsXmt(self, ch, hcore):
            return 1 if ch in (4, 5) else 0

        def BTI429_ChConfig(self, cfg, ch, hcore):
            calls.append(("ChConfig", ch, cfg))
            return 0

        def BTI429_FilterDefault(self, cfg, ch, hcore):
            calls.append(("FilterDefault", ch))
            return 0x3000 + ch

        def BTI429_ListAsyncCreate(self, cfg, cnt, ch, hcore):
            calls.append(("ListAsyncCreate", ch, cnt))
            return 0x4000 + ch

        def BTI429_ListDataWr(self, val, laddr, hcore):
            sent_words.append(val)
            return 1

        def BTI429_ListStatus(self, laddr, hcore):
            return ballard.STAT_EMPTY

        def BTI429_SchedGap(self, gap, ch, hcore):
            calls.append(("SchedGap", ch, gap))
            return 0

    def _ns(obj):
        import types
        ns = types.SimpleNamespace()
        for name in dir(obj):
            if name.startswith("BTI"):
                fn = getattr(obj, name)
                def _wrap(f):
                    def _call(*a):
                        return f(*a)
                    return _call
                setattr(ns, name, _wrap(fn))
        return ns

    drv = ballard.BTIDriver(_ns(FakeCardDLL()), _ns(Fake429DLL()), "BTICARD64.DLL", "BTI42964.DLL")
    with ballard.BallardSession(card_num=0, core_num=0, driver=drv) as sess:
        assert sess.info.product == "BUSBox BB1120"
        assert sess.info.rx_channels == [0, 1]
        assert sess.info.tx_channels == [4, 5]
        ok, _ = sess.self_test()
        assert ok
        sess.configure(rx_chan=0, tx_chan=4, rx_speed="HS", tx_speed="HS")
        sess.send_words([0x800000C8, 0x0000008A])
        assert sent_words == [0x800000C8, 0x0000008A]

        seq_records.append(ballard.SEQRECORD429(
            type=ballard.SEQTYPE_429 | ballard.SEQVER_1, count=10,
            timestamp=5000, activity=(0 << 8) | ballard.MSGACT429_SPD | ballard.MSGACT429_HIT,
            decgap=4, data=0x800000C8, timestamph=0,
        ))
        got = sess.read_rx(chan=0, timeout_s=0.05, min_count=1, quiet_gap_s=0.0)
        assert len(got) == 1 and got[0].word == 0x800000C8 and got[0].timestamp_us == 5000

    assert ("CardOpen", 0) in calls
    assert ("TimerResolution", ballard.TIMERRESOL_1US) in calls
    assert ("ChConfig", 0, ballard.CHCFG429_SEQALL | ballard.CHCFG429_HIGHSPEED | ballard.CHCFG429_PARODD) in calls
    assert ("ChConfig", 4, ballard.CHCFG429_HIGHSPEED | ballard.CHCFG429_PARDATA) in calls
    assert ("SchedGap", 4, 1024) in calls
    assert any(c[0] == "CardClose" for c in calls)


# =====================================================================================
# 2. Davranışsal IP 2.1.0 + MockBallardSession uçtan uca test düzeneği
# =====================================================================================
class FakeIpBus:
    """IP 2.1.0 register davranışını modelleyen ve MockBallardSession'a bağlanan sahte bus."""

    def __init__(self, bb: ballard.MockBallardSession, num_rx: int = 2, clk_hz: int = 50_000_000):
        self.bb = bb
        self.clk_hz = clk_hz
        self.ip = ipmap.to_ip_dict(num_rx=num_rx, has_tx=True, has_txbit=True)
        self.rm = RegMap(self.ip)
        self.models_line = True
        self.connected = True
        self._regs: dict[int, int] = {}
        self._rx_chans = [f"RX{i}" for i in range(num_rx)]
        self._all_chans = self._rx_chans + ["TB"]
        self._wram: dict[str, list[dict]] = {c: [] for c in self._all_chans}
        self._eram: dict[str, list[dict]] = {c: [] for c in self._all_chans}
        self._bram: dict[str, list[dict]] = {c: [] for c in self._all_chans}
        self._wptr: dict[str, int] = {c: 0 for c in self._all_chans}
        self._eptr: dict[str, int] = {c: 0 for c in self._all_chans}
        self._bptr: dict[str, int] = {c: 0 for c in self._all_chans}
        self._ts_clk = 0
        self._reset_all()
        self.bb.on_tx = self._on_bb_tx

    def lock(self):
        pass

    def unlock(self):
        pass

    def advance_us(self, us: float):
        self._ts_clk += int(round(us * self.clk_hz / 1e6))

    def _reset_all(self):
        self._regs.clear()
        for r in self.rm.regs.values():
            self._regs[r.offset] = int(r.reset)
        self._regs[self.rm.offset("IP_ID")] = ipmap.IP_ID_WORD
        v = ipmap.IP_VERSION
        self._regs[self.rm.offset("IP_VERSION")] = (v[0] << 16) | (v[1] << 8) | v[2]
        self._regs[self.rm.offset("CLK_HZ")] = self.clk_hz
        self._apply_tx_cfg(0)
        for ch in self._all_chans:
            self._apply_rx_cfg(ch, 0)
            self._clear_chan(ch)

    def _clear_chan(self, ch: str):
        p = channel_prefix(ch)
        for name in ("WORD_CNT", "ERR_CNT", "DROP_CNT", "LAST_WORD"):
            self._regs[self.rm.offset(p + name)] = 0
        self._wram[ch].clear()
        self._eram[ch].clear()
        self._bram[ch].clear()
        self._wptr[ch] = self._eptr[ch] = self._bptr[ch] = 0

    def _apply_tx_cfg(self, sel: int):
        if sel == 0:
            p, n, g, slp = 250, 250, 2000, 1
        elif sel == 1:
            p, n, g, slp = 2000, 2000, 16000, 0
        else:
            t = self._regs[self.rm.offset("TX_CUST_TIMING")]
            p, n = t & 0xFFFF, (t >> 16) & 0xFFFF
            g = self._regs[self.rm.offset("TX_CUST_GAP_DUR")]
            slp = self._regs[self.rm.offset("TX_CUST_SLP")] & 1
        self._regs[self.rm.offset("TX_ACT_TIMING")] = (p & 0xFFFF) | ((n & 0xFFFF) << 16)
        self._regs[self.rm.offset("TX_ACT_GAP_DUR")] = g
        self._regs[self.rm.offset("TX_ACT_SLP")] = slp
        st = self._regs[self.rm.offset("TX_STATUS")]
        st = (st & ~(3 << 2)) | ((sel & 3) << 2)
        self._regs[self.rm.offset("TX_STATUS")] = st

    def _apply_rx_cfg(self, ch: str, sel: int):
        p = channel_prefix(ch)
        if sel == 0:
            minp, maxp, minb, maxb = 175, 325, 450, 550
        elif sel == 1:
            minp, maxp, minb, maxb = 1400, 2600, 3600, 4400
        else:
            cp = self._regs[self.rm.offset(p + "CUST_PULSE")]
            cb = self._regs[self.rm.offset(p + "CUST_BIT")]
            minp, maxp = cp & 0xFFFF, (cp >> 16) & 0xFFFF
            minb, maxb = cb & 0xFFFF, (cb >> 16) & 0xFFFF
        self._regs[self.rm.offset(p + "ACT_PULSE")] = (minp & 0xFFFF) | ((maxp & 0xFFFF) << 16)
        self._regs[self.rm.offset(p + "ACT_BIT")] = (minb & 0xFFFF) | ((maxb & 0xFFFF) << 16)
        st = self._regs[self.rm.offset(p + "STATUS")]
        st = (st & ~(3 << 8)) | ((sel & 3) << 8)
        self._regs[self.rm.offset(p + "STATUS")] = st

    def _tx_speed_name(self) -> str:
        t = self._regs[self.rm.offset("TX_ACT_TIMING")]
        bit_clk = (t & 0xFFFF) + ((t >> 16) & 0xFFFF)
        return "HS" if bit_clk < 1500 else "LS"

    def _rx_speed_name(self, ch: str) -> str:
        p = channel_prefix(ch)
        cb = self._regs[self.rm.offset(p + "ACT_BIT")]
        minb = cb & 0xFFFF
        return "HS" if minb < 1500 else "LS"

    def _deliver_rx_word(self, ch: str, word: int, wire_speed: str, gap_clk: int = 2000):
        p = channel_prefix(ch)
        ctrl = self._regs[self.rm.offset(p + "CTRL")]
        if not (ctrl & 1):
            return
        if (ctrl & 2) or (self._regs[self.rm.offset("GLOBAL_FREEZE")] & 1):
            self._regs[self.rm.offset(p + "DROP_CNT")] += 1
            return
        rx_spd = self._rx_speed_name(ch)
        if wire_speed != rx_spd:
            code = ERR_BIT["Pulse Glitch"] if wire_speed == "HS" else ERR_BIT["Pulse Stuck"]
            self._regs[self.rm.offset(p + "ERR_CNT")] += 1
            self._eram[ch].append({"ts": self._ts_clk, "code": code, "addr": len(self._wram[ch]), "data": word})
            return
        if bin(word & 0xFFFFFFFF).count("1") % 2 == 0:
            self._regs[self.rm.offset(p + "ERR_CNT")] += 1
            self._eram[ch].append({"ts": self._ts_clk, "code": ERR_BIT["Parity Error"],
                                   "addr": len(self._wram[ch]), "data": word})
            return
        wno = self._regs[self.rm.offset(p + "WORD_CNT")]
        self._regs[self.rm.offset(p + "WORD_CNT")] = wno + 1
        self._regs[self.rm.offset(p + "LAST_WORD")] = word
        self._wram[ch].append({"ts": self._ts_clk, "data": word, "gap": gap_clk, "gap_err": 0})
        pulse_clk = 250 if wire_speed == "HS" else 2000
        null_clk = 250 if wire_speed == "HS" else 2000
        if not self._bram[ch]:
            self._bram[ch] = [{"pulse": 0, "perr": 0, "null": 0, "nerr": 0} for _ in range(8 * 32)]
        base = (wno % 8) * 32
        for b in range(32):
            self._bram[ch][base + b] = {"pulse": pulse_clk, "perr": 0, "null": null_clk, "nerr": 0}

    def _emit_tx_word(self, word: int, dt_us: int | None = None):
        self._regs[self.rm.offset("TX_WORD_CNT")] += 1
        spd = self._tx_speed_name()
        self.bb.push_rx(word, speed=spd, dt_us=dt_us)
        # TX BIT dahili yankı + checker
        self._deliver_rx_word("TB", word, spd)
        if self._regs[self.rm.offset("TB_CHK_CTRL")] & 1:
            if bin(word & 0xFFFFFFFF).count("1") % 2 == 1 and spd == self._rx_speed_name("TB"):
                self._regs[self.rm.offset("TB_CHK_OK_CNT")] += 1
            else:
                self._regs[self.rm.offset("TB_CHK_ERR_CNT")] += 1

    def _on_bb_tx(self, words: list[int], speed: str, raw_parity: bool):
        for w in words:
            for ch in self._rx_chans:
                self._deliver_rx_word(ch, w, speed)
            self._ts_clk += 18000 if speed == "HS" else 144000

    def _current_tx_word(self) -> int:
        ctrl = self._regs[self.rm.offset("TX_CTRL")]
        if ctrl & (1 << 2):  # BUILDER_EN
            tw = self._regs[self.rm.offset("TX_WORD")]
            lab = tw & 0xFF
            sdi = (tw >> 8) & 3
            data = (tw >> 10) & 0x7FFFF
            ssm = (tw >> 29) & 3
            odd = bool((tw >> 31) & 1)
            return build_word(lab, sdi, data, ssm, odd=odd)
        return self._regs[self.rm.offset("TX_EXT_DATA")] & 0xFFFFFFFF

    def read(self, offset: int, quiet: bool = True) -> int:
        for ch in self._all_chans:
            p = channel_prefix(ch)
            # Word RAM okuma
            if offset in (
                self.rm.offset(p + "WORD_RD_TS_MSB"), self.rm.offset(p + "WORD_RD_TS_LSB"),
                self.rm.offset(p + "WORD_RD_DATA"), self.rm.offset(p + "WORD_RD_GAP"),
                self.rm.offset(p + "WORD_RD_GAP_ERR"),
            ):
                rec = self._wram[ch][self._wptr[ch] % len(self._wram[ch])] if self._wram[ch] else {"ts": 0, "data": 0, "gap": 0, "gap_err": 0}
                if offset == self.rm.offset(p + "WORD_RD_TS_MSB"):
                    return (rec["ts"] >> 32) & 0xFFFFFFFF
                if offset == self.rm.offset(p + "WORD_RD_TS_LSB"):
                    return rec["ts"] & 0xFFFFFFFF
                if offset == self.rm.offset(p + "WORD_RD_DATA"):
                    return rec["data"]
                if offset == self.rm.offset(p + "WORD_RD_GAP"):
                    return rec["gap"]
                self._wptr[ch] += 1
                return rec["gap_err"]
            # Error RAM okuma
            if offset in (
                self.rm.offset(p + "ERR_RD_TS_MSB"), self.rm.offset(p + "ERR_RD_TS_LSB"),
                self.rm.offset(p + "ERR_RD_INFO"), self.rm.offset(p + "ERR_RD_DATA"),
            ):
                rec = self._eram[ch][self._eptr[ch] % len(self._eram[ch])] if self._eram[ch] else {"ts": 0, "code": 0, "addr": 0, "data": 0}
                if offset == self.rm.offset(p + "ERR_RD_TS_MSB"):
                    return (rec["ts"] >> 32) & 0xFFFFFFFF
                if offset == self.rm.offset(p + "ERR_RD_TS_LSB"):
                    return rec["ts"] & 0xFFFFFFFF
                if offset == self.rm.offset(p + "ERR_RD_INFO"):
                    return (rec["code"] & 0xFFFF) | ((rec["addr"] & 0xFFFF) << 16)
                self._eptr[ch] += 1
                return rec["data"]
            # Bit Diagnostic RAM okuma
            if offset in (self.rm.offset(p + "BIT_RD_PULSE"), self.rm.offset(p + "BIT_RD_NULL")):
                rec = self._bram[ch][self._bptr[ch] % len(self._bram[ch])] if self._bram[ch] else {"pulse": 0, "perr": 0, "null": 0, "nerr": 0}
                if offset == self.rm.offset(p + "BIT_RD_PULSE"):
                    return (rec["pulse"] & 0xFFFF) | ((rec["perr"] & 0xFFFF) << 16)
                self._bptr[ch] += 1
                return (rec["null"] & 0xFFFF) | ((rec["nerr"] & 0xFFFF) << 16)
        return self._regs.get(offset, 0)

    def write(self, offset: int, value: int, quiet: bool = True):
        value &= 0xFFFFFFFF
        if offset == self.rm.offset("SOFT_RESET"):
            if value & 1:
                self._reset_all()
            return
        if offset == self.rm.offset("TX_CFG"):
            self._regs[offset] = value & ~(1 << 4)
            if value & (1 << 4):
                self._apply_tx_cfg(value & 3)
            return
        if offset == self.rm.offset("TX_SEND_CMD"):
            if value & 1:
                self._emit_tx_word(self._current_tx_word())
            return
        if offset == self.rm.offset("TX_CTRL"):
            prev = self._regs.get(offset, 0)
            self._regs[offset] = value
            # SCHED_EN yükselen kenarı + TX_SCHED_COUNT > 0: tam N Word gönder ve SCHED_DONE=1 yap
            if (value & (1 << 3)) and not (prev & (1 << 3)):
                n_cnt = self._regs.get(self.rm.offset("TX_SCHED_COUNT"), 0)
                if n_cnt > 0:
                    t = self._regs[self.rm.offset("TX_ACT_TIMING")]
                    p_clk, n_clk = t & 0xFFFF, (t >> 16) & 0xFFFF
                    g_clk = self._regs[self.rm.offset("TX_ACT_GAP_DUR")]
                    iwg = self._regs[self.rm.offset("TX_INTER_WORD_GAP")]
                    period_clk = 32 * (p_clk + n_clk) + g_clk + iwg
                    dt_us = round(period_clk * 1e6 / self.clk_hz)
                    wd = self._current_tx_word()
                    for _ in range(n_cnt):
                        self._emit_tx_word(wd, dt_us=dt_us)
                    self._regs[self.rm.offset("TX_STATUS")] |= (1 << 4)  # SCHED_DONE
            elif not (value & (1 << 3)):
                self._regs[self.rm.offset("TX_STATUS")] &= ~(1 << 4)
            return
        if offset == self.rm.offset("TB_CHK_CTRL"):
            self._regs[offset] = value & 1
            return
        for ch in self._all_chans:
            p = channel_prefix(ch)
            if offset == self.rm.offset(p + "CFG"):
                self._regs[offset] = value & ~(1 << 4)
                if value & (1 << 4):
                    self._apply_rx_cfg(ch, value & 3)
                return
            if offset == self.rm.offset(p + "CTRL"):
                self._regs[offset] = value & 0b011
                if value & 0b100:
                    self._clear_chan(ch)
                return
            if offset == self.rm.offset(p + "WORD_RADDR"):
                self._wptr[ch] = value
                return
            if offset == self.rm.offset(p + "ERR_RADDR"):
                self._eptr[ch] = value
                return
            if offset == self.rm.offset(p + "BIT_RADDR"):
                self._bptr[ch] = (((value >> 8) & 0xFF) % 8) * 32 + (value & 0x1F)
                return
        self._regs[offset] = value

    def batch(self, ops, quiet: bool = True):
        out = []
        for op in ops:
            if op[0] == "read":
                out.append(self.read(op[1], quiet=quiet))
            else:
                self.write(op[1], op[2], quiet=quiet)
                out.append(None)
        return out


# =====================================================================================
# 3. Dış doğrulama test takımı doğrulaması
# =====================================================================================
def test_full_ballard_suite_passes():
    bb = ballard.MockBallardSession(rx_channels=[0, 1], tx_channels=[4, 5])
    bus = FakeIpBus(bb, num_rx=2)
    custom = {
        "tx": [("TX_CUST_PULSE_DUR", 250), ("TX_CUST_NULL_DUR", 250), ("TX_CUST_GAP_DUR", 2000), ("TX_CUST_SLP", 1)],
        "rx": {"CUST_MIN_PULSE": 175, "CUST_MAX_PULSE": 325, "CUST_MIN_BIT": 450, "CUST_MAX_BIT": 550},
    }
    rep = busbox_test.run(
        bus, bus.rm, ["RX0", "RX1"],
        ballard=bb, test_tx=True, test_rx=True, bb_rx_chan=0, bb_tx_chan=4,
        use_tb=True, custom=custom,
    )
    assert rep["passed"], busbox_test.report_text(rep)
    assert rep["mode"] == "ballard"
    assert rep["counts"]["FAIL"] == 0 and rep["counts"]["ERROR"] == 0 and rep["counts"]["SKIP"] == 0
    per_hs = next(r for r in rep["results"] if r.tid == "tx_period" and r.speed == "HS")
    assert abs(per_hs.measurements["clock_err_ppm"]) < 50
    bt_hs = next(r for r in rep["results"] if r.tid == "rx_bittime" and r.speed == "HS")
    assert bt_hs.measurements["RX0"]["rx_ic_skew_us"] == 0.0
    txt = busbox_test.report_text(rep)
    assert "GEÇTİ" in txt and "Ballard" in txt
    assert '"mode": "ballard"' in busbox_test.report_json(rep)


def test_clock_drift_caught_by_independent_ballard_timer():
    """Loopback'in gizleyeceği %5 saat kaymasını Ballard 1 µs zaman damgası yakalamalı."""
    bb = ballard.MockBallardSession(clock_scale=1.05)
    bus = FakeIpBus(bb, num_rx=1)
    rep = busbox_test.run(
        bus, bus.rm, ["RX0"],
        ballard=bb, test_tx=True, test_rx=False, bb_rx_chan=0,
        selected=["tx_period"], speeds=("HS",),
    )
    assert not rep["passed"]
    per = next(r for r in rep["results"] if r.tid == "tx_period")
    assert per.status == "FAIL"
    assert abs(per.measurements["clock_err_ppm"] - 50000) < 2500


@pytest.mark.parametrize("side, fault, expect", [
    ("tx", "swapped", "A/B hattı ters"),
    ("tx", "open", "sinyal yok"),
    ("rx", "swapped", "A/B hattı ters"),
    ("rx", "open", "hatta sinyal yok"),
])
def test_ballard_wiring_faults_isolated(side, fault, expect):
    bb = ballard.MockBallardSession()
    bus = FakeIpBus(bb, num_rx=1)
    if side == "tx":
        bb.wiring_tx = fault
    else:
        bb.wiring_rx = fault
    rep = busbox_test.run(
        bus, bus.rm, ["RX0"],
        ballard=bb, test_tx=True, test_rx=True, bb_rx_chan=0, bb_tx_chan=4,
        selected=["tx_single", "rx_single"], speeds=("HS",),
    )
    assert not rep["passed"]
    res_map = {r.tid: r for r in rep["results"]}
    # Arıza izolasyonu: yalnızca arızalı yön KALDI, sağlam yön GEÇTİ olmalı!
    bad_tid = "tx_single" if side == "tx" else "rx_single"
    good_tid = "rx_single" if side == "tx" else "tx_single"
    assert res_map[bad_tid].status == "FAIL"
    assert res_map[good_tid].status == "PASS"
    details = " ".join(ck.detail for ck in res_map[bad_tid].checks if ck.ok is False)
    assert expect in details, details


def test_direction_selection_skips_other_side():
    bb = ballard.MockBallardSession()
    bus = FakeIpBus(bb, num_rx=1)
    rep_tx = busbox_test.run(
        bus, bus.rm, ["RX0"],
        ballard=bb, test_tx=True, test_rx=False, bb_rx_chan=0, bb_tx_chan=4,
        selected=["tx_single", "rx_single", "duplex"], speeds=("HS",),
    )
    assert rep_tx["passed"]
    st = {r.tid: r.status for r in rep_tx["results"]}
    assert st["tx_single"] == "PASS" and st["rx_single"] == "SKIP" and st["duplex"] == "SKIP"


def test_stop_flag_aborts_ballard():
    bb = ballard.MockBallardSession()
    bus = FakeIpBus(bb, num_rx=1)
    ev = threading.Event()
    seen = []

    def on_res(r):
        seen.append(r.tid)
        if r.tid == "prep":
            ev.set()

    rep = busbox_test.run(
        bus, bus.rm, ["RX0"],
        ballard=bb, test_tx=True, test_rx=True, bb_rx_chan=0, bb_tx_chan=4,
        speeds=("HS",), stop=ev, on_result=on_res,
    )
    assert rep["aborted"] and not rep["passed"]
    assert seen[:2] == ["ident", "prep"] and len(seen) == 3


def test_resolve_dll_paths(tmp_path):
    card_name, a429_name = ballard.dll_names()
    assert ballard.resolve_dll_paths(None) == (card_name, a429_name)

    with pytest.raises(ballard.BallardError):
        ballard.resolve_dll_paths(str(tmp_path / "missing_dir"))

    (tmp_path / card_name).write_bytes(b"")
    with pytest.raises(ballard.BallardError):
        ballard.resolve_dll_paths(str(tmp_path))

    (tmp_path / a429_name).write_bytes(b"")
    c_path, a_path = ballard.resolve_dll_paths(str(tmp_path))
    assert c_path == str(tmp_path / card_name)
    assert a_path == str(tmp_path / a429_name)

