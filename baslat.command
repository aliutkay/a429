#!/bin/bash
# Mac başlatıcısı: Finder'da çift tıklayın.
cd "$(dirname "$0")" || exit 1

if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
else
    PY=python3
fi

if ! "$PY" -c 'import tkinter, sys; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)'; then
    echo "Bu Python'un Tk surumu eski veya tkinter yok (Tk 8.6+ gerekli)."
    echo "README.md dosyasindaki Mac kurulum adimlarini uygulayin."
    read -r -p "Kapatmak icin Enter'a basin..." _
    exit 1
fi

if ! "$PY" main.py; then
    read -r -p "Kapatmak icin Enter'a basin..." _
fi
