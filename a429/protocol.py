"""Seri haberleşme: handshake, config gönderme, veri okuma (TTL makrosunun Python karşılığı) + cihaz simülatörü."""
from __future__ import annotations

import random
import sys
import threading
import time
from dataclasses import dataclass, field, asdict

from .regmap import RegisterMap, parse_values

SIM_PORT = "SIMÜLATÖR"


def default_port() -> str:
    """İşletim sistemine uygun başlangıç portu."""
    if sys.platform == "win32":
        return "COM44"
    try:
        from serial.tools import list_ports
        usb = [p.device for p in list_ports.comports() if "usb" in p.device.lower()]
    except Exception:
        usb = []
    return usb[0] if usb else SIM_PORT


def native_port(port: str) -> str:
    """Başka işletim sisteminde kaydedilmiş port adını bu sisteme uygun hale getirir."""
    if port == SIM_PORT or (sys.platform == "win32") == port.upper().startswith("COM"):
        return port
    return default_port()


@dataclass
class LinkSettings:
    port: str = field(default_factory=default_port)
    baud: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    timeout_ms: int = 500          # handshake cevap bekleme
    retry: int = 3
    handshake: str = "AA 11 BB 22 CC 33 DD 44"
    hs_response: str = "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    ack_wait_ms: int = 10          # yazma sonrası bekleme (IP ACK göndermez)
    read_wait_ms: int = 10         # okuma cevabı
    reg_wcnt: str = "50"
    reg_ecnt: str = "51"
    reg_ts_lsb: str = "52"
    reg_ts_msb: str = "53"
    reg_waddr: str = "1D"
    reg_w: list = field(default_factory=lambda: ["54", "55", "56", "57", "58"])   # TS MSB, TS LSB, data, gap, gap_err
    wdepth: int = 256
    reg_eaddr: str = "1E"
    reg_e: list = field(default_factory=lambda: ["59", "5A", "5B", "5C", "5D"])   # TS MSB, TS LSB, code, addr, data
    edepth: int = 256
    reg_baddr: str = "1F"
    reg_b: list = field(default_factory=lambda: ["5E", "5F", "60", "61"])         # pulse, perr, null, nerr
    bit_words: int = 8
    read_word: str = "all"         # all | last | none
    read_word_n: int = 4
    read_error: str = "all"
    read_error_n: int = 4
    read_bit: str = "all"          # N: Bit Diagnostic verisi okunacak Word sayısı
    read_bit_n: int = 4
    out_dir: str = ""
    verify_select: bool = True     # BRAM adres seçimini geri okuyarak doğrula
    addr_version: int = 2

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        d = dict(d)
        if d.get("addr_version", 1) < 2:                    # eski adres seçimleri 1A/1B/1C → 1D/1E/1F
            for k, old, new in (("reg_waddr", "1A", "1D"), ("reg_eaddr", "1B", "1E"), ("reg_baddr", "1C", "1F")):
                if str(d.get(k, old)).upper() == old:
                    d[k] = new
            d["addr_version"] = 2
        if "zero_cnt" in d and "hs_response" not in d:      # eski dosyalar: 00 sayısı
            d["hs_response"] = " ".join(["00"] * int(d["zero_cnt"]))
        return LinkSettings(**{k: v for k, v in d.items() if k in LinkSettings.__dataclass_fields__})


def hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b) if b else "(boş)"


def h2i(s: str) -> int:
    return int(str(s).strip(), 16)


class LinkError(Exception):
    pass


