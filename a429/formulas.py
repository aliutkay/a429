"""RX ara hesaplarının salt okunur formülleri (matematiksel gösterim). compute() değişirse burası da güncellenmelidir."""
from __future__ import annotations

import re

from .model import ROW_PULSE, ROW_BIT, ROW_NULL

SYMBOLS = {
    "R": (r"$R$", "Bit Rate (kbps)"),
    "dbit": (r"$\delta_{bit}$", "1 Bit Time toleransı (oran)"),
    "dhalf": (r"$\delta_{1/2}$", "½ Bit Time toleransı (oran)"),
    "Tbit": (r"$T_{bit}$", "1 Bit Time (µs)"),
    "Thalf": (r"$T_{1/2}$", "½ Bit Time (µs)"),
    "tr": (r"$t_{r}$", "Rise Time (µs)"),
    "dtr": (r"$\Delta t_{r}$", "Rise Time toleransı (±µs)"),
    "tf": (r"$t_{f}$", "Fall Time (µs)"),
    "dtf": (r"$\Delta t_{f}$", "Fall Time toleransı (±µs)"),
    "A": (r"$A$", "Receiver giriş genliği (V)"),
    "V1": (r"$V_{1}$", "One/Zero eşiği (V)"),
    "VN": (r"$V_{N}$", "Null eşiği (V)"),
    "k": (r"$k$", "Rise/Fall ölçüm oranı (%10–%90)"),
    "c": (r"$c$", "½ Bit Time referans katsayısı"),
    "Er": (r"$E_{r}$", "Rising Edge eşik etkisi (µs)"),
    "Ef": (r"$E_{f}$", "Falling Edge eşik etkisi (µs)"),
    "VIL": (r"$V_{IL}$", "FPGA VIL MAX (V)"),
    "VIH": (r"$V_{IH}$", "FPGA VIH MIN (V)"),
    "VCC": (r"$V_{CC}$", "Receiver besleme gerilimi (V)"),
    "v": (r"$v$", "FPGA giriş eşiğinin VCC'ye oranı"),
    "tplh": (r"$t_{PLH}$", "Receiver Propagation Delay (ns)"),
    "tphl": (r"$t_{PHL}$", "Receiver Propagation Delay (ns)"),
    "trr": (r"$t_{rr}$", "Output Transition Time, Low → High (ns)"),
    "tfr": (r"$t_{fr}$", "Output Transition Time, High → Low (ns)"),
    "Dr": (r"$D_{r}$", "Rising Edge gecikmesi (µs)"),
    "Df": (r"$D_{f}$", "Falling Edge gecikmesi (µs)"),
    "P": (r"$P$", "FPGA'da görülen Pulse süresi (µs)"),
    "B": (r"$B$", "Receiver çıkışı Bit Time (µs)"),
    "N": (r"$N$", "Receiver çıkışı Null süresi (µs)"),
    "eps": (r"$\varepsilon$", "Test toleransı (oran)"),
    "f": (r"$f$", "System Clock (MHz)"),
    "ppm": (r"$ppm$", "System Clock toleransı (±ppm)"),
    "C": (r"$C$", "Clock sayısı (clk)"),
    "r": (r"$r$", "Glitch Filter oranı"),
    "g": (r"$g$", "İzin verilen MAX Glitch oranı"),
    "pmin": ("Pmin", "Min Pulse durumunda kullanılan değer (en küçük değer anlamına gelmez)"),
    "pmax": ("Pmax", "Max Pulse durumunda kullanılan değer (en büyük değer anlamına gelmez)"),
}

_FLOOR = r"\lfloor {} \rfloor"
_CEIL = r"\lceil {} \rceil"
_F_LOW = r"f\,\left(1 - \frac{ppm}{10^{6}}\right)"
_F_HIGH = r"f\,\left(1 + \frac{ppm}{10^{6}}\right)"


