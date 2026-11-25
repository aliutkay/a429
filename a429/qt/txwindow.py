"""TX Canlı Kontrol penceresi (Qt): Word, Scheduler veya manuel gönderim ve hat override."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QRadioButton, QVBoxLayout, QWidget,
)

from ..txlive import (
    OVERRIDE_LINES, TIME_UNITS, TRIGGER, build_word, fmt_binary, override_writes,
    parse_bin_word, parse_builder, parse_hex_word, parity_bit, sched_values as calc_sched,
    to_clk, word_fields_text,
)
from . import look

PLAY, PAUSE = "▶ Başlat", "⏸ Durdur"


class TxLiveWindow(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("TX Canlı Kontrol")
        self._loading = False
        self.sched_on = getattr(app, "tx_sched_on", False)
        self.manual_running = False
        self.sent = 0
        self.skipped = 0
        self._first_manual = True

        self._manual_timer = QTimer(self)
        self._manual_timer.timeout.connect(self._tick)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self._build_word(lay)
        self._build_send(lay)
        self._build_override(lay)
        lay.addWidget(look.label("Bu pencere AXIL Studio IP haritasındaki TX_* register'larını kullanır.", "muted"))

        self.load()

    def closeEvent(self, ev):
        self.stop_manual()
        super().closeEvent(ev)

    # ------------------------------------------------------------- Word
    def _build_word(self, parent_lay):
        self.word_box = QGroupBox("Word")
        lay = QVBoxLayout(self.word_box)

        self.rb_builder = QRadioButton("Word oluşturucu (alanları ayrı Register'lara yazar)")
        self.rb_direct = QRadioButton("Direkt 32-bit Word")
        grp = QButtonGroup(self.word_box)
        grp.addButton(self.rb_builder)
        grp.addButton(self.rb_direct)
        self.rb_builder.toggled.connect(self._changed)
        lay.addWidget(self.rb_builder)
        lay.addWidget(self.rb_direct)

        # Builder
        self.w_builder = QWidget()
        bl = QGridLayout(self.w_builder)
        bl.setContentsMargins(0, 4, 0, 0)
        self.ed_label = QLineEdit()
        self.ed_sdi = QLineEdit()
        self.ed_data = QLineEdit()
        self.ed_ssm = QLineEdit()
        for r, (txt, ed) in enumerate((
            ("Label (octal)", self.ed_label),
            ("SDI (0–3)", self.ed_sdi),
            ("Data (hex, 19 bit)", self.ed_data),
            ("SSM (0–3)", self.ed_ssm),
        )):
            bl.addWidget(QLabel(txt), r, 0)
            ed.setFixedWidth(120)
            ed.textChanged.connect(self._changed)
            bl.addWidget(ed, r, 1)
        bl.addWidget(QLabel("Parity tipi"), 4, 0)
        self.cb_par = QComboBox()
        self.cb_par.addItems(["Odd", "Even"])
        self.cb_par.setFixedWidth(100)
        self.cb_par.currentTextChanged.connect(self._changed)
        bl.addWidget(self.cb_par, 4, 1)
        bl.setColumnStretch(2, 1)
        lay.addWidget(self.w_builder)

        # Direct
        self.w_direct = QWidget()
        dl = QGridLayout(self.w_direct)
        dl.setContentsMargins(0, 4, 0, 0)
        self.ed_hex = QLineEdit()
        self.ed_hex.setFixedWidth(120)
        self.ed_hex.setFont(look.mono_font())
        self.ed_hex.textChanged.connect(lambda _: self._direct_edit("hex"))
        self.ed_bin = QLineEdit()
        self.ed_bin.setMinimumWidth(320)
        self.ed_bin.setFont(look.mono_font())
        self.ed_bin.textChanged.connect(lambda _: self._direct_edit("bin"))
        dl.addWidget(QLabel("Hex"), 0, 0)
        dl.addWidget(self.ed_hex, 0, 1)
        dl.addWidget(QLabel("Binary"), 1, 0)
        dl.addWidget(self.ed_bin, 1, 1)
        dl.setColumnStretch(2, 1)
        lay.addWidget(self.w_direct)

        # Önizleme
        out = QGridLayout()
        self.out_hex = QLineEdit()
        self.out_hex.setReadOnly(True)
        self.out_hex.setFixedWidth(120)
        self.out_hex.setFont(look.mono_font())
        self.out_bin = QLineEdit()
        self.out_bin.setReadOnly(True)
        self.out_bin.setMinimumWidth(320)
        self.out_bin.setFont(look.mono_font())
        out.addWidget(QLabel("Word (hex)"), 0, 0)
        out.addWidget(self.out_hex, 0, 1)
        out.addWidget(look.button("Kopyala", None, lambda: self._copy(self.out_hex.text())), 0, 2)
        out.addWidget(QLabel("Binary (P SSM Data SDI Label)"), 1, 0)
        out.addWidget(self.out_bin, 1, 1)
        out.addWidget(look.button("Kopyala", None, lambda: self._copy(self.out_bin.text())), 1, 2)
        out.setColumnStretch(3, 1)
        lay.addLayout(out)

        self.lbl_word_info = QLabel("")
        self.lbl_word_info.setWordWrap(True)
        lay.addWidget(self.lbl_word_info)
        bar = QHBoxLayout()
        bar.addWidget(look.button("Word'ü IP'ye yaz", "primary", self.write_word))
        bar.addStretch(1)
        lay.addLayout(bar)
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
            "gap_mode": "period" if self.rb_period.isChecked() else "direct",
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
        except ValueError as e:
            QMessageBox.warning(self, "TX Canlı Kontrol", str(e))
            return
        self.app.tx_write("TX Word yazılıyor", writes)

    # ------------------------------------------------------------- Gönderim
    def _build_send(self, parent_lay):
        self.send_box = QGroupBox("Gönderim")
        lay = QVBoxLayout(self.send_box)

        mrow = QHBoxLayout()
        self.rb_sched = QRadioButton("Scheduler (IP otomatik gönderir)")
        self.rb_manual = QRadioButton("Manuel gönder")
        mgrp = QButtonGroup(self.send_box)
        mgrp.addButton(self.rb_sched)
        mgrp.addButton(self.rb_manual)
        self.rb_sched.toggled.connect(self._changed)
        mrow.addWidget(self.rb_sched)
        mrow.addWidget(self.rb_manual)
        mrow.addStretch(1)
        lay.addLayout(mrow)

        # Scheduler
        self.w_sched = QWidget()
        sl = QVBoxLayout(self.w_sched)
        sl.setContentsMargins(0, 4, 0, 0)
        sg = QGridLayout()
        self.ed_delay = QLineEdit()
        self.ed_delay.setFixedWidth(100)
        self.ed_delay.textChanged.connect(self._changed)
        self.cb_delay_u = QComboBox()
        self.cb_delay_u.addItems(TIME_UNITS)
        self.cb_delay_u.currentTextChanged.connect(self._changed)
        sg.addWidget(QLabel("Initial delay"), 0, 0)
        sg.addWidget(self.ed_delay, 0, 1)
        sg.addWidget(self.cb_delay_u, 0, 2)

        sg.addWidget(QLabel("Inter word gap"), 1, 0)
        gmode = QHBoxLayout()
        self.rb_period = QRadioButton("Periyottan hesapla")
        self.rb_gap_dir = QRadioButton("Direkt gir")
        ggrp = QButtonGroup(self.w_sched)
        ggrp.addButton(self.rb_period)
        ggrp.addButton(self.rb_gap_dir)
        self.rb_period.toggled.connect(self._changed)
        gmode.addWidget(self.rb_period)
        gmode.addWidget(self.rb_gap_dir)
        sg.addLayout(gmode, 1, 1, 1, 2)

        self.lbl_period = QLabel("Periyot")
        self.ed_period = QLineEdit()
        self.ed_period.setFixedWidth(100)
        self.ed_period.textChanged.connect(self._changed)
        self.cb_period_u = QComboBox()
        self.cb_period_u.addItems(TIME_UNITS)
        self.cb_period_u.currentTextChanged.connect(self._changed)
        sg.addWidget(self.lbl_period, 2, 0)
        sg.addWidget(self.ed_period, 2, 1)
        sg.addWidget(self.cb_period_u, 2, 2)

        self.lbl_gap = QLabel("Inter word gap")
        self.ed_gap = QLineEdit()
        self.ed_gap.setFixedWidth(100)
        self.ed_gap.textChanged.connect(self._changed)
        self.cb_gap_u = QComboBox()
        self.cb_gap_u.addItems(TIME_UNITS)
        self.cb_gap_u.currentTextChanged.connect(self._changed)
        sg.addWidget(self.lbl_gap, 3, 0)
        sg.addWidget(self.ed_gap, 3, 1)
        sg.addWidget(self.cb_gap_u, 3, 2)
        sg.setColumnStretch(3, 1)
        sl.addLayout(sg)

        self.lbl_sched_info = QLabel("")
        self.lbl_sched_info.setWordWrap(True)
        sl.addWidget(self.lbl_sched_info)

        sbar = QHBoxLayout()
        self.btn_sched = look.button(PLAY, "primary", self.toggle_scheduler)
        sbar.addWidget(self.btn_sched)
        sbar.addWidget(look.button("Scheduler ayarlarını yaz", None, self.write_scheduler))
        sbar.addStretch(1)
        sl.addLayout(sbar)
        sl.addWidget(look.label("Durdurulunca IP'deki clock sıfırlanır.", "muted"))
        lay.addWidget(self.w_sched)

        # Manuel
        self.w_manual = QWidget()
        ml = QVBoxLayout(self.w_manual)
        ml.setContentsMargins(0, 4, 0, 0)
        mg = QGridLayout()
        self.ed_mper = QLineEdit()
        self.ed_mper.setFixedWidth(100)
        self.ed_mper.textChanged.connect(self._changed)
        self.cb_mper_u = QComboBox()
        self.cb_mper_u.addItems(TIME_UNITS)
        self.cb_mper_u.currentTextChanged.connect(self._changed)
        mg.addWidget(QLabel("Periyot"), 0, 0)
        mg.addWidget(self.ed_mper, 0, 1)
        mg.addWidget(self.cb_mper_u, 0, 2)
        mg.setColumnStretch(3, 1)
        ml.addLayout(mg)

        self.lbl_manual_info = QLabel("")
        ml.addWidget(self.lbl_manual_info)
        mbar = QHBoxLayout()
        self.btn_mplay = look.button(PLAY, "primary", self.press_manual)
        self.btn_msingle = look.button("Tek gönder", None, self.manual_send)
        mbar.addWidget(self.btn_mplay)
        mbar.addWidget(self.btn_msingle)
        mbar.addStretch(1)
        ml.addLayout(mbar)
        ml.addWidget(look.label("Periyodik gönderimi bilgisayar zamanlar; süre tutarlı olmayabilir.", "muted"))
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

        def done(ok):
            if ok:
                self.sched_on = enable
                self.app.tx_sched_on = enable
                self._sync_run_state()

        self.app.tx_write("TX Scheduler " + ("başlatılıyor" if enable else "durduruluyor"), writes, on_done=done)

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
            raise ValueError("Bilgisayarla periyodik gönderimde periyot en az 1 ms olmalı.")
        return ms

    def manual_send(self):
        self.app.tx_write("TX manuel gönderim", [("TX_MSG_SCHED_EN", 0)] + TRIGGER)

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
        if ok:
            self.sent += 1
            self._update_manual_text()
        else:
            self.stop_manual()

    def stop_manual(self):
        self.manual_running = False
        self._manual_timer.stop()
        self._sync_run_state()

    def _update_manual_text(self):
        try:
            txt = f"Periyot = {self.manual_period_ms():g} ms"
            color = look.tokens()["muted" if self.override_on() else "text"]
        except ValueError as e:
            txt = str(e)
            color = look.tokens()["danger"]
        if self.sent or self.skipped or self.manual_running:
            txt += f"  ·  Gönderilen: {self.sent}, atlanan: {self.skipped}"
        self.lbl_manual_info.setText(txt)
        self.lbl_manual_info.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------- Hat override
    def _build_override(self, parent_lay):
        g = QGroupBox("Hat override")
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        self._ov_btns: dict[str, QRadioButton] = {}
        grp = QButtonGroup(g)
        for name in OVERRIDE_LINES:
            rb = QRadioButton(name)
            grp.addButton(rb)
            row.addWidget(rb)
            self._ov_btns[name] = rb
        row.addSpacing(8)
        row.addWidget(look.button("Uygula", "primary", self.apply_override))
        row.addStretch(1)
        lay.addLayout(row)
        self.lbl_ov_info = QLabel("")
        self.lbl_ov_info.setWordWrap(True)
        self.lbl_ov_info.setStyleSheet(f"color: {look.tokens()['danger']};")
        lay.addWidget(self.lbl_ov_info)
        parent_lay.addWidget(g)

    def apply_override(self):
        choice = next((k for k, rb in self._ov_btns.items() if rb.isChecked()), "Kapalı")

        def done(ok: bool):
            if ok:
                self.app.tx_override = choice
                self.app.recalc_tx()
                self._sync_override()

        self.app.tx_write(f"TX hat override: {choice}", override_writes(choice), on_done=done)

    def override_on(self) -> bool:
        return getattr(self.app, "tx_override", "Kapalı") != "Kapalı"

    def _sync_override(self):
        on = self.override_on()
        if on:
            self.stop_manual()
        self.word_box.setEnabled(not on)
        self.send_box.setEnabled(not on)
        self.lbl_ov_info.setText(
            f"Hat override etkin: {self.app.tx_override}. Word ve Gönderim kapatıldı; devam etmek için Kapalı seçip Uygula'ya basın."
            if on
            else ""
        )
        self._sync_run_state()
        self.refresh()

    def _sync_run_state(self):
        self.btn_sched.setText(PAUSE if self.sched_on else PLAY)
        self.btn_mplay.setText(PAUSE if self.manual_running else PLAY)
        self.btn_msingle.setEnabled(not self.manual_running)
        running = self.sched_on or self.manual_running
        self.rb_sched.setEnabled(not running)
        self.rb_manual.setEnabled(not running)

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
        self.rb_period.setChecked(cfg.get("gap_mode") != "direct")
        self.rb_gap_dir.setChecked(cfg.get("gap_mode") == "direct")
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
            self.out_hex.setText(f"{word:08X}")
            self.out_bin.setText(fmt_binary(word))
            info = word_fields_text(word)
            info = (
                f"Hesaplanan Parity biti: {word >> 31}\n" + info
                if not direct
                else info + f"\nParity tipi: {'Odd' if parity_bit(word, True) == word >> 31 else 'Even'}"
            )
            self.lbl_word_info.setText(info)
            self.lbl_word_info.setStyleSheet(f"color: {look.tokens()['muted' if self.override_on() else 'text']};")
        except ValueError as e:
            self.out_hex.setText("")
            self.out_bin.setText("")
            self.lbl_word_info.setText(str(e))
            self.lbl_word_info.setStyleSheet(f"color: {look.tokens()['danger']};")

        by_sched = self.rb_sched.isChecked()
        self.w_sched.setVisible(by_sched)
        self.w_manual.setVisible(not by_sched)

        by_per = self.rb_period.isChecked()
        for w in (self.lbl_period, self.ed_period, self.cb_period_u):
            w.setVisible(by_per)
        for w in (self.lbl_gap, self.ed_gap, self.cb_gap_u):
            w.setVisible(not by_per)

        try:
            self.lbl_sched_info.setText(self.sched_values()[2])
            self.lbl_sched_info.setStyleSheet(f"color: {look.tokens()['muted' if self.override_on() else 'success']};")
        except ValueError as e:
            self.lbl_sched_info.setText(str(e))
            self.lbl_sched_info.setStyleSheet(f"color: {look.tokens()['danger']};")
        self._update_manual_text()
