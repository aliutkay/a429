"""Kontrol sekmesi (Taslak A): üst hızlı şerit, yan yana RX Kanal Kontrolü | TX Canlı Kontrol ve alt işlem logu."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QProgressBar, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ..regs import channel_label
from . import look
from .dialogs import READ_MODES, READ_MODES_REV
from .txwindow import TxLivePanel, TxLiveWindow


def _stat_box(title: str) -> tuple[QFrame, QLabel]:
    fr = QFrame()
    fr.setObjectName("StatBox")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(10, 7, 10, 7)
    lay.setSpacing(2)
    lay.addWidget(look.label(title, "muted"))
    val = QLabel("—")
    val.setFont(look.bold(look.mono_font(1.5)))
    lay.addWidget(val)
    return fr, val


def _card_header(card: look.Card) -> QHBoxLayout:
    hdr = QWidget()
    hdr.setObjectName("CardHeader")
    hdr.setStyleSheet(f"QWidget#CardHeader {{ border-bottom: 1px solid {look.tokens()['border']}; }}")
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(12, 7, 10, 7)
    hl.setSpacing(8)
    card.lay.addWidget(hdr)
    return hl


class ControlTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._loading = False
        self._syncing_en = False
        self._log_big = False
        self._tx_win: TxLiveWindow | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- 1. Üst Hızlı Şerit (Config + Oku olmadan, sade global aksiyonlar)
        top_card = look.Card(margins=8, spacing=6, object_name="SubCard")
        trow = QHBoxLayout()
        trow.setSpacing(8)
        self.btn_reset = look.button("IP Reset", "danger", app.do_ip_reset)
        self.btn_stop = look.button("Durdur", None, app.do_stop)
        self.btn_tx_live = look.button("TX'i panele geri al ↙", None, self.toggle_tx_popout)
        self.btn_tx_live.setVisible(False)
        trow.addWidget(self.btn_reset)
        trow.addWidget(self.btn_stop)
        trow.addWidget(self.btn_tx_live)
        trow.addSpacing(6)
        self.btn_health = look.button(
            "IP Durumu", None, app.do_check_ip_dialog,
            "Logger enable/freeze, hat (LINE/SYNC_WAIT), IP sürümü, saat ve TX/RX hız uyumunu kontrol eder",
        )
        trow.addWidget(self.btn_health)
        self.health_pill = look.Pill("Kontrol edilmedi", "")
        trow.addWidget(self.health_pill)

        trow.addSpacing(6)
        self.lbl_map_state = look.label("", "muted")
        trow.addWidget(self.lbl_map_state, 1)

        trow.addWidget(look.label("Kayıt:", "muted"))
        self.lbl_dir_short = look.label("", "mono")
        trow.addWidget(self.lbl_dir_short)
        self.btn_files = look.button("Dosya Ayarları ⚙", None, self._toggle_files)
        trow.addWidget(self.btn_files)
        top_card.lay.addLayout(trow)

        # Katlanabilir Dosya Ayarları Çekmecesi
        self.files_drawer = QWidget()
        self.files_drawer.setVisible(False)
        fdl = QHBoxLayout(self.files_drawer)
        fdl.setContentsMargins(2, 4, 2, 0)
        fdl.setSpacing(10)
        fdl.addWidget(look.label("Klasör:", "muted"))
        self.ed_dir = QLineEdit()
        self.ed_dir.setMinimumWidth(220)
        self.ed_dir.textChanged.connect(self._on_file_opt_changed)
        fdl.addWidget(self.ed_dir, 1)
        fdl.addWidget(look.button("…", None, self._pick_dir))
        self.chk_txt = QCheckBox("TTL/Excel txt yaz")
        self.chk_txt.toggled.connect(self._on_file_opt_changed)
        fdl.addWidget(self.chk_txt)
        self.chk_wlog = QCheckBox("Register yazma logu")
        self.chk_wlog.toggled.connect(self._on_file_opt_changed)
        fdl.addWidget(self.chk_wlog)
        self.chk_verb = QCheckBox("Bridge trafiğine yaz")
        self.chk_verb.toggled.connect(self._on_file_opt_changed)
        fdl.addWidget(self.chk_verb)
        top_card.lay.addWidget(self.files_drawer)
        root.addWidget(top_card)

        # ---- 2. Orta Alan: 2 Eşit Ana Kart (RX Kanal Kontrolü | TX Canlı Kontrol)
        self.cards_split = QSplitter(Qt.Orientation.Horizontal)

        # === SOL KART: RX Kanal Kontrolü ===
        self.rx_card = look.Card(margins=0, spacing=0, object_name="SubCard")
        rxh = _card_header(self.rx_card)
        rxh.addWidget(look.label("RX Kanal Kontrolü", "cardTitle"))
        self.rx_ch_pill = look.Pill("RX0", "accent")
        rxh.addWidget(self.rx_ch_pill)
        rxh.addStretch(1)
        self.chk_rx_en = QCheckBox("Logger Enable")
        self.chk_rx_en.setToolTip("Kanalın CTRL.ENABLE bitini açıp kapatır")
        self.chk_rx_en.toggled.connect(self._on_rx_enable_toggled)
        rxh.addWidget(self.chk_rx_en)
        self.btn_refresh_stat = look.button("↻ Yenile", None, app.do_refresh_status, "WORD_CNT, ERR_CNT, DROP_CNT ve LAST_WORD sayaçlarını okur")
        rxh.addWidget(self.btn_refresh_stat)

        rxb = QWidget()
        rxbl = QVBoxLayout(rxb)
        rxbl.setContentsMargins(12, 10, 12, 10)
        rxbl.setSpacing(10)

        # Karttaki Aktif RX Config Şeridi
        rx_cfg_bar = QFrame()
        rx_cfg_bar.setObjectName("SubPanel")
        rcbl = QHBoxLayout(rx_cfg_bar)
        rcbl.setContentsMargins(10, 6, 8, 6)
        rcbl.setSpacing(8)
        rcbl.addWidget(look.label("Karttaki Config:", "muted"))
        self.rx_cfg_pill = look.Pill("Okunmadı", "")
        rcbl.addWidget(self.rx_cfg_pill)
        rcbl.addStretch(1)
        self.btn_check_rx = look.button(
            "Config Kontrol", None, app.do_check_rx_config_dialog,
            "Karttaki aktif RX config (STATUS.ACT_CFG + ACT_*) değerlerini okur ve Config sekmesiyle karşılaştırır",
        )
        rcbl.addWidget(self.btn_check_rx)
        rxbl.addWidget(rx_cfg_bar)

        # Kanal uyarı şeridi: logger kapalı / hat 11 / senkron bekleniyor (yalnız sorun varken görünür)
        self.rx_warn = QFrame()
        self.rx_warn.setObjectName("SubPanel")
        rwl = QHBoxLayout(self.rx_warn)
        rwl.setContentsMargins(10, 6, 8, 6)
        rwl.setSpacing(8)
        self.rx_warn_pill = look.Pill("", "warn")
        rwl.addWidget(self.rx_warn_pill)
        self.lbl_rx_warn = look.label("", None, True)
        rwl.addWidget(self.lbl_rx_warn, 1)
        self.btn_rx_warn_fix = look.button("Logger'ı Aç", "primary", lambda: self.app.do_toggle_rx_enable(True))
        rwl.addWidget(self.btn_rx_warn_fix)
        self.rx_warn.setVisible(False)
        rxbl.addWidget(self.rx_warn)

        # 4 Canlı Sayaç Kutusu
        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        f_w, self.lbl_stat_w = _stat_box("Word Sayısı")
        f_e, self.lbl_stat_e = _stat_box("Error Sayısı")
        f_d, self.lbl_stat_d = _stat_box("Drop (Freeze)")
        f_l, self.lbl_stat_last = _stat_box("Son Word")
        self.lbl_stat_last.setFont(look.bold(look.mono_font(-0.5)))
        for c, fr in enumerate((f_w, f_e, f_d, f_l)):
            sgrid.addWidget(fr, 0, c)
        rxbl.addLayout(sgrid)

        # Okuma Kapsamı (tek satırda 3 kompakt sütun)
        scope_fr = QFrame()
        scope_fr.setObjectName("SubPanel")
        scl = QVBoxLayout(scope_fr)
        scl.setContentsMargins(10, 8, 10, 8)
        scl.setSpacing(6)
        scl.addWidget(look.label("Okuma Kapsamı (en yeni kayıtlar)", "cardTitle"))
        sc_grid = QGridLayout()
        sc_grid.setSpacing(6)
        self.read_opts: dict[str, tuple[QComboBox, QLineEdit]] = {}
        for c, (key, title) in enumerate((("word", "Word RAM"), ("error", "Error RAM"), ("bit", "Bit Diagnostic"))):
            sc_grid.addWidget(look.label(title, "muted"), 0, c)
            row = QHBoxLayout()
            row.setSpacing(4)
            cb = QComboBox()
            cb.addItems(list(READ_MODES))
            ed = QLineEdit()
            ed.setFixedWidth(54)
            ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ed.setPlaceholderText("N")
            cb.currentTextChanged.connect(lambda _t, k=key: self._on_read_opt_changed(k))
            ed.textChanged.connect(lambda _t, k=key: self._on_read_opt_changed(k))
            row.addWidget(cb, 1)
            row.addWidget(ed)
            sc_grid.addLayout(row, 1, c)
            self.read_opts[key] = (cb, ed)
        scl.addLayout(sc_grid)
        scl.addWidget(look.label(
            "Bit Diagnostic için N, Word sayısıdır. Okuma süresince CTRL.FREEZE=1 ve Debug Bridge kilidi uygulanır.",
            "muted", True,
        ))
        rxbl.addWidget(scope_fr)

        rxbl.addStretch(1)

        # RX Aksiyon Düğmeleri + İlerleme
        rx_btns = QHBoxLayout()
        rx_btns.setSpacing(8)
        self.btn_send_rx = look.button("RX Config Gönder", "primary", app.do_send_rx_cfg)
        self.btn_read_rx = look.button("RX Verilerini Oku", "primary", app.do_read)
        self.btn_clear_ch = look.button("Sayaçları Temizle", None, app.do_clear_channel, "Kanalın CTRL.CLEAR darbesini gönderir")
        rx_btns.addWidget(self.btn_send_rx, 1)
        rx_btns.addWidget(self.btn_read_rx, 1)
        rx_btns.addWidget(self.btn_clear_ch)
        rxbl.addLayout(rx_btns)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self.prog.setFormat("%p%")
        rxbl.addWidget(self.prog)

        self.lbl_last_read = look.label("Henüz okuma yapılmadı.", "muted")
        rxbl.addWidget(self.lbl_last_read)

        self.rx_card.lay.addWidget(rxb, 1)
        self.cards_split.addWidget(self.rx_card)

        # === SAĞ KART: TX Canlı Kontrol (scrollsuz, ayrılabilir) ===
        self.tx_card = look.Card(margins=0, spacing=0, object_name="SubCard")
        txh = _card_header(self.tx_card)
        txh.addWidget(look.label("TX Canlı Kontrol", "cardTitle"))
        self.tx_drv_pill = look.Pill("HI-8597", "ok")
        txh.addWidget(self.tx_drv_pill)
        txh.addStretch(1)
        self.btn_send_tx = look.button("TX Config Gönder", None, app.do_send_tx_cfg)
        txh.addWidget(self.btn_send_tx)
        self.btn_tx_pop = look.button(
            "Ayrı pencerede aç ↗", None, self.popout_tx,
            "RX Okunan Veriler'i izlerken TX göndermek için ayrı pencereye çıkarır",
        )
        txh.addWidget(self.btn_tx_pop)

        # Karttaki Aktif TX Config Şeridi
        tx_cfg_wrap = QWidget()
        txcw = QVBoxLayout(tx_cfg_wrap)
        txcw.setContentsMargins(12, 10, 12, 0)
        txcw.setSpacing(0)
        tx_cfg_bar = QFrame()
        tx_cfg_bar.setObjectName("SubPanel")
        tcbl = QHBoxLayout(tx_cfg_bar)
        tcbl.setContentsMargins(10, 6, 8, 6)
        tcbl.setSpacing(8)
        tcbl.addWidget(look.label("Karttaki Config:", "muted"))
        self.tx_cfg_pill = look.Pill("Okunmadı", "")
        tcbl.addWidget(self.tx_cfg_pill)
        tcbl.addStretch(1)
        self.btn_check_tx = look.button(
            "Config Kontrol", None, app.do_check_tx_config_dialog,
            "Karttaki aktif TX config (TX_STATUS.ACT_CFG + TX_ACT_*) değerlerini okur ve Config sekmesiyle karşılaştırır",
        )
        tcbl.addWidget(self.btn_check_tx)
        txcw.addWidget(tx_cfg_bar)
        self.tx_card.lay.addWidget(tx_cfg_wrap)

        self.tx_scroll = QScrollArea()
        self.tx_scroll.setWidgetResizable(True)
        self.tx_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tx_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.tx_panel = TxLivePanel(app)
        self.tx_scroll.setWidget(self.tx_panel)
        self.tx_card.lay.addWidget(self.tx_scroll, 1)
        self.cards_split.addWidget(self.tx_card)

        self.cards_split.setStretchFactor(0, 1)
        self.cards_split.setStretchFactor(1, 1)
        self.cards_split.setSizes([680, 720])
        root.addWidget(self.cards_split, 1)

        # ---- 3. Alt Şerit: Kompakt Büyütülebilir İşlem Logu
        log_card = look.Card(margins=0, spacing=0, object_name="SubCard")
        lh = _card_header(log_card)
        lh.addWidget(look.label("İşlem Logu", "cardTitle"))
        lh.addStretch(1)
        lh.addWidget(look.button("Temizle", None, lambda: self.log_txt.clear()))
        lh.addWidget(look.button("Kaydet…", None, self._save_log))
        self.btn_log_size = look.button("Büyüt ⤢", None, self._toggle_log_size)
        lh.addWidget(self.btn_log_size)

        self.log_txt = QPlainTextEdit()
        self.log_txt.setReadOnly(True)
        self.log_txt.setFont(look.mono_font(-0.5))
        self.log_txt.setMaximumBlockCount(4000)
        self.log_txt.setStyleSheet("QPlainTextEdit { border: none; border-radius: 0; background: transparent; padding: 6px 10px; }")
        self.log_txt.setFixedHeight(108)
        log_card.lay.addWidget(self.log_txt)
        root.addWidget(log_card)

    # ------------------------------------------------------------- çekmece & log boyutu
    def _toggle_files(self):
        self.files_drawer.setVisible(not self.files_drawer.isVisible())

    def _toggle_log_size(self):
        self._log_big = not self._log_big
        self.log_txt.setFixedHeight(230 if self._log_big else 108)
        self.btn_log_size.setText("Küçült ⤡" if self._log_big else "Büyüt ⤢")

    def _short_dir(self, path: str) -> str:
        home = os.path.expanduser("~")
        if path.startswith(home):
            return "~" + path[len(home):]
        return path

    # ------------------------------------------------------------- TX hibrit (gömülü <-> pencere)
    @property
    def tx_popped_out(self) -> bool:
        return self._tx_win is not None and self._tx_win.isVisible()

    def toggle_tx_popout(self):
        if self.tx_popped_out:
            self._tx_win.close()
        else:
            self.popout_tx()

    def popout_tx(self):
        if self.tx_popped_out:
            self._tx_win.raise_()
            self._tx_win.activateWindow()
            return
        self.tx_scroll.takeWidget()
        self.tx_card.setVisible(False)
        self._tx_win = TxLiveWindow(self.app, self.tx_panel, on_dock=self.dock_tx)
        self.btn_tx_live.setVisible(True)
        self._tx_win.show()

    def dock_tx(self):
        win, self._tx_win = self._tx_win, None
        if win is not None:
            win.detach_panel()
        self.tx_scroll.setWidget(self.tx_panel)
        self.tx_panel.show()
        self.tx_card.setVisible(True)
        self.btn_tx_live.setVisible(False)

    def close_floating(self):
        self.tx_panel.stop_manual()
        if self._tx_win is not None:
            self._tx_win.close()

    # ------------------------------------------------------------- canlı sayaçlar
    def update_live_stats(self, info: dict | None):
        if not info:
            for lbl in (self.lbl_stat_w, self.lbl_stat_e, self.lbl_stat_d, self.lbl_stat_last):
                lbl.setText("—")
                lbl.setStyleSheet("")
            self._update_rx_warn(None)
            return
        w = info.get("word_cnt")
        e = info.get("err_cnt")
        d = info.get("drop_cnt")
        lw = info.get("last_word")
        self.lbl_stat_w.setText("—" if w is None else f"{w:,}")
        self.lbl_stat_e.setText("—" if e is None else f"{e:,}")
        self.lbl_stat_e.setStyleSheet(f"color: {look.tokens()['warning']};" if (e or 0) > 0 else "")
        self.lbl_stat_d.setText("—" if d is None else f"{d:,}")
        self.lbl_stat_last.setText("—" if lw is None else f"0x{lw:08X}")
        self._syncing_en = True
        self.chk_rx_en.setChecked(bool(info.get("enable", False)))
        self._syncing_en = False
        self._update_rx_warn(info)

    def _update_rx_warn(self, info: dict | None):
        """Logger kapalı / hat 11 / senkron bekleme durumlarını RX kartında belirgin gösterir."""
        msg, state, fix = "", "warn", False
        if info:
            hi, lo, sw = info.get("line_high"), info.get("line_low"), info.get("sync_wait")
            if not info.get("enable", True):
                msg, state, fix = ("Logger kapalı (CTRL.ENABLE=0): bu kanal Word ve hata KAYDETMİYOR. "
                                   "Reset sonrası varsayılan kapalıdır."), "err", True
            elif hi and lo:
                msg, state = ("Hat 11 (HIGH ve LOW aynı anda 1): alıcı çıkışları ters / pull-up / alıcı beslemesi yok. "
                              "Decoder senkron bekliyor, kayıt yok."), "err"
            elif sw:
                msg = "Decoder hat senkronu bekliyor (SYNC_WAIT=1): Word'ler arası 4 bit temiz NULL görülmedi."
            elif info.get("freeze"):
                msg = "Kanal donduruldu (CTRL.FREEZE=1): kayıtlar DROP_CNT'ye düşüyor."
        self.rx_warn.setVisible(bool(msg))
        if msg:
            self.rx_warn_pill.set("Hata" if state == "err" else "Uyarı", state)
            self.lbl_rx_warn.setText(msg)
            self.btn_rx_warn_fix.setVisible(fix)

    def update_health(self, res: dict | None):
        if not res:
            self.health_pill.set("Kontrol edilmedi", "")
            self.health_pill.setToolTip("")
            return
        c = res.get("counts", {})
        if c.get("error") or c.get("warn"):
            parts = [f"{c[k]} {n}" for k, n in (("error", "hata"), ("warn", "uyarı")) if c.get(k)]
            self.health_pill.set(" · ".join(parts), "err" if c.get("error") else "warn")
        else:
            self.health_pill.set("Sorun yok ✓", "ok")
        tips = [f"• [{f['area']}] {f['title']}" for f in res.get("findings", []) if f["level"] in ("error", "warn")]
        self.health_pill.setToolTip("\n".join(tips[:8]) or "IP ayarları ve hat durumu normal.")

    def set_last_read_summary(self, text: str):
        self.lbl_last_read.setText(text)

    @staticmethod
    def _set_cfg_pill(pill: look.Pill, info: dict | None):
        if not info:
            pill.set("Okunmadı", "")
            pill.setToolTip("")
            return
        mode_name = info.get("mode_name", "Bilinmiyor")
        mismatch = info.get("mismatch", 0)
        if info.get("all_match"):
            pill.set(f"{mode_name} · Eşleşiyor ✓", "ok")
        elif mismatch > 0:
            pill.set(f"{mode_name} · {mismatch} fark", "warn")
        else:
            pill.set(mode_name, "accent")

        lines = [f"Aktif Mod: {mode_name}"]
        diffs = [
            f"• {disp}: kart={act}, config={exp}"
            for disp, _reg, act, exp, m in info.get("rows", [])
            if m is False
        ]
        if diffs:
            lines.append("Arayüzle farklı parametreler:")
            lines.extend(diffs[:6])
            if len(diffs) > 6:
                lines.append(f"… +{len(diffs) - 6} fark daha")
        elif info.get("all_match"):
            lines.append("Tüm parametreler Config sekmesiyle eşleşiyor.")
        pill.setToolTip("\n".join(lines))

    def update_rx_active_config(self, info: dict | None):
        self._set_cfg_pill(self.rx_cfg_pill, info)

    def update_tx_active_config(self, info: dict | None):
        self._set_cfg_pill(self.tx_cfg_pill, info)

    def _on_rx_enable_toggled(self, checked: bool):
        if not self._syncing_en:
            self.app.do_toggle_rx_enable(checked)

    # ------------------------------------------------------------- ayar senkronizasyonu
    def load_from_model(self):
        self._loading = True
        rs = self.app.rs
        for key, (cb, ed) in self.read_opts.items():
            mode = getattr(rs, f"read_{key}", "all")
            cb.setCurrentText(READ_MODES_REV.get(mode, "Tümü"))
            ed.setText(str(getattr(rs, f"read_{key}_n", 4)))
            ed.setVisible(mode == "last")
            ed.setProperty("bad", "false")
            look.repolish(ed)
        self.ed_dir.setText(rs.out_dir)
        self.lbl_dir_short.setText(self._short_dir(rs.out_dir))
        self.chk_txt.setChecked(rs.auto_txt)
        self.chk_wlog.setChecked(rs.auto_write_log)
        self.chk_verb.setChecked(rs.verbose_bridge_log)
        self._loading = False
        self.tx_panel.load()

    def _on_read_opt_changed(self, key: str):
        if self._loading:
            return
        cb, ed = self.read_opts[key]
        mode = READ_MODES[cb.currentText()]
        ed.setVisible(mode == "last")
        setattr(self.app.rs, f"read_{key}", mode)
        if mode == "last":
            try:
                n = int(ed.text().strip())
                if n < 1:
                    raise ValueError
                setattr(self.app.rs, f"read_{key}_n", n)
                ed.setProperty("bad", "false")
            except ValueError:
                ed.setProperty("bad", "true")
            look.repolish(ed)
        self.app.mark_dirty()

    def _on_file_opt_changed(self):
        if self._loading:
            return
        rs = self.app.rs
        rs.out_dir = self.ed_dir.text().strip() or rs.out_dir
        self.lbl_dir_short.setText(self._short_dir(rs.out_dir))
        rs.auto_txt = self.chk_txt.isChecked()
        rs.auto_write_log = self.chk_wlog.isChecked()
        rs.verbose_bridge_log = self.chk_verb.isChecked()
        self.app.mark_dirty()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Okuma klasörü", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _save_log(self):
        p, _ = QFileDialog.getSaveFileName(self, "Logu kaydet", "", "Metin (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_txt.toPlainText())

    def update_map_summary(self, client, rm, ch: str):
        self.rx_ch_pill.set(channel_label(ch), "accent")
        self.tx_drv_pill.set(self.app.ci.driver.name, "ok")
        if client is None:
            self.lbl_map_state.setText("Çevrimdışı mod (AXIL Studio Debug Bridge'den açın veya --sim kullanın)")
            return
        rx_miss = sorted(set(rm.missing_for_rx_config(ch) + rm.missing_for_rx_read(ch)))
        tx_miss = rm.missing_for_tx_config()
        if not rx_miss and not tx_miss:
            self.lbl_map_state.setText(f"Harita: {len(rm.regs)} register · {channel_label(ch)} & TX hazır")
        else:
            parts = [f"Harita: {len(rm.regs)} reg"]
            if rx_miss:
                parts.append(f"{channel_label(ch)} eksik ({len(rx_miss)})")
            if tx_miss:
                parts.append(f"TX eksik ({len(tx_miss)})")
            self.lbl_map_state.setText(" · ".join(parts))
