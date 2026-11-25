"""TX Gönderilen Veriler sekmesi: TX Canlı Kontrol gönderim geçmişi ve TX Built-In Test (TX BIT) Checker özeti."""
from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QSplitter, QVBoxLayout, QWidget,
)

from ..decode import decode_errors, ft, session_mhz, word_fields
from . import look
from .celltable import Cell, CellTable
from .control_tab import _card_header, _stat_box

FILTER_KINDS = ["Tümü", "Gönderim", "Word Yaz", "Scheduler", "Override"]


class TxSentTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._tb_session: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        split = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(split, 1)

        # ============================================================ 1. Üst Kart: TX Canlı Gönderim Geçmişi
        hist_card = look.Card(margins=0, spacing=0, object_name="SubCard")
        hh = _card_header(hist_card)
        hh.addWidget(look.label("TX Canlı Kontrol Gönderim Geçmişi", "cardTitle"))
        self.hist_pill = look.Pill("0 kayıt", "accent")
        hh.addWidget(self.hist_pill)
        hh.addStretch(1)
        hh.addWidget(look.label("Filtre:", "muted"))
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(FILTER_KINDS)
        self.cb_filter.currentTextChanged.connect(lambda _: self.refresh_history())
        hh.addWidget(self.cb_filter)
        hh.addWidget(look.button("CSV Dışa Aktar…", None, self._export_csv))
        hh.addWidget(look.button("Temizle", None, self._clear_history))

        hb = QWidget()
        hbl = QVBoxLayout(hb)
        hbl.setContentsMargins(10, 8, 10, 8)
        hbl.setSpacing(4)
        self.tv_hist = CellTable(
            ["Saat", "İşlem", "Label (oct)", "SDI", "Data (hex)", "SSM", "Parity", "Word (hex)", "Ayrıntı", "Durum"],
            [88, 105, 82, 42, 82, 42, 56, 98, 280, 72],
        )
        hbl.addWidget(self.tv_hist, 1)
        hbl.addWidget(look.label(
            "TX Canlı Kontrol'den yapılan manuel/periyodik gönderimler, Word yazmaları, Scheduler ve Hat Override işlemleri en yeni üstte listelenir.",
            "muted",
        ))
        hist_card.lay.addWidget(hb, 1)
        split.addWidget(hist_card)

        # ============================================================ 2. Alt Kart: TX Built-In Test (TX BIT)
        bit_card = look.Card(margins=0, spacing=0, object_name="SubCard")
        bh = _card_header(bit_card)
        bh.addWidget(look.label("TX Built-In Test (TX BIT · Wraparound Checker)", "cardTitle"))
        self.chk_pill = look.Pill("—")
        bh.addWidget(self.chk_pill)
        bh.addStretch(1)
        self.btn_refresh_tb = look.button("↻ Yenile", None, app.do_refresh_tx_bit, "TX_WORD_CNT ve TB_CHK_* sayaçlarını okur")
        self.btn_read_tb = look.button(
            "TB Verilerini Oku && RX'te İncele →", "primary", app.do_read_tx_bit,
            "TX BIT kanalının Word/Error/Bit Diagnostic RAM'lerini okuyup RX Okunan Veriler sekmesinde açar",
        )
        bh.addWidget(self.btn_refresh_tb)
        bh.addWidget(self.btn_read_tb)

        bb = QWidget()
        bbl = QVBoxLayout(bb)
        bbl.setContentsMargins(10, 8, 10, 8)
        bbl.setSpacing(8)

        # 5 Canlı Sayaç Kutusu
        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        f1, self.lbl_tx_cnt = _stat_box("TX Gönderilen (TX_WORD_CNT)")
        f2, self.lbl_tb_cnt = _stat_box("TX BIT Alınan (TB_WORD_CNT)")
        f3, self.lbl_chk_ok = _stat_box("Eşleşen (CHK_OK_CNT)")
        f4, self.lbl_chk_err = _stat_box("Checker Hatası (CHK_ERR_CNT)")
        f5, self.lbl_chk_fifo = _stat_box("Checker FIFO")
        for c, fr in enumerate((f1, f2, f3, f4, f5)):
            sgrid.addWidget(fr, 0, c)
        bbl.addLayout(sgrid)

        # Checker Kontrol Şeridi
        ctrl_fr = QFrame()
        ctrl_fr.setObjectName("SubPanel")
        cl = QHBoxLayout(ctrl_fr)
        cl.setContentsMargins(10, 6, 10, 6)
        cl.setSpacing(8)
        self.chk_enable = QCheckBox("Checker Enable")
        cl.addWidget(self.chk_enable)
        cl.addWidget(look.label("Timeout (clk, 0=kapalı):", "muted"))
        self.ed_timeout = QLineEdit("0")
        self.ed_timeout.setFixedWidth(96)
        self.ed_timeout.setFont(look.mono_font(-0.5))
        cl.addWidget(self.ed_timeout)
        self.btn_apply_chk = look.button("Uygula", "primary", self._apply_checker)
        self.btn_clr_fifo = look.button("FIFO Temizle", None, app.do_clear_tx_checker_fifo)
        cl.addWidget(self.btn_apply_chk)
        cl.addWidget(self.btn_clr_fifo)
        cl.addStretch(1)
        cl.addWidget(look.label("Dalga formu ve Bit Diagnostic analizi için 'RX Okunan Veriler' sekmesi kullanılır.", "muted"))
        bbl.addWidget(ctrl_fr)

        # Son TB okumasındaki Error / Checker kayıtları
        self.lbl_tb_sess = look.label("Henüz TX BIT (TB) okuması yapılmadı.", "muted")
        bbl.addWidget(self.lbl_tb_sess)
        self.tv_tb_err = CellTable(
            ["No", "Timestamp", "Aktif Error'lar", "FIFO / Adres", "Beklenen / Alınan Word (hex)", "Decimal"],
            [45, 115, 300, 100, 200, 120],
            on_double=lambda _r: self._open_tb_in_rx(),
        )
        bbl.addWidget(self.tv_tb_err, 1)

        bit_card.lay.addWidget(bb, 1)
        split.addWidget(bit_card)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 360])

    # ------------------------------------------------------------- geçmiş tablosu
    def refresh_history(self):
        flt = self.cb_filter.currentText()
        items = self.app.tx_history
        self.hist_pill.set(f"{len(items)} kayıt", "accent")
        rows = []
        for e in reversed(items):
            if flt != "Tümü" and e.get("cat") != flt:
                continue
            wd = e.get("word")
            if wd is not None:
                f = word_fields(wd)
                lab, sdi, dat, ssm, par, whex = (
                    f"{f['label']:03o}", str(f["sdi"]), f"{f['data']:05X}",
                    str(f["ssm"]), str(f["p"]), f"0x{wd:08X}",
                )
            else:
                lab = sdi = dat = ssm = par = whex = "—"
            ok = e.get("ok", True)
            rows.append([
                e.get("time", ""),
                e.get("kind", ""),
                lab, sdi, dat, ssm, par, whex,
                e.get("detail", ""),
                Cell("OK" if ok else "HATA", ok, "Yazma başarılı." if ok else "Yazma başarısız (log'a bakın)."),
            ])
        self.tv_hist.set_rows(rows)

    def _clear_history(self):
        if not self.app.tx_history:
            return
        if look.confirm(self, "TX Gönderim Geçmişi", "Listelenen TX gönderim geçmişi temizlensin mi?", "Temizle"):
            self.app.tx_history.clear()
            self.app.mark_dirty()
            self.refresh_history()

    def _export_csv(self):
        if not self.app.tx_history:
            QMessageBox.information(self, "TX Gönderim Geçmişi", "Dışa aktarılacak kayıt yok.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "TX geçmişini CSV kaydet", "tx_gecmis.csv", "CSV (*.csv)")
        if not p:
            return
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Saat", "Islem", "Label_oct", "SDI", "Data_hex", "SSM", "Parity", "Word_hex", "Ayrinti", "Durum"])
            for e in self.app.tx_history:
                wd = e.get("word")
                if wd is not None:
                    fl = word_fields(wd)
                    vals = [f"{fl['label']:03o}", fl["sdi"], f"{fl['data']:05X}", fl["ssm"], fl["p"], f"0x{wd:08X}"]
                else:
                    vals = ["", "", "", "", "", ""]
                w.writerow([e.get("time", ""), e.get("kind", ""), *vals, e.get("detail", ""), "OK" if e.get("ok", True) else "HATA"])
        self.app.set_status(f"TX geçmişi kaydedildi: {p}")

    # ------------------------------------------------------------- TX BIT Checker
    def update_tx_bit_status(self, info: dict | None):
        if not info:
            for lbl in (self.lbl_tx_cnt, self.lbl_tb_cnt, self.lbl_chk_ok, self.lbl_chk_err, self.lbl_chk_fifo):
                lbl.setText("—")
                lbl.setStyleSheet("")
            self.chk_pill.set("Çevrimdışı", "")
            return
        txc = info.get("tx_word_cnt")
        tbc = info.get("tb_word_cnt")
        okc = info.get("chk_ok_cnt")
        errc = info.get("chk_err_cnt")
        lvl = info.get("chk_fifo_level")
        ovf = info.get("chk_fifo_ovf", False)
        self.lbl_tx_cnt.setText("—" if txc is None else f"{txc:,}")
        self.lbl_tb_cnt.setText("—" if tbc is None else f"{tbc:,}")
        self.lbl_chk_ok.setText("—" if okc is None else f"{okc:,}")
        self.lbl_chk_ok.setStyleSheet(f"color: {look.tokens()['success']};" if (okc or 0) > 0 else "")
        self.lbl_chk_err.setText("—" if errc is None else f"{errc:,}")
        self.lbl_chk_err.setStyleSheet(f"color: {look.tokens()['danger']};" if (errc or 0) > 0 else "")
        if lvl is None:
            self.lbl_chk_fifo.setText("—")
            self.lbl_chk_fifo.setStyleSheet("")
        else:
            self.lbl_chk_fifo.setText(f"{lvl} (TAŞTI)" if ovf else str(lvl))
            self.lbl_chk_fifo.setStyleSheet(f"color: {look.tokens()['danger']};" if ovf else "")

        if not info.get("has_checker"):
            self.chk_pill.set("Checker yok", "")
        elif info.get("chk_en"):
            self.chk_pill.set("● Checker aktif", "ok")
        else:
            self.chk_pill.set("● Checker kapalı", "warn")

        self.chk_enable.setChecked(bool(info.get("chk_en", False)))
        if info.get("chk_timeout") is not None:
            self.ed_timeout.setText(str(info["chk_timeout"]))

    def refresh_tb_session(self):
        """Projedeki en son TX BIT ('TB') okumasının Checker/Error özetini gösterir."""
        tb = next((s for s in reversed(self.app.sessions) if s.get("channel") == "TB"), None)
        self._tb_session = tb
        if tb is None:
            self.lbl_tb_sess.setText("Henüz TX BIT (TB) okuması yapılmadı. Detaylı hata ve dalga formu için yukarıdan TB verilerini okuyun.")
            self.tv_tb_err.set_rows([])
            return
        mhz = session_mhz(tb, self.app.ci.clk_mhz)
        errs = decode_errors(tb)
        self.lbl_tb_sess.setText(
            f"Son TX BIT oturumu: {tb['name']} · {len(tb.get('words', []))} Word, {len(errs)} Error "
            "(RX Okunan Veriler'de açmak için satıra çift tıklayın)"
        )
        rows = []
        for i, r in enumerate(errs):
            has_err = any(r["flags"])
            rows.append([
                i + 1,
                ft(r["ts"], "ms", mhz),
                Cell(r["active"], r["code_ok"] and not has_err, f"Aktif Error'lar: {r['active']}."),
                r["addr"],
                f"0x{(r['data'] or 0):08X}",
                r["data"],
            ])
        self.tv_tb_err.set_rows(rows)

    def _apply_checker(self):
        try:
            to = int(self.ed_timeout.text().strip())
            if to < 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "TX BIT Checker", "Timeout değeri 0 veya pozitif tam sayı (clk) olmalı.")
            return
        self.app.do_apply_tx_checker(self.chk_enable.isChecked(), to)

    def _open_tb_in_rx(self):
        if self._tb_session is None:
            return
        self.app.cur_session = self._tb_session
        self.app.read_tab.refresh_sessions()
        self.app.tabs.setCurrentWidget(self.app.read_tab)

    def set_controls_enabled(self, connected: bool, has_tb: bool, has_checker: bool, busy: bool):
        on = connected and not busy
        self.btn_refresh_tb.setEnabled(on)
        self.btn_read_tb.setEnabled(on and has_tb)
        self.chk_enable.setEnabled(on and has_checker)
        self.ed_timeout.setEnabled(on and has_checker)
        self.btn_apply_chk.setEnabled(on and has_checker)
        self.btn_clr_fifo.setEnabled(on and has_checker)
