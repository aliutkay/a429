"""TX Config hesabı: TX ARINC profilinden Pulse/Null/Gap süreleri ve TX Register değerleri."""
from __future__ import annotations

from .regs import TX_CONFIG_ORDER, TX_REG_NAMES, RegMap
from .txlive import OVERRIDE_LINES, build_word, parse_builder, parse_hex_word, sched_values


def tx_profile(ci):
    return next((p for p in ci.profiles if p.name == ci.tx_profile), ci.profiles[0])


def compute_tx(ci, override: str = "Kapalı", rm: RegMap | None = None) -> dict:
    """{"regs": [(ad, reg_adı, offset, değer, değer_hex, hata)], "writes": [(reg_adı, değer)],
        "checks": [(ad, ok)], "errors": [..], "text": ..}"""
    p, mhz, cfg = tx_profile(ci), ci.clk_mhz, ci.tx_live
    if p.rate_nom <= 0 or mhz <= 0:
        raise ValueError("TX profilinde Bit Rate NOM ve System Clock sıfırdan büyük olmalı.")
    tbit = 1000 / p.rate_nom
    bit = round(tbit * mhz)
    pulse = round(tbit / 2 * mhz)
    null = bit - pulse
    gap = 4 * bit
    slp = 1 if p.rate_nom > 14.5 else 0          # 14.5 kbps üstü High Speed: 1.5 µs eğim

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
        delay, igap, _ = sched_values(cfg, mhz, tbit, p.name)
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

    real_bit = bit / mhz
    checks = [
        ("TX Pulse > 0 ve Null > 0", pulse > 0 and null > 0),
        ("TX Bit Time sapması ≤ %0.5 (clock yuvarlaması)", abs(real_bit - tbit) / tbit <= 0.005),
        ("Bütün TX Register değerleri geçerli", not errors),
    ] + [(e, False) for e in errors]
    text = (
        f"TX profili: {p.name} · 1 Bit = {bit:,} clk ({real_bit:g} µs) · Pulse {pulse:,} · Null {null:,} · "
        f"Word Gap {gap:,} clk · SLP {slp} ({'1.5 µs' if slp else '10 µs'} eğim)"
    )
    return {"regs": regs, "writes": writes, "checks": checks, "errors": errors, "text": text}
