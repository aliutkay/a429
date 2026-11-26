"""Loopback test takımının (a429/selftest.py) gerçek RTL'e karşı doğrulanması (a429/cosim.py).

ghdl + verilator (veya iverilog) yoksa atlanır.
"""
import pytest

from a429 import cosim, selftest
from a429.regs import RegMap

pytestmark = pytest.mark.skipif(not cosim.available(), reason="ghdl + verilator/iverilog gerekli")


@pytest.fixture(scope="module")
def rtl():
    c = cosim.CosimClient(num_rx=1)
    yield c
    c.close()


def _failed(rep):
    return [(r.tid, ck.name, ck.detail) for r in rep["results"] for ck in r.checks if ck.ok is False]


def test_full_suite_passes_on_rtl(rtl):
    rtl.set_rx_wiring(0, "loop")
    rep = selftest.run(rtl, RegMap(rtl.ip), ["RX0"])
    assert rep["passed"], selftest.report_text(rep)
    ids = {(r.tid, r.speed) for r in rep["results"]}
    for tid in ("idle", "polarity", "switch", "mismatch", "parity", "gapviol", "logger"):
        assert (tid, "") in ids
    for tid in ("single", "pattern", "bittime", "period", "burst"):
        assert (tid, "HS") in ids and (tid, "LS") in ids
    # Ölçümler RTL ile birebir: HS 5 µs pulse, periyot = 32 bit + 4 bit gap + 10 bit inter-word gap
    bt = next(r for r in rep["results"] if r.tid == "bittime" and r.speed == "HS")
    assert bt.measurements["RX0"]["pulse_us"][1] == 5.0
    per = next(r for r in rep["results"] if r.tid == "period" and r.speed == "LS")
    assert abs(per.measurements["RX0"]["period_us"][0] - 46 * 80) < 0.1
    txt = selftest.report_text(rep)
    assert "GEÇTİ" in txt and "Gap ihlali" in txt
    assert '"results"' in selftest.report_json(rep)


@pytest.mark.parametrize("mode, expect", [
    ("swapped", "A/B hattı ters"),
    ("inverted", "alıcı çıkış"),
    ("open", "kablo kopuk"),
])
def test_wiring_faults_are_diagnosed(rtl, mode, expect):
    rtl.set_rx_wiring(0, mode)
    try:
        rep = selftest.run(rtl, RegMap(rtl.ip), ["RX0"], selected=["idle", "polarity", "single"], speeds=("HS",))
    finally:
        rtl.set_rx_wiring(0, "loop")
    assert not rep["passed"]
    bad = _failed(rep)
    assert all(name.startswith("RX0") for _, name, _ in bad), bad          # TX BIT etkilenmez
    assert any(expect in detail for _, _, detail in bad), bad


def test_stop_flag_aborts(rtl):
    import threading
    ev = threading.Event()
    seen = []

    def on_result(r):
        seen.append(r.tid)
        if r.tid == "prep":
            ev.set()

    rep = selftest.run(rtl, RegMap(rtl.ip), ["RX0"], speeds=("HS",), stop=ev, on_result=on_result)
    assert rep["aborted"] and not rep["passed"]
    assert seen[:2] == ["ident", "prep"] and len(seen) == 3