def _duration(sym, x, low):
    """Test toleransı ve clock ppm eklenmiş Min/Max süre formülü."""
    tag, sign = ("MIN", "-") if low else ("MAX", "+")
    prime = rf"{x}'_{{{tag}}}"
    rounded = (_FLOOR if low else _CEIL).format(rf"{prime} \cdot {_F_LOW if low else _F_HIGH}")
    return ([rf"${prime} = {x}_{{{tag}}}\,(1 {sign} \varepsilon)$   [µs]",
             rf"$C_{{{sym},{tag}}} = {rounded}$   [clk]"],
            [x, "eps", "f", "ppm", "C"])


_T = {
    "Bit Rate (kbps)": (["$R_{MIN},\\ R_{NOM},\\ R_{MAX}$ : seçili RX profilindeki değerler"], ["R"]),
    "1 Bit Time (µs)": ([r"$T_{bit,MIN} = \frac{1000}{R_{MAX}}\,(1 - \delta_{bit})$",
                         r"$T_{bit,NOM} = \frac{1000}{R_{NOM}}$",
                         r"$T_{bit,MAX} = \frac{1000}{R_{MIN}}\,(1 + \delta_{bit})$"], ["Tbit", "R", "dbit"]),
    "½ Bit Time (µs)": ([r"$T_{1/2,MIN} = \frac{1000}{2\,R_{MAX}}\,(1 - \delta_{1/2})$",
                         r"$T_{1/2,NOM} = \frac{T_{bit,NOM}}{2}$",
                         r"$T_{1/2,MAX} = \frac{1000}{2\,R_{MIN}}\,(1 + \delta_{1/2})$"], ["Thalf", "Tbit", "R", "dhalf"]),
    "Rise Time (µs)": ([r"$t_{r,MIN} = t_{r,NOM} - \Delta t_{r}$", r"$t_{r,MAX} = t_{r,NOM} + \Delta t_{r}$"], ["tr", "dtr"]),
    "Fall Time (µs)": ([r"$t_{f,MIN} = t_{f,NOM} - \Delta t_{f}$", r"$t_{f,MAX} = t_{f,NOM} + \Delta t_{f}$"], ["tf", "dtf"]),
    "Receiver giriş genliği A (V)": (["$A_{MIN},\\ A_{MAX}$ : seçili RX profilindeki değerler"], ["A"]),
    "Rising Edge eşik etkisi (µs)": (
        [r"$x_{1} = \frac{V_{1,MAX}}{A_{MIN}} - c \qquad x_{2} = \frac{V_{1,MIN}}{A_{MAX}} - c$",
         r"$c = 0$ (ARINC referansı)   ·   $c = 0.5$ (%50 referansı)",
         r"$E_{r,MIN} = \min\left(\frac{-x_{1}\,t_{r,MIN}}{k},\ \frac{-x_{1}\,t_{r,MAX}}{k}\right)$",
         r"$E_{r,NOM} = \frac{-x_{N}\,t_{r,NOM}}{k} \qquad x_{N} = \frac{V_{1,NOM}}{10\,V} - c$",
         r"$E_{r,MAX} = \max\left(\frac{-x_{2}\,t_{r,MIN}}{k},\ \frac{-x_{2}\,t_{r,MAX}}{k}\right)$"],
        ["Er", "V1", "A", "c", "tr", "k"]),
    "Falling Edge eşik etkisi (µs)": (
        [r"$y_{1} = c - \frac{V_{N,MAX}}{A_{MIN}} \qquad y_{2} = c - \frac{V_{N,MIN}}{A_{MAX}}$",
         r"$c = 1$ (ARINC referansı)   ·   $c = 0.5$ (%50 referansı)",
         r"$E_{f,MIN} = \min\left(\frac{y_{1}\,t_{f,MIN}}{k},\ \frac{y_{1}\,t_{f,MAX}}{k}\right)$",
         r"$E_{f,NOM} = \frac{y_{N}\,t_{f,NOM}}{k} \qquad y_{N} = c - \frac{V_{N,NOM}}{10\,V}$",
         r"$E_{f,MAX} = \max\left(\frac{y_{2}\,t_{f,MIN}}{k},\ \frac{y_{2}\,t_{f,MAX}}{k}\right)$"],
        ["Ef", "VN", "A", "c", "tf", "k"]),
    "FPGA giriş eşiği v = Vt / VCC (alt / NOM / üst)": (
        [r"$v_{low} = \frac{V_{IL}}{V_{CC,MAX}}$", r"$v_{NOM} = \frac{V_{IL} + V_{IH}}{2\,V_{CC,NOM}}$",
         r"$v_{high} = \frac{V_{IH}}{V_{CC,MIN}}$"], ["v", "VIL", "VIH", "VCC"]),
    "Rising Edge gecikmesi: Receiver giriş eşiği → FPGA (µs)": (
        [r"$G_{r}(t_{P}, t, v) = \max\left(t_{P},\ \frac{0.5\,t}{0.8}\right) + \frac{(v - 0.5)\,t}{0.8}$   [ns]",
         r"$D_{r,Pmin}$ = $t_{rr}$ MIN ve MAX uçlarında $G_{r}(t_{PLH,MAX},\ t,\ v_{high})$ değerlerinin en büyüğü",
         r"$D_{r,NOM} = G_{r}(t_{PLH,NOM},\ t_{rr,NOM},\ v_{NOM})$",
         r"$D_{r,Pmax}$ = $t_{rr}$ aralığında $G_{r}(t_{PLH,MIN},\ t,\ v_{low})$ değerinin en küçüğü",
         "Sonuç ns'dir, 1000'e bölünerek µs yapılır."], ["Dr", "tplh", "trr", "v", "pmin", "pmax"]),
    "Falling Edge gecikmesi: Receiver giriş eşiği → FPGA (µs)": (
        [r"$G_{f}(t_{P}, t, v) = \max\left(t_{P},\ \frac{0.5\,t}{0.8}\right) + \frac{(0.5 - v)\,t}{0.8}$   [ns]",
         r"$D_{f,Pmin}$ = $t_{fr}$ aralığında $G_{f}(t_{PHL,MIN},\ t,\ v_{high})$ değerinin en küçüğü",
         r"$D_{f,NOM} = G_{f}(t_{PHL,NOM},\ t_{fr,NOM},\ v_{NOM})$",
         r"$D_{f,Pmax}$ = $t_{fr}$ MIN ve MAX uçlarında $G_{f}(t_{PHL,MAX},\ t,\ v_{low})$ değerlerinin en büyüğü",
         "Sonuç ns'dir, 1000'e bölünerek µs yapılır."], ["Df", "tphl", "tfr", "v", "pmin", "pmax"]),
    ROW_PULSE: ([r"$P_{MIN} = T_{1/2,MIN} + E_{r,MIN} + E_{f,MIN} + D_{f,Pmin} - D_{r,Pmin}$",
                 r"$P_{NOM} = T_{1/2,NOM} + E_{r,NOM} + E_{f,NOM} + D_{f,NOM} - D_{r,NOM}$",
                 r"$P_{MAX} = T_{1/2,MAX} + E_{r,MAX} + E_{f,MAX} + D_{f,Pmax} - D_{r,Pmax}$"],
                ["P", "Thalf", "Er", "Ef", "Df", "Dr", "pmin", "pmax"]),
    ROW_BIT: ([r"$B_{MIN} = T_{bit,MIN} \qquad B_{NOM} = T_{bit,NOM} \qquad B_{MAX} = T_{bit,MAX}$"], ["B", "Tbit"]),
    ROW_NULL: ([r"$N_{MIN} = \max\left(0,\ B_{MIN} - P_{MAX}\right)$", r"$N_{NOM} = B_{NOM} - P_{NOM}$",
                r"$N_{MAX} = B_{MAX} - P_{MIN}$"], ["N", "B", "P"]),
    "Min Pulse": _duration("pulse", "P", True),
    "Max Pulse": _duration("pulse", "P", False),
    "Min Bit": _duration("bit", "B", True),
    "Max Bit": _duration("bit", "B", False),
    "Min Null": _duration("null", "N", True),
    "Max Null": _duration("null", "N", False),
    "Word Gap referans süresi (4 × Min Bit)": ([r"$C_{gap} = 4 \cdot C_{bit,MIN}$"], ["C"]),
    "Glitch Filter Size": ([r"Süreye oranlı:   $C_{GF} = \max\left(1,\ \lfloor C_{ref} \cdot r \rfloor\right)$",
                            r"$C_{ref}$ : seçilen referans süre (Min Pulse, Min Null veya Min Bit)",
                            r"Clock sayısı:   $C_{GF}$ = girilen değer"], ["C", "r"]),
    "Pulse Glitch referans süresi": ([r"MIN seçiliyse:   $C_{P,ref} = C_{pulse,MIN}$", r"MAX seçiliyse:   $C_{P,ref} = C_{pulse,MAX}$",
                                      r"NOM seçiliyse:   $C_{P,ref} = round\left(P_{NOM} \cdot f\right)$"], ["C", "P", "f"]),
    "Null Glitch referans süresi": ([r"MIN seçiliyse:   $C_{N,ref} = C_{null,MIN}$", r"MAX seçiliyse:   $C_{N,ref} = C_{null,MAX}$",
                                     r"NOM seçiliyse:   $C_{N,ref} = round\left(N_{NOM} \cdot f\right)$"], ["C", "N", "f"]),
    "Word Gap Glitch Error limiti": ([r"$C_{gap,err} = \lfloor C_{gap} \cdot g_{gap} \rfloor$"], ["C", "g"]),
    "Null Glitch Error limiti": ([r"$C_{null,err} = \lfloor C_{N,ref} \cdot g_{null} \rfloor$"], ["C", "g"]),
    "Pulse Glitch Error limiti": ([r"$C_{pulse,err} = \lfloor C_{P,ref} \cdot g_{pulse} \rfloor$"], ["C", "g"]),
    "Nominal Pulse": ([r"$C_{pulse,NOM} = round\left(P_{NOM} \cdot f\right)$"], ["C", "P", "f"]),
    "Nominal Bit Time": ([r"$C_{bit,NOM} = round\left(B_{NOM} \cdot f\right)$"], ["C", "B", "f"]),
    "Nominal Null": ([r"$C_{null,NOM} = C_{bit,NOM} - C_{pulse,NOM}$"], ["C"]),
}

