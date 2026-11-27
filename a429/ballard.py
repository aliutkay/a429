"""Ballard Technology / Astronics BTIDriver 64-bit ARINC 429 arayüzü (ctypes).

Desteklenen donanımlar: Ballard BUSBox (BB1xxx), OmniBusBox / OmniBusBox II,
UA1xxx / UA2000 USB ve BTIDriver uyumlu tüm ARINC 429 kartları.

Windows 64-bit Python altında ``BTICARD64.DLL`` ve ``BTI42964.DLL`` (32-bit
Python altında ``BTICARD.DLL`` ve ``BTI429.DLL``) doğrudan ``ctypes.WinDLL``
ile yüklenir; ek paket veya CoPilot lisansı gerektirmez.

ABI tanımı Ballard BTICARD.H / BTI429.H (BTIDriver universal API) ile
birebirdir: ``_WIN64`` altında ``HCARD`` ve ``HCORE`` ``void *`` (``c_void_p``),
``ULONG`` 32-bit işaretsiz tam sayıdır (``c_uint32``).
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from dataclasses import dataclass, field

# =====================================================================================
# BTICARD.H / BTI429.H sabitleri
# =====================================================================================
ERR_NONE = 0

# BTICard_CardGetInfo infotype
INFOTYPE_PLAT = 0x0001
INFOTYPE_PROD = 0x0002
INFOTYPE_GEN = 0x0003
INFOTYPE_429COUNT = 0x0006
INFOTYPE_VERSION = 0x000C
INFOTYPE_DATE = 0x000D
INFOTYPE_CHINFO = 0x000E
INFOTYPE_HWGEN = 0x0015
INFOTYPE_CARDTYPE = 0x0018
INFOTYPE_SERIALNUM = 0x0019

# BTICard_TimerResolution
TIMERRESOL_1US = 1
TIMERRESOL_16US = 2
TIMERRESOL_1024US = 3

# BTICard_CardTest levels
TEST_LEVEL_0 = 0  # I/O arayüzü
TEST_LEVEL_1 = 1  # Bellek arayüzü
TEST_LEVEL_2 = 2  # İletişim işlemcisi
TEST_LEVEL_3 = 3  # Hat sürücü/alıcı (dış hatta sinyal çıkarabilir)

# BTICard_SeqConfig
SEQCFG_DEFAULT = 0x00000000
SEQCFG_FILLHALT = 0x00000000
SEQCFG_DISABLE = 0x00000001
SEQCFG_CONTINUOUS = 0x00000002
SEQCFG_16K = 0x00000000
SEQCFG_32K = 0x02000000
SEQCFG_64K = 0x04000000
SEQCFG_128K = 0x08000000

SEQTYPE_MASK = 0x00FF
SEQTYPE_429 = 0x0001
SEQVER_MASK = 0xFF00
SEQVER_0 = 0x0000
SEQVER_1 = 0x0100

# BTI429_ListStatus
STAT_EMPTY = 0
STAT_PARTIAL = 1
STAT_FULL = 2
STAT_OFF = 3

# BTI429_ChConfig
CHCFG429_DEFAULT = 0x00000000
CHCFG429_HIGHSPEED = 0x00000001
CHCFG429_AUTOSPEED = 0x00000002
CHCFG429_LOWSPEED = 0x00000000
CHCFG429_SELFTEST = 0x00000004
CHCFG429_PARODD = 0x00000000
CHCFG429_PAREVEN = 0x00000010
CHCFG429_PARDATA = 0x00000020
CHCFG429_ACTIVE = 0x00000000
CHCFG429_INACTIVE = 0x00000040
CHCFG429_PARERR = 0x00000100
CHCFG429_SEQALL = 0x00080000

# BTI429_FilterDefault / BTI429_MsgCreate
MSGCRT429_DEFAULT = 0x00000000
MSGCRT429_SEQ = 0x00000001
MSGCRT429_PARERR = 0x00000200

# BTI429_ListAsyncCreate
LISTCRT429_FIFO = 0x00000000

# SEQRECORD429.activity bitleri (MSGACT429_*)
MSGACT429_CHMASK = 0xFF00
MSGACT429_CHSHIFT = 8
MSGACT429_SPD = 0x0080   # 1 = High Speed, 0 = Low Speed
MSGACT429_ERR = 0x0040   # Herhangi bir hata
MSGACT429_GAP = 0x0020   # Gap hatası
MSGACT429_PAR = 0x0010   # Parity hatası
MSGACT429_LONG = 0x0008  # Uzun Word hatası
MSGACT429_BIT = 0x0004   # Bit zamanı hatası
MSGACT429_TO = 0x0002    # Zaman aşımı hatası
MSGACT429_HIT = 0x0001   # Her zaman 1

# BTI429_ChGetInfo / CardGetInfo(INFOTYPE_CHINFO)
INFO429_PARAM = 0x0001

# =====================================================================================
# C yapıları (Windows LLP64 ve Linux LP64'te sabit genişlikli alanlar)
# =====================================================================================
_IS_64BIT = ctypes.sizeof(ctypes.c_void_p) == 8
HCARD_T = ctypes.c_void_p if _IS_64BIT else ctypes.c_int32
HCORE_T = ctypes.c_void_p if _IS_64BIT else ctypes.c_int32


class SEQRECORD429(ctypes.Structure):
    """BTICARD.H SEQRECORD429 (20 bayt, doğal hizalı)."""
    _fields_ = [
        ("type", ctypes.c_uint16),
        ("count", ctypes.c_uint16),
        ("timestamp", ctypes.c_uint32),
        ("activity", ctypes.c_uint16),
        ("decgap", ctypes.c_uint16),
        ("data", ctypes.c_uint32),
        ("timestamph", ctypes.c_uint32),
    ]


class SEQFINDINFO(ctypes.Structure):
    """BTICARD.H SEQFINDINFO."""
    _fields_ = [
        ("pRecFirst", ctypes.POINTER(ctypes.c_uint16)),
        ("pRecNext", ctypes.POINTER(ctypes.c_uint16)),
        ("pRecLast", ctypes.POINTER(ctypes.c_uint16)),
    ]


# =====================================================================================
# Veri modelleri
# =====================================================================================
class BallardError(Exception):
    """Ballard BTIDriver çağrı / kurulum hatası."""


@dataclass
class CardInfo:
    card_num: int
    core_num: int
    product: str
    card_type: str
    rx_channels: list[int] = field(default_factory=list)
    tx_channels: list[int] = field(default_factory=list)
    serial: int = 0
    parametric: bool = False

    def display_label(self) -> str:
        name = self.product or self.card_type or "Ballard"
        ch = f"{len(self.rx_channels)}R/{len(self.tx_channels)}T"
        sn = f" · S/N {self.serial}" if self.serial else ""
        return f"Kart #{self.card_num} · Core #{self.core_num} — {name} ({ch}{sn})"


@dataclass
class RxRecord:
    """Ballard Sequential Monitor'dan okunan tek ARINC 429 kaydı."""
    word: int
    timestamp_us: int
    channel: int
    activity: int = MSGACT429_HIT
    decgap: int = 0

    @property
    def speed_hs(self) -> bool:
        return bool(self.activity & MSGACT429_SPD)

    @property
    def err(self) -> bool:
        return bool(self.activity & MSGACT429_ERR)

    @property
    def parity_err(self) -> bool:
        return bool(self.activity & MSGACT429_PAR)

    @property
    def gap_err(self) -> bool:
        return bool(self.activity & MSGACT429_GAP)

    @property
    def bit_err(self) -> bool:
        return bool(self.activity & MSGACT429_BIT)

    @property
    def long_err(self) -> bool:
        return bool(self.activity & MSGACT429_LONG)

    @property
    def timeout_err(self) -> bool:
        return bool(self.activity & MSGACT429_TO)

    @property
    def error_flags(self) -> list[str]:
        out = []
        for mask, name in (
            (MSGACT429_PAR, "PAR"),
            (MSGACT429_GAP, "GAP"),
            (MSGACT429_BIT, "BIT"),
            (MSGACT429_LONG, "LONG"),
            (MSGACT429_TO, "TO"),
        ):
            if self.activity & mask:
                out.append(name)
        if not out and (self.activity & MSGACT429_ERR):
            out.append("ERR")
        return out


