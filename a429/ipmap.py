"""ARINC 429 IP register haritasının TEK kaynağı.

Bu modülden üretilenler:
  * AXIL Studio register spec'i (``build_regspec``) -> vhdl/scripts/gen_axil_spec.py ile
    arinc429_axil.regspec.json / .axproj.json / .axlib.json ve AXIL Studio (axilgen) ile
    arinc429_axil.v / arinc429_axil_pk.v,
  * top VHDL (arinc429_ip.vhd) port bağlantıları (``port_bindings``),
  * uygulama ve simülatör için IP sözlüğü (``to_ip_dict``),
  * mantıksal alan adları (``LOGICAL_*``): uygulama eski register adlarını (ör. TX_LABEL,
    RX0_CUST_MIN_PULSE) kullanmaya devam eder; bunlar gruplanmış register'daki alana çözülür.

Gruplama kuralı: aynı işleve ait küçük alanlar tek 32-bit register'da durur
(ör. TX_WORD = Label/SDI/Data/SSM/Parity ARINC Word düzeninde, *_CUST_PULSE = MIN|MAX).
"""
from __future__ import annotations

IP_VERSION = (2, 0, 0)
IP_VERSION_STR = "%d.%d.%d" % IP_VERSION
IP_VERSION_WORD = (IP_VERSION[0] << 16) | (IP_VERSION[1] << 8) | IP_VERSION[2]
IP_ID_WORD = 0x41343239  # 'A429'
MAX_RX = 16              # SOFT_RESET[31:16], RXn sayfaları 0x4000..0x7FFF

# ---------------------------------------------------------------------------
# Mantıksal alanlar: eski (tek alanlı register) adı -> (fiziksel register, alan)
# Kanal alanları önek olmadan (RX0_ / TB_ eklenir). Alan adı "=" ise register adıyla aynıdır.
# ---------------------------------------------------------------------------
LOGICAL_TX = {
    "TX_TRANSMITTER_EN": ("TX_CTRL", "TRANSMITTER_EN"),
    "TX_MSG_SCHED_EN": ("TX_CTRL", "MSG_SCHED_EN"),
    "TX_BUILDER_EN": ("TX_CTRL", "BUILDER_EN"),
    "TX_SCHED_EN": ("TX_CTRL", "SCHED_EN"),
    "TX_LABEL": ("TX_WORD", "LABEL_VAL"),
    "TX_SDI": ("TX_WORD", "SDI"),
    "TX_DATA": ("TX_WORD", "DATA"),
    "TX_SSM": ("TX_WORD", "SSM"),
    "TX_PARITY_TYPE": ("TX_WORD", "PARITY_TYPE"),
    "TX_EXT_HIGH": ("TX_EXT_LINE", "HIGH"),
    "TX_EXT_LOW": ("TX_EXT_LINE", "LOW"),
    "TX_CFG_SEL": ("TX_CFG", "SEL"),
    "TX_CFG_APPLY": ("TX_CFG", "APPLY"),
    "TX_CUST_PULSE_DUR": ("TX_CUST_TIMING", "PULSE_DUR"),
    "TX_CUST_NULL_DUR": ("TX_CUST_TIMING", "NULL_DUR"),
    "TX_ACT_PULSE_DUR": ("TX_ACT_TIMING", "PULSE_DUR"),
    "TX_ACT_NULL_DUR": ("TX_ACT_TIMING", "NULL_DUR"),
}

