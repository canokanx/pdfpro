# -*- coding: utf-8 -*-
"""
Fare tekerlegi + touchpad (iki parmak) kaydirma yonlendiricisi.

Windows'ta tekerlek olayi bazen odaktaki pencereye gider, touchpad ise cok kucuk
adimlar (ya da Tk 9'da <TouchpadScroll>) uretir. Burada tum olaylar tek yerden
yakalanir, imlecin ALTINDAKI kayitli alana yonlendirilir ve kucuk adimlar biriktirilir.
"""
import tkinter as tk

BIRIM_PER_CENTIK = 3          # bir tekerlek centigi = 3 birim kaydirma
TOUCHPAD_PX_PER_CENTIK = 60   # Tk 9 TouchpadScroll: bu kadar piksel = 1 centik

_kayit = {}       # widget yolu -> fonk(dy_birim, dx_birim, zoom_adim)
_birikim = {}     # (yol, eksen) -> kesirli birikim
_kurulu = set()


def kaydet(widget, fonk):
    """widget ve tum alt pencereleri icin kaydirma islevi kaydeder.
    fonk(dy, dx, zoom): dy/dx tam sayi birim (+ asagi/saga), zoom +1/-1/0."""
    _kayit[str(widget)] = fonk
    widget.bind("<Destroy>", lambda e, y=str(widget): _kayit.pop(y, None) if e.widget is widget else None, add="+")


def canvas_kaydirici(tuval, sonra=None):
    """Bir Canvas icin hazir kaydirma islevi."""
    def fonk(dy, dx, zoom):
        if dy:
            tuval.yview_scroll(dy, "units")
        if dx:
            tuval.xview_scroll(dx, "units")
        if sonra and (dy or dx):
            sonra()
    return fonk


def _bul(w):
    while w is not None:
        f = _kayit.get(str(w))
        if f:
            return w, f
        try:
            ad = w.winfo_parent()
            w = w.nametowidget(ad) if ad else None
        except Exception:
            return None, None
    return None, None


def _birik(yol, eksen, deger):
    t = _birikim.get((yol, eksen), 0.0) + deger
    n = int(t)               # sifira dogru yuvarla
    _birikim[(yol, eksen)] = t - n
    return n


def _gonder(kok, e, cy, cx):
    """cy/cx: centik cinsinden (+ asagi / saga)."""
    try:
        w = kok.winfo_containing(e.x_root, e.y_root)
    except (tk.TclError, KeyError):
        w = None
    if w is None:
        w = e.widget if isinstance(e.widget, tk.Misc) else None
    if w is None:
        return None
    hedef, fonk = _bul(w)
    ctrl = bool(e.state & 0x0004)
    if fonk is None:
        # kayitli olmayan bir alan: imlecin altindaki liste/metin kutusu kendisi kaymiyorsa kaydir
        if w is not e.widget and cy and hasattr(w, "yview_scroll") and not ctrl:
            try:
                w.yview_scroll(int(round(cy * BIRIM_PER_CENTIK)) or (1 if cy > 0 else -1), "units")
            except tk.TclError:
                pass
            return "break"
        return None
    yol = str(hedef)
    if ctrl:
        z = _birik(yol, "z", -cy)          # yukari = yakinlas
        if z:
            fonk(0, 0, 1 if z > 0 else -1)
        return "break"
    dy = _birik(yol, "y", cy * BIRIM_PER_CENTIK) if cy else 0
    dx = _birik(yol, "x", cx * BIRIM_PER_CENTIK) if cx else 0
    if dy or dx:
        fonk(dy, dx, 0)
    return "break"


def _isaretli16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def kur(kok):
    """Uygulama basinda bir kez cagrilir (her Tk koku icin)."""
    if str(kok) in _kurulu:
        return
    _kurulu.add(str(kok))

    def teker(e):
        if not e.delta:
            return None
        c = -e.delta / 120.0
        if e.state & 0x0001:                       # Shift = yatay
            return _gonder(kok, e, 0, c)
        return _gonder(kok, e, c, 0)

    def linux(e, yon):
        if e.state & 0x0001:
            return _gonder(kok, e, 0, yon)
        return _gonder(kok, e, yon, 0)

    def touchpad(e):
        d = int(e.delta)
        dx, dy = _isaretli16(d >> 16), _isaretli16(d)
        return _gonder(kok, e, -dy / TOUCHPAD_PX_PER_CENTIK, -dx / TOUCHPAD_PX_PER_CENTIK)

    kok.bind_all("<MouseWheel>", teker)
    kok.bind_all("<Shift-MouseWheel>", teker)
    kok.bind_all("<Control-MouseWheel>", teker)
    kok.bind_all("<Button-4>", lambda e: linux(e, -1))
    kok.bind_all("<Button-5>", lambda e: linux(e, 1))
    try:
        kok.bind_all("<TouchpadScroll>", touchpad)      # Tk 9 (iki parmak kaydirma)
    except tk.TclError:
        pass
