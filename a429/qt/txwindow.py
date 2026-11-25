"""TX Canlı Kontrol bileşeni (Qt): Taslak A kompakt gömülü panel (TxLivePanel) + ayrılabilir pencere (TxLiveWindow)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QRadioButton, QVBoxLayout, QWidget,
)

from ..txlive import (
    OVERRIDE_LINES, TIME_UNITS, TRIGGER, build_word, fmt_binary, override_writes,
    parse_bin_word, parse_builder, parse_hex_word, parity_bit, sched_values as calc_sched,
    to_clk, word_fields_text,
)
from . import look

PLAY, PAUSE = "▶ Başlat", "⏸ Durdur"


def _subpanel() -> tuple[QFrame, QVBoxLayout]:
    fr = QFrame()
    fr.setObjectName("SubPanel")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(6)
    return fr, lay


class TxLivePanel(QWidget):
    """Scroll gerektirmeyen kompakt TX Canlı Kontrol paneli (gömülü veya yüzen pencerede)."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._loading = False
        self._io_enabled = True
        self.sched_on = getattr(app, "tx_sched_on", False)
        self._sched_start_cnt: int | None = None
        self.manual_running = False
        self.sent = 0
        self.skipped = 0
        self._first_manual = True

        self._manual_timer = QTimer(self)
        self._manual_timer.timeout.connect(self._tick)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._build_word(lay)
        self._build_send(lay)
        self._build_override(lay)
        lay.addStretch(1)

        self.load()

    # ------------------------------------------------------------- Word
    def _build_word(self, parent_lay):
        self.word_box, lay = _subpanel()

        # Üst satır: kaynak seçici + hex özet + Word Yaz
        top = QHBoxLayout()
        top.setSpacing(8)
        self.rb_builder = QRadioButton("Word Oluşturucu")
        self.rb_direct = QRadioButton("Direkt 32-bit")
        grp = QButtonGroup(self.word_box)
        grp.addButton(self.rb_builder)
        grp.addButton(self.rb_direct)
        self.rb_builder.toggled.connect(self._changed)
        top.addWidget(self.rb_builder)
        top.addWidget(self.rb_direct)
        top.addStretch(1)

        self.lbl_hex_out = look.label("0x00000000", "mono")
        self.lbl_hex_out.setFont(look.bold(look.mono_font()))
        top.addWidget(self.lbl_hex_out)
        top.addWidget(look.button("Kopyala", None, lambda: self._copy(self.lbl_hex_out.text().replace("0x", ""))))
        self.btn_write_word = look.button("Word Yaz", "primary", self.write_word)
        top.addWidget(self.btn_write_word)
        lay.addLayout(top)

        # Builder: tek satırda 5 sütun
        self.w_builder = QWidget()
        bl = QGridLayout(self.w_builder)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setHorizontalSpacing(6)
        bl.setVerticalSpacing(2)
        self.ed_label = QLineEdit()
        self.ed_sdi = QLineEdit()
        self.ed_data = QLineEdit()
        self.ed_ssm = QLineEdit()
        self.cb_par = QComboBox()
        self.cb_par.addItems(["Odd", "Even"])
        self.cb_par.currentTextChanged.connect(self._changed)
        for ed in (self.ed_label, self.ed_sdi, self.ed_data, self.ed_ssm):
            ed.setFont(look.mono_font(-0.5))
            ed.textChanged.connect(self._changed)
        for c, (hdr, w) in enumerate((
            ("Label (oct)", self.ed_label),
            ("SDI (0–3)", self.ed_sdi),
            ("Data (hex)", self.ed_data),
            ("SSM (0–3)", self.ed_ssm),
            ("Parity", self.cb_par),
        )):
            bl.addWidget(look.label(hdr, "muted"), 0, c)
            bl.addWidget(w, 1, c)
        bl.setColumnStretch(0, 2)
        bl.setColumnStretch(1, 1)
        bl.setColumnStretch(2, 3)
        bl.setColumnStretch(3, 1)
        bl.setColumnStretch(4, 2)
        lay.addWidget(self.w_builder)

        # Direct: tek satırda Hex + Binary
        self.w_direct = QWidget()
        dl = QHBoxLayout(self.w_direct)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        self.ed_hex = QLineEdit()
        self.ed_hex.setFixedWidth(100)
        self.ed_hex.setPlaceholderText("Hex")
        self.ed_hex.setFont(look.mono_font(-0.5))
        self.ed_hex.textChanged.connect(lambda _: self._direct_edit("hex"))
        self.ed_bin = QLineEdit()
        self.ed_bin.setPlaceholderText("32-bit Binary")
        self.ed_bin.setFont(look.mono_font(-0.5))
        self.ed_bin.textChanged.connect(lambda _: self._direct_edit("bin"))
        dl.addWidget(look.label("Hex:", "muted"))
        dl.addWidget(self.ed_hex)
        dl.addWidget(look.label("Bin:", "muted"))
        dl.addWidget(self.ed_bin, 1)
        lay.addWidget(self.w_direct)

        # Tek satır Binary + alan bilgisi
        brow = QHBoxLayout()
        brow.setSpacing(6)
        self.lbl_bin_out = look.label("", "mono")
        self.lbl_bin_out.setFont(look.mono_font(-1))
        self.lbl_bin_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        brow.addWidget(self.lbl_bin_out, 1)
        self.lbl_word_info = look.label("", "muted")
        brow.addWidget(self.lbl_word_info)
        lay.addLayout(brow)

        parent_lay.addWidget(self.word_box)

    def _copy(self, text: str):
        if text:
            QApplication.clipboard().setText(text.replace(" ", ""))
            self.app.set_status(f"Kopyalandı: {text}")

    def _direct_edit(self, kind: str):
        if self._loading:
            return
        self._loading = True
        try:
            word = parse_hex_word(self.ed_hex.text()) if kind == "hex" else parse_bin_word(self.ed_bin.text())
            if kind == "hex":
                self.ed_bin.setText(fmt_binary(word))
            else:
                self.ed_hex.setText(f"{word:08X}")
            self.app.ci.tx_live["word"] = f"{word:08X}"
        except ValueError:
            pass
        self._loading = False
        self._changed()

    def _cfg_dict(self) -> dict:
        return {
            "source": "direct" if self.rb_direct.isChecked() else "builder",
            "label": self.ed_label.text(),
            "sdi": self.ed_sdi.text(),
            "data": self.ed_data.text(),
            "ssm": self.ed_ssm.text(),
            "parity": self.cb_par.currentText(),
            "word": self.ed_hex.text(),
            "send_mode": "scheduler" if self.rb_sched.isChecked() else "manual",
            "delay_us": self.ed_delay.text(),
            "delay_unit": self.cb_delay_u.currentText(),
            "gap_mode": "period" if self.cb_gap_mode.currentIndex() == 0 else "direct",
            "period_us": self.ed_period.text(),
            "period_unit": self.cb_period_u.currentText(),
            "gap_us": self.ed_gap.text(),
            "gap_unit": self.cb_gap_u.currentText(),
            "manual_period": self.ed_mper.text(),
            "manual_unit": self.cb_mper_u.currentText(),
        }

    def current_word(self) -> int:
        cfg = self._cfg_dict()
        if cfg["source"] == "builder":
            return build_word(*parse_builder(cfg))
        if self.ed_bin.text().replace(" ", "") != f"{parse_hex_word(self.ed_hex.text()):032b}":
            parse_bin_word(self.ed_bin.text())
        return parse_hex_word(self.ed_hex.text())

    def word_writes(self) -> list[tuple[str, int]]:
        cfg = self._cfg_dict()
        if cfg["source"] == "direct":
            return [("TX_EXT_DATA", self.current_word()), ("TX_BUILDER_EN", 0)]
        label, sdi, data, ssm, odd = parse_builder(cfg)
        build_word(label, sdi, data, ssm, odd)
        return [
            ("TX_LABEL", label), ("TX_SDI", sdi), ("TX_DATA", data),
            ("TX_SSM", ssm), ("TX_PARITY_TYPE", int(odd)), ("TX_BUILDER_EN", 1),
        ]

    def write_word(self):
        try:
            writes = self.word_writes()
            wd = self.current_word()
        except ValueError as e:
            QMessageBox.warning(self, "TX Canlı Kontrol", str(e))
            return
        src = "Direkt 32-bit" if self.rb_direct.isChecked() else "Word Oluşturucu"
        self.app.tx_write(
            "TX Word yazılıyor", writes,
            on_done=lambda ok: self.app.record_tx_event("Word Yaz", "Word Yaz", wd, src, ok),
        )

    # ------------------------------------------------------------- Gönderim
    def _build_send(self, parent_lay):
        self.send_box, lay = _subpanel()

        # Üst satır: Scheduler / Manuel seçici + aksiyon düğmeleri
        top = QHBoxLayout()
        top.setSpacing(8)
        self.rb_sched = QRadioButton("Scheduler (IP)")
        self.rb_manual = QRadioButton("Manuel")
        mgrp = QButtonGroup(self.send_box)
        mgrp.addButton(self.rb_sched)
        mgrp.addButton(self.rb_manual)
        self.rb_sched.toggled.connect(self._changed)
        top.addWidget(self.rb_sched)
        top.addWidget(self.rb_manual)
        top.addStretch(1)

        self.btn_sched = look.button(PLAY, "primary", self.toggle_scheduler)
        self.btn_write_sched = look.button("Ayarları Yaz", None, self.write_scheduler)
        self.btn_mplay = look.button(PLAY, "primary", self.press_manual)
        self.btn_msingle = look.button("Tek Gönder", None, self.manual_send)
        for b in (self.btn_sched, self.btn_write_sched, self.btn_mplay, self.btn_msingle):
            top.addWidget(b)
        lay.addLayout(top)

        # Scheduler: tek satırda Initial delay | Mod | Periyot veya Gap
        self.w_sched = QWidget()
        sl = QVBoxLayout(self.w_sched)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        sg = QGridLayout()
        sg.setContentsMargins(0, 0, 0, 0)
        sg.setHorizontalSpacing(6)
        sg.setVerticalSpacing(2)

        sg.addWidget(look.label("Initial delay", "muted"), 0, 0, 1, 2)
        self.ed_delay = QLineEdit()
        self.ed_delay.setMinimumWidth(60)
        self.ed_delay.textChanged.connect(self._changed)
        self.cb_delay_u = QComboBox()
        self.cb_delay_u.addItems(TIME_UNITS)
        self.cb_delay_u.setFixedWidth(58)
        self.cb_delay_u.currentTextChanged.connect(self._changed)
        sg.addWidget(self.ed_delay, 1, 0)
        sg.addWidget(self.cb_delay_u, 1, 1)

        sg.addWidget(look.label("Gap modu", "muted"), 0, 2)
        self.cb_gap_mode = QComboBox()
        self.cb_gap_mode.addItems(["Periyottan", "Direkt Gap"])
        self.cb_gap_mode.currentIndexChanged.connect(self._changed)
        sg.addWidget(self.cb_gap_mode, 1, 2)

        self.lbl_period = look.label("Periyot", "muted")
        self.ed_period = QLineEdit()
        self.ed_period.setMinimumWidth(60)
        self.ed_period.textChanged.connect(self._changed)
        self.cb_period_u = QComboBox()
        self.cb_period_u.addItems(TIME_UNITS)
        self.cb_period_u.setFixedWidth(58)
        self.cb_period_u.currentTextChanged.connect(self._changed)
        sg.addWidget(self.lbl_period, 0, 3, 1, 2)
        sg.addWidget(self.ed_period, 1, 3)
        sg.addWidget(self.cb_period_u, 1, 4)

        self.lbl_gap = look.label("Inter word gap", "muted")
        self.ed_gap = QLineEdit()
        self.ed_gap.setMinimumWidth(60)
        self.ed_gap.textChanged.connect(self._changed)
        self.cb_gap_u = QComboBox()
        self.cb_gap_u.addItems(TIME_UNITS)
        self.cb_gap_u.setFixedWidth(58)
        self.cb_gap_u.currentTextChanged.connect(self._changed)
        sg.addWidget(self.lbl_gap, 0, 5, 1, 2)
        sg.addWidget(self.ed_gap, 1, 5)
        sg.addWidget(self.cb_gap_u, 1, 6)
        sl.addLayout(sg)

        self.lbl_sched_info = QLabel("")
        self.lbl_sched_info.setWordWrap(True)
        sl.addWidget(self.lbl_sched_info)
        lay.addWidget(self.w_sched)

        # Manuel: tek satır
        self.w_manual = QWidget()
        ml = QHBoxLayout(self.w_manual)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(6)
        ml.addWidget(look.label("PC Periyodu:", "muted"))
        self.ed_mper = QLineEdit()
        self.ed_mper.setFixedWidth(72)
        self.ed_mper.textChanged.connect(self._changed)
        self.cb_mper_u = QComboBox()
        self.cb_mper_u.addItems(TIME_UNITS)
        self.cb_mper_u.setFixedWidth(58)
        self.cb_mper_u.currentTextChanged.connect(self._changed)
        ml.addWidget(self.ed_mper)
        ml.addWidget(self.cb_mper_u)
        self.lbl_manual_info = QLabel("")
        ml.addWidget(self.lbl_manual_info, 1)
        lay.addWidget(self.w_manual)

        parent_lay.addWidget(self.send_box)

    def _tbit_us(self) -> float:
        p = next((x for x in self.app.ci.profiles if x.name == self.app.ci.tx_profile), self.app.ci.profiles[0])
        if p.rate_nom <= 0:
            raise ValueError("TX ARINC profilinde Bit Rate NOM sıfırdan büyük olmalı.")
        return 1000.0 / p.rate_nom

    def sched_values(self):
        p = next((x for x in self.app.ci.profiles if x.name == self.app.ci.tx_profile), self.app.ci.profiles[0])
        return calc_sched(self._cfg_dict(), self.app.ci.clk_mhz, self._tbit_us(), p.name)

    def sched_writes(self) -> list[tuple[str, int]]:
        delay, gap, _ = self.sched_values()
        return [("TX_INITIAL_DELAY", delay), ("TX_INTER_WORD_GAP", gap)]

    def write_scheduler(self):
        try:
            writes = self.sched_writes()
        except ValueError as e:
            QMessageBox.warning(self, "TX Canlı Kontrol", str(e))
            return
        self.app.tx_write("TX Scheduler ayarları yazılıyor", writes)

    def toggle_scheduler(self):
        enable = not self.sched_on
        try:
            writes = (
                self.sched_writes() + [("TX_MSG_SCHED_EN", 1), ("TX_SCHED_EN", 1)]
                if enable
                else [("TX_SCHED_EN", 0)]
            )
        except ValueError as e:
            QMessageBox.warning(self, "TX Canlı Kontrol", str(e))
            return

        try:
            wd = self.current_word()
        except ValueError:
            wd = None

        def on_res(ok: bool, cnt: int | None):
            if ok:
                self.sched_on = enable
                self.app.tx_sched_on = enable
                self._sync_run_state()
                if enable:
                    self._sched_start_cnt = cnt
                    detail = self.lbl_sched_info.text()
                    if cnt is not None:
                        detail += f" · Başlangıç TX_WORD_CNT={cnt:,}"
                else:
                    start = self._sched_start_cnt
                    self._sched_start_cnt = None
                    if start is not None and cnt is not None:
                        delta = (cnt - start) & 0xFFFFFFFF
                        detail = f"Donanımda {delta:,} Word gönderildi (Δ TX_WORD_CNT: {start:,} → {cnt:,})"
                    else:
                        detail = "Durduruldu"
            else:
                detail = "Başlatılamadı" if enable else "Durdurulamadı"
            self.app.record_tx_event(
                "Scheduler", "Scheduler ▶" if enable else "Scheduler ⏸", wd, detail, ok,
            )

        self.app.tx_scheduler_write(enable, writes, on_result=on_res)

    def manual_period_ms(self) -> float:
        cfg = self._cfg_dict()
        mhz = self.app.ci.clk_mhz
        try:
            v = float(cfg["manual_period"].strip().replace(",", "."))
        except ValueError:
            raise ValueError("Periyot sayı olmalı.") from None
        if v < 0:
            raise ValueError("Periyot negatif olamaz.")
        ms = to_clk(v, cfg["manual_unit"], mhz) / mhz / 1000.0
        if ms < 1.0:
            raise ValueError("Periyot en az 1 ms olmalı.")
        return ms

    def manual_send(self):
        try:
            wd = self.current_word()
        except ValueError:
            wd = None
        self.app.tx_write(
            "TX manuel gönderim", [("TX_MSG_SCHED_EN", 0)] + TRIGGER,
            on_done=lambda ok: self.app.record_tx_event("Gönderim", "Tek Gönder", wd, "SEND_CMD darbesi", ok),
        )

    def press_manual(self):
        if self.manual_running:
            self.stop_manual()
            return
        try:
            ms = self.manual_period_ms()
        except ValueError as e:
            QMessageBox.warning(self, "TX Canlı Kontrol", str(e))
            return
        self.manual_running = True
        self.sent = 0
        self.skipped = 0
        self._first_manual = True
        self._sync_run_state()
        self._manual_timer.start(max(1, round(ms)))
        self._tick()

    def _tick(self):
        if not self.manual_running:
            return
        try:
            ms = self.manual_period_ms()
        except ValueError:
            self.stop_manual()
            return
        self._manual_timer.setInterval(max(1, round(ms)))
        if self.app.busy:
            self.skipped += 1
        else:
            writes = ([("TX_MSG_SCHED_EN", 0)] if self._first_manual else []) + TRIGGER
            if not self.app.tx_write("TX periyodik gönderim", writes, on_done=self._tick_done, quiet=True, verify=False):
                self.stop_manual()
                return
            self._first_manual = False
        self._update_manual_text()

    def _tick_done(self, ok: bool):
        try:
            wd = self.current_word()
        except ValueError:
            wd = None
        if ok:
            self.sent += 1
            self.app.record_tx_event("Gönderim", "Periyodik", wd, f"#{self.sent}", True)
            self._update_manual_text()
        else:
            self.app.record_tx_event("Gönderim", "Periyodik", wd, "Başarısız", False)
            self.stop_manual()

    def stop_manual(self):
        self.manual_running = False
        self._manual_timer.stop()
        self._sync_run_state()

    def _update_manual_text(self):
        try:
            txt = f"{self.manual_period_ms():g} ms"
            color = look.tokens()["muted"]
        except ValueError as e:
            txt = str(e)
            color = look.tokens()["danger"]
        if self.sent or self.skipped or self.manual_running:
            txt += f" · Gönderilen: {self.sent}, atlanan: {self.skipped}"
        self.lbl_manual_info.setText(txt)
        self.lbl_manual_info.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------- Hat override (tek satır)
    def _build_override(self, parent_lay):
        fr, lay = _subpanel()
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(look.label("Hat Override", "cardTitle"))
        row.addSpacing(4)
        self._ov_btns: dict[str, QRadioButton] = {}
        grp = QButtonGroup(fr)
        for name in OVERRIDE_LINES:
            rb = QRadioButton(name)
            grp.addButton(rb)
            row.addWidget(rb)
            self._ov_btns[name] = rb
        row.addStretch(1)
        self.btn_override = look.button("Uygula", "primary", self.apply_override)
        row.addWidget(self.btn_override)
        lay.addLayout(row)

        self.lbl_ov_info = QLabel("")
        self.lbl_ov_info.setWordWrap(True)
        self.lbl_ov_info.setStyleSheet(f"color: {look.tokens()['danger']};")
        self.lbl_ov_info.setVisible(False)
        lay.addWidget(self.lbl_ov_info)
        parent_lay.addWidget(fr)

    def apply_override(self):
        choice = next((k for k, rb in self._ov_btns.items() if rb.isChecked()), "Kapalı")

        def done(ok: bool):
            if ok:
                self.app.tx_override = choice
                self.app.recalc_tx()
                self._sync_override()
            self.app.record_tx_event("Override", f"Override: {choice}", None, "Hat sürüş modu", ok)

        self.app.tx_write(f"TX hat override: {choice}", override_writes(choice), on_done=done)

    def override_on(self) -> bool:
        return getattr(self.app, "tx_override", "Kapalı") != "Kapalı"

    def _sync_override(self):
        on = self.override_on()
        if on:
            self.stop_manual()
        self.word_box.setEnabled(not on)
        self.send_box.setEnabled(not on)
        self.lbl_ov_info.setVisible(on)
        if on:
            self.lbl_ov_info.setText(
                f"Hat override etkin: {self.app.tx_override}. Word ve Gönderim kilitli; devam etmek için Kapalı → Uygula."
            )
        self._sync_run_state()
        self.refresh()

    def _sync_run_state(self):
        self.btn_sched.setText(PAUSE if self.sched_on else PLAY)
        self.btn_mplay.setText(PAUSE if self.manual_running else PLAY)
        self.btn_msingle.setEnabled(not self.manual_running and self._io_enabled)
        running = self.sched_on or self.manual_running
        self.rb_sched.setEnabled(not running)
        self.rb_manual.setEnabled(not running)

    def set_io_enabled(self, enabled: bool, tip: str = ""):
        self._io_enabled = enabled
        for b in (self.btn_write_word, self.btn_sched, self.btn_write_sched, self.btn_mplay, self.btn_msingle, self.btn_override):
            b.setEnabled(enabled)
            b.setToolTip(tip)
        if not enabled and self.manual_running:
            self.stop_manual()
        self._sync_run_state()

    # ------------------------------------------------------------- durum
    def load(self):
        self._loading = True
        cfg = self.app.ci.tx_live
        self.rb_direct.setChecked(cfg.get("source") == "direct")
        self.rb_builder.setChecked(cfg.get("source") != "direct")
        self.ed_label.setText(cfg.get("label", "310"))
        self.ed_sdi.setText(cfg.get("sdi", "0"))
        self.ed_data.setText(cfg.get("data", "00000"))
        self.ed_ssm.setText(cfg.get("ssm", "0"))
        self.cb_par.setCurrentText(cfg.get("parity", "Odd"))
        try:
            w = parse_hex_word(cfg.get("word", "00000000"))
            self.ed_hex.setText(f"{w:08X}")
            self.ed_bin.setText(fmt_binary(w))
        except ValueError:
            self.ed_hex.setText(cfg.get("word", "00000000"))

        self.rb_sched.setChecked(cfg.get("send_mode") != "manual")
        self.rb_manual.setChecked(cfg.get("send_mode") == "manual")
        self.ed_delay.setText(cfg.get("delay_us", "0"))
        self.cb_delay_u.setCurrentText(cfg.get("delay_unit", "µs"))
        self.cb_gap_mode.setCurrentIndex(0 if cfg.get("gap_mode") != "direct" else 1)
        self.ed_period.setText(cfg.get("period_us", "1000"))
        self.cb_period_u.setCurrentText(cfg.get("period_unit", "µs"))
        self.ed_gap.setText(cfg.get("gap_us", "100"))
        self.cb_gap_u.setCurrentText(cfg.get("gap_unit", "µs"))
        self.ed_mper.setText(cfg.get("manual_period", "100"))
        self.cb_mper_u.setCurrentText(cfg.get("manual_unit", "ms"))

        ov = getattr(self.app, "tx_override", "Kapalı")
        if ov in self._ov_btns:
            self._ov_btns[ov].setChecked(True)
        self._loading = False
        self._sync_override()

    def _changed(self):
        if self._loading:
            return
        self.app.ci.tx_live.update(self._cfg_dict())
        self.app.mark_dirty()
        self.app.recalc_tx()
        self.refresh()

    def refresh(self):
        direct = self.rb_direct.isChecked()
        self.w_builder.setVisible(not direct)
        self.w_direct.setVisible(direct)
        try:
            word = self.current_word()
            self.lbl_hex_out.setText(f"0x{word:08X}")
            self.lbl_bin_out.setText(fmt_binary(word))
            p_txt = (
                f"Parity biti: {word >> 31}"
                if not direct
                else f"Parity: {'Odd' if parity_bit(word, True) == word >> 31 else 'Even'}"
            )
            self.lbl_word_info.setText(p_txt)
            self.lbl_word_info.setStyleSheet(f"color: {look.tokens()['muted']};")
        except ValueError as e:
            self.lbl_hex_out.setText("HATA")
            self.lbl_bin_out.setText("")
            self.lbl_word_info.setText(str(e))
            self.lbl_word_info.setStyleSheet(f"color: {look.tokens()['danger']};")

        by_sched = self.rb_sched.isChecked()
        self.w_sched.setVisible(by_sched)
        self.w_manual.setVisible(not by_sched)
        self.btn_sched.setVisible(by_sched)
        self.btn_write_sched.setVisible(by_sched)
        self.btn_mplay.setVisible(not by_sched)
        self.btn_msingle.setVisible(not by_sched)

        by_per = self.cb_gap_mode.currentIndex() == 0
        for w in (self.lbl_period, self.ed_period, self.cb_period_u):
            w.setVisible(by_per)
        for w in (self.lbl_gap, self.ed_gap, self.cb_gap_u):
            w.setVisible(not by_per)

        try:
            delay_clk, gap_clk, _ = self.sched_values()
            mhz = self.app.ci.clk_mhz
            self.lbl_sched_info.setText(
                f"Inter-word gap: {gap_clk / mhz:g} µs ({gap_clk:,} clk)  ·  Initial delay: {delay_clk / mhz:g} µs ({delay_clk:,} clk)"
            )
            self.lbl_sched_info.setStyleSheet(f"color: {look.tokens()['muted' if self.override_on() else 'success']};")
        except ValueError as e:
            first_line = str(e).splitlines()[-1]
            self.lbl_sched_info.setText(first_line)
            self.lbl_sched_info.setStyleSheet(f"color: {look.tokens()['danger']};")
        self._update_manual_text()


class TxLiveWindow(QDialog):
    """TxLivePanel'i yüzen pencerede barındırır; kapanınca Kontrol sekmesine geri yerleştirir."""

    def __init__(self, parent, panel: TxLivePanel, on_dock):
        super().__init__(parent)
        self.panel = panel
        self._on_dock = on_dock
        self._docked = False
        self.setWindowTitle("TX Canlı Kontrol")
        self.resize(560, 420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(look.label("TX Canlı Kontrol", "cardTitle"))
        bar.addStretch(1)
        bar.addWidget(look.button("Panele geri al ↙", None, self.close))
        lay.addLayout(bar)

        self._card = look.Card(margins=2, spacing=0, object_name="Card")
        self._card.lay.addWidget(panel, 1)
        lay.addWidget(self._card, 1)

    def detach_panel(self):
        self._card.lay.removeWidget(self.panel)

    def closeEvent(self, ev):
        if not self._docked:
            self._docked = True
            self._on_dock()
        super().closeEvent(ev)
