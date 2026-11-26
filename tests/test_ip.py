"""Çekirdek modül testleri: RegMap, ip.py, SimClient, model/txcfg/decode, proje uyumluluğu."""
import json
import zipfile

from a429.decode import DecodeSettings, Limits, decode_bits, decode_errors, decode_words, stats
from a429.ip import (
    ReadSettings, clear_channel, clear_tx_checker_fifo, read_channel, read_channel_status,
    read_rx_active_config, read_tx_active_config, read_tx_bit_status, recompare_active_config,
    send_rx_config, send_tx_config, set_channel_enable, set_tx_checker, soft_reset, tx_write,
)
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
    assert data["words"][0]["no"] == 22 and data["words"][-1]["no"] == 0
    assert len(data["errors"]) == 3
    assert len(data["bits"]) == 7 * 32
    assert data["bits"][0]["word"] == 22 and data["bits"][0]["bit"] == 0
    assert data["bits"][31]["word"] == 22 and data["bits"][31]["bit"] == 31
    assert data["bits"][32]["word"] == 21 and data["bits"][32]["bit"] == 0

    # "Son N kayıt" kısmi okuma da tek RADDR yazması + auto-increment ile doğru kayıtları getirmeli
    rs_last = ReadSettings(read_word="last", read_word_n=5, read_error="last", read_error_n=2, read_bit="last", read_bit_n=2)
    data_last = read_channel(sim, rm, "RX0", rs_last)
    assert [w["no"] for w in data_last["words"]] == [22, 21, 20, 19, 18]
    assert data_last["words"][0]["w"] == data["words"][0]["w"]
    assert data_last["words"][4]["w"] == data["words"][4]["w"]
    assert len(data_last["errors"]) == 2
    assert len(data_last["bits"]) == 2 * 32
    assert data_last["bits"][0]["w"] == data["bits"][0]["w"]

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

    # Canlı durum okuma, enable ve temizleme
    st0 = read_channel_status(sim, rm, "RX0")
    assert st0["word_cnt"] == 23 and st0["err_cnt"] == 3 and st0["enable"] is False
    set_channel_enable(sim, rm, "RX0", True)
    assert read_channel_status(sim, rm, "RX0")["enable"] is True
    clear_channel(sim, rm, "RX0")
    st1 = read_channel_status(sim, rm, "RX0")
    assert st1["word_cnt"] == 0 and st1["err_cnt"] == 0 and st1["enable"] is True


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

    # TX BIT Checker durumu ve kontrolü
    sim_tb = SimClient(num_rx=1, has_tx=True, has_txbit=True)
    rm_tb = RegMap(sim_tb.ip)
    tb0 = read_tx_bit_status(sim_tb, rm_tb)
    assert tb0["has_checker"] and tb0["tx_word_cnt"] == 12 and tb0["chk_ok_cnt"] == 11 and tb0["chk_err_cnt"] == 1
    set_tx_checker(sim_tb, rm_tb, True, 75000)
    assert read_tx_bit_status(sim_tb, rm_tb)["chk_timeout"] == 75000
    clear_tx_checker_fifo(sim_tb, rm_tb)
    assert read_tx_bit_status(sim_tb, rm_tb)["chk_en"] is True


