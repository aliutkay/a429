"""Logic-analyzer görünümlü grafikler (matplotlib): örnek dalga formu, tek bit analizi, word dalga formu."""
from __future__ import annotations

from .decode import conv, rx_bits, word_fields, fmt_val

BG, FG, TRACE, GRID = "#000000", "#C0C0C0", "#00FF00", "#5A5A5A"
CASE_COL = {"MIN": "#FF4040", "NOM": "#00FF00", "MAX": "#00B0F0"}


# ---------------------------------------------------------------- yakınlaştırmaya duyarlı yazılar
ZOOM_FS_CAP = 18        # yakınlaştırınca yazıların çıkabileceği en büyük punto
VLINE_FS_CAP = 13       # zaman damgaları (dikey) için üst sınır


def _txt(ax, x, y, s, fs=8, span=None, above=False, cap=ZOOM_FS_CAP, **kw):
    """Eksene yazı ekler ve yakınlaştırma için kaydeder.
    span=(x1, x2): süre etiketi → sığarsa yatay, sığmazsa dik yazılır."""
    kw.setdefault("ha", "center")
    datax = "transform" not in kw
    if not datax:
        cap = fs                                    # eksene sabit bilgi yazıları büyümez
    t = ax.text(x, y, s, fontsize=fs, clip_on=False, **kw)
    if not hasattr(ax, "_zt"):
        ax._zt = []
    ax._zt.append(dict(t=t, fs=fs, span=span, above=above, cap=max(cap, fs), x=x if datax else None, y=y))
    return t


def relayout_ax(ax, renderer=None):
    """Yazı boyutlarını yakınlaştırma oranıyla büyütür; süre etiketlerini sığmıyorsa dik çevirir."""
    zt = getattr(ax, "_zt", None)
    if not zt or not hasattr(ax, "_zt_w0"):
        return
    fig = ax.figure
    if renderer is None:
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            return
    x0, x1 = ax.get_xlim()
    lo, hi = min(x0, x1), max(x0, x1)
    f = max(1.0, ax._zt_w0 / max(hi - lo, 1e-30))
    tr = ax.transData
    ylo, yhi = sorted(ax.get_ylim())
    y_zoomed = (yhi - ylo) < ax._zt_h0 * 0.999
    for e in zt:
        t = e["t"]
        if y_zoomed and not ylo <= e["y"] <= yhi:   # dikey zoomda görünüm dışındaki yazılar taşmasın
            t.set_visible(False)
            continue
        t.set_visible(True)
        if e["span"] is not None:                   # süre etiketi: görünen kısmın ortasına
            a, b = sorted(e["span"])
            va_, vb_ = max(a, lo), min(b, hi)
            vis = vb_ > va_
            t.set_visible(vis)
            if not vis:
                continue
            t.set_position(((va_ + vb_) / 2, e["y"]))
        elif e["x"] is not None:                    # görünüm dışındaki yazılar kenar boşluğuna taşmasın
            vis = lo <= e["x"] <= hi
            t.set_visible(vis)
            if not vis:
                continue
        t.set_fontsize(min(e["fs"] * f, e["cap"]))
        if e["span"] is None:
            continue
        px = abs(tr.transform((vb_, 0))[0] - tr.transform((va_, 0))[0])
        t.set_rotation(0); t.set_va("bottom" if e["above"] else "top")
        if t.get_window_extent(renderer).width > px * 0.96:
            t.set_rotation(90)
            # dik yazı eksen dışına taşıyorsa sığacak kadar küçült
            yp = tr.transform((0, e["y"]))[1]
            room = (ax.bbox.y1 - yp) if e["above"] else (yp - ax.bbox.y0)
            h = t.get_window_extent(renderer).height
            if h > room:
                fs_fit = t.get_fontsize() * max(room, 0) / h * 0.95
                if fs_fit >= e["fs"]:            # okunur boyutta dik sığıyor
                    t.set_fontsize(fs_fit)
                else:                            # dik sığmıyor → yatay kalsın (okunurluk öncelikli)
                    t.set_rotation(0)


def relayout(fig):
    try:
        r = fig.canvas.get_renderer()
    except Exception:
        r = None
    for ax in fig.axes:
        relayout_ax(ax, r)


