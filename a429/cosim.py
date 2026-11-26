"""ARINC 429 IP RTL eş-simülasyonu: Debug Bridge (AxilClient) arayüzüyle gerçek RTL'i (GHDL + Icarus) sürer.

Kart yokken uygulamanın ve Test menüsünün gerçek RTL davranışına karşı çalıştırılması için:

    python main.py --cosim            # 1 RX, TX -> RX0 loopback
    CosimClient(num_rx=2)             # testlerde

Gerekenler: ghdl (mcode/llvm), iverilog / vvp ve AXIL Studio'nun ürettiği vhdl/axil/arinc429_axil*.v.
Zaman yalnızca komutlarla ilerler: ``advance_us(us)`` (Test menüsü bekleme yerine bunu kullanır).
RX hat bağlantısı ``set_rx_wiring(rx, mode)``: "loop", "open" (00), "inverted" (boşta 11), "swapped" (A/B ters).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading

from . import ipmap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLK_HZ = 50_000_000
WIRING = {"loop": 0, "open": 1, "inverted": 2, "swapped": 3}

_RTL = [
    "a429_pkg.vhd", "a429_presets_pkg.vhd", "a429_rst_sync.vhd", "a429_timestamp.vhd", "a429_sdp_ram.vhd",
    "a429_cdc_sync.vhd", "a429_glitch_filter.vhd", "a429_rx_decoder.vhd", "a429_rx_core.vhd",
    "a429_rx_cfg_sel.vhd", "a429_rx_logger.vhd", "a429_word_checker.vhd", "a429_rx_channel.vhd",
    "a429_tx_cfg_sel.vhd", "a429_tx_word_builder.vhd", "a429_tx_scheduler.vhd", "a429_tx_transmitter.vhd",
    "a429_tx_core.vhd", "a429_tx_word_evt.vhd", "a429_tx_channel.vhd", "arinc429_core.vhd",
]


class CosimError(RuntimeError):
    pass


def available() -> bool:
    return bool(shutil.which("ghdl")) and (bool(shutil.which("verilator")) or
                                          all(shutil.which(t) for t in ("iverilog", "vvp")))


def build(num_rx: int = 1, workdir: str | None = None) -> str:
    """RTL'i derler (GHDL synth -> Verilog netlist + AXIL slave + tb_cosim.v); vvp dosyasının yolunu döner.

    num_rx deponun üretilmiş haritasından farklıysa top VHDL ve AXIL slave geçici olarak yeniden üretilir.
    """
    if not available():
        raise CosimError("Eş-simülasyon için ghdl ve verilator (önerilen) ya da iverilog/vvp gerekli.")
    work = workdir or os.path.join(tempfile.gettempdir(), f"a429_cosim_rx{num_rx}")
    os.makedirs(work, exist_ok=True)
    use_vl = bool(shutil.which("verilator"))
    vvp = os.path.join(work, "vl", "obj_dir", "tbv") if use_vl else os.path.join(work, "tb_cosim.vvp")
    srcs = [os.path.join(ROOT, "vhdl", "rtl", f) for f in _RTL] + [os.path.join(ROOT, "tools", "cosim", "tb_cosim.v"),
                                                                   os.path.join(ROOT, "a429", "ipmap.py")]
    axil_dir = os.path.join(ROOT, "vhdl", "axil")
    top = os.path.join(ROOT, "vhdl", "rtl", "arinc429_ip.vhd")
    with open(os.path.join(axil_dir, "arinc429_axil.regspec.json"), encoding="utf-8") as fh:
        repo_rx = sum(1 for r in __import__("json").load(fh)["registers"] if r["name"].endswith("_CTRL")
                      and r["name"].startswith("RX"))
    if num_rx != repo_rx:
        gen = os.path.join(work, "gen")
        os.makedirs(gen, exist_ok=True)
        studio = os.environ.get("AXIL_STUDIO", "")
        if not studio:
            raise CosimError(f"{num_rx} RX için AXIL slave yeniden üretilmeli: AXIL_STUDIO=<axil-studio yolu> verin.")
        subprocess.run(["python3", os.path.join(ROOT, "vhdl", "scripts", "gen_axil_spec.py"), "-o", gen,
                        "--num-rx", str(num_rx), "--top-vhd", os.path.join(gen, "arinc429_ip.vhd"),
                        "--library", "", "--axil-studio", studio], check=True, capture_output=True)
        axil_dir, top = gen, os.path.join(gen, "arinc429_ip.vhd")
    srcs += [top, os.path.join(axil_dir, "arinc429_axil.v"), os.path.join(axil_dir, "arinc429_axil_pk.v")]
    if os.path.exists(vvp) and os.path.getmtime(vvp) > max(os.path.getmtime(s) for s in srcs):
        return vvp

    lib = os.path.join(work, "ghdl")
    os.makedirs(lib, exist_ok=True)
    rtl = [os.path.join(ROOT, "vhdl", "rtl", f) for f in _RTL] + [top]

    def run(cmd, **kw):
        p = subprocess.run(cmd, capture_output=True, text=True, **kw)
        if p.returncode != 0:
            raise CosimError(f"{cmd[0]} başarısız:\n{p.stderr[-2000:]}")
        return p

    run(["ghdl", "-a", "--std=08", f"--workdir={lib}"] + rtl)
    net = run(["ghdl", "--synth", "--std=08", f"--workdir={lib}", "--out=verilog", "arinc429_ip"]).stdout
    netv = os.path.join(work, "arinc429_ip_syn.v")
    with open(netv, "w", encoding="utf-8") as fh:
        fh.write(net)
    vsrc = [netv, os.path.join(axil_dir, "arinc429_axil_pk.v"), os.path.join(axil_dir, "arinc429_axil.v"),
            os.path.join(ROOT, "tools", "cosim", "tb_cosim.v")]
    if use_vl:   # Verilator: Icarus'tan ~100 kat hızlı (Low Speed testleri için gerekli)
        vdir = os.path.join(work, "vl")
        os.makedirs(vdir, exist_ok=True)
        run(["verilator", "--binary", "--timing", "-j", "4", "-Wno-fatal", "-Wno-lint", "-Wno-style",
             "--top-module", "tb_cosim", f"-GNRX={num_rx}", "-o", "tbv"] + vsrc, cwd=vdir)
    else:
        run(["iverilog", "-g2012", f"-Ptb_cosim.NRX={num_rx}", "-o", vvp] + vsrc)
    return vvp


class CosimClient:
    """AxilClient / SimClient ile aynı arayüz; erişimler gerçek RTL simülasyonuna gider."""

    def __init__(self, num_rx: int = 1, base: int = 0x40000000, workdir: str | None = None):
        vvp = build(num_rx, workdir)
        self.num_rx = num_rx
        self.ip = ipmap.to_ip_dict(name="arinc429_rtl", base=base, num_rx=num_rx)
        self.ip["desc"] = "RTL eş-simülasyonu " + self.ip["desc"]
        self.models_line = True
        self.connected = True
        self.port = "RTL"
        self.lang = "tr"
        self.theme = {}
        self.settings: dict = {}
        self.on_event = None
        self.locked = False
        self.bridge_logs: list[str] = []
        self.added_configs: list = []
        self.sim_cycles = 0
        self._lk = threading.Lock()
        self._tmp = tempfile.mkdtemp(prefix="a429cosim_")
        cmd, rsp = os.path.join(self._tmp, "cmd"), os.path.join(self._tmp, "rsp")
        os.mkfifo(cmd)
        os.mkfifo(rsp)
        argv = [vvp] if vvp.endswith("tbv") else ["vvp", "-n", vvp]
        self._proc = subprocess.Popen(argv + [f"+CMD={cmd}", f"+RSP={rsp}"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._rsp = open(rsp, "r", encoding="ascii")
        self._cmd = open(cmd, "w", encoding="ascii")
        ready = self._rsp.readline().strip()
        if not ready.startswith("READY"):
            raise CosimError(f"Simülasyon başlamadı: {ready!r}")

    # ---- protokol
    def _x(self, line: str) -> str:
        with self._lk:
            if self._proc.poll() is not None:
                raise CosimError("RTL simülasyonu sonlandı.")
            self._cmd.write(line + "\n")
            self._cmd.flush()
            r = self._rsp.readline().strip()
        if not r or r[0] == "E":
            raise CosimError(f"Simülasyon yanıtı: {r!r}")
        return r

    def _off(self, offset=0, addr=None) -> int:
        if addr is not None:
            return (int(addr) - int(self.ip["base"])) & 0xFFFFFFFF
        return int(offset) & 0xFFFFFFFF

    def read(self, offset=0, addr=None, quiet=False) -> int:
        r = self._x(f"R {self._off(offset, addr):X}")
        self.sim_cycles += 6
        return int(r.split()[1], 16)

    def write(self, offset=0, value=0, addr=None, quiet=False):
        self._x(f"W {self._off(offset, addr):X} {int(value) & 0xFFFFFFFF:X}")
        self.sim_cycles += 6

    def batch(self, steps, quiet=False):
        out = []
        for st in steps:
            if isinstance(st, dict):
                if st["op"] == "read":
                    out.append(self.read(st.get("offset", 0), st.get("addr")))
                else:
                    self.write(st.get("offset", 0), st.get("value", 0), st.get("addr"))
                    out.append(None)
            elif st[0] == "read":
                out.append(self.read(st[1]))
            else:
                self.write(st[1], st[2])
                out.append(None)
        return out

    def read_until(self, offset, mask, value, max_reads=256, addr=None, quiet=True):
        out = []
        for _ in range(max_reads):
            w = self.read(offset, addr=addr)
            out.append(w)
            if (w & mask) == value:
                break
            self.advance_us(5)
        return out

    def advance_us(self, us: float):
        cyc = max(1, int(round(us * CLK_HZ / 1e6)))
        self._x(f"T {cyc}")
        self.sim_cycles += cyc

    def set_rx_wiring(self, rx: int, mode: str):
        self._x(f"M {int(rx)} {WIRING[mode]}")

    # ---- AxilClient uyumluluğu
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

    def close(self):
        try:
            if self._proc.poll() is None:
                self._cmd.write("Q\n")
                self._cmd.flush()
                self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
        finally:
            for f in (self._cmd, self._rsp):
                try:
                    f.close()
                except Exception:
                    pass
            shutil.rmtree(self._tmp, ignore_errors=True)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