LOGICAL_CH = {
    "CFG_SEL": ("CFG", "SEL"),
    "CFG_APPLY": ("CFG", "APPLY"),
    "CUST_MIN_PULSE": ("CUST_PULSE", "MIN"),
    "CUST_MAX_PULSE": ("CUST_PULSE", "MAX"),
    "CUST_MIN_BIT": ("CUST_BIT", "MIN"),
    "CUST_MAX_BIT": ("CUST_BIT", "MAX"),
    "CUST_MAX_PULSE_ERR": ("CUST_NOISE", "PULSE_ERR"),
    "CUST_MAX_NULL_ERR": ("CUST_NOISE", "NULL_ERR"),
    "CUST_GLITCH_FILTER_SIZE": ("CUST_FILTER", "GLITCH_SIZE"),
    "CUST_MAX_GAP_ERR": ("CUST_FILTER", "GAP_ERR"),
    "CUST_PARITY_MODE": ("CUST_PARITY", "="),
    "ACT_MIN_PULSE": ("ACT_PULSE", "MIN"),
    "ACT_MAX_PULSE": ("ACT_PULSE", "MAX"),
    "ACT_MIN_BIT": ("ACT_BIT", "MIN"),
    "ACT_MAX_BIT": ("ACT_BIT", "MAX"),
    "ACT_MAX_PULSE_ERR": ("ACT_NOISE", "PULSE_ERR"),
    "ACT_MAX_NULL_ERR": ("ACT_NOISE", "NULL_ERR"),
    "ACT_GLITCH_FILTER_SIZE": ("ACT_FILTER", "GLITCH_SIZE"),
    "ACT_MAX_GAP_ERR": ("ACT_FILTER", "GAP_ERR"),
    "ACT_PARITY_MODE": ("ACT_PARITY", "="),
    "ERR_RD_CODE": ("ERR_RD_INFO", "CODE"),
    "ERR_RD_ADDR": ("ERR_RD_INFO", "ADDR"),
    "BIT_RD_PULSE": ("BIT_RD_PULSE", "DUR"),
    "BIT_RD_PULSE_ERR": ("BIT_RD_PULSE", "ERR"),
    "BIT_RD_NULL": ("BIT_RD_NULL", "DUR"),
    "BIT_RD_NULL_ERR": ("BIT_RD_NULL", "ERR"),
}


def logical_target(name: str):
    """Mantıksal ad -> (fiziksel register, alan) ya da None. Kanal önekleri: RXn_ / TB_."""
    if name in LOGICAL_TX:
        return LOGICAL_TX[name]
    for pre in ("TB_",) + tuple(f"RX{n}_" for n in range(32)):
        if name.startswith(pre):
            t = LOGICAL_CH.get(name[len(pre):])
            if t:
                reg = pre + t[0]
                return reg, (reg if t[1] == "=" else t[1])
            return None
    return None


# ---------------------------------------------------------------------------
# Register spec üreteci
# ---------------------------------------------------------------------------
class _Builder:
    def __init__(self):
        self.regs: list[dict] = []
        self.bind: dict[tuple[str, str], str] = {}     # (reg, field) -> VHDL ifadesi
        self.strobe: dict[str, str] = {}               # port adı -> VHDL ifadesi

    def f(self, name, lsb, width=1, kind="RW", reset=0, desc="", bind=None):
        return {"name": name, "lsb": lsb, "width": width, "kind": kind, "reset": f"0x{reset:X}",
                "desc": desc, "_bind": bind}

    def reg(self, name, offset, fields, desc="", wr=None, rd=None):
        d = {"name": name, "offset": f"0x{offset:04X}", "desc": desc, "fields": []}
        for fd in fields:
            b = fd.pop("_bind")
            if b is not None:
                self.bind[(name, fd["name"])] = b
            d["fields"].append(fd)
        if wr is not None:
            d["wr_strobe"] = True
            self.strobe[f"o_{name.lower()}_wr"] = wr
        if rd is not None:
            d["rd_strobe"] = True
            self.strobe[f"o_{name.lower()}_rd"] = rd
        self.regs.append(d)

    def sreg(self, name, offset, width, kind="RW", reset=0, desc="", bind=None, **kw):
        """Tek alanlı register (alan adı = register adı -> kısa port o_<reg> / i_<reg>)."""
        self.reg(name, offset, [self.f(name, 0, width, kind, reset, desc, bind)], desc, **kw)