_ROMAN = re.compile(r"_\{([A-Za-z0-9,/]+)\}")


def _upright(s):
    return _ROMAN.sub(lambda m: r"_{\mathrm{" + m.group(1) + "}}", s)


FORMULAS = {k: ([_upright(x) for x in eqs], syms) for k, (eqs, syms) in _T.items()}
DERIVED_ROWS = [("Word Gap Glitch Error limiti", "max_gap_glitch_error"), ("Null Glitch Error limiti", "max_null_glitch_error"),
                ("Pulse Glitch Error limiti", "max_pulse_glitch_error"), ("Nominal Pulse", "nom_pulse"),
                ("Nominal Bit Time", "nom_bit"), ("Nominal Null", "nom_null")]


def draw_formula(fig, key):
    """Formülü ve sembol açıklamalarını figüre çizer; (genişlik, yükseklik) inç döner."""
    eqs, syms = FORMULAS[key]
    row_eq, row_sym, margin = 0.66, 0.27, 0.22
    height = 2 * margin + 0.4 + row_eq * len(eqs) + 0.36 + row_sym * len(syms)
    width = 10.5
    fig.clear(); fig.set_size_inches(width, height); fig.patch.set_facecolor("white")
    y = height - margin
    add = lambda x, text, **kw: fig.text(x / width, y / height, text, va="center", **kw)
    y -= 0.14
    add(0.3, key, fontsize=13, fontweight="bold", color="#1F3864")
    y -= 0.32
    for line in eqs:
        y -= row_eq / 2
        add(0.5, line, fontsize=15, color="black")
        y -= row_eq / 2
    y -= 0.18
    add(0.3, "Semboller", fontsize=11, fontweight="bold", color="#1F3864")
    y -= 0.14
    for s in syms:
        y -= row_sym / 2
        math, text = SYMBOLS[s]
        add(0.5, _upright(math), fontsize=11, color="black")
        add(1.25, text, fontsize=10.5, color="#404040")
        y -= row_sym / 2
    return width, height