# =====================================================================================
# DLL bulma ve yükleme
# =====================================================================================
def dll_names() -> tuple[str, str]:
    """Çalışan Python mimarisine uygun (BTICard, BTI429) DLL adları."""
    return ("BTICARD64.DLL", "BTI42964.DLL") if _IS_64BIT else ("BTICARD.DLL", "BTI429.DLL")


def _search_dirs(dll_dir: str | None = None) -> list[str]:
    dirs: list[str] = []
    if dll_dir:
        dirs.append(dll_dir)
    if os.name == "nt":
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        dirs.append(os.path.join(sysroot, "System32"))
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ):
            for vendor in ("Ballard Technology", "Astronics", "Astronics AES"):
                root = os.path.join(base, vendor)
                if os.path.isdir(root):
                    dirs.append(root)
                    for sub in ("BTIDriver", "Drivers", "API", "Bin", "x64"):
                        p = os.path.join(root, sub)
                        if os.path.isdir(p):
                            dirs.append(p)
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if p:
                dirs.append(p)
    seen, out = set(), []
    for d in dirs:
        norm = os.path.normcase(os.path.normpath(d))
        if norm not in seen and os.path.isdir(d):
            seen.add(norm)
            out.append(d)
    return out


def _find_in_dir(directory: str, target_name: str) -> str | None:
    direct = os.path.join(directory, target_name)
    if os.path.isfile(direct):
        return direct
    want = target_name.lower()
    try:
        for fn in os.listdir(directory):
            if fn.lower() == want:
                return os.path.join(directory, fn)
    except OSError:
        pass
    return None


