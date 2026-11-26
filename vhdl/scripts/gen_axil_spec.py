#!/usr/bin/env python3
"""ARINC 429 IP için AXIL Studio (.regspec.json / .axproj.json) üreteci.

Kullanım:
  python3 vhdl/scripts/gen_axil_spec.py -o vhdl/axil --num-rx 1 --axil-studio /yol/axil-studio

AXIL Studio yolu verilmezse yalnızca arinc429_axil.regspec.json, arinc429.axproj.json ve
IP kütüphanesi arinc429.axlib.json (depo kökü, --library) dosyalarını üretir; bu dosyalar doğrudan AXIL Studio'da açılıp Slave Interface Wrapper ile
AXI4-Lite slave (arinc429_axil.v / arinc429_axil_pk.v / testbench) üretilebilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


# Register haritasının tek kaynağı: a429/ipmap.py (uygulama ve simülatör de aynısını kullanır)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from a429 import ipmap  # noqa: E402

build_regspec = ipmap.build_regspec



def build_axproj(spec: dict, ip_name: str = "ARINC429", base: int = 0x40000000) -> dict:
    ip_regs = ipmap.to_ip_registers(spec)
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


def build_axlib(proj: dict, updated: str = "") -> dict:
    """AXIL Studio IP kütüphanesi (.axlib.json, format "axil-ip-library" v1).

    axil_studio/core/library.py LibEntry biçimi: "ip" adressiz IPBlock (register haritası,
    sürüm, IP arayüzü kimliği "panel"), "regspec" ayrı anahtarda (Wrapper HDL'i yeniden üretebilsin).
    Kütüphane depo kökünde axil-interface.json (id "arinc429") ile aynı klasörde durursa
    Debug Bridge ARINC 429 arayüzünü ek ayar olmadan bulur.
    """
    import datetime

    entries = []
    for ip in proj["ips"]:
        ipd = {k: ip[k] for k in ("name", "desc", "version", "panel") if ip.get(k)}
        ipd["registers"] = ip["registers"]
        entry = {"ip": ipd, "updated": updated or datetime.date.today().isoformat()}
        if ip.get("regspec"):
            entry["regspec"] = ip["regspec"]
        entries.append(entry)
    return {
        "format": "axil-ip-library",
        "version": 1,
        "name": "ARINC 429",
        "desc": "ARINC 429 IP (RX/TX/TX BIT, AXI4-Lite, easyaxil wrapper + VHDL çekirdek, vhdl/rtl). "
                "IP arayüzü: arinc429 (a429_ui.py).",
        "entries": entries,
    }


def _vhdl_type(width: int) -> str:
    return "std_logic" if width == 1 else f"std_logic_vector({width - 1} downto 0)"


# AXIL Studio paketli (HDL Designer) AXI4-Lite arayüzü: <module>_pk.v ile aynı düzen (32-bit adres/veri)
_PK_REQ_W = 111
_PK_RSP_W = 41
_PK_HDR = [
    "--   REQ-1 : Dış bus arayüzü HDL Designer uyumlu paketli 32-bit AXI4-Lite Slave",
    "--           (SLAVE_AXI_REQ / SLAVE_AXI_RSP) olup tek saat domain'inde",
    "--           (S_AXI_ACLK, S_AXI_ARESETN) çalışır. Paket düzeni (arinc429_axil_pk.v):",
    "--             REQ[110:0] = AWADDR[110:79] AWPROT[78:76] AWVALID[75] WDATA[74:43]",
    "--                          WSTRB[42:39] WVALID[38] BREADY[37] ARADDR[36:5]",
    "--                          ARPROT[4:2] ARVALID[1] RREADY[0]",
    "--             RSP[40:0]  = AWREADY[40] WREADY[39] BRESP[38:37] BVALID[36]",
    "--                          ARREADY[35] RDATA[34:3] RRESP[2:1] RVALID[0]",
]
_PK_ENT_PORTS = [
    "        -- AXI4-Lite Slave, HDL Designer paketli (AXIL Studio arinc429_axil_pk)",
    "        S_AXI_ACLK    : in  std_logic;",
    "        S_AXI_ARESETN : in  std_logic;",
    f"        SLAVE_AXI_REQ : in  std_logic_vector({_PK_REQ_W - 1} downto 0);",
    f"        SLAVE_AXI_RSP : out std_logic_vector({_PK_RSP_W - 1} downto 0);",
]


def _is_axi_chan(name: str) -> bool:
    """S_AXI_* kanal sinyali mi (saat ve reset hariç)."""
    return name.startswith("S_AXI_") and name not in ("S_AXI_ACLK", "S_AXI_ARESETN")


def build_top_vhd(
    module: str = "arinc429_axil",
    num_rx: int = 1,
    has_tx: bool = True,
    has_txbit: bool = True,
    wdepth_log2: int = 8,
    edepth_log2: int = 8,
    bitdiag_log2: int = 3,
    packed: bool = True,
) -> str:
    """AXIL Studio arinc429_axil (AXI4-Lite slave) + arinc429_core (VHDL) top wrapper üretir.

    packed=True (varsayılan): HDL Designer uyumlu top. İçeride AXIL Studio'nun paketli wrapper'ı
    <module>_pk örneklenir; dış AXI4-Lite arayüzü SLAVE_AXI_REQ[110:0] / SLAVE_AXI_RSP[40:0]
    vektörleridir (adres genişliği 32 bit sabit, generic yok).
    packed=False: eski düz S_AXI_* portlu top (<module> doğrudan).
    """
    if not has_tx:
        has_txbit = False
    n_rx_vec = max(num_rx, 1)

    axi_ports: list[tuple[str, str, str]] = [
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
    ]
    # IP tarafı portları ve bağlantıları a429/ipmap.py'den (AXIL Studio port sırası ve adlandırması)
    binds = ipmap.port_bindings(num_rx=num_rx, has_tx=has_tx, has_txbit=has_txbit,
                                wdepth_log2=wdepth_log2, edepth_log2=edepth_log2, bitdiag_log2=bitdiag_log2)
    comp_ports = axi_ports + [(pn, d, _vhdl_type(w)) for pn, d, w, _ in binds]

    if packed:
        # S_AXI_* kanalları paketli vektörlere: <module>_pk port sırası (saat/reset başta, REQ/RSP sonda)
        comp_ports = [cp for cp in comp_ports if not _is_axi_chan(cp[0])] + [
            ("SLAVE_AXI_REQ", "in", f"std_logic_vector({_PK_REQ_W - 1} downto 0)"),
            ("SLAVE_AXI_RSP", "out", f"std_logic_vector({_PK_RSP_W - 1} downto 0)"),
        ]

    lines = [
        "--------------------------------------------------------------------------------",
        "-- Dosya       : arinc429_ip.vhd",
        "-- Standart    : VHDL-93 / VHDL-2008 uyumlu",
        "--",
        "-- Amaç:",
        (f"--   AXIL Studio'nun ürettiği {module}_pk.v (HDL Designer paketli AXI4-Lite slave," if packed else
         f"--   AXIL Studio'nun ürettiği {module}.v (AXI4-Lite slave, ZipCPU easyaxil)"),
        *([f"--   içinde {module}.v / ZipCPU easyaxil)"] if packed else []),
        "--   ile saf VHDL arinc429_core çekirdeğini tek üst modülde birleştirir.",
        "--",
        "-- Gereksinimler:",
        *(_PK_HDR if packed else [
        "--   REQ-1 : Dış bus arayüzü standart 32-bit AXI4-Lite Slave (S_AXI_*) olup",
        "--           tek saat domain'inde (S_AXI_ACLK, S_AXI_ARESETN) çalışır.",
        ]),
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
        *([] if packed else ["        C_AXI_ADDR_WIDTH     : positive := 32;"]),
        "        G_SYNC_STAGES        : positive := 4;",
        "        G_CHK_FIFO_DEPTH     : positive := 4",
        "    );",
        "    port (",
        *(_PK_ENT_PORTS if packed else [
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
        ]),
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
        f"    component {module}_pk is" if packed else f"    component {module} is",
        *([] if packed else [
        "        generic (",
        "            C_AXI_ADDR_WIDTH : integer := 32",
        "        );",
        ]),
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
    pmap: list[tuple[str, str]] = [(n, n) for n, _, _ in axi_ports] + [(pn, sig) for pn, _, _, sig in binds]

    if packed:
        pmap = [pm for pm in pmap if not _is_axi_chan(pm[0])] + [
            ("SLAVE_AXI_REQ", "SLAVE_AXI_REQ"),
            ("SLAVE_AXI_RSP", "SLAVE_AXI_RSP"),
        ]

    lines += [
        "",
        f"    u_axil : {module}_pk" if packed else f"    u_axil : {module}",
        *([] if packed else ["        generic map (C_AXI_ADDR_WIDTH => C_AXI_ADDR_WIDTH)"]),
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
    ap.add_argument("--num-rx", type=int, default=1, help="RX kanal sayısı (varsayılan: 1)")
    ap.add_argument("--no-tx", action="store_true", help="TX kanalını kapat")
    ap.add_argument("--no-txbit", action="store_true", help="TX BIT kanalını kapat")
    ap.add_argument("--clk-hz", type=int, default=50_000_000, help="Sistem clock frekansı (Hz)")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x40000000, help="Proje base adresi")
    ap.add_argument("--plain-top", action="store_true",
                    help="Top'u düz S_AXI_* portlarıyla üret (varsayılan: HDL Designer paketli arinc429_axil_pk)")
    ap.add_argument("--library", default="arinc429.axlib.json",
                    help="AXIL Studio IP kütüphanesi yolu (varsayılan: depo kökünde arinc429.axlib.json; '' = yazma)")
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

    if a.library:
        lib = build_axlib(proj)
        if os.path.exists(a.library):
            # Register haritası değişmediyse tarih korunur (gereksiz diff olmasın)
            try:
                with open(a.library, encoding="utf-8") as fh:
                    old = json.load(fh)
                for e_new, e_old in zip(lib["entries"], old.get("entries", [])):
                    if {k: v for k, v in e_new.items() if k != "updated"} == \
                       {k: v for k, v in e_old.items() if k != "updated"}:
                        e_new["updated"] = e_old.get("updated", e_new["updated"])
            except (OSError, ValueError):
                pass
        with open(a.library, "w", encoding="utf-8") as fh:
            json.dump(lib, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"Wrote {a.library}")

    if a.top_vhd:
        os.makedirs(os.path.dirname(os.path.abspath(a.top_vhd)), exist_ok=True)
        with open(a.top_vhd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_top_vhd(
                module=a.module,
                num_rx=a.num_rx,
                has_tx=not a.no_tx,
                has_txbit=not a.no_txbit,
                packed=not a.plain_top,
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
