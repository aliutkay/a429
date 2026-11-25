#!/usr/bin/env python3
"""ARINC 429 IP için AXIL Studio (.regspec.json / .axproj.json) üreteci.

Kullanım:
  python3 vhdl/scripts/gen_axil_spec.py -o vhdl/axil --num-rx 2 --axil-studio /yol/axil-studio

AXIL Studio yolu verilmezse yalnızca arinc429_axil.regspec.json ve arinc429.axproj.json
dosyalarını üretir; bu dosyalar doğrudan AXIL Studio'da açılıp Slave Interface Wrapper ile
AXI4-Lite slave (arinc429_axil.v / arinc429_axil_pk.v / testbench) üretilebilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _field(name: str, lsb: int, width: int = 1, kind: str = "RW", reset: int = 0, desc: str = "") -> dict:
    return {
        "name": name,
        "lsb": lsb,
        "width": width,
        "kind": kind,
        "reset": f"0x{reset:X}",
        "desc": desc,
    }


def _reg(
    name: str,
    offset: int,
    fields: list[dict],
    desc: str = "",
    wr_strobe: bool = False,
    rd_strobe: bool = False,
) -> dict:
    d = {
        "name": name,
        "offset": f"0x{offset:04X}",
        "desc": desc,
        "fields": fields,
    }
    if wr_strobe:
        d["wr_strobe"] = True
    if rd_strobe:
        d["rd_strobe"] = True
    return d


def _sreg(name: str, offset: int, width: int, kind: str = "RW", reset: int = 0, desc: str = "", **kw) -> dict:
    """Tek alanlı register (alan adı = register adı -> kısa port adı o_<reg> / i_<reg>)."""
    return _reg(name, offset, [_field(name, 0, width, kind, reset, desc)], desc=desc, **kw)


def build_regspec(
    module: str = "arinc429_axil",
    num_rx: int = 2,
    has_tx: bool = True,
    has_txbit: bool = True,
    has_bitdiag: bool = True,
    clk_hz: int = 50_000_000,
    wdepth_log2: int = 8,
    edepth_log2: int = 8,
    bitdiag_log2: int = 3,
    packed: bool = True,
) -> dict:
    if not has_tx:
        has_txbit = False
    regs: list[dict] = []

    # ---- Global sayfa (0x0000)
    regs.append(_sreg("IP_ID", 0x0000, 32, "CONST", 0x41343239, "ARINC 429 IP kimliği ('A429')"))
    regs.append(_sreg("IP_VERSION", 0x0004, 32, "CONST", 0x00010000, "IP sürümü (1.0.0)"))
    regs.append(_reg("CAPS", 0x0008, [
        _field("NUM_RX", 0, 5, "CONST", num_rx, "RX kanal sayısı"),
        _field("TX", 8, 1, "CONST", int(has_tx), "TX kanalı var"),
        _field("TXBIT", 9, 1, "CONST", int(has_txbit), "TX BIT kanalı var"),
        _field("RX_TEST", 10, 1, "CONST", 0, "RX test pinleri var"),
        _field("BITDIAG", 11, 1, "CONST", int(has_bitdiag), "Bit diagnostic RAM var"),
    ], "Donanım yetenekleri"))
    regs.append(_reg("CAPS_MEM", 0x000C, [
        _field("WORD_DEPTH_LOG2", 0, 8, "CONST", wdepth_log2, "Word RAM derinliği (log2)"),
        _field("ERR_DEPTH_LOG2", 8, 8, "CONST", edepth_log2, "Error RAM derinliği (log2)"),
        _field("BITDIAG_WORDS_LOG2", 16, 8, "CONST", bitdiag_log2, "Bit diagnostic Word sayısı (log2)"),
    ], "RAM derinlikleri"))
    regs.append(_sreg("CLK_HZ", 0x0010, 32, "CONST", clk_hz, "IP sistem saati (Hz)"))

    rst_fields = [
        _field("RST_ALL", 0, 1, "PULSE", 0, "Tüm IP yumuşak reseti"),
        _field("TX", 1, 1, "PULSE", 0, "TX kanalı reseti"),
        _field("TXBIT", 2, 1, "PULSE", 0, "TX BIT kanalı reseti"),
    ]
    for n in range(num_rx):
        rst_fields.append(_field(f"RX{n}", 16 + n, 1, "PULSE", 0, f"RX{n} kanalı reseti"))
    regs.append(_reg("SOFT_RESET", 0x0020, rst_fields, "Yumuşak reset darbeleri (self-clearing)"))
    regs.append(_sreg("GLOBAL_FREEZE", 0x0024, 1, "RW", 0, "Tüm logger'ları eşzamanlı dondur"))
    regs.append(_reg("TS_CTRL", 0x0028, [
        _field("ENABLE", 0, 1, "RW", 1, "64-bit timestamp sayacı etkin"),
        _field("CLEAR", 1, 1, "PULSE", 0, "Timestamp sayacını sıfırla"),
    ], "Timestamp kontrol"))
    regs.append(_sreg("TS_LSB", 0x002C, 32, "RO", 0, "Timestamp alt 32 bit (okununca MSB latch'lenir)", rd_strobe=True))
    regs.append(_sreg("TS_MSB", 0x0030, 32, "RO", 0, "Latch'lenmiş timestamp üst 32 bit"))

    # ---- TX sayfası (0x0400)
    if has_tx:
        tb = 0x0400
        regs += [
            _sreg("TX_TRANSMITTER_EN", tb + 0x00, 1, "RW", 0, "1: Word Transmitter, 0: EXT_HIGH/LOW override"),
            _sreg("TX_MSG_SCHED_EN", tb + 0x04, 1, "RW", 0, "1: Message Scheduler, 0: SEND_CMD tek gönderim"),
            _sreg("TX_BUILDER_EN", tb + 0x08, 1, "RW", 0, "1: Word Builder alanları, 0: EXT_DATA"),
            _sreg("TX_LABEL", tb + 0x0C, 8, "RW", 0, "ARINC 429 Label (octal 000-377)"),
            _sreg("TX_SDI", tb + 0x10, 2, "RW", 0, "SDI (0-3)"),
            _sreg("TX_DATA", tb + 0x14, 19, "RW", 0, "Data (19-bit)"),
            _sreg("TX_SSM", tb + 0x18, 2, "RW", 0, "SSM (0-3)"),
            _sreg("TX_PARITY_TYPE", tb + 0x1C, 1, "RW", 1, "Parity tipi (1: Odd, 0: Even)"),
            _sreg("TX_SCHED_EN", tb + 0x20, 1, "RW", 0, "Message Scheduler başlat/durdur"),
            _sreg("TX_INITIAL_DELAY", tb + 0x24, 32, "RW", 0, "Scheduler başlangıç gecikmesi (clk)"),
            _sreg("TX_INTER_WORD_GAP", tb + 0x28, 32, "RW", 1, "Scheduler Word arası ekstra bekleme (clk, >=1)"),
            _reg("TX_SEND_CMD", tb + 0x2C, [_field("SEND", 0, 1, "PULSE", 0, "Tek Word gönderim tetiği")], "Tek gönderim darbesi"),
            _sreg("TX_EXT_DATA", tb + 0x30, 32, "RW", 0, "Hazır 32-bit Word"),
            _sreg("TX_EXT_HIGH", tb + 0x34, 1, "RW", 0, "Hat override HIGH çıkışı"),
            _sreg("TX_EXT_LOW", tb + 0x38, 1, "RW", 0, "Hat override LOW çıkışı"),
            _sreg("TX_CFG_SEL", tb + 0x40, 2, "RW", 0, "Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom)"),
            _reg("TX_CFG_APPLY", tb + 0x44, [_field("APPLY", 0, 1, "PULSE", 0, "Seçili TX config'i etkinleştir")], "TX Config uygula"),
            _sreg("TX_CUST_PULSE_DUR", tb + 0x48, 16, "RW", 0, "Custom Pulse süresi (clk)"),
            _sreg("TX_CUST_NULL_DUR", tb + 0x4C, 16, "RW", 0, "Custom Null süresi (clk)"),
            _sreg("TX_CUST_GAP_DUR", tb + 0x50, 32, "RW", 0, "Custom Word Gap süresi (clk)"),
            _sreg("TX_CUST_SLP", tb + 0x54, 1, "RW", 0, "Custom SLP eğim çıkışı (1: HS, 0: LS)"),
            _sreg("TX_ACT_PULSE_DUR", tb + 0x60, 16, "RO", 0, "Aktif Pulse süresi (clk)"),
            _sreg("TX_ACT_NULL_DUR", tb + 0x64, 16, "RO", 0, "Aktif Null süresi (clk)"),
            _sreg("TX_ACT_GAP_DUR", tb + 0x68, 32, "RO", 0, "Aktif Word Gap süresi (clk)"),
            _sreg("TX_ACT_SLP", tb + 0x6C, 1, "RO", 0, "Aktif SLP eğim çıkışı"),
            _reg("TX_STATUS", tb + 0x80, [
                _field("BUSY", 0, 1, "RO", 0, "TX gönderim yapıyor"),
                _field("SCHED_ACTIVE", 1, 1, "RO", 0, "Scheduler aktif"),
                _field("ACT_CFG", 2, 2, "RO", 0, "Aktif TX config modu (0:HS, 1:LS, 2:Custom)"),
            ], "TX durum register'ı"),
            _sreg("TX_WORD_CNT", tb + 0x84, 32, "RO", 0, "Gönderilen toplam Word sayısı"),
        ]

    # ---- Kanal sayfası (TB ve RX0..RXn ortak)
    def add_rx_page(prefix: str, base: int, has_checker: bool):
        regs.extend([
            _reg(prefix + "CTRL", base + 0x00, [
                _field("ENABLE", 0, 1, "RW", 0, "Logger kayıt etkin"),
                _field("FREEZE", 1, 1, "RW", 0, "RAM okuma için dondur"),
                _field("CLEAR", 2, 1, "PULSE", 0, "Sayaç ve RAM pointer'larını temizle"),
            ], f"{prefix} kanal kontrolü"),
            _reg(prefix + "STATUS", base + 0x04, [
                _field("FROZEN", 4, 1, "RO", 0, "Logger donduruldu"),
                _field("WORD_WRAP", 5, 1, "RO", 0, "Word RAM taştı/döndü"),
                _field("ERR_WRAP", 6, 1, "RO", 0, "Error RAM taştı/döndü"),
                _field("ACT_CFG", 8, 2, "RO", 0, "Aktif RX config modu (0:HS, 1:LS, 2:Custom)"),
            ], f"{prefix} kanal durumu"),
            _sreg(prefix + "CFG_SEL", base + 0x08, 2, "RW", 0, "Config seçimi (0: HS, 1: LS, 2: Custom)"),
            _reg(prefix + "CFG_APPLY", base + 0x0C, [_field("APPLY", 0, 1, "PULSE", 0, "Seçili RX config'i uygula")], "RX Config uygula"),
            _sreg(prefix + "CUST_GLITCH_FILTER_SIZE", base + 0x40, 16, "RW", 0, "Custom Glitch Filter boyu (clk)"),
            _sreg(prefix + "CUST_MIN_PULSE", base + 0x44, 16, "RW", 0, "Custom Min Pulse (clk)"),
            _sreg(prefix + "CUST_MAX_PULSE", base + 0x48, 16, "RW", 0, "Custom Max Pulse (clk)"),
            _sreg(prefix + "CUST_MIN_BIT", base + 0x4C, 16, "RW", 0, "Custom Min Bit (clk)"),
            _sreg(prefix + "CUST_MAX_BIT", base + 0x50, 16, "RW", 0, "Custom Max Bit (clk)"),
            _sreg(prefix + "CUST_MAX_PULSE_ERR", base + 0x54, 16, "RW", 0, "Custom Max Pulse Glitch Error"),
            _sreg(prefix + "CUST_MAX_NULL_ERR", base + 0x58, 16, "RW", 0, "Custom Max Null Glitch Error"),
            _sreg(prefix + "CUST_MAX_GAP_ERR", base + 0x5C, 16, "RW", 0, "Custom Max Gap Glitch Error"),
            _sreg(prefix + "CUST_PARITY_MODE", base + 0x60, 2, "RW", 1, "Custom Parity modu (0:Kapalı, 1:Odd, 2:Even)"),
            _sreg(prefix + "ACT_GLITCH_FILTER_SIZE", base + 0xA0, 16, "RO", 0, "Aktif Glitch Filter boyu (clk)"),
            _sreg(prefix + "ACT_MIN_PULSE", base + 0xA4, 16, "RO", 0, "Aktif Min Pulse (clk)"),
            _sreg(prefix + "ACT_MAX_PULSE", base + 0xA8, 16, "RO", 0, "Aktif Max Pulse (clk)"),
            _sreg(prefix + "ACT_MIN_BIT", base + 0xAC, 16, "RO", 0, "Aktif Min Bit (clk)"),
            _sreg(prefix + "ACT_MAX_BIT", base + 0xB0, 16, "RO", 0, "Aktif Max Bit (clk)"),
            _sreg(prefix + "ACT_MAX_PULSE_ERR", base + 0xB4, 16, "RO", 0, "Aktif Max Pulse Glitch Error"),
            _sreg(prefix + "ACT_MAX_NULL_ERR", base + 0xB8, 16, "RO", 0, "Aktif Max Null Glitch Error"),
            _sreg(prefix + "ACT_MAX_GAP_ERR", base + 0xBC, 16, "RO", 0, "Aktif Max Gap Glitch Error"),
            _sreg(prefix + "ACT_PARITY_MODE", base + 0xC0, 2, "RO", 0, "Aktif Parity modu"),
            _sreg(prefix + "WORD_CNT", base + 0xE0, 32, "RO", 0, "Geçerli Word sayısı"),
            _sreg(prefix + "ERR_CNT", base + 0xE4, 32, "RO", 0, "Hata kaydı sayısı"),
            _sreg(prefix + "DROP_CNT", base + 0xE8, 32, "RO", 0, "Freeze sırasında atılan kayıt sayısı"),
            _sreg(prefix + "LAST_WORD", base + 0xEC, 32, "RO", 0, "Alınan son geçerli Word"),
            _sreg(prefix + "WORD_RADDR", base + 0x100, wdepth_log2, "RW", 0, "Word RAM başlangıç okuma adresi (yazınca pointer yüklenir)", wr_strobe=True),
            _sreg(prefix + "WORD_RD_TS_MSB", base + 0x104, 32, "RO", 0, "Word kaydı Timestamp MSB"),
            _sreg(prefix + "WORD_RD_TS_LSB", base + 0x108, 32, "RO", 0, "Word kaydı Timestamp LSB"),
            _sreg(prefix + "WORD_RD_DATA", base + 0x10C, 32, "RO", 0, "Word kaydı 32-bit veri"),
            _sreg(prefix + "WORD_RD_GAP", base + 0x110, 32, "RO", 0, "Word kaydı önceki Gap süresi (clk)"),
            _sreg(prefix + "WORD_RD_GAP_ERR", base + 0x114, 16, "RO", 0, "Word kaydı Gap gürültü sayısı (okununca pointer +1)", rd_strobe=True),
            _sreg(prefix + "ERR_RADDR", base + 0x120, edepth_log2, "RW", 0, "Error RAM başlangıç okuma adresi (yazınca pointer yüklenir)", wr_strobe=True),
            _sreg(prefix + "ERR_RD_TS_MSB", base + 0x124, 32, "RO", 0, "Error kaydı Timestamp MSB"),
            _sreg(prefix + "ERR_RD_TS_LSB", base + 0x128, 32, "RO", 0, "Error kaydı Timestamp LSB"),
            _sreg(prefix + "ERR_RD_CODE", base + 0x12C, 16, "RO", 0, "Error kaydı hata kodu bitmask"),
            _sreg(prefix + "ERR_RD_ADDR", base + 0x130, 16, "RO", 0, "Error kaydı konum/bit/FIFO adresi"),
            _sreg(prefix + "ERR_RD_DATA", base + 0x134, 32, "RO", 0, "Error kaydı ölçüm/beklenen veri (okununca pointer +1)", rd_strobe=True),
            _reg(prefix + "BIT_RADDR", base + 0x140, [
                _field("BIT_IDX", 0, 5, "RW", 0, "Bit indeksi (0-31)"),
                _field("WORD_IDX", 8, bitdiag_log2, "RW", 0, "Bit Diagnostic Word indeksi"),
            ], "Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir)", wr_strobe=True),
            _sreg(prefix + "BIT_RD_PULSE", base + 0x144, 16, "RO", 0, "Bit Pulse süresi (clk)"),
            _sreg(prefix + "BIT_RD_PULSE_ERR", base + 0x148, 16, "RO", 0, "Bit Pulse gürültü sayısı"),
            _sreg(prefix + "BIT_RD_NULL", base + 0x14C, 16, "RO", 0, "Bit Null süresi (clk)"),
            _sreg(prefix + "BIT_RD_NULL_ERR", base + 0x150, 16, "RO", 0, "Bit Null gürültü sayısı (okununca pointer +1)", rd_strobe=True),
        ])
        if has_checker:
            regs.extend([
                _reg(prefix + "CHK_CTRL", base + 0x1C0, [
                    _field("ENABLE", 0, 1, "RW", 0, "Word Checker etkin"),
                    _field("CLEAR", 1, 1, "PULSE", 0, "Checker FIFO ve sayaçlarını temizle"),
                ], "TX BIT Word Checker kontrol"),
                _sreg(prefix + "CHK_TIMEOUT", base + 0x1C4, 32, "RW", 0, "Echo zaman aşımı (clk, 0=kapalı)"),
                _sreg(prefix + "CHK_OK_CNT", base + 0x1C8, 32, "RO", 0, "Eşleşen Word sayısı"),
                _sreg(prefix + "CHK_ERR_CNT", base + 0x1CC, 32, "RO", 0, "Checker hata sayısı"),
                _reg(prefix + "CHK_STATUS", base + 0x1D0, [
                    _field("FIFO_LEVEL", 0, 4, "RO", 0, "Beklenen Word FIFO doluluğu"),
                    _field("FIFO_OVF", 4, 1, "RO", 0, "FIFO taşma bayrağı"),
                ], "TX BIT Checker FIFO durumu"),
            ])

    if has_txbit:
        add_rx_page("TB_", 0x0800, has_checker=True)
    for n in range(num_rx):
        add_rx_page(f"RX{n}_", 0x4000 + n * 0x0400, has_checker=False)

    return {
        "format": "axil-regspec",
        "version": 1,
        "module": module,
        "desc": f"ARINC 429 IP ({num_rx} RX, TX={'Var' if has_tx else 'Yok'}, TX BIT={'Var' if has_txbit else 'Yok'}, {clk_hz // 1_000_000} MHz)",
        "packed": packed,
        "ip_version": "1.0.0",
        "panel": "arinc429",
        "registers": sorted(regs, key=lambda r: int(r["offset"], 0)),
    }


def _reg_access(reg: dict) -> str:
    kinds = {f["kind"] for f in reg["fields"]}
    if kinds <= {"RO", "CONST"}:
        return "RO"
    if kinds <= {"PULSE"}:
        return "WO"
    return "RW"


def _reg_reset(reg: dict) -> int:
    v = 0
    for f in reg["fields"]:
        if f["kind"] in ("RW", "CONST"):
            mask = ((1 << f["width"]) - 1) << f["lsb"]
            v |= (int(f["reset"], 0) << f["lsb"]) & mask
    return v


def build_axproj(spec: dict, ip_name: str = "ARINC429", base: int = 0x40000000) -> dict:
    ip_regs = []
    for r in spec["registers"]:
        ip_regs.append({
            "name": r["name"],
            "offset": f"0x{int(r['offset'], 0):08X}",
            "access": _reg_access(r),
            "reset": f"0x{_reg_reset(r):08X}",
            "desc": r.get("desc", ""),
            "fields": [
                {"name": f["name"], "lsb": f["lsb"], "width": f["width"], "desc": f.get("desc", ""), "kind": f["kind"]}
                for f in r["fields"]
            ],
        })
    return {
        "format": "axil-uart-project",
        "version": 2,
        "name": "ARINC 429 IP",
        "ips": [
            {
                "name": ip_name,
                "desc": spec["desc"],
                "version": spec["ip_version"],
                "panel": "arinc429",
                "regspec": spec,
                "registers": ip_regs,
            }
        ],
        "instances": [
            {
                "name": f"{ip_name}_0",
                "ip": ip_name,
                "base": f"0x{base:08X}",
                "window": "0x10000",
                "fixed": True,
            }
        ],
    }


def _vhdl_type(width: int) -> str:
    return "std_logic" if width == 1 else f"std_logic_vector({width - 1} downto 0)"


def build_top_vhd(
    module: str = "arinc429_axil",
    num_rx: int = 2,
    has_tx: bool = True,
    has_txbit: bool = True,
    wdepth_log2: int = 8,
    edepth_log2: int = 8,
    bitdiag_log2: int = 3,
) -> str:
    """AXIL Studio arinc429_axil (AXI4-Lite slave) + arinc429_core (VHDL) top wrapper üretir."""
    if not has_tx:
        has_txbit = False
    n_rx_vec = max(num_rx, 1)

    comp_ports: list[tuple[str, str, str]] = [
        ("S_AXI_ACLK", "in", "std_logic"),
        ("S_AXI_ARESETN", "in", "std_logic"),
        ("S_AXI_AWVALID", "in", "std_logic"),
        ("S_AXI_AWREADY", "out", "std_logic"),
        ("S_AXI_AWADDR", "in", "std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0)"),
        ("S_AXI_AWPROT", "in", "std_logic_vector(2 downto 0)"),
        ("S_AXI_WVALID", "in", "std_logic"),
        ("S_AXI_WREADY", "out", "std_logic"),
        ("S_AXI_WDATA", "in", "std_logic_vector(31 downto 0)"),
        ("S_AXI_WSTRB", "in", "std_logic_vector(3 downto 0)"),
        ("S_AXI_BVALID", "out", "std_logic"),
        ("S_AXI_BREADY", "in", "std_logic"),
        ("S_AXI_BRESP", "out", "std_logic_vector(1 downto 0)"),
        ("S_AXI_ARVALID", "in", "std_logic"),
        ("S_AXI_ARREADY", "out", "std_logic"),
        ("S_AXI_ARADDR", "in", "std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0)"),
        ("S_AXI_ARPROT", "in", "std_logic_vector(2 downto 0)"),
        ("S_AXI_RVALID", "out", "std_logic"),
        ("S_AXI_RREADY", "in", "std_logic"),
        ("S_AXI_RDATA", "out", "std_logic_vector(31 downto 0)"),
        ("S_AXI_RRESP", "out", "std_logic_vector(1 downto 0)"),
        # Global
        ("o_soft_reset_rst_all", "out", "std_logic"),
        ("o_soft_reset_tx", "out", "std_logic"),
        ("o_soft_reset_txbit", "out", "std_logic"),
    ]
    for n in range(num_rx):
        comp_ports.append((f"o_soft_reset_rx{n}", "out", "std_logic"))
    comp_ports += [
        ("o_global_freeze", "out", "std_logic"),
        ("o_ts_ctrl_enable", "out", "std_logic"),
        ("o_ts_ctrl_clear", "out", "std_logic"),
        ("i_ts_lsb", "in", "std_logic_vector(31 downto 0)"),
        ("o_ts_lsb_rd", "out", "std_logic"),
        ("i_ts_msb", "in", "std_logic_vector(31 downto 0)"),
    ]

    if has_tx:
        comp_ports += [
            ("o_tx_transmitter_en", "out", "std_logic"),
            ("o_tx_msg_sched_en", "out", "std_logic"),
            ("o_tx_builder_en", "out", "std_logic"),
            ("o_tx_label", "out", "std_logic_vector(7 downto 0)"),
            ("o_tx_sdi", "out", "std_logic_vector(1 downto 0)"),
            ("o_tx_data", "out", "std_logic_vector(18 downto 0)"),
            ("o_tx_ssm", "out", "std_logic_vector(1 downto 0)"),
            ("o_tx_parity_type", "out", "std_logic"),
            ("o_tx_sched_en", "out", "std_logic"),
            ("o_tx_initial_delay", "out", "std_logic_vector(31 downto 0)"),
            ("o_tx_inter_word_gap", "out", "std_logic_vector(31 downto 0)"),
            ("o_tx_send_cmd_send", "out", "std_logic"),
            ("o_tx_ext_data", "out", "std_logic_vector(31 downto 0)"),
            ("o_tx_ext_high", "out", "std_logic"),
            ("o_tx_ext_low", "out", "std_logic"),
            ("o_tx_cfg_sel", "out", "std_logic_vector(1 downto 0)"),
            ("o_tx_cfg_apply_apply", "out", "std_logic"),
            ("o_tx_cust_pulse_dur", "out", "std_logic_vector(15 downto 0)"),
            ("o_tx_cust_null_dur", "out", "std_logic_vector(15 downto 0)"),
            ("o_tx_cust_gap_dur", "out", "std_logic_vector(31 downto 0)"),
            ("o_tx_cust_slp", "out", "std_logic"),
            ("i_tx_act_pulse_dur", "in", "std_logic_vector(15 downto 0)"),
            ("i_tx_act_null_dur", "in", "std_logic_vector(15 downto 0)"),
            ("i_tx_act_gap_dur", "in", "std_logic_vector(31 downto 0)"),
            ("i_tx_act_slp", "in", "std_logic"),
            ("i_tx_status_busy", "in", "std_logic"),
            ("i_tx_status_sched_active", "in", "std_logic"),
            ("i_tx_status_act_cfg", "in", "std_logic_vector(1 downto 0)"),
            ("i_tx_word_cnt", "in", "std_logic_vector(31 downto 0)"),
        ]

    def add_ch_comp(p: str, chk: bool):
        comp_ports.extend([
            (f"o_{p}ctrl_enable", "out", "std_logic"),
            (f"o_{p}ctrl_freeze", "out", "std_logic"),
            (f"o_{p}ctrl_clear", "out", "std_logic"),
            (f"i_{p}status_frozen", "in", "std_logic"),
            (f"i_{p}status_word_wrap", "in", "std_logic"),
            (f"i_{p}status_err_wrap", "in", "std_logic"),
            (f"i_{p}status_act_cfg", "in", "std_logic_vector(1 downto 0)"),
            (f"o_{p}cfg_sel", "out", "std_logic_vector(1 downto 0)"),
            (f"o_{p}cfg_apply_apply", "out", "std_logic"),
            (f"o_{p}cust_glitch_filter_size", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_min_pulse", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_max_pulse", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_min_bit", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_max_bit", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_max_pulse_err", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_max_null_err", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_max_gap_err", "out", "std_logic_vector(15 downto 0)"),
            (f"o_{p}cust_parity_mode", "out", "std_logic_vector(1 downto 0)"),
            (f"i_{p}act_glitch_filter_size", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_min_pulse", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_max_pulse", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_min_bit", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_max_bit", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_max_pulse_err", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_max_null_err", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_max_gap_err", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}act_parity_mode", "in", "std_logic_vector(1 downto 0)"),
            (f"i_{p}word_cnt", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}err_cnt", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}drop_cnt", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}last_word", "in", "std_logic_vector(31 downto 0)"),
            (f"o_{p}word_raddr", "out", _vhdl_type(wdepth_log2)),
            (f"o_{p}word_raddr_wr", "out", "std_logic"),
            (f"i_{p}word_rd_ts_msb", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}word_rd_ts_lsb", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}word_rd_data", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}word_rd_gap", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}word_rd_gap_err", "in", "std_logic_vector(15 downto 0)"),
            (f"o_{p}word_rd_gap_err_rd", "out", "std_logic"),
            (f"o_{p}err_raddr", "out", _vhdl_type(edepth_log2)),
            (f"o_{p}err_raddr_wr", "out", "std_logic"),
            (f"i_{p}err_rd_ts_msb", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}err_rd_ts_lsb", "in", "std_logic_vector(31 downto 0)"),
            (f"i_{p}err_rd_code", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}err_rd_addr", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}err_rd_data", "in", "std_logic_vector(31 downto 0)"),
            (f"o_{p}err_rd_data_rd", "out", "std_logic"),
            (f"o_{p}bit_raddr_bit_idx", "out", "std_logic_vector(4 downto 0)"),
            (f"o_{p}bit_raddr_word_idx", "out", _vhdl_type(bitdiag_log2)),
            (f"o_{p}bit_raddr_wr", "out", "std_logic"),
            (f"i_{p}bit_rd_pulse", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}bit_rd_pulse_err", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}bit_rd_null", "in", "std_logic_vector(15 downto 0)"),
            (f"i_{p}bit_rd_null_err", "in", "std_logic_vector(15 downto 0)"),
            (f"o_{p}bit_rd_null_err_rd", "out", "std_logic"),
        ])
        if chk:
            comp_ports.extend([
                (f"o_{p}chk_ctrl_enable", "out", "std_logic"),
                (f"o_{p}chk_ctrl_clear", "out", "std_logic"),
                (f"o_{p}chk_timeout", "out", "std_logic_vector(31 downto 0)"),
                (f"i_{p}chk_ok_cnt", "in", "std_logic_vector(31 downto 0)"),
                (f"i_{p}chk_err_cnt", "in", "std_logic_vector(31 downto 0)"),
                (f"i_{p}chk_status_fifo_level", "in", "std_logic_vector(3 downto 0)"),
                (f"i_{p}chk_status_fifo_ovf", "in", "std_logic"),
            ])

    if has_txbit:
        add_ch_comp("tb_", True)
    for n in range(num_rx):
        add_ch_comp(f"rx{n}_", False)

    lines = [
        "--------------------------------------------------------------------------------",
        "-- Dosya       : arinc429_ip.vhd",
        "-- Standart    : VHDL-93 / VHDL-2008 uyumlu",
        "--",
        "-- Amaç:",
        f"--   AXIL Studio'nun ürettiği {module}.v (AXI4-Lite slave, ZipCPU easyaxil)",
        "--   ile saf VHDL arinc429_core çekirdeğini tek üst modülde birleştirir.",
        "--",
        "-- Gereksinimler:",
        "--   REQ-1 : Dış bus arayüzü standart 32-bit AXI4-Lite Slave (S_AXI_*) olup",
        "--           tek saat domain'inde (S_AXI_ACLK, S_AXI_ARESETN) çalışır.",
        "--   REQ-2 : Tüm o_* / i_* register portları ve RAM wr_strobe / rd_strobe",
        "--           sinyalleri arinc429_core record portlarına 1-1 bağlanır.",
        "--   REQ-3 : Bu dosya vhdl/scripts/gen_axil_spec.py ile otomatik üretilir;",
        "--           farklı RX kanal sayılarında tek komutla yenilenebilir.",
        "--------------------------------------------------------------------------------",
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "use work.a429_pkg.all;",
        "",
        "entity arinc429_ip is",
        "    generic (",
        "        C_AXI_ADDR_WIDTH     : positive := 32;",
        "        G_SYNC_STAGES        : positive := 4;",
        "        G_CHK_FIFO_DEPTH     : positive := 4",
        "    );",
        "    port (",
        "        -- AXI4-Lite Slave (AXIL Studio / easyaxil)",
        "        S_AXI_ACLK    : in  std_logic;",
        "        S_AXI_ARESETN : in  std_logic;",
        "        S_AXI_AWVALID : in  std_logic;",
        "        S_AXI_AWREADY : out std_logic;",
        "        S_AXI_AWADDR  : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);",
        "        S_AXI_AWPROT  : in  std_logic_vector(2 downto 0);",
        "        S_AXI_WVALID  : in  std_logic;",
        "        S_AXI_WREADY  : out std_logic;",
        "        S_AXI_WDATA   : in  std_logic_vector(31 downto 0);",
        "        S_AXI_WSTRB   : in  std_logic_vector(3 downto 0);",
        "        S_AXI_BVALID  : out std_logic;",
        "        S_AXI_BREADY  : in  std_logic;",
        "        S_AXI_BRESP   : out std_logic_vector(1 downto 0);",
        "        S_AXI_ARVALID : in  std_logic;",
        "        S_AXI_ARREADY : out std_logic;",
        "        S_AXI_ARADDR  : in  std_logic_vector(C_AXI_ADDR_WIDTH - 1 downto 0);",
        "        S_AXI_ARPROT  : in  std_logic_vector(2 downto 0);",
        "        S_AXI_RVALID  : out std_logic;",
        "        S_AXI_RREADY  : in  std_logic;",
        "        S_AXI_RDATA   : out std_logic_vector(31 downto 0);",
        "        S_AXI_RRESP   : out std_logic_vector(1 downto 0);",
        "",
        "        -- Fiziksel ARINC 429 pinleri",
        "        tx_high       : out std_logic;",
        "        tx_low        : out std_logic;",
        "        tx_slp        : out std_logic;",
        "        txbit_rx_high : in  std_logic := '0';",
        "        txbit_rx_low  : in  std_logic := '0';",
        f"        rx_high       : in  std_logic_vector({n_rx_vec - 1} downto 0) := (others => '0');",
        f"        rx_low        : in  std_logic_vector({n_rx_vec - 1} downto 0) := (others => '0')",
        "    );",
        "end entity arinc429_ip;",
        "",
        "architecture rtl of arinc429_ip is",
        "",
        f"    component {module} is",
        "        generic (",
        "            C_AXI_ADDR_WIDTH : integer := 32",
        "        );",
        "        port (",
    ]
    for i, (pname, pdir, ptyp) in enumerate(comp_ports):
        sep = ";" if i < len(comp_ports) - 1 else ""
        lines.append(f"            {pname:<30} : {pdir:<3} {ptyp}{sep}")
    lines += [
        "        );",
        "    end component;",
        "",
        "    signal rst_all       : std_logic;",
        "    signal rst_tx        : std_logic;",
        "    signal rst_txbit     : std_logic;",
        f"    signal rst_rx        : std_logic_vector({n_rx_vec - 1} downto 0) := (others => '0');",
        "    signal global_freeze : std_logic;",
        "    signal ts_en         : std_logic;",
        "    signal ts_clr        : std_logic;",
        "    signal ts_lsb_rd     : std_logic;",
        "    signal ts_lsb        : std_logic_vector(31 downto 0);",
        "    signal ts_msb        : std_logic_vector(31 downto 0);",
        "",
        "    signal tx_reg_in     : t_tx_reg_in  := C_TX_REG_IN_ZERO;",
        "    signal tx_reg_out    : t_tx_reg_out;",
        "    signal tb_reg_in     : t_rx_reg_in  := C_RX_REG_IN_ZERO;",
        "    signal tb_reg_out    : t_rx_reg_out;",
        f"    signal rx_reg_in     : t_rx_reg_in_arr(0 to {n_rx_vec - 1}) := (others => C_RX_REG_IN_ZERO);",
        f"    signal rx_reg_out    : t_rx_reg_out_arr(0 to {n_rx_vec - 1});",
    ]
    # Kısa adres ara sinyalleri (slice bağlama için)
    ch_list = ([("tb_", "tb_reg_in", "tb_reg_out", True)] if has_txbit else []) + [
        (f"rx{n}_", f"rx_reg_in({n})", f"rx_reg_out({n})", False) for n in range(num_rx)
    ]
    for p, _, _, _ in ch_list:
        lines.append(f"    signal s_{p}word_raddr : {_vhdl_type(wdepth_log2)};")
        lines.append(f"    signal s_{p}err_raddr  : {_vhdl_type(edepth_log2)};")
        lines.append(f"    signal s_{p}bit_widx   : {_vhdl_type(bitdiag_log2)};")

    lines += [
        "",
        "begin",
        "",
    ]
    for p, rin, _, _ in ch_list:
        lines.append(f"    {rin}.word_raddr <= (15 downto {wdepth_log2} => '0') & s_{p}word_raddr;")
        lines.append(f"    {rin}.err_raddr  <= (15 downto {edepth_log2} => '0') & s_{p}err_raddr;")
        lines.append(f"    {rin}.bit_raddr_word <= (7 downto {bitdiag_log2} => '0') & s_{p}bit_widx;")

    # AXIL port map
    pmap: list[tuple[str, str]] = [
        ("S_AXI_ACLK", "S_AXI_ACLK"),
        ("S_AXI_ARESETN", "S_AXI_ARESETN"),
        ("S_AXI_AWVALID", "S_AXI_AWVALID"),
        ("S_AXI_AWREADY", "S_AXI_AWREADY"),
        ("S_AXI_AWADDR", "S_AXI_AWADDR"),
        ("S_AXI_AWPROT", "S_AXI_AWPROT"),
        ("S_AXI_WVALID", "S_AXI_WVALID"),
        ("S_AXI_WREADY", "S_AXI_WREADY"),
        ("S_AXI_WDATA", "S_AXI_WDATA"),
        ("S_AXI_WSTRB", "S_AXI_WSTRB"),
        ("S_AXI_BVALID", "S_AXI_BVALID"),
        ("S_AXI_BREADY", "S_AXI_BREADY"),
        ("S_AXI_BRESP", "S_AXI_BRESP"),
        ("S_AXI_ARVALID", "S_AXI_ARVALID"),
        ("S_AXI_ARREADY", "S_AXI_ARREADY"),
        ("S_AXI_ARADDR", "S_AXI_ARADDR"),
        ("S_AXI_ARPROT", "S_AXI_ARPROT"),
        ("S_AXI_RVALID", "S_AXI_RVALID"),
        ("S_AXI_RREADY", "S_AXI_RREADY"),
        ("S_AXI_RDATA", "S_AXI_RDATA"),
        ("S_AXI_RRESP", "S_AXI_RRESP"),
        ("o_soft_reset_rst_all", "rst_all"),
        ("o_soft_reset_tx", "rst_tx"),
        ("o_soft_reset_txbit", "rst_txbit"),
    ]
    for n in range(num_rx):
        pmap.append((f"o_soft_reset_rx{n}", f"rst_rx({n})"))
    pmap += [
        ("o_global_freeze", "global_freeze"),
        ("o_ts_ctrl_enable", "ts_en"),
        ("o_ts_ctrl_clear", "ts_clr"),
        ("i_ts_lsb", "ts_lsb"),
        ("o_ts_lsb_rd", "ts_lsb_rd"),
        ("i_ts_msb", "ts_msb"),
    ]
    if has_tx:
        pmap += [
            ("o_tx_transmitter_en", "tx_reg_in.transmitter_en"),
            ("o_tx_msg_sched_en", "tx_reg_in.msg_sched_en"),
            ("o_tx_builder_en", "tx_reg_in.builder_en"),
            ("o_tx_label", "tx_reg_in.label_val"),
            ("o_tx_sdi", "tx_reg_in.sdi"),
            ("o_tx_data", "tx_reg_in.data"),
            ("o_tx_ssm", "tx_reg_in.ssm"),
            ("o_tx_parity_type", "tx_reg_in.parity_type"),
            ("o_tx_sched_en", "tx_reg_in.sched_en"),
            ("o_tx_initial_delay", "tx_reg_in.initial_delay"),
            ("o_tx_inter_word_gap", "tx_reg_in.inter_word_gap"),
            ("o_tx_send_cmd_send", "tx_reg_in.send_cmd"),
            ("o_tx_ext_data", "tx_reg_in.ext_data"),
            ("o_tx_ext_high", "tx_reg_in.ext_high"),
            ("o_tx_ext_low", "tx_reg_in.ext_low"),
            ("o_tx_cfg_sel", "tx_reg_in.cfg_sel"),
            ("o_tx_cfg_apply_apply", "tx_reg_in.cfg_apply"),
            ("o_tx_cust_pulse_dur", "tx_reg_in.cust.pulse_dur"),
            ("o_tx_cust_null_dur", "tx_reg_in.cust.null_dur"),
            ("o_tx_cust_gap_dur", "tx_reg_in.cust.gap_dur"),
            ("o_tx_cust_slp", "tx_reg_in.cust.slp"),
            ("i_tx_act_pulse_dur", "tx_reg_out.act.pulse_dur"),
            ("i_tx_act_null_dur", "tx_reg_out.act.null_dur"),
            ("i_tx_act_gap_dur", "tx_reg_out.act.gap_dur"),
            ("i_tx_act_slp", "tx_reg_out.act.slp"),
            ("i_tx_status_busy", "tx_reg_out.busy"),
            ("i_tx_status_sched_active", "tx_reg_out.sched_active"),
            ("i_tx_status_act_cfg", "tx_reg_out.act_cfg"),
            ("i_tx_word_cnt", "tx_reg_out.word_cnt"),
        ]
    for p, rin, rout, chk in ch_list:
        pmap += [
            (f"o_{p}ctrl_enable", f"{rin}.ctrl_enable"),
            (f"o_{p}ctrl_freeze", f"{rin}.ctrl_freeze"),
            (f"o_{p}ctrl_clear", f"{rin}.ctrl_clear"),
            (f"i_{p}status_frozen", f"{rout}.status_frozen"),
            (f"i_{p}status_word_wrap", f"{rout}.status_word_wrap"),
            (f"i_{p}status_err_wrap", f"{rout}.status_err_wrap"),
            (f"i_{p}status_act_cfg", f"{rout}.status_act_cfg"),
            (f"o_{p}cfg_sel", f"{rin}.cfg_sel"),
            (f"o_{p}cfg_apply_apply", f"{rin}.cfg_apply"),
            (f"o_{p}cust_glitch_filter_size", f"{rin}.cust.glitch_filter_size"),
            (f"o_{p}cust_min_pulse", f"{rin}.cust.min_pulse"),
            (f"o_{p}cust_max_pulse", f"{rin}.cust.max_pulse"),
            (f"o_{p}cust_min_bit", f"{rin}.cust.min_bit"),
            (f"o_{p}cust_max_bit", f"{rin}.cust.max_bit"),
            (f"o_{p}cust_max_pulse_err", f"{rin}.cust.max_pulse_err"),
            (f"o_{p}cust_max_null_err", f"{rin}.cust.max_null_err"),
            (f"o_{p}cust_max_gap_err", f"{rin}.cust.max_gap_err"),
            (f"o_{p}cust_parity_mode", f"{rin}.cust.parity_mode"),
            (f"i_{p}act_glitch_filter_size", f"{rout}.act.glitch_filter_size"),
            (f"i_{p}act_min_pulse", f"{rout}.act.min_pulse"),
            (f"i_{p}act_max_pulse", f"{rout}.act.max_pulse"),
            (f"i_{p}act_min_bit", f"{rout}.act.min_bit"),
            (f"i_{p}act_max_bit", f"{rout}.act.max_bit"),
            (f"i_{p}act_max_pulse_err", f"{rout}.act.max_pulse_err"),
            (f"i_{p}act_max_null_err", f"{rout}.act.max_null_err"),
            (f"i_{p}act_max_gap_err", f"{rout}.act.max_gap_err"),
            (f"i_{p}act_parity_mode", f"{rout}.act.parity_mode"),
            (f"i_{p}word_cnt", f"{rout}.word_cnt"),
            (f"i_{p}err_cnt", f"{rout}.err_cnt"),
            (f"i_{p}drop_cnt", f"{rout}.drop_cnt"),
            (f"i_{p}last_word", f"{rout}.last_word"),
            (f"o_{p}word_raddr", f"s_{p}word_raddr"),
            (f"o_{p}word_raddr_wr", f"{rin}.word_raddr_wr"),
            (f"i_{p}word_rd_ts_msb", f"{rout}.word_rd_ts_msb"),
            (f"i_{p}word_rd_ts_lsb", f"{rout}.word_rd_ts_lsb"),
            (f"i_{p}word_rd_data", f"{rout}.word_rd_data"),
            (f"i_{p}word_rd_gap", f"{rout}.word_rd_gap"),
            (f"i_{p}word_rd_gap_err", f"{rout}.word_rd_gap_err"),
            (f"o_{p}word_rd_gap_err_rd", f"{rin}.word_rd_last"),
            (f"o_{p}err_raddr", f"s_{p}err_raddr"),
            (f"o_{p}err_raddr_wr", f"{rin}.err_raddr_wr"),
            (f"i_{p}err_rd_ts_msb", f"{rout}.err_rd_ts_msb"),
            (f"i_{p}err_rd_ts_lsb", f"{rout}.err_rd_ts_lsb"),
            (f"i_{p}err_rd_code", f"{rout}.err_rd_code"),
            (f"i_{p}err_rd_addr", f"{rout}.err_rd_addr"),
            (f"i_{p}err_rd_data", f"{rout}.err_rd_data"),
            (f"o_{p}err_rd_data_rd", f"{rin}.err_rd_last"),
            (f"o_{p}bit_raddr_bit_idx", f"{rin}.bit_raddr_bit"),
            (f"o_{p}bit_raddr_word_idx", f"s_{p}bit_widx"),
            (f"o_{p}bit_raddr_wr", f"{rin}.bit_raddr_wr"),
            (f"i_{p}bit_rd_pulse", f"{rout}.bit_rd_pulse"),
            (f"i_{p}bit_rd_pulse_err", f"{rout}.bit_rd_pulse_err"),
            (f"i_{p}bit_rd_null", f"{rout}.bit_rd_null"),
            (f"i_{p}bit_rd_null_err", f"{rout}.bit_rd_null_err"),
            (f"o_{p}bit_rd_null_err_rd", f"{rin}.bit_rd_last"),
        ]
        if chk:
            pmap += [
                (f"o_{p}chk_ctrl_enable", f"{rin}.chk_enable"),
                (f"o_{p}chk_ctrl_clear", f"{rin}.chk_clear"),
                (f"o_{p}chk_timeout", f"{rin}.chk_timeout"),
                (f"i_{p}chk_ok_cnt", f"{rout}.chk_ok_cnt"),
                (f"i_{p}chk_err_cnt", f"{rout}.chk_err_cnt"),
                (f"i_{p}chk_status_fifo_level", f"{rout}.chk_fifo_level"),
                (f"i_{p}chk_status_fifo_ovf", f"{rout}.chk_fifo_ovf"),
            ]

    lines += [
        "",
        f"    u_axil : {module}",
        "        generic map (C_AXI_ADDR_WIDTH => C_AXI_ADDR_WIDTH)",
        "        port map (",
    ]
    for i, (pn, sig) in enumerate(pmap):
        sep = "," if i < len(pmap) - 1 else ""
        lines.append(f"            {pn:<30} => {sig}{sep}")
    lines += [
        "        );",
        "",
        "    u_core : entity work.arinc429_core",
        "        generic map (",
        f"            G_NUM_RX             => {num_rx},",
        f"            G_TX_EN              => {'true' if has_tx else 'false'},",
        f"            G_TXBIT_EN           => {'true' if has_txbit else 'false'},",
        "            G_SYNC_STAGES        => G_SYNC_STAGES,",
        f"            G_WORD_DEPTH_LOG2    => {wdepth_log2},",
        f"            G_ERR_DEPTH_LOG2     => {edepth_log2},",
        f"            G_BITDIAG_WORDS_LOG2 => {bitdiag_log2},",
        "            G_BITDIAG_EN         => true,",
        "            G_CHK_FIFO_DEPTH     => G_CHK_FIFO_DEPTH",
        "        )",
        "        port map (",
        "            clk           => S_AXI_ACLK,",
        "            rst_n         => S_AXI_ARESETN,",
        "            rst_all       => rst_all,",
        "            rst_tx        => rst_tx,",
        "            rst_txbit     => rst_txbit,",
        "            rst_rx        => rst_rx,",
        "            global_freeze => global_freeze,",
        "            ts_en         => ts_en,",
        "            ts_clr        => ts_clr,",
        "            ts_lsb_rd     => ts_lsb_rd,",
        "            ts_lsb        => ts_lsb,",
        "            ts_msb        => ts_msb,",
        "            tx_reg_in     => tx_reg_in,",
        "            tx_reg_out    => tx_reg_out,",
        "            tb_reg_in     => tb_reg_in,",
        "            tb_reg_out    => tb_reg_out,",
        "            rx_reg_in     => rx_reg_in,",
        "            rx_reg_out    => rx_reg_out,",
        "            tx_high       => tx_high,",
        "            tx_low        => tx_low,",
        "            tx_slp        => tx_slp,",
        "            txbit_rx_high => txbit_rx_high,",
        "            txbit_rx_low  => txbit_rx_low,",
        "            rx_high       => rx_high,",
        "            rx_low        => rx_low",
        "        );",
        "",
        "end architecture rtl;",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="ARINC 429 IP için AXIL Studio register spec ve HDL üreteci")
    ap.add_argument("-o", "--outdir", default="vhdl/axil", help="AXIL çıktı klasörü (varsayılan: vhdl/axil)")
    ap.add_argument("--top-vhd", default="vhdl/rtl/arinc429_ip.vhd", help="Üretilecek VHDL top wrapper yolu")
    ap.add_argument("--module", default="arinc429_axil", help="AXIL slave modül adı")
    ap.add_argument("--num-rx", type=int, default=2, help="RX kanal sayısı (varsayılan: 2)")
    ap.add_argument("--no-tx", action="store_true", help="TX kanalını kapat")
    ap.add_argument("--no-txbit", action="store_true", help="TX BIT kanalını kapat")
    ap.add_argument("--clk-hz", type=int, default=50_000_000, help="Sistem clock frekansı (Hz)")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x40000000, help="Proje base adresi")
    ap.add_argument("--axil-studio", default="", help="AXIL Studio repo yolu (verilirse easyaxil Verilog dosyaları da üretilir)")
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    spec = build_regspec(
        module=a.module,
        num_rx=a.num_rx,
        has_tx=not a.no_tx,
        has_txbit=not a.no_txbit,
        clk_hz=a.clk_hz,
    )
    spec_path = os.path.join(a.outdir, f"{a.module}.regspec.json")
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=True)
    print(f"Wrote {spec_path} ({len(spec['registers'])} registers)")

    proj = build_axproj(spec, base=a.base)
    proj_path = os.path.join(a.outdir, "arinc429.axproj.json")
    with open(proj_path, "w", encoding="utf-8") as fh:
        json.dump(proj, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {proj_path}")

    if a.top_vhd:
        os.makedirs(os.path.dirname(os.path.abspath(a.top_vhd)), exist_ok=True)
        with open(a.top_vhd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_top_vhd(
                module=a.module,
                num_rx=a.num_rx,
                has_tx=not a.no_tx,
                has_txbit=not a.no_txbit,
            ))
        print(f"Wrote {a.top_vhd}")

    if a.axil_studio:
        sys.path.insert(0, os.path.abspath(a.axil_studio))
        from axil_studio.core import axilgen, hdlspec as H
        ms = axilgen.ModuleSpec.from_dict(spec)
        errs = ms.validate()
        if errs:
            raise SystemExit("AXIL Studio spec doğrulama hatası:\n" + "\n".join(errs))
        for fname, text in axilgen.output_texts(ms, base=a.base).items():
            p = os.path.join(a.outdir, fname)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(f"Generated {p}")
        hp = os.path.join(a.outdir, f"{a.module}.hdlspec.json")
        H.save(H.ip_hdlspec(ms), hp)
        print(f"Generated {hp}")


if __name__ == "__main__":
    main()