def find_dlls(dll_dir: str | None = None) -> tuple[str | None, str | None]:
    """BTICard ve BTI429 DLL tam yollarını arar; bulunamazsa (None, None) döner."""
    card_name, a429_name = dll_names()
    card_path = a429_path = None
    for d in _search_dirs(dll_dir):
        if card_path is None:
            card_path = _find_in_dir(d, card_name)
        if a429_path is None:
            a429_path = _find_in_dir(d, a429_name)
        if card_path and a429_path:
            break
    return card_path, a429_path


def _bind_driver(card_dll, a429_dll):
    """Tüm BTICard / BTI429 fonksiyonlarının ctypes argtypes/restype imzalarını bağlar."""
    c_i32 = ctypes.c_int32
    c_u16 = ctypes.c_uint16
    c_u32 = ctypes.c_uint32
    c_str = ctypes.c_char_p
    p_u16 = ctypes.POINTER(c_u16)
    p_u32 = ctypes.POINTER(c_u32)

    def bind(lib, name, argtypes, restype, required=True):
        fn = getattr(lib, name, None)
        if fn is None:
            if required:
                raise BallardError(f"DLL içinde beklenen fonksiyon yok: {name}")
            return None
        fn.argtypes = argtypes
        fn.restype = restype
        return fn

    # BTICard
    bind(card_dll, "BTICard_CardOpen", [ctypes.POINTER(HCARD_T), c_i32], c_i32)
    bind(card_dll, "BTICard_CardClose", [HCARD_T], c_i32)
    bind(card_dll, "BTICard_CoreOpen", [ctypes.POINTER(HCORE_T), c_i32, HCARD_T], c_i32)
    bind(card_dll, "BTICard_CardReset", [HCORE_T], None)
    bind(card_dll, "BTICard_CardStart", [HCORE_T], c_i32)
    bind(card_dll, "BTICard_CardStop", [HCORE_T], c_i32)
    bind(card_dll, "BTICard_CardIsRunning", [HCORE_T], c_i32, required=False)
    bind(card_dll, "BTICard_CardGetInfo", [c_u16, c_i32, HCORE_T], c_u32, required=False)
    bind(card_dll, "BTICard_CardProductStr", [HCORE_T], c_str, required=False)
    bind(card_dll, "BTICard_CardTypeStr", [HCORE_T], c_str, required=False)
    bind(card_dll, "BTICard_ErrDescStr", [c_i32, HCORE_T], c_str, required=False)
    bind(card_dll, "BTICard_CardTest", [c_u16, HCORE_T], c_i32, required=False)
    bind(card_dll, "BTICard_TimerResolution", [c_i32, HCORE_T], c_i32, required=False)
    bind(card_dll, "BTICard_SeqConfig", [c_u32, HCORE_T], c_i32)
    bind(card_dll, "BTICard_SeqClear", [HCORE_T], c_i32, required=False)
    bind(card_dll, "BTICard_SeqBlkRd", [p_u16, c_u32, p_u32, HCORE_T], c_u32, required=False)
    bind(card_dll, "BTICard_SeqRdEx", [p_u16, c_u16, HCORE_T], c_u16, required=False)
    bind(card_dll, "BTICard_SeqFindInit", [p_u16, c_u32, ctypes.POINTER(SEQFINDINFO)], c_i32)
    bind(
        card_dll,
        "BTICard_SeqFindNext429Ex",
        [ctypes.POINTER(SEQRECORD429), c_u16, ctypes.POINTER(SEQFINDINFO)],
        c_i32,
        required=False,
    )
    bind(
        card_dll,
        "BTICard_SeqFindNext429",
        [ctypes.POINTER(ctypes.POINTER(SEQRECORD429)), ctypes.POINTER(SEQFINDINFO)],
        c_i32,
        required=False,
    )

    # BTI429
    bind(a429_dll, "BTI429_ChIsRcv", [c_i32, HCORE_T], c_i32)
    bind(a429_dll, "BTI429_ChIsXmt", [c_i32, HCORE_T], c_i32)
    bind(a429_dll, "BTI429_ChConfig", [c_u32, c_i32, HCORE_T], c_i32)
    bind(a429_dll, "BTI429_ChClear", [c_i32, HCORE_T], c_i32, required=False)
    bind(a429_dll, "BTI429_ChStart", [c_i32, HCORE_T], c_i32, required=False)
    bind(a429_dll, "BTI429_ChStop", [c_i32, HCORE_T], c_i32, required=False)
    bind(a429_dll, "BTI429_FilterDefault", [c_u32, c_i32, HCORE_T], c_u32)
    bind(a429_dll, "BTI429_ListAsyncCreate", [c_u32, c_i32, c_i32, HCORE_T], c_u32)
    bind(a429_dll, "BTI429_ListDataWr", [c_u32, c_u32, HCORE_T], c_i32)
    bind(a429_dll, "BTI429_ListStatus", [c_u32, HCORE_T], c_i32, required=False)
    bind(a429_dll, "BTI429_ListClear", [c_u32, HCORE_T], c_i32, required=False)
    bind(a429_dll, "BTI429_SchedGap", [c_u16, c_i32, HCORE_T], c_i32)
    bind(a429_dll, "BTI429_SchedGapList", [c_u16, c_u32, c_i32, HCORE_T], c_i32, required=False)


