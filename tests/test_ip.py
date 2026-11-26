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
    # Gruplanmış harita: CFG_SEL ve APPLY tek register'da (RX0_CFG.APPLY = bit 4), APPLY en son yazılır
    assert writes[-1][0] == "RX0_CFG" and writes[-1][1] == (2 | (1 << 4))
    assert writes[0] == ("RX0_CFG", 2)

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
    ci.err = 0.10          # preset'ten (±%5) farklı Custom config
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


# ---------------------------------------------------------------- IP 2.x gruplanmış harita
from a429 import ipmap
from a429.regs import channel_prefix
from a429.ip import RecordReader, apply_fix, check_ip, plan_writes, read_fields, tx_write, write_fields


def test_ipmap_logical_names_resolve_and_bindings_complete():
    rm = RegMap(ipmap.to_ip_dict(num_rx=2))
    assert rm.grouped()
    for name, (reg, fld) in ipmap.LOGICAL_TX.items():
        r = rm.resolve(name)
        assert r is not None and r[0].name == reg and r[1].name == fld, name
    for ch in ("RX0", "RX1", "TB"):
        p = channel_prefix(ch)
        for suf in ipmap.LOGICAL_CH:
            assert rm.has(p + suf), p + suf
    # Her IP tarafı alan/strobe portunun bir VHDL bağlantısı var ve adlar benzersiz
    binds = ipmap.port_bindings(num_rx=2)
    names = [b[0] for b in binds]
    assert len(names) == len(set(names))
    assert ("o_tx_word_label_val", "out", 8, "tx_reg_in.label_val") in binds
    assert ("i_rx1_bit_rd_null_err", "in", 16, "rx_reg_out(1).bit_rd_null_err") in binds
    assert ("o_rx1_bit_rd_null_rd", "out", 1, "rx_reg_in(1).bit_rd_last") in binds
    # 16 bitlik çiftler tek register'da
    assert rm.location("RX0_CUST_MAX_PULSE") == "RX0_CUST_PULSE.MAX @ 0x4040[31:16]"
    assert rm.location("TX_LABEL") == "TX_WORD.LABEL_VAL @ 0x0404[7:0]"


def test_grouped_writes_merge_and_keep_other_fields():
    sim = SimClient()
    rm = RegMap(sim.ip)
    ops = plan_writes(rm, [("TX_LABEL", 0o310), ("TX_SDI", 1), ("TX_DATA", 0x12345), ("TX_SSM", 3), ("TX_PARITY_TYPE", 1)])
    assert len(ops) == 1 and ops[0][0] == "TX_WORD"
    assert ops[0][2] == 0o310 | (1 << 8) | (0x12345 << 10) | (3 << 29) | (1 << 31)
    # Kısmi yazma: TX_CTRL'deki diğer bitler korunur
    write_fields(sim, rm, [("TX_TRANSMITTER_EN", 1), ("TX_BUILDER_EN", 1)])
    tx_write(sim, rm, [("TX_MSG_SCHED_EN", 1)], verify=True)
    got = read_fields(sim, rm, ["TX_TRANSMITTER_EN", "TX_MSG_SCHED_EN", "TX_BUILDER_EN", "TX_SCHED_EN"])
    assert got == {"TX_TRANSMITTER_EN": 1, "TX_MSG_SCHED_EN": 1, "TX_BUILDER_EN": 1, "TX_SCHED_EN": 0}
    # CFG_SEL ... CUST ... CFG_APPLY: APPLY en son ve SEL korunarak
    ops = plan_writes(rm, [("TX_CFG_SEL", 2), ("TX_CUST_PULSE_DUR", 100), ("TX_CUST_NULL_DUR", 90), ("TX_CFG_APPLY", 1)])
    assert [o[0] for o in ops] == ["TX_CFG", "TX_CUST_TIMING", "TX_CFG"]
    assert ops[1][2] == 100 | (90 << 16) and ops[2][2] == 2 | (1 << 4)


def test_old_ungrouped_map_still_works():
    """IP 1.x (tek alanlı register'lar) haritası: aynı mantıksal adlar register'ın tamamına çözülür."""
    def reg(name, off, width=32):
        return {"name": name, "offset": hex(off), "access": "RO", "reset": "0",
                "fields": [{"name": name, "lsb": 0, "width": width, "kind": "RO"}]}
    old = RegMap({"registers": [reg("TX_LABEL", 0x40C, 8), reg("RX0_ERR_RD_TS_MSB", 0x4124), reg("RX0_ERR_RD_TS_LSB", 0x4128),
                                reg("RX0_ERR_RD_CODE", 0x412C, 16), reg("RX0_ERR_RD_ADDR", 0x4130, 16), reg("RX0_ERR_RD_DATA", 0x4134)]})
    assert not old.grouped()
    assert old.location("TX_LABEL") == "TX_LABEL @ 0x040C"
    rec = RecordReader(old, ["RX0_ERR_RD_TS_MSB", "RX0_ERR_RD_TS_LSB", "RX0_ERR_RD_CODE", "RX0_ERR_RD_ADDR", "RX0_ERR_RD_DATA"])
    assert len(rec) == 5 and rec.decode([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]
    new = RegMap(ipmap.to_ip_dict())
    rec2 = RecordReader(new, ["RX0_ERR_RD_TS_MSB", "RX0_ERR_RD_TS_LSB", "RX0_ERR_RD_CODE", "RX0_ERR_RD_ADDR", "RX0_ERR_RD_DATA"])
    assert len(rec2) == 4 and rec2.decode([1, 2, 3 | (4 << 16), 5]) == [1, 2, 3, 4, 5]
    assert new.regs[rec2.phys[-1]].name == "RX0_ERR_RD_DATA"      # rd_strobe'lu register en son okunur


def test_ip_health_check_finds_disabled_logger_and_stuck_line():
    sim = SimClient(num_rx=1)
    rm = RegMap(sim.ip)
    res = check_ip(sim, rm, clk_hz=50_000_000)
    rx_off = [f for f in res["findings"] if f["area"] == "RX0" and f["fix"] == ("enable", "RX0")]
    assert res["worst"] == "error" and rx_off and rx_off[0]["level"] == "error"
    apply_fix(sim, rm, rx_off[0]["fix"])
    apply_fix(sim, rm, ("enable", "TB"))
    res = check_ip(sim, rm, clk_hz=50_000_000)
    assert not any(f["fix"] == ("enable", "RX0") for f in res["findings"])
    assert any(f["area"] == "IP" and f["title"].startswith("IP sürümü 2.") for f in res["findings"])

    sim.sim_line["RX0"] = (1, 1)            # ters bağlı alıcı: boşta 11
    res = check_ip(sim, rm)
    assert any(f["area"] == "RX0" and f["level"] == "error" and "11" in f["title"] for f in res["findings"])
    st = read_channel_status(sim, rm, "RX0")
    assert st["line_high"] and st["line_low"] and st["sync_wait"]

    # Saat uyuşmazlığı ve TX/TB hız uyuşmazlığı
    res = check_ip(sim, rm, clk_hz=100_000_000)
    assert any("MHz" in f["title"] for f in res["findings"] if f["level"] == "warn")
    write_fields(sim, rm, [("TX_CFG_SEL", 1), ("TX_CFG_APPLY", 1)])   # TX Low Speed, TB High Speed
    res = check_ip(sim, rm)
    assert any(f["area"] == "TX BIT" and "kabul aralığı" in f["title"] and f["level"] == "warn" for f in res["findings"])