class Link:
    """Seri port üzerinde protokol. log(str) geri çağrısı her TX/RX'i yazar."""

    def __init__(self, st: LinkSettings, log=print, regmap: RegisterMap = None):
        self.st, self.log = st, log
        self.regmap = regmap or RegisterMap()
        self.on_write = None                # yazma logu için: (adres, değer, TX, RX)
        self.ser = None
        self.opened = None
        self.stop_flag = threading.Event()

    # ---------- port
    def port_settings(self):
        st = self.st
        return (st.port, st.baud, st.bytesize, st.parity, st.stopbits)

    def open(self):
        if self.st.port == SIM_PORT:
            self.ser = SimDevice(self.regmap, self.st)
        else:
            import serial
            self.ser = serial.Serial(self.st.port, baudrate=self.st.baud, bytesize=self.st.bytesize,
                                     parity=self.st.parity, stopbits=self.st.stopbits, timeout=0.01, write_timeout=2)
        self.opened = self.port_settings()
        self.log(f"Port açıldı: {self.st.port} {self.st.baud} {self.st.bytesize}{self.st.parity}{self.st.stopbits:g}")

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            finally:
                self.ser = None
                self.log("Port kapatıldı.")

    # ---------- düşük seviye
    def txrx(self, data: bytes, wait_ms: int, quiet=False, until=None) -> bytes:
        """data gönder, wait_ms boyunca (veya until(buf) True olana kadar) gelenleri topla."""
        if self.stop_flag.is_set():
            raise LinkError("Kullanıcı durdurdu.")
        self.ser.reset_input_buffer()
        self.ser.write(data)
        self.ser.flush()
        t_end = time.monotonic() + wait_ms / 1000
        buf = bytearray()
        while time.monotonic() < t_end:
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
                if until and until(buf):
                    break
            else:
                time.sleep(0.0005)
        n = self.ser.in_waiting
        if n:
            buf += self.ser.read(n)
        if not quiet:
            self.log(f"  TX: {hx(data)}")
            self.log(f"  RX: {hx(bytes(buf))}")
        return bytes(buf)

    # ---------- handshake
    def handshake(self) -> bool:
        hs = bytes.fromhex(self.st.handshake)
        expected = bytes.fromhex(self.st.hs_response)
        for a in range(1, self.st.retry + 1):
            self.log(f"[Handshake] Deneme {a}/{self.st.retry}")
            rx = self.txrx(hs, self.st.timeout_ms)
            if rx == expected:
                self.log("  -> Cihaz zaten bağlı (beklenen cevap alındı).")
                return True
            if rx != hs:
                self.log("  -> Echo beklenen değerde değil, yeniden deneniyor.")
                continue
            rx = self.txrx(hs, self.st.timeout_ms)
            if rx == expected:
                self.log("  -> BAĞLANTI KURULDU.")
                return True
            self.log("  -> Beklenen Handshake cevabı gelmedi, yeniden deneniyor.")
        return False

    # ---------- yazma
    def write_reg(self, reg_hex: str, value: int, quiet=False) -> bytes:
        data = self.regmap.build_write(reg_hex, value)
        rx = self.txrx(data, self.st.ack_wait_ms, quiet)
        if self.on_write:
            self.on_write(reg_hex, value, data, rx)
        return rx

    def send_config(self, regs, title="RX Config", verify=True):
        """regs: [(ad, adres_hex, değer)]. verify: yazılanları geri okuyup karşılaştırır."""
        self.log(f"[{title}] {title} gönderiliyor")
        for name, adr, val in regs:
            self.log(f" {name}")
            self.write_reg(adr, val)
        if verify:
            bad = []
            for name, adr, val in regs:
                got = self.read_reg(adr, True)
                if got != val:
                    bad.append(f"{name} ({adr}): yazılan {val}, okunan {got}")
            for b in bad:
                self.log(f"  -> UYUŞMADI: {b}")
            if bad:
                raise LinkError(f"{title} geri okuma doğrulaması başarısız: {len(bad)} Register uyuşmadı.")
            self.log(f"{title} geri okuma ile doğrulandı.")
        self.log(f"{title} tamamlandı: {len(regs)} komut.")

    def select(self, reg_hex, addr, quiet=True):
        """BRAM adres seçimi; açıksa geri okuyup doğrular, uyuşmazsa bir kez tekrar yazar."""
        for _ in range(2):
            self.write_reg(reg_hex, addr, quiet)
            if not self.st.verify_select or self.read_reg(reg_hex, quiet) == addr:
                return
            self.log(f"  -> {reg_hex} adres seçimi ({addr}) doğrulanamadı, tekrar yazılıyor.")
        raise LinkError(f"{reg_hex} adres seçimi ({addr}) doğrulanamadı.")

    def read_all(self, progress=lambda done, total, msg: None, quiet=True) -> dict:
        """rx_cfg_read_mode okuma süresince 1 tutulur (kayıtlar dondurulur), sonunda 0 yapılır."""
        freeze = self.regmap.tx_regs.get("rx_read_mode")
        if freeze:
            self.write_reg(freeze, 1, quiet)
        try:
            return self._read_all(progress, quiet)
        finally:
            if freeze and self.ser:
                stopped = self.stop_flag.is_set(); self.stop_flag.clear()
                try:
                    self.write_reg(freeze, 0, quiet)
                except Exception as e:
                    self.log(f"UYARI: RX read mode kapatılamadı: {e}")
                if stopped:
                    self.stop_flag.set()

    # ---------- okuma
    def read_reg(self, reg_hex: str, quiet=False):
        data = self.regmap.build_read(reg_hex)
        find = lambda b: self.regmap.find_response(b, reg_hex)
        for t in range(self.st.retry):
            rx = self.txrx(data, self.st.read_wait_ms, quiet, lambda b: find(b) is not None)
            value = find(rx)
            if value is not None:
                return value
            self.log(f"  -> Register {reg_hex} cevabı hatalı, yeniden deneniyor.")
        self.log(f"HATA: Register {reg_hex} okunamadı.")
        return None

    def _read_all(self, progress, quiet):
        st = self.st
        self.log("[RX Okuma] RX okuma başlıyor")
        wtot = self.read_reg(st.reg_wcnt)
        etot = self.read_reg(st.reg_ecnt)
        if wtot is None or etot is None:
            raise LinkError("Word/Error sayaçları okunamadı.")
        msb = self.read_reg(st.reg_ts_msb)
        lsb = self.read_reg(st.reg_ts_lsb)
        msb2 = self.read_reg(st.reg_ts_msb)
        if msb2 != msb:                       # LSB iki okuma arasında taştı
            self.log("  -> Timestamp LSB okuma sırasında taştı, yeniden okunuyor.")
            msb, lsb = msb2, self.read_reg(st.reg_ts_lsb)
        def limit(available, mode, n):
            return available if mode == "all" else (0 if mode == "none" else min(available, n))
        wfull = min(wtot, st.wdepth); wstart = wtot % st.wdepth if wtot > st.wdepth else 0
        efull = min(etot, st.edepth); estart = etot % st.edepth if etot > st.edepth else 0
        wn = limit(wfull, st.read_word, st.read_word_n)
        en = limit(efull, st.read_error, st.read_error_n)
        bn = limit(min(wtot, st.bit_words - 1), st.read_bit, st.read_bit_n)      # en eski slot ezilmiş olabilir → 1 eksik
        total = wn * 6 + en * 6 + bn * 32 * 5
        done = 0
        words, errors, bits = [], [], []
        for i in range(wn):                   # en yeni önce
            addr = (wstart + wfull - 1 - i) % st.wdepth
            self.select(st.reg_waddr, addr, quiet)
            w = [self.read_reg(r, quiet) for r in st.reg_w]
            words.append({"no": wtot - 1 - i, "addr": addr, "w": w})
            done += 6; progress(done, total, f"Word {i + 1}/{wn}")
        for i in range(en):
            addr = (estart + efull - 1 - i) % st.edepth
            self.select(st.reg_eaddr, addr, quiet)
            w = [self.read_reg(r, quiet) for r in st.reg_e]
            errors.append({"addr": addr, "w": w})
            done += 6; progress(done, total, f"Error {i + 1}/{en}")
        for kb in range(bn * 32):
            wno, bno = wtot - 1 - kb // 32, kb % 32
            addr = (wno % st.bit_words) * 32 + bno
            self.select(st.reg_baddr, addr, quiet)
            w = [self.read_reg(r, quiet) for r in st.reg_b]
            bits.append({"word": wno, "bit": bno, "w": w})
            done += 5; progress(done, total, f"Bit Diagnostic: Word {wno}, Bit {bno + 1}")
        extra = [{"name": r.name, "addr": r.addr, "fmt": r.fmt, "value": self.read_reg(r.addr, quiet)}
                 for r in self.regmap.extra_read]
        wend, eend = self.read_reg(st.reg_wcnt, quiet), self.read_reg(st.reg_ecnt, quiet)
        if wend != wtot or eend != etot:
            self.log(f"UYARI: Okuma sırasında veri akışı sürdü (Word {wtot} → {wend}, Error {etot} → {eend}); veriler karışmış olabilir.")
        self.log(f"RX okuma tamamlandı: {wn} Word, {en} Error, {bn} Word için Bit Diagnostic.")
        return {"summary": {"total_word_cnt": wtot, "total_error_cnt": etot, "ts_msb": msb, "ts_lsb": lsb, "extra": extra, "wcnt_end": wend, "ecnt_end": eend,
                            "read_scope": {"word": st.read_word, "error": st.read_error, "bit": st.read_bit}},
                "words": words, "errors": errors, "bits": bits}