class BTIDriver:
    """Yüklenmiş BTICard + BTI429 DLL çifti."""

    def __init__(self, card_dll, a429_dll, card_path: str = "", a429_path: str = ""):
        self.card = card_dll
        self.a429 = a429_dll
        self.card_path = card_path
        self.a429_path = a429_path
        _bind_driver(self.card, self.a429)

    @classmethod
    def load(cls, dll_dir: str | None = None) -> "BTIDriver":
        if os.name != "nt":
            raise BallardError("Ballard BTIDriver DLL'leri yalnızca Windows'ta yüklenebilir.")
        card_name, a429_name = dll_names()
        card_path, a429_path = find_dlls(dll_dir)
        # Yol bulunamadıysa Windows varsayılan DLL arama yolundan dene
        c_target = card_path or card_name
        a_target = a429_path or a429_name
        add_dir = getattr(os, "add_dll_directory", None)
        handles = []
        try:
            if add_dir:
                for p in {os.path.dirname(x) for x in (card_path, a429_path) if x}:
                    if os.path.isdir(p):
                        handles.append(add_dir(p))
            try:
                card_dll = ctypes.WinDLL(c_target)
            except OSError as e:
                arch = "64-bit" if _IS_64BIT else "32-bit"
                raise BallardError(
                    f"{card_name} yüklenemedi ({arch} Python): {e}. "
                    "Ballard BTIDriver sürücüsünün kurulu olduğundan ve DLL klasörünün doğru seçildiğinden emin olun."
                ) from e
            try:
                a429_dll = ctypes.WinDLL(a_target)
            except OSError as e:
                raise BallardError(f"{a429_name} yüklenemedi: {e}") from e
            return cls(card_dll, a429_dll, card_path or c_target, a429_path or a_target)
        finally:
            for h in handles:
                try:
                    h.close()
                except Exception:
                    pass

    def err_str(self, errval: int, handle=None) -> str:
        fn = getattr(self.card, "BTICard_ErrDescStr", None)
        if fn is None:
            return f"ERR {errval}"
        try:
            raw = fn(int(errval), handle)
            if raw:
                return raw.decode("ascii", errors="replace").strip()
        except Exception:
            pass
        return f"ERR {errval}"

    def check(self, errval: int, what: str, handle=None):
        if int(errval) < 0:
            raise BallardError(f"{what}: {self.err_str(errval, handle)} (kod {errval})")


def probe_cards(dll_dir: str | None = None, max_cards: int = 8, max_cores: int = 4,
                max_ch: int = 32) -> tuple[list[CardInfo], str]:
    """Kurulu Ballard kartlarını ve ARINC 429 RX/TX kanallarını tarar.

    Dönüş: ``(kartlar, bilgi_metni)``. DLL yüklenemezse ``BallardError`` fırlatır.
    """
    drv = BTIDriver.load(dll_dir)
    found: list[CardInfo] = []
    for card_num in range(max_cards):
        h_card = HCARD_T()
        err = drv.card.BTICard_CardOpen(ctypes.byref(h_card), card_num)
        if err != ERR_NONE:
            continue
        try:
            for core_num in range(max_cores):
                h_core = HCORE_T()
                cerr = drv.card.BTICard_CoreOpen(ctypes.byref(h_core), core_num, h_card)
                if cerr != ERR_NONE:
                    break
                rx = [ch for ch in range(max_ch) if drv.a429.BTI429_ChIsRcv(ch, h_core)]
                tx = [ch for ch in range(max_ch) if drv.a429.BTI429_ChIsXmt(ch, h_core)]
                if not rx and not tx:
                    continue
                prod = _cstr(drv.card, "BTICard_CardProductStr", h_core)
                ctype = _cstr(drv.card, "BTICard_CardTypeStr", h_core)
                serial = _info(drv.card, INFOTYPE_SERIALNUM, 0, h_core)
                param = any(bool(_info(drv.card, INFOTYPE_CHINFO, ch, h_core) & INFO429_PARAM) for ch in tx)
                found.append(CardInfo(card_num, core_num, prod, ctype, rx, tx, serial, param))
        finally:
            drv.card.BTICard_CardClose(h_card)
    return found, drv.card_path


