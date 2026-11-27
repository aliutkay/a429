"""TX Config hesabı: FPGA çıkışı → Line Driver entegresi → ARINC 429 hattı analizi ve TX Register değerleri."""
from __future__ import annotations

import math

from .regs import TX_CONFIG_ORDER, TX_REG_NAMES, RegMap
from .txlive import OVERRIDE_LINES, build_word, parse_builder, parse_hex_word, sched_values


def tx_profile(ci):
    return next((p for p in ci.profiles if p.name == ci.tx_profile), ci.profiles[0])


def compute_tx(ci, override: str = "Kapalı", rm: RegMap | None = None) -> dict:
    """TX fiziksel katman hesabı ve Register değerleri.

    Dönen sözlük:
      regs   : [(görünen ad, Studio register adı, offset, değer, değer_hex, hata)]
      writes : [(register adı, değer)]
      rows   : {parametre: (min, nom, max)}
      checks : [(kontrol adı, ok)]
      errors : [hata metinleri]
      single : {"MIN"|"NOM"|"MAX": dalga formu parametre sözlüğü}
      nom_clk: (pulse_clk, bit_clk, null_clk)
      gap_clk: TX Word Gap (clk)
      text   : özet bilgi satırı
    """
    p, drv, mhz, cfg = tx_profile(ci), ci.driver, ci.clk_mhz, ci.tx_live
    voh_min, vol_max, vcc_fpga, tr_fpga_ns, tf_fpga_ns = ci.get_tx_fpga()
    for val, name in (
        (mhz, "System Clock"), (p.rate_nom, "TX Bit Rate NOM"), (p.k, "k"),
        (vcc_fpga, "FPGA VCC"), (drv.vdiff[0], "Line Driver Vdiff MIN"),
        (drv.vdiff[1], "Line Driver Vdiff NOM"), (drv.vdiff[2], "Line Driver Vdiff MAX"),
    ):
        if val <= 0:
            raise ValueError(f"{name} sıfırdan büyük olmalı.")

    flo, fhi = mhz * (1 - ci.ppm / 1e6), mhz * (1 + ci.ppm / 1e6)
    tbit_nom = 1000.0 / p.rate_nom
    thalf_nom = tbit_nom / 2.0
    tbit_lim = (tbit_nom * (1 - p.bit_tol), tbit_nom, tbit_nom * (1 + p.bit_tol))
    thalf_lim = (thalf_nom * (1 - p.half_tol), thalf_nom, thalf_nom * (1 + p.half_tol))
    arinc_rise = (p.rise_nom - p.rise_tol, p.rise_nom, p.rise_nom + p.rise_tol)
    arinc_fall = (p.fall_nom - p.fall_tol, p.fall_nom, p.fall_nom + p.fall_tol)

    slp = 1 if p.rate_nom > 14.5 else 0          # 14.5 kbps üstü High Speed: 1.5 µs eğim
    drv_tr = drv.tr_hs if slp else drv.tr_ls
    drv_tf = drv.tf_hs if slp else drv.tf_ls
    Tr = tuple(x / p.k for x in drv_tr)
    Tf = tuple(x / p.k for x in drv_tf)

    # FPGA çıkışı → Line Driver giriş eşiği kayması (µs)
    v_lo = drv.vil_max / vcc_fpga
    v_nom = (drv.vil_max + drv.vih_min) / 2.0 / vcc_fpga
    v_hi = drv.vih_min / vcc_fpga
    d_thr_fn = lambda v: ((0.5 - v) * tf_fpga_ns - (v - 0.5) * tr_fpga_ns) / 0.8 / 1000.0
    d_thr = (min(d_thr_fn(v_hi), d_thr_fn(v_lo)), d_thr_fn(v_nom), max(d_thr_fn(v_hi), d_thr_fn(v_lo)))

    # Line Driver yayılım gecikmesi asimetrisi Δt = tPHL - tPLH (µs)
    d_drv_nom = (drv.tphl[1] - drv.tplh[1]) / 1000.0
    if drv.skew_max > 0:
        sk = drv.skew_max / 1000.0
        d_drv = (d_drv_nom - sk, d_drv_nom, d_drv_nom + sk)
    else:
        d_drv = ((drv.tphl[0] - drv.tplh[2]) / 1000.0, d_drv_nom, (drv.tphl[2] - drv.tplh[0]) / 1000.0)

    # FPGA clock sayıları
    bit = max(2, round(tbit_nom * mhz))
    delta_nom = d_drv[1] + d_thr[1]
    if ci.tx_comp_delay:
        pulse = max(1, min(bit - 1, round((thalf_nom - delta_nom) * mhz)))
    else:
        pulse = max(1, min(bit - 1, round(thalf_nom * mhz)))
    null = bit - pulse
    gap = math.ceil(4 * tbit_nom * fhi - 1e-9) if ci.tx_gap_margin else 4 * bit

    # Fiziksel süreler (µs, MIN / NOM / MAX)
    fpga_pulse = (pulse / fhi, pulse / mhz, pulse / flo)
    fpga_null = (null / fhi, null / mhz, null / flo)
    fpga_bit = (bit / fhi, bit / mhz, bit / flo)
    fpga_gap = (gap / fhi, gap / mhz, gap / flo)

    line_pulse = (
        fpga_pulse[0] + d_thr[0] + d_drv[0],
        fpga_pulse[1] + d_thr[1] + d_drv[1],
        fpga_pulse[2] + d_thr[2] + d_drv[2],
    )
    line_bit = fpga_bit
    line_null = (
        max(0.0, line_bit[0] - line_pulse[2]),
        line_bit[1] - line_pulse[1],
        line_bit[2] - line_pulse[0],
    )
    flat_top = (
        line_pulse[0] - (Tr[2] + Tf[2]) / 2.0,
        line_pulse[1] - (Tr[1] + Tf[1]) / 2.0,
        line_pulse[2] - (Tr[0] + Tf[0]) / 2.0,
    )
    flat_null = (
        line_null[0] - (Tr[2] + Tf[2]) / 2.0,
        line_null[1] - (Tr[1] + Tf[1]) / 2.0,
        line_null[2] - (Tr[0] + Tf[0]) / 2.0,
    )
    rate_act = (1000.0 / line_bit[2], 1000.0 / line_bit[1], 1000.0 / line_bit[0])
    rate_dev = max(abs(rate_act[0] - p.rate_nom), abs(rate_act[2] - p.rate_nom)) / p.rate_nom

    rows = {
        "ARINC 1 Bit Time limiti (µs)": tbit_lim,
        "ARINC ½ Bit Time limiti (µs)": thalf_lim,
        "FPGA 1 Bit Time (µs)": fpga_bit,
        "FPGA Pulse süresi (µs)": fpga_pulse,
        "FPGA Null süresi (µs)": fpga_null,
        "FPGA → Driver eşik kayması (µs)": d_thr,
        "Line Driver gecikme asimetrisi tPHL − tPLH (µs)": d_drv,
        "Line Driver Rise Time (%10–%90, µs)": drv_tr,
        "Line Driver Fall Time (%10–%90, µs)": drv_tf,
        "Hatta oluşan Pulse süresi (µs)": line_pulse,
        "Hatta oluşan Null süresi (µs)": line_null,
        "Hatta oluşan 1 Bit Time (µs)": line_bit,
        "Pulse tepesinde düz bölge (µs)": flat_top,
        "Null fazında düz bölge (µs)": flat_null,
        "Word Gap süresi (µs)": fpga_gap,
        "Line Driver diferansiyel genliği Vdiff (V)": drv.vdiff,
        "Gerçek Bit Rate (kbps)": rate_act,
    }

    # TX Tek Bit dalga formu verileri (MIN / NOM / MAX)
    single = {}
    for idx, cname in enumerate(("MIN", "NOM", "MAX")):
        # MIN pulse: en kısa darbe + en yavaş eğim; MAX pulse: en uzun darbe + en hızlı eğim
        eidx = 2 - idx
        tr_c = Tr[eidx]
        tf_c = Tf[eidx]
        tp_on_raw = (drv.tplh[eidx] / 1000.0) if idx != 1 else (drv.tplh[1] / 1000.0)
        # Çıkış rampası FPGA kenarından önce başlayamaz (etkin %50 gecikmesi ≥ Tr / 2)
        ton_50 = max(tp_on_raw, tr_c / 2.0)
        toff_50 = ton_50 + line_pulse[idx]
        single[cname] = dict(
            vcc=vcc_fpga,
            vdiff=drv.vdiff[idx],
            fpga_p=fpga_pulse[idx],
            fpga_b=fpga_bit[idx],
            ton_50=ton_50,
            toff_50=toff_50,
            Tr=tr_c,
            Tf=tf_c,
            tr_10_90=drv_tr[eidx],
            tf_10_90=drv_tf[eidx],
            line_p=line_pulse[idx],
            line_b=line_bit[idx],
            lim_p=(thalf_lim[0], thalf_lim[2]),
            lim_b=(tbit_lim[0], tbit_lim[2]),
            driver=drv.name,
            fpga=ci.tx_fpga_std,
            comp=ci.tx_comp_delay,
        )

    # Register değerleri
    errors, vals = [], {}
    lines = OVERRIDE_LINES.get(override)
    vals.update(
        TX_TRANSMITTER_EN=int(lines is None),
        TX_EXT_HIGH=0 if lines is None else lines[0],
        TX_EXT_LOW=0 if lines is None else lines[1],
        TX_MSG_SCHED_EN=int(cfg["send_mode"] == "scheduler"),
        TX_BUILDER_EN=int(cfg["source"] == "builder"),
    )
    try:
        label, sdi, data, ssm, odd = parse_builder(cfg)
        build_word(label, sdi, data, ssm, odd)
        vals.update(TX_LABEL=label, TX_SDI=sdi, TX_DATA=data, TX_SSM=ssm, TX_PARITY_TYPE=int(odd))
    except ValueError as e:
        errors.append(f"Word oluşturucu: {e}")
    try:
        vals["TX_EXT_DATA"] = parse_hex_word(cfg["word"])
    except ValueError as e:
        errors.append(f"Direkt Word: {e}")
    try:
        delay, igap, _ = sched_values(cfg, mhz, tbit_nom, p.name, bit_clk=bit, gap_clk=gap)
        vals.update(TX_INITIAL_DELAY=delay, TX_INTER_WORD_GAP=igap)
    except ValueError as e:
        errors.append(f"Scheduler: {e}")

    vals.update(
        TX_CFG_SEL=2,                # Custom
        TX_CUST_PULSE_DUR=pulse,
        TX_CUST_NULL_DUR=null,
        TX_CUST_GAP_DUR=gap,
        TX_CUST_SLP=slp,
        TX_CFG_APPLY=1,
        TX_SCHED_EN=0,               # başlangıçta durgun; en son yazılır
    )

    loaded = rm is not None and rm.is_loaded()
    regs = []
    writes = []
    for rname in TX_CONFIG_ORDER:
        disp = TX_REG_NAMES.get(rname, rname)
        val = vals.get(rname)
        err = None
        if val is None:
            val_hex = "HATA"
            err = "Değer hesaplanamadı"
        elif val < 0 or val > 0xFFFFFFFF:
            val_hex = "HATA"
            err = f"{val} değeri 32 bit aralığı dışında"
            errors.append(f"{disp}: {err}")
            val = None
        else:
            val_hex = f"0x{val:08X}"
            writes.append((rname, int(val)))
        off_str = rm.offset_hex(rname) if loaded else "—"
        if loaded and not rm.has(rname) and err is None:
            err = "IP haritasında yok"
        regs.append((disp, rname, off_str, val, val_hex, err))

    # Kontroller
    checks = [
        ("FPGA VOH MIN ≥ Line Driver VIH MIN", voh_min >= drv.vih_min),
        ("FPGA VOL MAX ≤ Line Driver VIL MAX", vol_max <= drv.vil_max),
        ("Line Driver VIL MAX < VIH MIN", drv.vil_max < drv.vih_min),
        ("TX Pulse > 0 ve Null > 0", pulse > 0 and null > 0),
        (f"TX Bit Rate sapması (clock + ±ppm) ≤ %{p.rate_tol * 100:g}", rate_dev <= p.rate_tol),
        ("Hatta oluşan 1 Bit Time (MIN…MAX) ARINC limiti içinde",
         line_bit[0] >= tbit_lim[0] - 1e-9 and line_bit[2] <= tbit_lim[2] + 1e-9),
        ("Hatta oluşan ½ Bit Time / Pulse (MIN…MAX) ARINC limiti içinde",
         line_pulse[0] >= thalf_lim[0] - 1e-9 and line_pulse[2] <= thalf_lim[2] + 1e-9),
        ("Pulse tepesinde düz bölge var (flat-top > 0)", flat_top[0] > 0),
        ("Null fazında düz bölge var (> 0)", flat_null[0] > 0),
        ("Word Gap MIN ≥ 4 × ARINC Min Bit Time", fpga_gap[0] >= 4 * tbit_lim[0] - 1e-9),
        ("Line Driver Rise Time ARINC limiti içinde",
         drv_tr[0] >= arinc_rise[0] - 1e-9 and drv_tr[2] <= arinc_rise[2] + 1e-9),
        ("Line Driver Fall Time ARINC limiti içinde",
         drv_tf[0] >= arinc_fall[0] - 1e-9 and drv_tf[2] <= arinc_fall[2] + 1e-9),
        ("Line Driver Vdiff (MIN…MAX) ARINC TX limiti (9–11 V) içinde",
         drv.vdiff[0] >= 9.0 - 1e-9 and drv.vdiff[2] <= 11.0 + 1e-9),
        ("Line Driver parametrelerinde MIN ≤ NOM ≤ MAX",
         all(t[0] <= t[1] <= t[2] for t in (drv.tplh, drv.tphl, drv.tr_hs, drv.tf_hs, drv.tr_ls, drv.tf_ls, drv.vdiff))),
        ("Bütün TX Register değerleri geçerli", not errors),
    ]
    if override == "HIGH-Z" and not drv.has_hiz:
        checks.append((f"Seçili Line Driver ({drv.name}) HIGH-Z (11) desteklemiyor", False))
    checks += [(e, False) for e in errors]

    slp_txt = f"SLP {slp} ({'1.5 µs' if slp else '10 µs'} eğim)" if drv.has_slp else "Harici kapasitörlü eğim (SLP pini yok)"
    comp_txt = " · Gecikme telafili" if ci.tx_comp_delay else ""
    text = (
        f"TX: {p.name} · Driver: {drv.name} · 1 Bit = {bit:,} clk ({bit / mhz:g} µs) · "
        f"Pulse {pulse:,} · Null {null:,} · Gap {gap:,} clk · {slp_txt}{comp_txt}"
    )
    return {
        "regs": regs,
        "writes": writes,
        "rows": rows,
        "checks": checks,
        "errors": errors,
        "single": single,
        "nom_clk": (pulse, bit, null),
        "gap_clk": gap,
        "text": text,
    }