def finalize(fig):
    """Çizim bitince: başlangıç görünümünü kaydet, eksen değişimine bağla, yazıları yerleştir."""
    fig._home = {}
    for ax in fig.axes:
        x0, x1 = ax.get_xlim()
        ax._zt_w0 = abs(x1 - x0)
        ax._zt_h0 = abs(ax.get_ylim()[1] - ax.get_ylim()[0])
        fig._home[ax] = (ax.get_xlim(), ax.get_ylim())
        ax.callbacks.connect("xlim_changed", lambda a: relayout_ax(a))
    relayout(fig)


def _style(ax, title, ylabel):
    ax.set_facecolor(BG)
    ax.set_title(title, color=TRACE, fontsize=10, fontweight="bold")
    ax.set_ylabel(ylabel, color=FG, fontsize=9)
    ax.tick_params(colors=FG, labelsize=8)
    ax.set_xticks([])                          # eksenin kendi bölmeleri yok; zamanlar kesikli çizgilerde
    for s in ax.spines.values():
        s.set_color("#7F7F7F")


def _fmt(v, unit):
    """clk tam sayıysa tam, değilse 1 ondalık (fiziksel süreler) – her yerde aynı biçim."""
    if unit == "clk":
        return f"{v:,.0f} clk" if abs(v - round(v)) < 1e-6 else f"{v:,.1f} clk"
    return f"{v:,.3f} {unit}"


def _vline(ax, x, y0, y1, label=None, color=GRID, ls="--", tcol="#909090", fs=7):
    ax.plot([x, x], [y0, y1], ls=ls, color=color, lw=0.7)
    if label:
        _txt(ax, x, y0, label, fs=fs, rotation=90, va="top", color=tcol, cap=VLINE_FS_CAP)


def _arrow(ax, x1, x2, y, text, color, above=False, fs=8, rot=None):
    # çizgi + uç işaretleri: eksen dışına taşmaz (zoom'da kırpılır)
    ax.plot([x1, x2], [y, y], color=color, lw=0.8)
    ax.plot([x1], [y], marker="<", color=color, ms=4, ls="none")
    ax.plot([x2], [y], marker=">", color=color, ms=4, ls="none")
    if text:
        _txt(ax, (x1 + x2) / 2, y, text, fs=fs, span=(x1, x2), above=above,
             va="bottom" if above else "top", color=color)


# ---------------------------------------------------------------- Config: örnek dalga formları
def draw_examples(fig, res, mhz, unit, pattern, only=None):
    fig.clear(); fig.set_facecolor(BG)
    cases = [("MIN", res.dur["Min Pulse"][1], res.dur["Min Bit"][1], "CFG Min Pulse, Min Bit register değerleri"),
             ("NOM", res.nom_clk[0], res.nom_clk[1], "nominal"),
             ("MAX", res.dur["Max Pulse"][1], res.dur["Max Bit"][1], "CFG Max Pulse, Max Bit register değerleri")]
    if only:
        cases = [c for c in cases if c[0] == only]
    axs = fig.subplots(len(cases), 1, squeeze=False).ravel()
    for ax, (nm, pc, bc, desc) in zip(axs, cases):
        col = CASE_COL[nm]
        P, Bt = conv(pc, unit, mhz), conv(bc, unit, mhz)
        xs, ys = [0], [0]
        for k, b in enumerate(pattern):
            lv = 1 if b else -1
            xs += [k * Bt, k * Bt, k * Bt + P, k * Bt + P]; ys += [0, lv, lv, 0]
        xs.append(len(pattern) * Bt); ys.append(0)
        ax.plot(xs, ys, color=col, lw=1.8)
        for k in range(len(pattern) + 1):
            _vline(ax, k * Bt, -1.9, 2.3, _fmt(k * Bt, unit))
            if k < len(pattern):
                _vline(ax, k * Bt + P, -1.9, 2.3, _fmt(k * Bt + P, unit), "#3C3C3C", ":", "#707070")
                _arrow(ax, k * Bt, k * Bt + P, -1.3, _fmt(P, unit), col, fs=7)
                _arrow(ax, k * Bt + P, (k + 1) * Bt, -1.3, _fmt(Bt - P, unit), "#A0A0A0", fs=7)
        _arrow(ax, 2 * Bt, 2 * Bt + P, 1.35, f"Pulse = {_fmt(P, unit)}", col, above=True, fs=8)
        _arrow(ax, 2 * Bt, 3 * Bt, 1.95, f"Bit = {_fmt(Bt, unit)}", col, above=True, fs=8)
        _style(ax, f"RX örnek dalga formu – {nm} ({desc})", "Seviye")
        ax.set_ylim(-3.2, 2.5); ax.set_xlim(-0.01 * len(pattern) * Bt, len(pattern) * Bt * 1.01)
        ax.set_yticks([-1, 0, 1])
    axs[-1].set_xlabel(f"Zaman ({unit}) – geçiş anları kesikli çizgilerin altında", color=FG, fontsize=8)
    fig.tight_layout(); finalize(fig)