def _cstr(card_dll, name: str, h_core) -> str:
    fn = getattr(card_dll, name, None)
    if fn is None:
        return ""
    try:
        raw = fn(h_core)
        return raw.decode("ascii", errors="replace").strip() if raw else ""
    except Exception:
        return ""


def _info(card_dll, infotype: int, ch: int, h_core) -> int:
    fn = getattr(card_dll, "BTICard_CardGetInfo", None)
    if fn is None:
        return 0
    try:
        return int(fn(infotype, ch, h_core))
    except Exception:
        return 0


# =====================================================================================
# BallardSession: gerçek BTIDriver donanım oturumu
# =====================================================================================
class BallardSession:
    """Tek bir Ballard kart / core üzerinde ARINC 429 RX + TX test oturumu."""

    SEQ_BUF_WORDS = 16384  # 32 KB USHORT tamponu (~1600 SEQRECORD429 kaydı/okuma)

    def __init__(self, card_num: int = 0, core_num: int = 0, dll_dir: str | None = None,
                 driver: BTIDriver | None = None):
        self.card_num = int(card_num)
        self.core_num = int(core_num)
        self.dll_dir = dll_dir
        self._drv = driver
        self._h_card = HCARD_T()
        self._h_core = HCORE_T()
        self._opened = False
        self._running = False
        self._rx_chan: int | None = None
        self._tx_chan: int | None = None
        self._tx_list: int = 0
        self._tx_speed: str = "HS"
        self._rx_speed: str = "HS"
        self._seq_buf = (ctypes.c_uint16 * self.SEQ_BUF_WORDS)()
        self.info: CardInfo | None = None

    def open(self) -> CardInfo:
        if self._opened:
            return self.info  # type: ignore[return-value]
        if self._drv is None:
            self._drv = BTIDriver.load(self.dll_dir)
        err = self._drv.card.BTICard_CardOpen(ctypes.byref(self._h_card), self.card_num)
        self._drv.check(err, f"Kart #{self.card_num} açılamadı", self._h_card)
        try:
            cerr = self._drv.card.BTICard_CoreOpen(ctypes.byref(self._h_core), self.core_num, self._h_card)
            self._drv.check(cerr, f"Core #{self.core_num} açılamadı", self._h_card)
            rx = [ch for ch in range(32) if self._drv.a429.BTI429_ChIsRcv(ch, self._h_core)]
            tx = [ch for ch in range(32) if self._drv.a429.BTI429_ChIsXmt(ch, self._h_core)]
            prod = _cstr(self._drv.card, "BTICard_CardProductStr", self._h_core)
            ctype = _cstr(self._drv.card, "BTICard_CardTypeStr", self._h_core)
            serial = _info(self._drv.card, INFOTYPE_SERIALNUM, 0, self._h_core)
            param = any(bool(_info(self._drv.card, INFOTYPE_CHINFO, ch, self._h_core) & INFO429_PARAM) for ch in tx)
            self.info = CardInfo(self.card_num, self.core_num, prod, ctype, rx, tx, serial, param)
            self._opened = True
            return self.info
        except Exception:
            self._drv.card.BTICard_CardClose(self._h_card)
            self._h_card = HCARD_T()
            self._h_core = HCORE_T()
            raise

    def close(self):
        if not self._opened or self._drv is None:
            return
        try:
            if self._running:
                self._drv.card.BTICard_CardStop(self._h_core)
        except Exception:
            pass
        try:
            self._drv.card.BTICard_CardClose(self._h_card)
        except Exception:
            pass
        self._running = False
        self._opened = False
        self._h_card = HCARD_T()
        self._h_core = HCORE_T()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def self_test(self) -> tuple[bool, str]:
        """Kartın yerleşik donanım öz-testlerini (seviye 0..2: I/O, bellek, işlemci) koşar."""
        fn = getattr(self._drv.card, "BTICard_CardTest", None) if self._drv else None
        if fn is None:
            return True, "CardTest bu sürücüde yok (atlandı)"
        if self._running:
            self._drv.card.BTICard_CardStop(self._h_core)
            self._running = False
        for lvl, label in ((TEST_LEVEL_0, "I/O"), (TEST_LEVEL_1, "Bellek"), (TEST_LEVEL_2, "İşlemci")):
            err = fn(lvl, self._h_core)
            if err != ERR_NONE:
                return False, f"Seviye {lvl} ({label}) başarısız: {self._drv.err_str(err, self._h_core)}"
        return True, "Seviye 0..2 (I/O, Bellek, İşlemci) geçti"

    def configure(
        self,
        rx_chan: int | None = None,
        tx_chan: int | None = None,
        rx_speed: str = "HS",
        tx_speed: str = "HS",
        rx_parity: str = "odd",
        tx_raw_parity: bool = True,
        selftest_loop: bool = False,
        async_capacity: int = 2048,
    ):
        """Kanalları ve Sequential Monitor'ü yapılandırıp kartı başlatır."""
        assert self._drv is not None and self._opened
        if self._running:
            self._drv.card.BTICard_CardStop(self._h_core)
            self._running = False

        self._drv.card.BTICard_CardReset(self._h_core)
        tr_fn = getattr(self._drv.card, "BTICard_TimerResolution", None)
        if tr_fn is not None:
            tr_fn(TIMERRESOL_1US, self._h_core)

        self._rx_chan = rx_chan
        self._tx_chan = tx_chan
        self._rx_speed = rx_speed
        self._tx_speed = tx_speed
        self._tx_list = 0

        if rx_chan is not None:
            rcfg = CHCFG429_SEQALL | (CHCFG429_HIGHSPEED if rx_speed == "HS" else CHCFG429_LOWSPEED)
            if rx_parity == "odd":
                rcfg |= CHCFG429_PARODD
            elif rx_parity == "even":
                rcfg |= CHCFG429_PAREVEN
            elif rx_parity == "data":
                rcfg |= CHCFG429_PARDATA
            if selftest_loop:
                rcfg |= CHCFG429_SELFTEST
            err = self._drv.a429.BTI429_ChConfig(rcfg, int(rx_chan), self._h_core)
            self._drv.check(err, f"Ballard RX CH{rx_chan} yapılandırma", self._h_core)
            faddr = self._drv.a429.BTI429_FilterDefault(MSGCRT429_DEFAULT, int(rx_chan), self._h_core)
            if faddr == 0:
                raise BallardError(f"Ballard RX CH{rx_chan} varsayılan filtresi oluşturulamadı")

        if tx_chan is not None:
            tcfg = CHCFG429_HIGHSPEED if tx_speed == "HS" else CHCFG429_LOWSPEED
            tcfg |= CHCFG429_PARDATA if tx_raw_parity else CHCFG429_PARODD
            if selftest_loop:
                tcfg |= CHCFG429_SELFTEST
            err = self._drv.a429.BTI429_ChConfig(tcfg, int(tx_chan), self._h_core)
            self._drv.check(err, f"Ballard TX CH{tx_chan} yapılandırma", self._h_core)
            laddr = self._drv.a429.BTI429_ListAsyncCreate(
                LISTCRT429_FIFO, int(async_capacity), int(tx_chan), self._h_core
            )
            if laddr == 0:
                raise BallardError(f"Ballard TX CH{tx_chan} asenkron FIFO listesi oluşturulamadı")
            self._tx_list = int(laddr)
            # EXAMP7.C: SchedGap(1024) asenkron FIFO'daki Word'leri standart 4-bit gap ile kesintisiz gönderir
            sched_err = self._drv.a429.BTI429_SchedGap(1024, int(tx_chan), self._h_core)
            if sched_err < 0:
                self._drv.check(sched_err, f"Ballard TX CH{tx_chan} SchedGap", self._h_core)

        if rx_chan is not None:
            serr = self._drv.card.BTICard_SeqConfig(SEQCFG_CONTINUOUS | SEQCFG_64K, self._h_core)
            if serr < 0:
                serr = self._drv.card.BTICard_SeqConfig(SEQCFG_CONTINUOUS, self._h_core)
            if serr < 0:
                serr = self._drv.card.BTICard_SeqConfig(SEQCFG_DEFAULT, self._h_core)
            self._drv.check(serr, "Ballard Sequential Monitor yapılandırma", self._h_core)

        err = self._drv.card.BTICard_CardStart(self._h_core)
        self._drv.check(err, "Ballard kart başlatma", self._h_core)
        self._running = True

    def drain_rx(self):
        """Sequential Monitor tamponunda birikmiş eski kayıtları temizler."""
        if not self._running or self._rx_chan is None:
            return
        for _ in range(16):
            if not self._read_seq_once():
                break

    def _read_seq_once(self) -> list[RxRecord]:
        assert self._drv is not None
        blk_fn = getattr(self._drv.card, "BTICard_SeqBlkRd", None)
        if blk_fn is not None:
            blkcnt = ctypes.c_uint32(0)
            seqcount = int(blk_fn(self._seq_buf, self.SEQ_BUF_WORDS, ctypes.byref(blkcnt), self._h_core))
        else:
            rd_fn = getattr(self._drv.card, "BTICard_SeqRdEx", None)
            if rd_fn is None:
                return []
            seqcount = int(rd_fn(self._seq_buf, self.SEQ_BUF_WORDS, self._h_core))
        if seqcount <= 0:
            return []
        sfinfo = SEQFINDINFO()
        if self._drv.card.BTICard_SeqFindInit(self._seq_buf, seqcount, ctypes.byref(sfinfo)) != ERR_NONE:
            return []

        out: list[RxRecord] = []
        next_ex = getattr(self._drv.card, "BTICard_SeqFindNext429Ex", None)
        if next_ex is not None:
            rec = SEQRECORD429()
            rec_sz = ctypes.sizeof(SEQRECORD429)
            while next_ex(ctypes.byref(rec), rec_sz, ctypes.byref(sfinfo)) == ERR_NONE:
                out.append(self._to_rx_record(rec))
        else:
            next_ptr = getattr(self._drv.card, "BTICard_SeqFindNext429", None)
            if next_ptr is not None:
                prec = ctypes.POINTER(SEQRECORD429)()
                while next_ptr(ctypes.byref(prec), ctypes.byref(sfinfo)) == ERR_NONE and prec:
                    out.append(self._to_rx_record(prec.contents))
        return out

    @staticmethod
    def _to_rx_record(rec: SEQRECORD429) -> RxRecord:
        ver1 = (rec.type & SEQVER_MASK) >= SEQVER_1
        ts = ((int(rec.timestamph) << 32) | int(rec.timestamp)) if ver1 else int(rec.timestamp)
        ch = (int(rec.activity) & MSGACT429_CHMASK) >> MSGACT429_CHSHIFT
        return RxRecord(
            word=int(rec.data) & 0xFFFFFFFF,
            timestamp_us=ts,
            channel=ch,
            activity=int(rec.activity),
            decgap=int(rec.decgap) if ver1 else 0,
        )

    def read_rx(
        self,
        chan: int | None = None,
        timeout_s: float = 0.0,
        min_count: int = 0,
        quiet_gap_s: float = 0.015,
        stop: threading.Event | None = None,
    ) -> list[RxRecord]:
        """Sequential Monitor'dan ``chan`` kanalına ait kayıtları okur."""
        target = self._rx_chan if chan is None else chan
        got: list[RxRecord] = []
        deadline = time.monotonic() + max(0.0, timeout_s)
        last_rx = time.monotonic()
        while True:
            if stop is not None and stop.is_set():
                break
            chunk = self._read_seq_once()
            if chunk:
                for r in chunk:
                    if target is None or r.channel == target:
                        got.append(r)
                last_rx = time.monotonic()
            now = time.monotonic()
            if min_count > 0 and len(got) >= min_count and (now - last_rx) >= quiet_gap_s:
                break
            if now >= deadline:
                break
            time.sleep(0.002)
        return got

    def send_words(self, words: list[int], wait_done_s: float = 5.0, stop: threading.Event | None = None):
        """Asenkron FIFO üzerinden Word listesini sırayla gönderir ve hat boşalana kadar bekler."""
        if not self._running or not self._tx_list:
            raise BallardError("Ballard TX kanalı yapılandırılmadı.")
        assert self._drv is not None
        t_end = time.monotonic() + max(0.5, wait_done_s)
        for wd in words:
            val = int(wd) & 0xFFFFFFFF
            while not self._drv.a429.BTI429_ListDataWr(val, self._tx_list, self._h_core):
                if stop is not None and stop.is_set():
                    return
                if time.monotonic() > t_end:
                    raise BallardError("Ballard TX asenkron FIFO doldu (zaman aşımı).")
                time.sleep(0.0005)

        # FIFO boşalana kadar bekle
        st_fn = getattr(self._drv.a429, "BTI429_ListStatus", None)
        if st_fn is not None:
            while st_fn(self._tx_list, self._h_core) not in (STAT_EMPTY, STAT_OFF):
                if stop is not None and stop.is_set():
                    return
                if time.monotonic() > t_end:
                    raise BallardError("Ballard TX gönderimi zaman aşımına uğradı.")
                time.sleep(0.001)
        # Son Word + 4 bit gap'in hattan tamamen çıkması için bekleme (HS: 0.36 ms, LS: 2.88 ms)
        word_s = 0.0005 if self._tx_speed == "HS" else 0.0035
        time.sleep(word_s * 2)


