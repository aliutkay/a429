"""Dosya formatları.

.a429cfg   – config + okuma + çözümleme ayarları (JSON)
.a429read  – tek bir okuma oturumu (JSON: özet, word, error, bit diag + o anki config)
.a429proj  – proje paketi (ZIP): project.json (ayarlar) + sessions/*.a429read (tüm okumalar)
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import zipfile

from .model import ConfigInputs
from .ip import ReadSettings
from .decode import DecodeSettings

VERSION = 2


def settings_dict(ci: ConfigInputs, rs: ReadSettings, ds: DecodeSettings) -> dict:
    return {"version": VERSION, "config": ci.to_dict(), "read": rs.to_dict(), "decode": ds.to_dict()}


def settings_from(d: dict):
    read_raw = d.get("read") if "read" in d else d.get("link", {})
    return (
        ConfigInputs.from_dict(d.get("config", {}), d.get("link")),
        ReadSettings.from_dict(read_raw),
        DecodeSettings.from_dict(d.get("decode", {})),
    )


def save_config(path, ci, rs, ds):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings_dict(ci, rs, ds), f, ensure_ascii=False, indent=1)


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return settings_from(json.load(f))


def new_session(data: dict, ci, rs, ds, name=None) -> dict:
    now = _dt.datetime.now()
    s = dict(data)
    ch = s.get("channel")
    default_name = now.strftime(f"okuma_{ch}_%Y%m%d_%H%M%S" if ch else "okuma_%Y%m%d_%H%M%S")
    s["name"] = name or default_name
    s["created"] = now.isoformat(timespec="seconds")
    s["clk_mhz"] = ci.clk_mhz
    s["settings"] = settings_dict(ci, rs, ds)
    return s


def save_session(path, sess):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=1)


def load_session(path):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    return s


def save_project(path, ci, rs, ds, sessions, tx_history=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        idx = []
        for i, s in enumerate(sessions):
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in s["name"])
            fn = f"sessions/{i:04d}_{safe}.a429read"
            z.writestr(fn, json.dumps(s, ensure_ascii=False, indent=1))
            idx.append(fn)
        proj = settings_dict(ci, rs, ds)
        proj["sessions"] = idx
        if tx_history:
            proj["tx_history"] = list(tx_history)
        z.writestr("project.json", json.dumps(proj, ensure_ascii=False, indent=1))


def load_project(path):
    with zipfile.ZipFile(path) as z:
        proj = json.loads(z.read("project.json").decode("utf-8"))
        sessions = [json.loads(z.read(fn).decode("utf-8")) for fn in proj.get("sessions", [])]
    ci, rs, ds = settings_from(proj)
    return ci, rs, ds, sessions


def load_tx_history(path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        proj = json.loads(z.read("project.json").decode("utf-8"))
    return list(proj.get("tx_history", []))
