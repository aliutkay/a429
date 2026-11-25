"""Çekirdek modül testleri: RegMap, ip.py, SimClient, model/txcfg/decode, proje uyumluluğu."""
import json
import zipfile

from a429.decode import DecodeSettings, Limits, decode_bits, decode_errors, decode_words, stats
from a429.ip import ReadSettings, read_channel, send_rx_config, send_tx_config, soft_reset, tx_write
from a429.model import ConfigInputs, compute
from a429.project import load_project, new_session, save_project
from a429.regs import RegMap
from a429.sim import SimClient
from a429.txcfg import compute_tx


def test_regmap_discovery_and_missing():
    sim = SimClient(num_rx=3, has_tx=True, has_txbit=True)
    rm = RegMap(sim.ip)
    assert rm.channels() == ["RX0", "RX1", "RX2", "TB"]
    assert rm.has_tx()
    assert rm.missing_for_rx_config("RX0") == []
    assert rm.missing_for_rx_read("RX0") == []
    assert rm.missing_for_rx_read("TB") == []
    assert rm.missing_for_tx_config() == []
    assert rm.missing_for_tx_live() == []
    assert rm.missing_for_reset() == []

    # Boş harita (çevrimdışı)
    empty = RegMap.empty()
    assert not empty.is_loaded()
    assert empty.channels() == ["RX0"]
    assert len(empty.missing_for_rx_config("RX0")) > 0


def test_rx_config_and_read_channel():
    sim = SimClient(num_rx=2, has_tx=True, has_txbit=True)
    rm = RegMap(sim.ip)
    ci = ConfigInputs()
    res = compute(ci, rm, "RX0")
    assert len(res.rx_values) == 8
    assert all(r[5] is None for r in res.regs)

    writes = []
    send_rx_config(sim, rm, "RX0", res.rx_values, verify=True, on_write=lambda n, o, v: writes.append((n, v)))
    assert any(n == "RX0_CFG_APPLY" for n, _ in writes)

    rs = ReadSettings()
    data = read_channel(sim, rm, "RX0", rs)
    assert not sim.locked
    # FREEZE temizlenmiş olmalı
    assert (sim.read(rm.offset("RX0_CTRL")) & 2) == 0
    assert data["channel"] == "RX0"
    assert len(data["words"]) == 23
    assert len(data["errors"]) == 3
    assert len(data["bits"]) == 7 * 32

    ds = DecodeSettings()
    lim = Limits.from_result(res, ci.clk_mhz)
    wrows = decode_words(data, lim, ds)
    brows = decode_bits(data, lim)
    erows = decode_errors(data)
    st_rows, st_chk = stats(data, lim, data["wdepth"], data["edepth"], data["bit_words"])
    assert len(wrows) == 23
    assert len(brows) == 7 * 32
    assert len(erows) == 3
    assert len(st_rows) > 0
    assert all(c[1] != "FAIL" for c in st_chk)


def test_tx_config_and_live_write():
    sim = SimClient(num_rx=1, has_tx=True, has_txbit=False)
    rm = RegMap(sim.ip)
    ci = ConfigInputs()
    tx = compute_tx(ci, "Kapalı", rm)
    assert tx["errors"] == []
    send_tx_config(sim, rm, tx["writes"], verify=True)

    before = sim.read(rm.offset("TX_WORD_CNT"))
    tx_write(sim, rm, [("TX_MSG_SCHED_EN", 0), ("TX_SEND_CMD", 1)], verify=True)
    assert sim.read(rm.offset("TX_WORD_CNT")) == before + 1

    soft_reset(sim, rm, "ALL")


def test_legacy_project_compatibility(tmp_path):
    legacy = {
        "version": 1,
        "config": {
            "clk_mhz": 80.0,
            "profile": "High Speed (100k)",
            "regmap": {"write_cmd": "C3 00 {IP} {REG} {DATA32}", "ip_port": "01"},
        },
        "link": {
            "port": "COM44",
            "baud": 115200,
            "read_word": "last",
            "read_word_n": 10,
            "out_dir": "/tmp/a429",
        },
        "decode": {"parity_odd": False},
        "sessions": [],
    }
    p = tmp_path / "legacy.a429proj"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("project.json", json.dumps(legacy))

    ci, rs, ds, sessions = load_project(str(p))
    assert ci.clk_mhz == 80.0
    assert rs.read_word == "last"
    assert rs.read_word_n == 10
    assert ds.parity_odd is False
    assert sessions == []

    # Yeni formatta tekrar kaydet ve aç
    sim = SimClient()
    data = read_channel(sim, RegMap(sim.ip), "RX0", rs)
    s = new_session(data, ci, rs, ds)
    p2 = tmp_path / "new.a429proj"
    save_project(str(p2), ci, rs, ds, [s])
    ci2, rs2, ds2, sessions2 = load_project(str(p2))
    assert ci2.clk_mhz == 80.0
    assert len(sessions2) == 1
    assert sessions2[0]["channel"] == "RX0"