# ---------------------------------------------------------------- Config: tek bit analizi
def draw_single(fig, res, mhz, unit, case):
    """Fiziksel en kötü durum (test toleransı eklenmemiş). Değerler Config ara hesaplarıyla birebir aynı kaynaktan (res.single)."""
    fig.clear(); fig.set_facecolor(BG)
    d = res.single[case]; col = CASE_COL[case]
    T = lambda us: conv(us * mhz, unit, mhz)
    Tr, Tf, fs_, th, hs, tend = T(d["Tr"]), T(d["Tf"]), T(d["fs"]), T(d["th"]), T(d["hs"]), T(d["tend"])
    ton, toff, oon, ooff = T(d["ton"]), T(d["toff"]), T(d["oon"]), T(d["ooff"])
    A, V1, VN = d["A"], d["V1"], d["VN"]
    ax, bx = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    yx = ax.get_yaxis_transform()
    # analog
    ax.plot([0, Tr, fs_, fs_ + Tf, tend], [0, A, A, 0, 0], color=col, lw=1.8)
    ax.axhline(V1, color="#FFFF00", ls="--", lw=1); ax.axhline(VN, color="#FF9900", ls="--", lw=1)
    _txt(ax, 0.995, V1, f"One/Zero eşiği (Latch set): {V1:.2f} V", fs=8, color="#FFFF00", ha="right", va="bottom", transform=yx)
    _txt(ax, 0.995, VN, f"Null eşiği (Latch reset): {VN:.2f} V", fs=8, color="#FF9900", ha="right", va="top", transform=yx)
    ax.plot([ton], [V1], "o", color="#FFFF00", ms=5); ax.plot([toff], [VN], "o", color="#FF9900", ms=5)
    _txt(ax, ton, V1, f"  Latch set: {_fmt(ton, unit)}", fs=8, color="#FFFF00", va="top", ha="left")
    _txt(ax, toff, VN, f"Latch reset: {_fmt(toff, unit)}  ", fs=8, color="#FF9900", va="bottom", ha="right")
    for x in (0, Tr, fs_, fs_ + Tf, tend):
        _vline(ax, x, -1.9, A + 2.5, _fmt(x, unit))
    for x1, x2, t, c in ((0, Tr, "Rise (0 → A)", "#C8C8C8"), (Tr, fs_, "HIGH", col), (fs_, fs_ + Tf, "Fall (A → 0)", "#C8C8C8"),
                         (fs_ + Tf, tend, "NULL", "#A0A0A0")):
        _arrow(ax, x1, x2, -1.2, f"{t} = {_fmt(x2 - x1, unit)}", c)
    _arrow(ax, hs, hs + th, A / 2, f"½ Bit Time = {_fmt(th, unit)}", "#FFFFFF", above=True, fs=9)
    _arrow(ax, 0.1 * Tr, 0.9 * Tr, A + 1.3, f"Rise Time (%10–%90) = {_fmt(0.8 * Tr, unit)}", "#C8C8C8", above=True)
    _arrow(ax, fs_ + 0.1 * Tf, fs_ + 0.9 * Tf, A + 1.3, f"Fall Time (%10–%90) = {_fmt(0.8 * Tf, unit)}", "#C8C8C8", above=True)
    _style(ax, f"{case} – analog giriş ve eşikler (A = {A:.1f} V) · fiziksel değerler, test toleransı eklenmemiş", "Gerilim (V)")
    ax.set_ylim(-6, A + 3.5)
    # dijital (FPGA'nın gördüğü)
    bx.plot([0, oon, oon, ooff, ooff, tend], [0, 0, 1, 1, 0, 0], color=col, lw=1.8)
    _vline(bx, ton, -0.9, 2.1, _fmt(ton, unit), "#FFFF00", ":", "#FFFF00")
    _vline(bx, toff, -0.9, 2.1, _fmt(toff, unit), "#FF9900", ":", "#FF9900")
    for x in (0, oon, ooff, tend):
        _vline(bx, x, -0.9, 2.1, _fmt(x, unit))
    _arrow(bx, 0, oon, -0.45, _fmt(oon, unit), "#A0A0A0")
    _arrow(bx, oon, ooff, -0.45, f"Pulse = {_fmt(ooff - oon, unit)}", col, fs=9)
    _arrow(bx, ooff, tend, -0.45, _fmt(tend - ooff, unit), "#A0A0A0")
    _arrow(bx, ton, oon, 1.5, f"tPLH + eşik gecikmesi = {_fmt(oon - ton, unit)}", "#FFFF00", above=True)
    _arrow(bx, toff, ooff, 1.5, f"tPHL + eşik gecikmesi = {_fmt(ooff - toff, unit)}", "#FF9900", above=True)
    extra = ""
    if case != "NOM":
        key = "Min Pulse" if case == "MIN" else "Max Pulse"
        extra = f"\nFiziksel Pulse = {_fmt(ooff - oon, unit)}  →  CFG {key} (test toleransı ve clock ppm dahil) = {_fmt(conv(res.dur[key][1], unit, mhz), unit)}"
    _style(bx, f"{case} – FPGA'da görülen Receiver çıkışı (FPGA giriş eşiği v = {d['v']:.3f}·VCC) · fiziksel değerler, test toleransı eklenmemiş{extra}", "Lojik")
    bx.set_ylim(-2.2, 2.2); bx.set_yticks([0, 1])
    bx.set_xlim(-0.01 * tend, tend * 1.01)
    bx.set_xlabel(f"Zaman ({unit}) – geçiş anları kesikli çizgilerin altında", color=FG, fontsize=8)
    fig.tight_layout(); finalize(fig)


