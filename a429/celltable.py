"""Hücre bazında PASS/FAIL renklendirme yapan tablo. Üzerine gelince veya sağ tıklayınca nedeni gösterir."""
from __future__ import annotations

import bisect
import tkinter as tk
from tkinter import ttk, font as tkfont

PASS_BG, PASS_FG = "#C6EFCE", "#006100"
FAIL_BG, FAIL_FG = "#FFC7CE", "#9C0006"
SEL_BG, HEAD_BG, LINE = "#DDEBF7", "#DCDAD5", "#D9D9D9"


class Cell:
    """ok: True (PASS), False (FAIL), None (kontrol yok). why: neden açıklaması."""
    __slots__ = ("text", "ok", "why")

    def __init__(self, text, ok=None, why=""):
        self.text, self.ok, self.why = "" if text is None else str(text), ok, why

    def tip(self):
        if self.ok is None:
            return self.why
        return f"{'PASS' if self.ok else 'FAIL'}: {self.why}"


class CellTable(ttk.Frame):
    ROW_H, HEAD_H = 20, 22

    def __init__(self, master, columns, widths, on_double=None):
        super().__init__(master)
        self.columns, self.widths, self.on_double = list(columns), list(widths), on_double
        self.rows, self.selected = [], None
        self.font = tkfont.nametofont("TkDefaultFont")
        self._clip, self._hover, self._after, self._tip, self._drag = {}, None, None, None, None
        self.head = tk.Canvas(self, height=self.HEAD_H, bg=HEAD_BG, highlightthickness=0)
        self.body = tk.Canvas(self, bg="white", highlightthickness=0)
        self.vs = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.body.yview)
        self.hs = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self._xview)
        self.body.configure(yscrollcommand=self._yset, xscrollcommand=self._xset)
        self.head.grid(row=0, column=0, sticky="ew"); self.body.grid(row=1, column=0, sticky="nsew")
        self.vs.grid(row=0, column=1, rowspan=2, sticky="ns"); self.hs.grid(row=2, column=0, sticky="ew")
        self.rowconfigure(1, weight=1); self.columnconfigure(0, weight=1)
        b = self.body
        b.configure(yscrollincrement=1, xscrollincrement=1)
        self.head.configure(xscrollincrement=1)
        b.bind("<Configure>", lambda e: (self._region(), self._render()))
        b.bind("<Button-1>", self._click); b.bind("<Double-1>", self._double)
        b.bind("<Motion>", self._motion); b.bind("<Leave>", lambda e: self._hide())
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            b.bind(seq, self._right)
        for w in (b, self.head):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Shift-MouseWheel>", self._hwheel)
        self.head.bind("<Button-1>", self._head_press); self.head.bind("<B1-Motion>", self._head_drag)
        self.head.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.head.bind("<Motion>", self._head_cursor)
        self._layout()

    # ------------------------------------------------------------- veri
    def set_rows(self, rows):
        self.rows = [[c if isinstance(c, Cell) else Cell(c) for c in r] for r in rows]
        self.selected = None
        self._hide(); self._layout()

    def cell_text(self, row, col):
        return self.rows[row][col].text

    # ------------------------------------------------------------- yerleşim ve çizim
    def _layout(self):
        self._edges = [0]
        for w in self.widths:
            self._edges.append(self._edges[-1] + w)
        self._region(); self._draw_head(); self._render()

    def _region(self):
        """Kaydırma alanı en az pencere kadardır: içerik sığıyorsa boş alana kaymaz."""
        w = max(self._edges[-1], self.body.winfo_width())
        h = max(len(self.rows) * self.ROW_H, self.body.winfo_height())
        self.body.configure(scrollregion=(0, 0, w, h))
        self.head.configure(scrollregion=(0, 0, w, self.HEAD_H))

    def _xview(self, *a):
        self.body.xview(*a); self.head.xview(*a)

    def _xset(self, a, b):
        self.hs.set(a, b); self.head.xview_moveto(a); self._render()

    def _yset(self, a, b):
        self.vs.set(a, b); self._render()

    def _fit(self, text, width):
        key = (text, width)
        if key not in self._clip:
            s = text
            if self.font.measure(s) > width:
                while s and self.font.measure(s + "…") > width:
                    s = s[:-1]
                s += "…"
            if len(self._clip) > 20000:
                self._clip.clear()
            self._clip[key] = s
        return self._clip[key]

    def _draw_head(self):
        h = self.head
        h.delete("all")
        for i, name in enumerate(self.columns):
            x0, x1 = self._edges[i], self._edges[i + 1]
            h.create_text((x0 + x1) / 2, self.HEAD_H / 2, text=self._fit(name, x1 - x0 - 8), font=self.font, fill="black")
            h.create_line(x1 - 1, 2, x1 - 1, self.HEAD_H - 2, fill="#9E9A91")

    def _render(self):
        b, rh = self.body, self.ROW_H
        b.delete("all")
        y0 = b.canvasy(0)
        first, last = max(0, int(y0 // rh)), min(len(self.rows), int((y0 + b.winfo_height()) // rh) + 1)
        for r in range(first, last):
            top, row = r * rh, self.rows[r]
            if r == self.selected:
                b.create_rectangle(0, top, self._edges[-1], top + rh, fill=SEL_BG, outline="")
            for c, cell in enumerate(row[:len(self.columns)]):
                x0, x1 = self._edges[c], self._edges[c + 1]
                if cell.ok is not None:
                    b.create_rectangle(x0, top, x1, top + rh, fill=PASS_BG if cell.ok else FAIL_BG, outline="")
                fg = "black" if cell.ok is None else (PASS_FG if cell.ok else FAIL_FG)
                b.create_text((x0 + x1) / 2, top + rh / 2, text=self._fit(cell.text, x1 - x0 - 6), font=self.font, fill=fg)
            b.create_line(0, top + rh - 1, self._edges[-1], top + rh - 1, fill=LINE)
        bottom = last * rh
        if last > first:
            for x in self._edges[1:]:
                b.create_line(x - 1, first * rh, x - 1, bottom, fill=LINE)

    # ------------------------------------------------------------- fare
    def _at(self, ev):
        y, x = self.body.canvasy(ev.y), self.body.canvasx(ev.x)
        r = int(y // self.ROW_H)
        c = bisect.bisect_right(self._edges, x) - 1
        if 0 <= r < len(self.rows) and 0 <= c < len(self.columns) and c < len(self.rows[r]):
            return r, c
        return None

    def _click(self, ev):
        hit = self._at(ev)
        self.selected = hit[0] if hit else None
        self._render()

    def _double(self, ev):
        hit = self._at(ev)
        if hit and self.on_double:
            self.selected = hit[0]; self._render(); self.on_double(hit[0])

    def _wheel(self, ev):
        self._hide()
        self.body.yview_scroll(self._units(ev) * self.ROW_H, "units")

    def _hwheel(self, ev):
        self._hide()
        self._xview("scroll", self._units(ev) * (20 if abs(ev.delta) < 120 else 80), "units")

    @staticmethod
    def _units(ev):
        step = ev.delta / 120 if abs(ev.delta) >= 120 else ev.delta
        return -int(step) or (-1 if ev.delta > 0 else 1)

    # ------------------------------------------------------------- sütun genişliği
    def _head_edge(self, ev):
        x = self.head.canvasx(ev.x)
        for i, e in enumerate(self._edges[1:]):
            if abs(x - e) <= 5:
                return i
        return None

    def _head_cursor(self, ev):
        self.head.configure(cursor="sb_h_double_arrow" if self._head_edge(ev) is not None else "")

    def _head_press(self, ev):
        i = self._head_edge(ev)
        self._drag = (i, self.head.canvasx(ev.x), self.widths[i]) if i is not None else None

    def _head_drag(self, ev):
        if self._drag:
            i, x0, w0 = self._drag
            self.widths[i] = max(30, int(w0 + self.head.canvasx(ev.x) - x0))
            self._layout()

    # ------------------------------------------------------------- neden penceresi
    def _motion(self, ev):
        hit = self._at(ev)
        if hit == self._hover:
            return
        self._hide()
        self._hover = hit
        if hit and self.rows[hit[0]][hit[1]].tip():
            x, y = ev.x_root, ev.y_root
            self._after = self.after(350, lambda: self._show(hit, x, y))

    def _right(self, ev):
        hit = self._at(ev)
        self._hide()
        self._hover = hit
        if hit and self.rows[hit[0]][hit[1]].tip():
            self._show(hit, ev.x_root, ev.y_root)

    def _show(self, hit, x, y):
        self._after = None
        cell = self.rows[hit[0]][hit[1]]
        t = tk.Toplevel(self); t.wm_overrideredirect(True)
        if self.tk.call("tk", "windowingsystem") == "aqua":
            try:
                t.tk.call("::tk::unsupported::MacWindowStyle", "style", t._w, "help", "noActivates")
            except tk.TclError:
                pass
        t.wm_geometry(f"+{x + 14}+{y + 14}")
        tk.Label(t, text=cell.tip(), justify=tk.LEFT, bg="#FFFFE1", fg="black", relief=tk.SOLID, bd=1,
                 padx=6, pady=3, wraplength=480, font=self.font).pack()
        self._tip = t

    def _hide(self):
        self._hover = None
        if self._after:
            self.after_cancel(self._after); self._after = None
        if self._tip:
            self._tip.destroy(); self._tip = None