def test_tx_driver_compensation_and_checks():
    ci = ConfigInputs()
    # Varsayılan HI-8597 ile tüm TX kontrolleri OK olmalı
    tx0 = compute_tx(ci)
    assert all(ok for _, ok in tx0["checks"]), [n for n, ok in tx0["checks"] if not ok]
    assert "Hatta oluşan Pulse süresi (µs)" in tx0["rows"]

    # Asimetrik tPHL > tPLH (+200 ns) verip gecikme telafisi açıldığında TX_CUST_PULSE_DUR kısalmalı
    ci.driver.tplh = (200.0, 400.0, 800.0)
    ci.driver.tphl = (400.0, 600.0, 1000.0)
    tx_nocomp = compute_tx(ci)
    p_nocomp = dict(tx_nocomp["writes"])["TX_CUST_PULSE_DUR"]
    ci.tx_comp_delay = True
    tx_comp = compute_tx(ci)
    p_comp = dict(tx_comp["writes"])["TX_CUST_PULSE_DUR"]
    assert p_comp < p_nocomp

    # Word Gap +ppm marjı açıldığında gap_clk >= 4 * bit_clk olmalı
    g0 = dict(tx_comp["writes"])["TX_CUST_GAP_DUR"]
    ci.tx_gap_margin = True
    tx_gm = compute_tx(ci)
    assert dict(tx_gm["writes"])["TX_CUST_GAP_DUR"] > g0

    # HIGH-Z desteklemeyen HS-3182 ile HIGH-Z override seçilirse uyarı vermeli
    ci.tx_driver = "HS-3182"
    tx_hiz = compute_tx(ci, override="HIGH-Z")
    assert any("HIGH-Z" in n and not ok for n, ok in tx_hiz["checks"])

    # DC uyumsuzluğu (VIH MIN > FPGA VOH MIN) yakalanmalı
    ci.driver.vih_min = 3.5
    tx_dc = compute_tx(ci)
    assert any("FPGA VOH MIN" in n and not ok for n, ok in tx_dc["checks"])


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


def test_active_config_check_and_recompare():
    sim = SimClient(num_rx=2, has_tx=True, has_txbit=True)
    rm = RegMap(sim.ip)
    ci = ConfigInputs()
    res = compute(ci, rm, "RX0")
    tx = compute_tx(ci, "Kapalı", rm)
    tx_exp = {r: v for r, v in tx["writes"] if r.startswith("TX_CUST_")}

    # Reset sonrası kartta High Speed (Preset) aktif olmalı
    rx0 = read_rx_active_config(sim, rm, "RX0", expected=res.rx_values)
    assert rx0["mode"] == 0 and "High Speed" in rx0["mode_name"]
    assert rx0["mismatch"] > 0 and not rx0["all_match"]

    tx0 = read_tx_active_config(sim, rm, expected=tx_exp)
    assert tx0["mode"] == 0 and "High Speed" in tx0["mode_name"]

    # Custom RX & TX config gönderilince Custom + tam eşleşme olmalı
    send_rx_config(sim, rm, "RX0", res.rx_values, verify=True)
    rx1 = read_rx_active_config(sim, rm, "RX0", expected=res.rx_values)
    assert rx1["mode"] == 2 and rx1["mode_name"] == "Custom"
    assert rx1["all_match"] and rx1["mismatch"] == 0

    send_tx_config(sim, rm, tx["writes"], verify=True)
    tx1 = read_tx_active_config(sim, rm, expected=tx_exp)
    assert tx1["mode"] == 2 and tx1["mode_name"] == "Custom"
    assert tx1["all_match"] and tx1["mismatch"] == 0

    # Arayüzdeki clock değişince recompare anında farkı yakalamalı
    ci.clk_mhz = 100.0
    res_new = compute(ci, rm, "RX0")
    rx2 = recompare_active_config(rx1, res_new.rx_values)
    assert rx2["mismatch"] > 0 and not rx2["all_match"]

    # SOFT_RESET.ALL sonrası tekrar High Speed (Preset)'e dönmeli
    soft_reset(sim, rm, "ALL")
    rx3 = read_rx_active_config(sim, rm, "RX0", expected=res.rx_values)
    tx3 = read_tx_active_config(sim, rm, expected=tx_exp)
    assert rx3["mode"] == 0 and tx3["mode"] == 0


def test_generated_axil_project_matches_regmap():
    with open("vhdl/axil/arinc429.axproj.json", encoding="utf-8") as fh:
        proj = json.load(fh)
    ip = proj["ips"][0]
    assert ip["panel"] == "arinc429"
    rm = RegMap(ip)
    assert rm.channels() == ["RX0", "TB"]
    for ch in rm.channels():
        assert rm.missing_for_rx_config(ch) == []
        assert rm.missing_for_rx_read(ch) == []
    assert rm.missing_for_tx_config() == []
    assert rm.missing_for_tx_live() == []
    assert rm.missing_for_reset() == []
