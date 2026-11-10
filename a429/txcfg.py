"""TX Config hesabı: TX ARINC profilinden Pulse/Null/Gap süreleri ve TX Register değerleri."""
from __future__ import annotations

from .regmap import TX_REGISTERS, FrameError, hexstr
from .txlive import OVERRIDE_LINES, build_word, parse_builder, parse_hex_word, sched_values

TX_CONFIG_KEYS = ["tx_transmitter_en", "tx_msg_sched_en", "tx_builder_en", "tx_label", "tx_sdi", "tx_data", "tx_ssm",
                  "tx_parity_type", "sched_delay", "sched_gap", "tx_pulse_dur", "tx_null_dur", "tx_gap_dur", "tx_slp",
                  "tx_ext_valid", "tx_ext_data", "tx_ext_high", "tx_ext_low", "sched_enable"]   # scheduler en son


def tx_profile(ci):
    return next((p for p in ci.profiles if p.name == ci.tx_profile), ci.profiles[0])


def compute_tx(ci, override="Kapalı"):
    """{"regs": [(ad, adres, değer, değer_hex, komut_hex)], "checks": [(ad, ok)], "errors": [..], "text": ..}"""
    p, mhz, rm, cfg = tx_profile(ci), ci.clk_mhz, ci.regmap, ci.tx_live
    if p.rate_nom <= 0 or mhz <= 0:
        raise ValueError("TX profilinde Bit Rate NOM ve System Clock sıfırdan büyük olmalı.")
    tbit = 1000 / p.rate_nom
    bit = round(tbit * mhz); pulse = round(tbit / 2 * mhz); null = bit - pulse; gap = 4 * bit
    slp = 1 if p.rate_nom > 14.5 else 0          # 14.5 kbps üstü High Speed: 1.5 µs eğim
    errors, vals = [], {}
    lines = OVERRIDE_LINES.get(override)
    vals.update(tx_transmitter_en=int(lines is None), tx_ext_high=0 if lines is None else lines[0],
                tx_ext_low=0 if lines is None else lines[1])
    vals.update(tx_msg_sched_en=int(cfg["send_mode"] == "scheduler"), tx_builder_en=int(cfg["source"] == "builder"))
    try:
        label, sdi, data, ssm, odd = parse_builder(cfg)
        build_word(label, sdi, data, ssm, odd)
        vals.update(tx_label=label, tx_sdi=sdi, tx_data=data, tx_ssm=ssm, tx_parity_type=int(odd))
    except ValueError as e:
        errors.append(f"Word oluşturucu: {e}")
    try:
        vals["tx_ext_data"] = parse_hex_word(cfg["word"])
    except ValueError as e:
        errors.append(f"Direkt Word: {e}")
    try:
        delay, igap, _ = sched_values(cfg, mhz, tbit, p.name)
        vals.update(sched_delay=delay, sched_gap=igap)
    except ValueError as e:
        errors.append(f"Scheduler: {e}")
    vals.update(tx_pulse_dur=pulse, tx_null_dur=null, tx_gap_dur=gap, tx_slp=slp, tx_ext_valid=0, sched_enable=0)

    names = dict(TX_REGISTERS)
    regs = []
    for key in TX_CONFIG_KEYS:
        addr, value = rm.tx_regs.get(key, ""), vals.get(key)
        if not addr:
            errors.append(f"{names[key]}: adres girilmemiş")
        try:
            value_hex = "" if value is None else hexstr(value.to_bytes(rm.data_bytes(), rm.endian))
            cmd = hexstr(rm.build_write(addr, value)) if addr and value is not None else ""
        except (OverflowError, FrameError, ValueError) as e:
            errors.append(f"{names[key]}: {e}"); value_hex, cmd = "HATA", ""
        regs.append((names[key], addr, value, value_hex, cmd))
    real_bit = bit / mhz
    checks = [
        ("TX Pulse > 0 ve Null > 0", pulse > 0 and null > 0),
        ("TX Bit Time sapması ≤ %0.5 (clock yuvarlaması)", abs(real_bit - tbit) / tbit <= 0.005),
        ("Bütün TX Register değerleri geçerli", not errors),
    ] + [(e, False) for e in errors]
    text = (f"TX profili: {p.name} · 1 Bit = {bit:,} clk ({real_bit:g} µs) · Pulse {pulse:,} · Null {null:,} · "
            f"Word Gap {gap:,} clk · SLP {slp} ({'1.5 µs' if slp else '10 µs'} eğim)")
    return {"regs": regs, "checks": checks, "errors": errors, "text": text}
