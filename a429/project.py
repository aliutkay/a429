"""Dosya formatları.

.a429cfg   – config + bağlantı + çözümleme ayarları (JSON)
.a429read  – tek bir okuma oturumu (JSON: özet, word, error, bit diag + o anki config)
.a429proj  – proje paketi (ZIP): project.json (ayarlar) + sessions/*.a429read (tüm okumalar)
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import zipfile

from .model import ConfigInputs
from .protocol import LinkSettings
from .decode import DecodeSettings

VERSION = 1


def settings_dict(ci: ConfigInputs, ls: LinkSettings, ds: DecodeSettings) -> dict:
    return {"version": VERSION, "config": ci.to_dict(), "link": ls.to_dict(), "decode": ds.to_dict()}


def settings_from(d: dict):
    return (ConfigInputs.from_dict(d.get("config", {}), d.get("link", {})), LinkSettings.from_dict(d.get("link", {})),
            DecodeSettings.from_dict(d.get("decode", {})))


def save_config(path, ci, ls, ds):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings_dict(ci, ls, ds), f, ensure_ascii=False, indent=1)


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return settings_from(json.load(f))


def new_session(data: dict, ci, ls, ds, name=None) -> dict:
    now = _dt.datetime.now()
    s = dict(data)
    s["name"] = name or now.strftime("okuma_%Y%m%d_%H%M%S")
    s["created"] = now.isoformat(timespec="seconds")
    s["clk_mhz"] = ci.clk_mhz
    s["settings"] = settings_dict(ci, ls, ds)
    return s


def save_session(path, sess):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=1)


def load_session(path):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    s.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    return s


def save_project(path, ci, ls, ds, sessions):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        idx = []
        for i, s in enumerate(sessions):
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in s["name"])
            fn = f"sessions/{i:04d}_{safe}.a429read"
            z.writestr(fn, json.dumps(s, ensure_ascii=False, indent=1))
            idx.append(fn)
        proj = settings_dict(ci, ls, ds)
        proj["sessions"] = idx
        z.writestr("project.json", json.dumps(proj, ensure_ascii=False, indent=1))


def load_project(path):
    with zipfile.ZipFile(path) as z:
        proj = json.loads(z.read("project.json").decode("utf-8"))
        sessions = [json.loads(z.read(fn).decode("utf-8")) for fn in proj.get("sessions", [])]
    ci, ls, ds = settings_from(proj)
    return ci, ls, ds, sessions