def _build(num_rx=1, has_tx=True, has_txbit=True, has_bitdiag=True, clk_hz=50_000_000,
           wdepth_log2=8, edepth_log2=8, bitdiag_log2=3) -> _Builder:
    if not 0 <= num_rx <= MAX_RX:
        # Sınırlar: SOFT_RESET.RXn bit 16..31, RXn sayfası 0x4000 + n*0x400 (64 KB pencere), CAPS.NUM_RX 5 bit
        raise ValueError(f"num_rx 0..{MAX_RX} olmalı (verilen: {num_rx})")
    if not has_tx:
        has_txbit = False
    B = _Builder()
    f = B.f

    # ---- Global sayfa (0x0000)
    B.sreg("IP_ID", 0x0000, 32, "CONST", IP_ID_WORD, "ARINC 429 IP kimliği ('A429')")
    B.sreg("IP_VERSION", 0x0004, 32, "CONST", IP_VERSION_WORD,
           f"IP sürümü ({IP_VERSION_STR}; [23:16] major, [15:8] minor, [7:0] patch)")
    B.reg("CAPS", 0x0008, [
        f("NUM_RX", 0, 5, "CONST", num_rx, "RX kanal sayısı"),
        f("TX", 8, 1, "CONST", int(has_tx), "TX kanalı var"),
        f("TXBIT", 9, 1, "CONST", int(has_txbit), "TX BIT kanalı var"),
        f("RX_TEST", 10, 1, "CONST", 0, "RX test pinleri var"),
        f("BITDIAG", 11, 1, "CONST", int(has_bitdiag), "Bit diagnostic RAM var"),
    ], "Donanım yetenekleri")
    B.reg("CAPS_MEM", 0x000C, [
        f("WORD_DEPTH_LOG2", 0, 8, "CONST", wdepth_log2, "Word RAM derinliği (log2)"),
        f("ERR_DEPTH_LOG2", 8, 8, "CONST", edepth_log2, "Error RAM derinliği (log2)"),
        f("BITDIAG_WORDS_LOG2", 16, 8, "CONST", bitdiag_log2, "Bit diagnostic Word sayısı (log2)"),
    ], "RAM derinlikleri")
    B.sreg("CLK_HZ", 0x0010, 32, "CONST", clk_hz, "IP sistem saati (Hz)")

    rst = [
        f("RST_ALL", 0, 1, "PULSE", 0, "Tüm IP yumuşak reseti", "rst_all"),
        f("TX", 1, 1, "PULSE", 0, "TX kanalı reseti", "rst_tx"),
        f("TXBIT", 2, 1, "PULSE", 0, "TX BIT kanalı reseti", "rst_txbit"),
    ]
    for n in range(num_rx):
        rst.append(f(f"RX{n}", 16 + n, 1, "PULSE", 0, f"RX{n} kanalı reseti", f"rst_rx({n})"))
    B.reg("SOFT_RESET", 0x0020, rst, "Yumuşak reset darbeleri (self-clearing)")
    B.sreg("GLOBAL_FREEZE", 0x0024, 1, "RW", 0, "Tüm logger'ları eşzamanlı dondur", "global_freeze")
    B.reg("TS_CTRL", 0x0028, [
        f("ENABLE", 0, 1, "RW", 1, "64-bit timestamp sayacı etkin", "ts_en"),
        f("CLEAR", 1, 1, "PULSE", 0, "Timestamp sayacını sıfırla", "ts_clr"),
    ], "Timestamp kontrol")
    B.sreg("TS_LSB", 0x002C, 32, "RO", 0, "Timestamp alt 32 bit (okununca MSB latch'lenir)", "ts_lsb",
           rd="ts_lsb_rd")
    B.sreg("TS_MSB", 0x0030, 32, "RO", 0, "Latch'lenmiş timestamp üst 32 bit", "ts_msb")

    # ---- TX sayfası (0x0400)
    if has_tx:
        t = 0x0400
        i, o = "tx_reg_in", "tx_reg_out"
        B.reg("TX_CTRL", t + 0x00, [
            f("TRANSMITTER_EN", 0, 1, "RW", 0, "1: Word Transmitter, 0: EXT_LINE hat override", f"{i}.transmitter_en"),
            f("MSG_SCHED_EN", 1, 1, "RW", 0, "1: Message Scheduler, 0: SEND_CMD tek gönderim", f"{i}.msg_sched_en"),
            f("BUILDER_EN", 2, 1, "RW", 0, "1: Word Builder (TX_WORD), 0: EXT_DATA", f"{i}.builder_en"),
            f("SCHED_EN", 3, 1, "RW", 0, "Message Scheduler başlat/durdur", f"{i}.sched_en"),
        ], "TX kanal kontrolü (kaynak ve mod seçimleri)")
        B.reg("TX_WORD", t + 0x04, [
            f("LABEL_VAL", 0, 8, "RW", 0, "ARINC 429 Label (octal 000-377)", f"{i}.label_val"),
            f("SDI", 8, 2, "RW", 0, "SDI (0-3)", f"{i}.sdi"),
            f("DATA", 10, 19, "RW", 0, "Data (19-bit)", f"{i}.data"),
            f("SSM", 29, 2, "RW", 0, "SSM (0-3)", f"{i}.ssm"),
            f("PARITY_TYPE", 31, 1, "RW", 1, "Parity tipi (1: Odd, 0: Even); parity bitini IP hesaplar",
              f"{i}.parity_type"),
        ], "Word Builder alanları (ARINC 429 Word bit düzeninde)")
        B.reg("TX_SEND_CMD", t + 0x08, [f("SEND", 0, 1, "PULSE", 0, "Tek Word gönderim tetiği", f"{i}.send_cmd")],
              "Tek gönderim darbesi")
        B.sreg("TX_EXT_DATA", t + 0x0C, 32, "RW", 0, "Hazır 32-bit Word (BUILDER_EN=0)", f"{i}.ext_data")
        B.reg("TX_EXT_LINE", t + 0x10, [
            f("HIGH", 0, 1, "RW", 0, "Hat override HIGH çıkışı", f"{i}.ext_high"),
            f("LOW", 1, 1, "RW", 0, "Hat override LOW çıkışı", f"{i}.ext_low"),
        ], "Hat override (TRANSMITTER_EN=0): 10 HIGH, 01 LOW, 00 NULL, 11 HIGH-Z")
        B.sreg("TX_INITIAL_DELAY", t + 0x20, 32, "RW", 0, "Scheduler başlangıç gecikmesi (clk)", f"{i}.initial_delay")
        B.sreg("TX_INTER_WORD_GAP", t + 0x24, 32, "RW", 1, "Scheduler Word arası ekstra bekleme (clk, >=1)",
               f"{i}.inter_word_gap")
        B.reg("TX_CFG", t + 0x40, [
            f("SEL", 0, 2, "RW", 0, "Config seçimi (0: HS Preset, 1: LS Preset, 2: Custom)", f"{i}.cfg_sel"),
            f("APPLY", 4, 1, "PULSE", 0, "Seçili TX config'i etkinleştir", f"{i}.cfg_apply"),
        ], "TX config seçimi ve uygulama")
        B.reg("TX_CUST_TIMING", t + 0x44, [
            f("PULSE_DUR", 0, 16, "RW", 0, "Custom Pulse süresi (clk)", f"{i}.cust.pulse_dur"),
            f("NULL_DUR", 16, 16, "RW", 0, "Custom Null süresi (clk)", f"{i}.cust.null_dur"),
        ], "Custom bit zamanlaması")
        B.sreg("TX_CUST_GAP_DUR", t + 0x48, 32, "RW", 0, "Custom Word Gap süresi (clk)", f"{i}.cust.gap_dur")
        B.sreg("TX_CUST_SLP", t + 0x4C, 1, "RW", 0, "Custom SLP eğim çıkışı (1: HS, 0: LS)", f"{i}.cust.slp")
        B.reg("TX_ACT_TIMING", t + 0x60, [
            f("PULSE_DUR", 0, 16, "RO", 0, "Aktif Pulse süresi (clk)", f"{o}.act.pulse_dur"),
            f("NULL_DUR", 16, 16, "RO", 0, "Aktif Null süresi (clk)", f"{o}.act.null_dur"),
        ], "Aktif bit zamanlaması")
        B.sreg("TX_ACT_GAP_DUR", t + 0x64, 32, "RO", 0, "Aktif Word Gap süresi (clk)", f"{o}.act.gap_dur")
        B.sreg("TX_ACT_SLP", t + 0x68, 1, "RO", 0, "Aktif SLP eğim çıkışı", f"{o}.act.slp")
        B.reg("TX_STATUS", t + 0x80, [
            f("BUSY", 0, 1, "RO", 0, "TX gönderim yapıyor", f"{o}.busy"),
            f("SCHED_ACTIVE", 1, 1, "RO", 0, "Scheduler aktif", f"{o}.sched_active"),
            f("ACT_CFG", 2, 2, "RO", 0, "Aktif TX config modu (0:HS, 1:LS, 2:Custom)", f"{o}.act_cfg"),
        ], "TX durum register'ı")
        B.sreg("TX_WORD_CNT", t + 0x84, 32, "RO", 0, "Gönderilen toplam Word sayısı", f"{o}.word_cnt")

    # ---- Kanal sayfası (TB ve RX0..RXn ortak)
    def page(P: str, base: int, rin: str, rout: str, checker: bool):
        p = P.lower()
        B.reg(P + "CTRL", base + 0x00, [
            f("ENABLE", 0, 1, "RW", 0, "Logger kayıt etkin (0 iken Word ve hata KAYDEDİLMEZ)", f"{rin}.ctrl_enable"),
            f("FREEZE", 1, 1, "RW", 0, "RAM okuma için dondur", f"{rin}.ctrl_freeze"),
            f("CLEAR", 2, 1, "PULSE", 0, "Sayaç ve RAM pointer'larını temizle", f"{rin}.ctrl_clear"),
        ], f"{P[:-1]} kanal kontrolü")
        B.reg(P + "STATUS", base + 0x04, [
            f("FROZEN", 4, 1, "RO", 0, "Logger donduruldu", f"{rout}.status_frozen"),
            f("WORD_WRAP", 5, 1, "RO", 0, "Word RAM taştı/döndü", f"{rout}.status_word_wrap"),
            f("ERR_WRAP", 6, 1, "RO", 0, "Error RAM taştı/döndü", f"{rout}.status_err_wrap"),
            f("ACT_CFG", 8, 2, "RO", 0, "Aktif RX config modu (0:HS, 1:LS, 2:Custom)", f"{rout}.status_act_cfg"),
            f("LINE_HIGH", 12, 1, "RO", 0, "Hat anlık seviyesi: alıcı HIGH çıkışı (senkronlanmış)",
              f"{rout}.status_line_high"),
            f("LINE_LOW", 13, 1, "RO", 0, "Hat anlık seviyesi: alıcı LOW çıkışı (senkronlanmış)",
              f"{rout}.status_line_low"),
            f("SYNC_WAIT", 14, 1, "RO", 0, "Decoder hat senkronu bekliyor (en az 4 bit temiz NULL gerekli)",
              f"{rout}.status_sync_wait"),
        ], f"{P[:-1]} kanal durumu ve hat teşhisi")
        B.reg(P + "CFG", base + 0x08, [
            f("SEL", 0, 2, "RW", 0, "Config seçimi (0: HS, 1: LS, 2: Custom)", f"{rin}.cfg_sel"),
            f("APPLY", 4, 1, "PULSE", 0, "Seçili config'i uygula", f"{rin}.cfg_apply"),
        ], "RX config seçimi ve uygulama")
        for kind, off, side, acc in (("CUST", 0x40, rin + ".cust", "RW"), ("ACT", 0x60, rout + ".act", "RO")):
            what = "Custom" if kind == "CUST" else "Aktif"
            B.reg(P + kind + "_PULSE", base + off + 0x00, [
                f("MIN", 0, 16, acc, 0, f"{what} Min Pulse (clk)", f"{side}.min_pulse"),
                f("MAX", 16, 16, acc, 0, f"{what} Max Pulse (clk)", f"{side}.max_pulse"),
            ], f"{what} pulse süre sınırları")
            B.reg(P + kind + "_BIT", base + off + 0x04, [
                f("MIN", 0, 16, acc, 0, f"{what} Min Bit (clk)", f"{side}.min_bit"),
                f("MAX", 16, 16, acc, 0, f"{what} Max Bit (clk)", f"{side}.max_bit"),
            ], f"{what} bit süre sınırları")
            B.reg(P + kind + "_NOISE", base + off + 0x08, [
                f("PULSE_ERR", 0, 16, acc, 0, f"{what} Max Pulse Glitch Error", f"{side}.max_pulse_err"),
                f("NULL_ERR", 16, 16, acc, 0, f"{what} Max Null Glitch Error", f"{side}.max_null_err"),
            ], f"{what} pulse/null gürültü (glitch) limitleri")
            B.reg(P + kind + "_FILTER", base + off + 0x0C, [
                f("GLITCH_SIZE", 0, 16, acc, 0, f"{what} Glitch Filter boyu (clk)", f"{side}.glitch_filter_size"),
                f("GAP_ERR", 16, 16, acc, 0, f"{what} Max Gap Glitch Error", f"{side}.max_gap_err"),
            ], f"{what} glitch filtresi ve gap gürültü limiti")
            B.sreg(P + kind + "_PARITY", base + off + 0x10, 2, acc, 1 if kind == "CUST" else 0,
                   f"{what} Parity modu (0:Kapalı, 1:Odd, 2:Even)", f"{side}.parity_mode")
        B.sreg(P + "WORD_CNT", base + 0xE0, 32, "RO", 0, "Geçerli Word sayısı", f"{rout}.word_cnt")
        B.sreg(P + "ERR_CNT", base + 0xE4, 32, "RO", 0, "Hata kaydı sayısı", f"{rout}.err_cnt")
        B.sreg(P + "DROP_CNT", base + 0xE8, 32, "RO", 0, "Freeze sırasında atılan kayıt sayısı", f"{rout}.drop_cnt")
        B.sreg(P + "LAST_WORD", base + 0xEC, 32, "RO", 0, "Alınan son geçerli Word", f"{rout}.last_word")
        # Word kaydı (son register okununca pointer +1)
        B.sreg(P + "WORD_RADDR", base + 0x100, wdepth_log2, "RW", 0,
               "Word RAM başlangıç okuma adresi (yazınca pointer yüklenir)", f"s_{p}word_raddr",
               wr=f"{rin}.word_raddr_wr")
        B.sreg(P + "WORD_RD_TS_MSB", base + 0x104, 32, "RO", 0, "Word kaydı Timestamp MSB", f"{rout}.word_rd_ts_msb")
        B.sreg(P + "WORD_RD_TS_LSB", base + 0x108, 32, "RO", 0, "Word kaydı Timestamp LSB", f"{rout}.word_rd_ts_lsb")
        B.sreg(P + "WORD_RD_DATA", base + 0x10C, 32, "RO", 0, "Word kaydı 32-bit veri", f"{rout}.word_rd_data")
        B.sreg(P + "WORD_RD_GAP", base + 0x110, 32, "RO", 0, "Word kaydı önceki Gap süresi (clk)", f"{rout}.word_rd_gap")
        B.sreg(P + "WORD_RD_GAP_ERR", base + 0x114, 16, "RO", 0,
               "Word kaydı Gap gürültü sayısı (okununca pointer +1)", f"{rout}.word_rd_gap_err",
               rd=f"{rin}.word_rd_last")
        # Error kaydı
        B.sreg(P + "ERR_RADDR", base + 0x120, edepth_log2, "RW", 0,
               "Error RAM başlangıç okuma adresi (yazınca pointer yüklenir)", f"s_{p}err_raddr",
               wr=f"{rin}.err_raddr_wr")
        B.sreg(P + "ERR_RD_TS_MSB", base + 0x124, 32, "RO", 0, "Error kaydı Timestamp MSB", f"{rout}.err_rd_ts_msb")
        B.sreg(P + "ERR_RD_TS_LSB", base + 0x128, 32, "RO", 0, "Error kaydı Timestamp LSB", f"{rout}.err_rd_ts_lsb")
        B.reg(P + "ERR_RD_INFO", base + 0x12C, [
            f("CODE", 0, 16, "RO", 0, "Hata kodu bitmask", f"{rout}.err_rd_code"),
            f("ADDR", 16, 16, "RO", 0, "Konum: bit no / 32 = gap / FIFO adresi", f"{rout}.err_rd_addr"),
        ], "Error kaydı hata kodu ve konumu")
        B.sreg(P + "ERR_RD_DATA", base + 0x130, 32, "RO", 0,
               "Error kaydı ölçüm/beklenen veri (okununca pointer +1)", f"{rout}.err_rd_data",
               rd=f"{rin}.err_rd_last")
        # Bit Diagnostic kaydı
        B.reg(P + "BIT_RADDR", base + 0x140, [
            f("BIT_IDX", 0, 5, "RW", 0, "Bit indeksi (0-31)", f"{rin}.bit_raddr_bit"),
            f("WORD_IDX", 8, bitdiag_log2, "RW", 0, "Bit Diagnostic Word indeksi", f"s_{p}bit_widx"),
        ], "Bit Diagnostic RAM başlangıç okuma adresi (yazınca pointer yüklenir)", wr=f"{rin}.bit_raddr_wr")
        B.reg(P + "BIT_RD_PULSE", base + 0x144, [
            f("DUR", 0, 16, "RO", 0, "Bit Pulse süresi (clk)", f"{rout}.bit_rd_pulse"),
            f("ERR", 16, 16, "RO", 0, "Bit Pulse gürültü sayısı", f"{rout}.bit_rd_pulse_err"),
        ], "Bit Pulse süresi ve gürültüsü")
        B.reg(P + "BIT_RD_NULL", base + 0x148, [
            f("DUR", 0, 16, "RO", 0, "Bit Null süresi (clk)", f"{rout}.bit_rd_null"),
            f("ERR", 16, 16, "RO", 0, "Bit Null gürültü sayısı", f"{rout}.bit_rd_null_err"),
        ], "Bit Null süresi ve gürültüsü (okununca pointer +1)", rd=f"{rin}.bit_rd_last")
        if checker:
            B.reg(P + "CHK_CTRL", base + 0x1C0, [
                f("ENABLE", 0, 1, "RW", 0, "Word Checker etkin", f"{rin}.chk_enable"),
                f("CLEAR", 1, 1, "PULSE", 0, "Checker FIFO ve sayaçlarını temizle", f"{rin}.chk_clear"),
            ], "TX BIT Word Checker kontrol")
            B.sreg(P + "CHK_TIMEOUT", base + 0x1C4, 32, "RW", 0, "Echo zaman aşımı (clk, 0=kapalı)",
                   f"{rin}.chk_timeout")
            B.sreg(P + "CHK_OK_CNT", base + 0x1C8, 32, "RO", 0, "Eşleşen Word sayısı", f"{rout}.chk_ok_cnt")
            B.sreg(P + "CHK_ERR_CNT", base + 0x1CC, 32, "RO", 0, "Checker hata sayısı", f"{rout}.chk_err_cnt")
            B.reg(P + "CHK_STATUS", base + 0x1D0, [
                f("FIFO_LEVEL", 0, 4, "RO", 0, "Beklenen Word FIFO doluluğu", f"{rout}.chk_fifo_level"),
                f("FIFO_OVF", 4, 1, "RO", 0, "FIFO taşma bayrağı", f"{rout}.chk_fifo_ovf"),
            ], "TX BIT Checker FIFO durumu")

    if has_txbit:
        page("TB_", 0x0800, "tb_reg_in", "tb_reg_out", True)
    for n in range(num_rx):
        page(f"RX{n}_", 0x4000 + n * 0x0400, f"rx_reg_in({n})", f"rx_reg_out({n})", False)
    B.regs.sort(key=lambda r: int(r["offset"], 0))
    return B