# ---------------------------------------------------------------- Okuma: word dalga formu
def draw_word(fig, wrow, bitmap, mhz, unit, ds, nominal=(250, 250)):
    """wrow: decode_words satırı; bitmap: {bit: (pulse_clk, null_clk)} (yoksa nominal)."""
    fig.clear(); fig.set_facecolor(BG)
    ax = fig.add_subplot(111)
    wd = wrow.get("wd")
    if wd is None:
        _style(ax, "Word verisi yok", ""); finalize(fig); return
    measured = len(bitmap) >= 32
    # 0 okunan (henüz yazılmamış / boş) bit kayıtları normaldir → o bit nominal çizilir
    pb = [(bitmap[b] if measured and sum(bitmap[b]) > 0 else nominal) for b in range(32)]
    n_zero = sum(1 for b in range(32) if measured and sum(bitmap[b]) == 0)
    c = lambda clk: conv(clk, unit, mhz)
    starts, t = [], 0.0
    for p, n in pb:
        starts.append(t); t += c(p + n)
    total = t
    gv = 4 * total / 32                                          # gap ölçeksiz: 4 ortalama bit
    tsw = conv(wrow["ts"], unit, mhz) if wrow.get("ts") is not None else 0.0
    t0 = tsw - total if ds.ts_at_word_end else tsw              # bit 1 başlangıcı (gerçek zaman)
    gap_real = c(wrow.get("gap") or 0)
    bits = rx_bits(wd)
    # gap (kesikli + kırık işareti)
    ax.plot([-gv, 0], [0, 0], ls="--", color=TRACE, lw=1.8)
    m = -gv / 2; w = gv * 0.025
    ax.plot([m - 2 * w, m], [-0.25, 0.25], color="white", lw=1.2); ax.plot([m, m + 2 * w], [-0.25, 0.25], color="white", lw=1.2)
    _vline(ax, -gv, -2.0, 1.12, _fmt(t0 - gap_real, unit), tcol="#FFC000")
    _arrow(ax, -gv, 0, -1.2, f"ölçülen Word Gap = {_fmt(gap_real, unit)}", "#FFC000", fs=7)
    # iz
    xs, ys = [0], [0]
    for k, (st, (p, n)) in enumerate(zip(starts, pb)):
        lv = 1 if bits[k] else -1
        xs += [st, st, st + c(p), st + c(p)]; ys += [0, lv, lv, 0]
    xs.append(total); ys.append(0)
    ax.plot(xs, ys, color=TRACE, lw=1.6)
    for k, (st, (p, n)) in enumerate(zip(starts, pb)):
        _vline(ax, st, -2.0, 1.12, _fmt(t0 + st, unit))
        _vline(ax, st + c(p), -2.0, 1.12, _fmt(t0 + st + c(p), unit), "#3C3C3C", ":", "#707070")
        _arrow(ax, st, st + c(p), -1.15, _fmt(c(p), unit), "#9AFF9A", fs=7)
        _arrow(ax, st + c(p), st + c(p + n), -1.15, _fmt(c(n), unit), "#B0B0B0", fs=7)
    _vline(ax, total, -2.0, 1.12, _fmt(t0 + total, unit))
    # alan ayraçları
    f = word_fields(wd)
    b = "".join(map(str, bits))
    fields = [("LABEL", 0, 8, fmt_val(f["label"], ds.label_fmt, 2), b[0:8], ("MSB", "LSB"), "#00B0F0"),
              ("SDI", 8, 10, fmt_val(f["sdi"], ds.sdi_fmt, 1), b[8:10], ("LSB", "MSB"), "#FF66FF"),
              ("DATA", 10, 29, fmt_val(f["data"], ds.data_fmt, 5), b[10:29], ("LSB", "MSB"), "#FFFF00"),
              ("SSM", 29, 31, fmt_val(f["ssm"], ds.ssm_fmt, 1), b[29:31], ("LSB", "MSB"), "#FF8080"),
              ("PARITY", 31, 32, f"d'{f['p']}", b[31], None, "#C0C0C0")]
    ax.plot([-gv, -gv, 0, 0], [1.2, 1.35, 1.35, 1.2], color="#FFC000", lw=1.2)
    _txt(ax, -gv / 2, 1.38, "WORD GAP (ölçeksiz)", fs=8, color="#FFC000", va="bottom")
    for nm, a, e, val, bs, ends, colr in fields:
        x1, x2 = starts[a], (starts[e] if e < 32 else total)
        ax.plot([x1, x1, x2, x2], [1.2, 1.35, 1.35, 1.2], color=colr, lw=1.2)
        _txt(ax, (x1 + x2) / 2, 1.38, f"{nm} {val} · b'{bs}", fs=8, color=colr, va="bottom")
        if ends:
            _txt(ax, x1, 1.1, ends[0], fs=7, color=colr, ha="left", va="top")
            _txt(ax, x2, 1.1, ends[1], fs=7, color=colr, ha="right", va="top")
    src = "Bit Diagnostic (ölçülen)" if measured else "nominal (Bit Diagnostic verisi yok)"
    if n_zero:
        src += f" · {n_zero} Bit için 0 okundu, nominal süreyle çizildi"
    _style(ax, f"Word {wrow['no']} – logic analyzer görünümü (+1 HIGH / 0 NULL / −1 LOW) · süre kaynağı: {src}", "Seviye")
    ax.set_ylim(-3.2, 1.75); ax.set_yticks([-1, 0, 1])
    span = total + gv
    ax.set_xlim(-gv - 0.01 * span, total + 0.01 * span)
    ax.set_xlabel(f"Zaman ({unit}) – geçiş anları Word Timestamp'ine göre kesikli çizgilerin altında; Word Gap ölçeksiz",
                  color=FG, fontsize=8)
    fig.tight_layout(); finalize(fig)