# =====================================================================================
# MockBallardSession: birim testi / donanımsız doğrulama için
# =====================================================================================
class MockBallardSession:
    """Donanım olmadan a429/busbox_test.py'yi uçtan uca test eden bellek-içi BusBox modeli.

    ``on_tx(words, speed, raw_parity)`` geri çağrısı ile gönderilen Word'leri dış
    sisteme (ör. sahte IP veya RTL eş-simülatörü) iletebilir; ``push_rx(word, ...)``
    ile dış TX'ten gelen Word'leri Sequential Monitor'e kaydeder.
    """

    def __init__(
        self,
        rx_channels: list[int] | None = None,
        tx_channels: list[int] | None = None,
        product: str = "BUSBox BB1120 (Mock)",
        on_tx=None,
        clock_scale: float = 1.0,
    ):
        self.info = CardInfo(
            card_num=0,
            core_num=0,
            product=product,
            card_type="BUSBOX",
            rx_channels=list(rx_channels if rx_channels is not None else [0, 1, 2, 3]),
            tx_channels=list(tx_channels if tx_channels is not None else [4, 5]),
            serial=1120001,
            parametric=False,
        )
        self.on_tx = on_tx
        self.clock_scale = clock_scale
        self._opened = False
        self._running = False
        self._rx_chan: int | None = None
        self._tx_chan: int | None = None
        self._rx_speed = "HS"
        self._tx_speed = "HS"
        self._rx_parity = "odd"
        self._tx_raw_parity = True
        self._rx_queue: list[RxRecord] = []
        self._ts_us = 1000
        self.tx_log: list[tuple[str, list[int]]] = []
        self.wiring_tx = "ok"    # ok | swapped | open
        self.wiring_rx = "ok"    # ok | swapped | open

    def open(self) -> CardInfo:
        self._opened = True
        return self.info

    def close(self):
        self._running = False
        self._opened = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def self_test(self) -> tuple[bool, str]:
        return True, "Mock öz-test geçti"

    def configure(
        self,
        rx_chan: int | None = None,
        tx_chan: int | None = None,
        rx_speed: str = "HS",
        tx_speed: str = "HS",
        rx_parity: str = "odd",
        tx_raw_parity: bool = True,
        selftest_loop: bool = False,
        async_capacity: int = 2048,
    ):
        self._rx_chan = rx_chan
        self._tx_chan = tx_chan
        self._rx_speed = rx_speed
        self._tx_speed = tx_speed
        self._rx_parity = rx_parity
        self._tx_raw_parity = tx_raw_parity
        self._rx_queue.clear()
        self._running = True

    def drain_rx(self):
        self._rx_queue.clear()

    def push_rx(self, word: int, speed: str = "HS", dt_us: int | None = None, decgap: int = 4):
        """Dış vericiden (ör. FPGA TX) BusBox RX kanalına Word enjekte eder."""
        if not self._running or self._rx_chan is None:
            return
        if self.wiring_tx == "open":
            return
        if speed != self._rx_speed:
            return
        w = (word ^ 0xFFFFFFFF) if self.wiring_tx == "swapped" else (word & 0xFFFFFFFF)
        act = (self._rx_chan << MSGACT429_CHSHIFT) | MSGACT429_HIT
        if speed == "HS":
            act |= MSGACT429_SPD
        ones = bin(w).count("1")
        if self._rx_parity == "odd" and ones % 2 == 0:
            act |= MSGACT429_PAR | MSGACT429_ERR
        elif self._rx_parity == "even" and ones % 2 == 1:
            act |= MSGACT429_PAR | MSGACT429_ERR
        step = dt_us if dt_us is not None else (360 if speed == "HS" else 2880)
        self._ts_us += max(1, round(step * self.clock_scale))
        self._rx_queue.append(RxRecord(word=w, timestamp_us=self._ts_us, channel=self._rx_chan, activity=act, decgap=decgap))

    def read_rx(
        self,
        chan: int | None = None,
        timeout_s: float = 0.0,
        min_count: int = 0,
        quiet_gap_s: float = 0.015,
        stop: threading.Event | None = None,
    ) -> list[RxRecord]:
        target = self._rx_chan if chan is None else chan
        matched, rest = [], []
        for r in self._rx_queue:
            if target is None or r.channel == target:
                matched.append(r)
            else:
                rest.append(r)
        self._rx_queue = rest
        return matched

    def send_words(self, words: list[int], wait_done_s: float = 5.0, stop: threading.Event | None = None):
        if not self._running or self._tx_chan is None:
            raise BallardError("Mock Ballard TX yapılandırılmadı.")
        out = [int(w) & 0xFFFFFFFF for w in words]
        self.tx_log.append((self._tx_speed, out))
        if self.wiring_rx == "open":
            return
        if self.wiring_rx == "swapped":
            out = [w ^ 0xFFFFFFFF for w in out]
        if self.on_tx is not None:
            self.on_tx(out, self._tx_speed, self._tx_raw_parity)