def build_regspec(module="arinc429_axil", num_rx=1, has_tx=True, has_txbit=True, has_bitdiag=True,
                  clk_hz=50_000_000, wdepth_log2=8, edepth_log2=8, bitdiag_log2=3, packed=True) -> dict:
    """AXIL Studio register spec'i (axilgen.ModuleSpec.from_dict biçimi)."""
    B = _build(num_rx, has_tx, has_txbit, has_bitdiag, clk_hz, wdepth_log2, edepth_log2, bitdiag_log2)
    has_txbit = has_txbit and has_tx
    return {
        "format": "axil-regspec",
        "version": 1,
        "module": module,
        "desc": f"ARINC 429 IP ({num_rx} RX, TX={'Var' if has_tx else 'Yok'}, "
                f"TX BIT={'Var' if has_txbit else 'Yok'}, {clk_hz // 1_000_000} MHz)",
        "packed": packed,
        "ip_version": IP_VERSION_STR,
        "panel": "arinc429",
        "registers": B.regs,
    }


def _field_base(reg: str, field: str) -> str:
    """AXIL Studio axilgen.fbase: alan adı register adıyla aynıysa yalnızca register adı."""
    return reg.lower() if field.upper() == reg.upper() else f"{reg.lower()}_{field.lower()}"