# =====================================================================================
class SimDevice:
    """Gerçek kart yokken arayüzü denemek için protokolü taklit eden sahte cihaz."""

    def __init__(self, regmap: RegisterMap = None, st: LinkSettings = None, n_words=23, n_err=3, mhz=50, seed=1):
        rnd = random.Random(seed)
        self.rm = regmap or RegisterMap()
        st = st or LinkSettings()
        self.hs, self.hs_rsp = bytes.fromhex(st.handshake), bytes.fromhex(st.hs_response)
        self._rx = bytearray(); self.hs_count = 0
        self.regs = {}; self.sel = {st.reg_waddr.upper(): 0, st.reg_eaddr.upper(): 0, st.reg_baddr.upper(): 0}
        self.wsel, self.esel, self.bsel = st.reg_waddr.upper(), st.reg_eaddr.upper(), st.reg_baddr.upper()
        self.wtot, self.etot = n_words, n_err
        ts = 1_000_000
        self.wmem, self.bmem, self.emem = {}, {}, {}
        for n in range(n_words):
            lab = rnd.choice([0o310, 0o203, 0o206, 0o312])
            data = rnd.randrange(1 << 19)
            wd = lab | (rnd.randrange(4) << 8) | (data << 10) | (rnd.randrange(4) << 29)
            if bin(wd).count("1") % 2 == 0:
                wd |= 1 << 31
            gap = 4 * 500 + rnd.randrange(0, 3000)
            bits = []
            for b in range(32):
                p = 250 + rnd.randint(-3, 3); nl = 248 + rnd.randint(-3, 3)
                bits.append((p, rnd.randint(0, 2), nl, rnd.randint(0, 2)))
            ts += gap + sum(x[0] + x[2] for x in bits)
            self.wmem[n % 256] = [ts >> 32, ts & 0xFFFFFFFF, wd, gap, rnd.randint(0, 3)]
            for b, v in enumerate(bits):
                self.bmem[(n % 8) * 32 + b] = list(v)
        self.now = ts + 123_456
        for i in range(n_err):
            t = self.wmem[(n_words - n_err + i) % 256][1] + 77
            self.emem[i % 256] = [0, t, 1 << rnd.randrange(8), rnd.randrange(32), self.wmem[i % 256][2]]

    # --- serial benzeri arayüz
    def write(self, data):
        self._process(bytes(data))
        return len(data)

    def flush(self):
        pass

    @property
    def in_waiting(self):
        return len(self._rx)

    def read(self, n=1):
        out = bytes(self._rx[:n]); del self._rx[:n]; return out

    def reset_input_buffer(self):
        self._rx.clear()

    def close(self):
        pass

    def _reply(self, v):
        self._rx += self.rm.build_response(int(v & 0xFFFFFFFF))

    def _process(self, pkt):
        if pkt == self.hs:
            self.hs_count += 1
            self._rx += pkt if self.hs_count == 1 else self.hs_rsp
            return
        wr = parse_values(self.rm.write_cmd, pkt, self.rm.endian)
        rd = parse_values(self.rm.read_cmd, pkt, self.rm.endian)
        if wr is not None:
            reg = f"{wr['REG']:02X}"
            if reg in self.sel:
                self.sel[reg] = wr["DATA"]
            else:
                self.regs[reg] = wr["DATA"]
        elif rd is not None:
            r = rd["REG"]
            if r == 0x50: self._reply(self.wtot)
            elif r == 0x51: self._reply(self.etot)
            elif r == 0x52: self._reply(self.now & 0xFFFFFFFF)
            elif r == 0x53: self._reply(self.now >> 32)
            elif 0x54 <= r <= 0x58: self._reply(self.wmem.get(self.sel[self.wsel], [0] * 5)[r - 0x54])
            elif 0x59 <= r <= 0x5D: self._reply(self.emem.get(self.sel[self.esel], [0] * 5)[r - 0x59])
            elif 0x5E <= r <= 0x61: self._reply(self.bmem.get(self.sel[self.bsel], [0] * 4)[r - 0x5E])
            elif f"{r:02X}" in self.sel: self._reply(self.sel[f"{r:02X}"])
            else: self._reply(self.regs.get(f"{r:02X}", 0))     # Config Register'ları geri okunabilir
