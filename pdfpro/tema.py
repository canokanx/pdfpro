# -*- coding: utf-8 -*-
"""
PDF PRO - Gorunum: acik / koyu tema ve arayuz buyuklugu.

Koyu temada tum pencereler tek tek yeniden yazilmadan cevrilir: tkinter'in renk
secenekleri (bg, fg, fill ...) widget'a gitmeden once buradan gecer.
  * acik zeminler  -> koyu zemin       (beyaz kart -> koyu kart)
  * koyu yazilar   -> acik yazi        (siyah yazi -> beyaza yakin)
  * canli renkler (simge kareleri, vurgu renkleri) aynen kalir
  * PDF sayfasi (kagit) her zaman beyaz kalir: "#FFFFFE" rengi ve adinda "kagit" gecen widget'lar cevrilmez
Ayarlar program basinda okunur; degisiklik yeniden baslatinca uygulanir.
"""
import colorsys
import sys
import tkinter as tk
from tkinter import ttk

WINDOWS = sys.platform.startswith("win")

KOYU = False          # koyu tema acik mi
OLCEK = 1.0           # arayuz buyuklugu (yazi + simge)
KAGIT = "#FFFFFE"     # cevrilmeyen beyaz (PDF sayfasi)

BUYUKLUKLER = [("Küçük", 0.9), ("Normal", 1.0), ("Büyük", 1.15), ("Çok büyük", 1.3)]
TEMALAR = [("Açık", "acik"), ("Koyu", "koyu")]

_ARKA = {"background", "bg", "activebackground", "fieldbackground", "troughcolor", "readonlybackground",
         "disabledbackground", "selectcolor", "selectbackground", "indicatorbackground"}
_ON = {"foreground", "fg", "activeforeground", "insertbackground", "disabledforeground", "arrowcolor",
       "selectforeground", "insertcolor"}
_CIZGI = {"highlightbackground", "highlightcolor", "bordercolor", "lightcolor", "darkcolor", "outline"}