def port_bindings(num_rx=1, has_tx=True, has_txbit=True, has_bitdiag=True, clk_hz=50_000_000,
                  wdepth_log2=8, edepth_log2=8, bitdiag_log2=3) -> list[tuple[str, str, int, str]]:
    """AXIL slave IP tarafı portları, AXIL Studio sırasıyla: (port, yön 'in'/'out', genişlik, VHDL sinyali)."""
    B = _build(num_rx, has_tx, has_txbit, has_bitdiag, clk_hz, wdepth_log2, edepth_log2, bitdiag_log2)
    out = []
    for r in B.regs:
        for fd in sorted(r["fields"], key=lambda x: x["lsb"]):
            kind = fd["kind"]
            if kind == "CONST":
                continue
            base = _field_base(r["name"], fd["name"])
            port = ("i_" if kind in ("RO", "W1C") else "o_") + base
            sig = B.bind.get((r["name"], fd["name"]))
            if sig is None:
                raise ValueError(f"{r['name']}.{fd['name']}: top VHDL bağlantısı tanımsız")
            out.append((port, "in" if port.startswith("i_") else "out", fd["width"], sig))
        for flag, suf in (("wr_strobe", "wr"), ("rd_strobe", "rd")):
            if r.get(flag):
                port = f"o_{r['name'].lower()}_{suf}"
                out.append((port, "out", 1, B.strobe[port]))
    return out


def reg_access(reg: dict) -> str:
    kinds = {f["kind"] for f in reg["fields"]}
    if kinds <= {"RO", "CONST"}:
        return "RO"
    if kinds <= {"PULSE"}:
        return "WO"
    return "RW"


def reg_reset(reg: dict) -> int:
    v = 0
    for fd in reg["fields"]:
        if fd["kind"] in ("RW", "CONST"):
            mask = ((1 << fd["width"]) - 1) << fd["lsb"]
            v |= (int(fd["reset"], 0) << fd["lsb"]) & mask
    return v


def to_ip_registers(spec: dict) -> list[dict]:
    """Spec -> AXIL Studio IPBlock register listesi (proje / kütüphane / Debug Bridge biçimi)."""
    out = []
    for r in spec["registers"]:
        out.append({
            "name": r["name"],
            "offset": f"0x{int(r['offset'], 0):08X}",
            "access": reg_access(r),
            "reset": f"0x{reg_reset(r):08X}",
            "desc": r.get("desc", ""),
            "fields": [{"name": fd["name"], "lsb": fd["lsb"], "width": fd["width"], "desc": fd.get("desc", ""),
                        "kind": fd["kind"]} for fd in r["fields"]],
        })
    return out


def to_ip_dict(name="ARINC429", base=0x40000000, **kw) -> dict:
    """Uygulama / simülatör için Debug Bridge IP sözlüğü (client.ip biçimi)."""
    spec = build_regspec(**kw)
    return {"name": name, "base": base, "panel": "arinc429", "desc": spec["desc"],
            "version": IP_VERSION_STR, "registers": to_ip_registers(spec)}