_ADLAR = {"white": (255, 255, 255), "black": (0, 0, 0), "gray": (190, 190, 190), "grey": (190, 190, 190),
          "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0)}
_onbellek = {}
_kok = None
_kurulu = False


def px(n):
    """Piksel olcusunu arayuz buyuklugune gore ayarla."""
    return int(round(n * OLCEK))


# ------------------------------------------------------------------ renk donusumu
def _rgb(renk):
    r = renk.strip()
    if r.startswith("#"):
        h = r[1:]
        if len(h) == 3:
            return tuple(int(c * 2, 16) for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if len(h) == 12:
            return tuple(int(h[i:i + 4], 16) // 257 for i in (0, 4, 8))
        return None
    a = r.lower()
    if a in _ADLAR:
        return _ADLAR[a]
    if _kok is not None:
        try:
            return tuple(v // 257 for v in _kok.winfo_rgb(r))
        except Exception:
            return None
    return None


def _hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return "#%02x%02x%02x" % (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))


def cevir(renk, rol="arka"):
    """Acik temaya gore yazilmis bir rengi koyu temadaki karsiligina cevirir."""
    if not KOYU or not isinstance(renk, str) or not renk or renk.upper() == KAGIT:
        return renk
    anahtar = (renk, rol)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    rgb = _rgb(renk)
    if rgb is None:
        _onbellek[anahtar] = renk
        return renk
    h, l, s = colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))
    sonuc = renk
    if rol == "arka":
        if l >= 0.78:
            yeni_l = 0.105 + (1 - l) * 0.55
            if s < 0.12:
                h, s2 = 0.62, 0.10          # beyaz / gri -> hafif mavimsi koyu gri
            else:
                s2 = s * 0.35
            sonuc = _hex(h, yeni_l, s2)
    elif rol == "on":
        if l <= 0.5 and s <= 0.65:
            sonuc = _hex(h, 0.95 - l * 0.55, s * 0.6)
    elif rol == "cizgi":
        if l >= 0.70:
            sonuc = _hex(h if s >= 0.12 else 0.62, 0.20 + (1 - l) * 0.4, s * 0.3 if s >= 0.12 else 0.08)
    _onbellek[anahtar] = sonuc
    return sonuc


def _rol(anahtar, widget=None):
    if anahtar in _ARKA:
        return "arka"
    if anahtar in _ON:
        return "on"
    if anahtar in _CIZGI:
        return "cizgi"
    if anahtar == "fill":
        tur = getattr(widget, "_tema_tur", None)
        return "on" if tur == "text" else "arka"
    return None


def _cnf_cevir(widget, cnf):
    if not cnf:
        return cnf
    try:
        if "kagit" in str(getattr(widget, "_w", "")):
            return cnf
    except Exception:
        pass
    yeni = {}
    for k, v in cnf.items():
        rol = _rol(k, widget) if isinstance(v, str) else None
        yeni[k] = cevir(v, rol) if rol else v
    return yeni


# ------------------------------------------------------------------ tkinter'a baglanma
def _yamala():
    global _kurulu
    if _kurulu:
        return
    _kurulu = True
    orj_options = tk.Misc._options

    def _options(self, cnf, kw=None):
        if KOYU:
            if kw:
                cnf = tk._cnfmerge((cnf, kw))
            elif cnf:
                cnf = tk._cnfmerge(cnf)
            kw = None
            if isinstance(cnf, dict):
                cnf = _cnf_cevir(self, cnf)
        return orj_options(self, cnf, kw)
    tk.Misc._options = _options

    orj_create = tk.Canvas._create

    def _create(self, itemType, args, kw):
        onceki = getattr(self, "_tema_tur", None)
        self._tema_tur = itemType
        try:
            return orj_create(self, itemType, args, kw)
        finally:
            self._tema_tur = onceki
    tk.Canvas._create = _create

    orj_itemconfigure = tk.Canvas.itemconfigure

    def itemconfigure(self, tagOrId, cnf=None, **kw):
        if KOYU and (cnf or kw):
            try:
                self._tema_tur = self.type(tagOrId)
            except tk.TclError:
                self._tema_tur = None
            try:
                return orj_itemconfigure(self, tagOrId, cnf, **kw)
            finally:
                self._tema_tur = None
        return orj_itemconfigure(self, tagOrId, cnf, **kw)
    tk.Canvas.itemconfigure = itemconfigure
    tk.Canvas.itemconfig = itemconfigure

    orj_configure = ttk.Style.configure
    orj_map = ttk.Style.map

    def s_configure(self, style, query_opt=None, **kw):
        if KOYU and kw:
            kw = {k: (cevir(v, _rol(k)) if isinstance(v, str) and _rol(k) else v) for k, v in kw.items()}
        return orj_configure(self, style, query_opt, **kw)

    def s_map(self, style, query_opt=None, **kw):
        if KOYU and kw:
            yeni = {}
            for k, v in kw.items():
                rol = _rol(k)
                if rol and isinstance(v, (list, tuple)):
                    v = [tuple(x[:-1]) + (cevir(x[-1], rol),) if isinstance(x, (list, tuple)) and x
                         and isinstance(x[-1], str) else x for x in v]
                yeni[k] = v
            kw = yeni
        return orj_map(self, style, query_opt, **kw)
    ttk.Style.configure = s_configure
    ttk.Style.map = s_map


def baslat(ayar):
    """Program basinda, ilk pencereden ONCE cagrilir."""
    global KOYU, OLCEK
    KOYU = ayar.get("tema", "acik") == "koyu"
    try:
        OLCEK = float(ayar.get("arayuz_olcek", 1.0))
    except (TypeError, ValueError):
        OLCEK = 1.0
    OLCEK = max(0.8, min(1.5, OLCEK))
    _onbellek.clear()
    _yamala()


def kok_hazir(kok):
    """Ilk Tk penceresi olusunca: olcek, koyu baslik cubugu, acilir liste renkleri."""
    global _kok
    _kok = kok
    if OLCEK != 1.0:
        try:
            taban = kok.winfo_fpixels("1i") / 72.0
            kok.tk.call("tk", "scaling", taban * OLCEK)
        except tk.TclError:
            pass
    if KOYU:
        # renk verilmeden olusturulan widget'lar (Text, Listbox, Toplevel ...) da koyu olsun
        for ad, deger in (("*Background", cevir("white")), ("*Foreground", cevir("#111827", "on")),
                          ("*activeBackground", cevir("#F3F4F6")), ("*activeForeground", cevir("#111827", "on")),
                          ("*highlightBackground", cevir("white")), ("*insertBackground", cevir("#111827", "on")),
                          ("*selectColor", cevir("white")), ("*troughColor", cevir("#E5E7EB")),
                          ("*disabledForeground", "#6B7280"), ("*selectBackground", "#4F46E5"),
                          ("*selectForeground", "white")):
            kok.option_add(ad, deger)
        kok.configure(bg=cevir("white"))
        kok.option_add("*TCombobox*Listbox.background", cevir("white"))
        kok.option_add("*TCombobox*Listbox.foreground", cevir("#111827", "on"))
        kok.option_add("*TCombobox*Listbox.selectBackground", "#4F46E5")
        kok.option_add("*TCombobox*Listbox.selectForeground", "white")
        kok.option_add("*Menu.background", cevir("white"))
        kok.option_add("*Menu.foreground", cevir("#111827", "on"))
        kok.option_add("*Menu.activeBackground", "#4F46E5")
        kok.option_add("*Menu.activeForeground", "white")
        kok.bind_class("Toplevel", "<Map>", lambda e: koyu_baslik(e.widget), add="+")
        kok.after(50, lambda: koyu_baslik(kok))


def koyu_baslik(pencere):
    """Windows 10/11: pencerenin baslik cubugunu da koyu yap."""
    if not (KOYU and WINDOWS):
        return
    try:
        if pencere.winfo_toplevel() is not pencere:
            return
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(pencere.winfo_id()) or pencere.winfo_id()
        deger = ctypes.c_int(1)
        for nitelik in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (yeni / eski Windows)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, nitelik, ctypes.byref(deger),
                                                          ctypes.sizeof(deger)) == 0:
                break
    except Exception:
        pass
