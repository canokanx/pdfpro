# -*- coding: utf-8 -*-
"""
PDF PRO - Yazi tipleri (font) kutuphanesi
Bilgisayardaki tum fontlari (Windows\\Fonts + kullanici fontlari + programin fonts klasoru)
tarar, aile adiyla listeler ve PDF'e yazmak icin yukler. Tarama sonucu onbellege yazilir,
sonraki acilislar aninda olur.
"""
import json
import os
import sys
import threading

from .cekirdek import fitz

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONBELLEK = os.path.join(PROGRAM_KLASORU, "fontlar_onbellek.json")
WINDOWS = sys.platform.startswith("win")

_aileler = {}          # aile -> {"normal": yol, "kalin": yol, "italik": yol, "kalin_italik": yol}
_hazir = threading.Event()
_yuklu = {}            # yol -> fitz.Font

STANDART_STIL = {
    "regular": "normal", "normal": "normal", "book": "normal", "roman": "normal", "medium": None,
    "bold": "kalin", "italic": "italik", "oblique": "italik",
    "bold italic": "kalin_italik", "bold oblique": "kalin_italik", "italic bold": "kalin_italik",
}

ONERILEN = ["Arial", "Calibri", "Segoe UI", "Times New Roman", "Tahoma", "Verdana", "Georgia",
            "Cambria", "Courier New", "Trebuchet MS", "Century Gothic", "Garamond", "Book Antiqua",
            "Arial Narrow", "Segoe UI Semibold", "Bahnschrift", "Consolas", "DejaVu Sans", "DejaVu Serif",
            "Carlito", "Caladea"]


def _klasorler():
    k = [os.path.join(PROGRAM_KLASORU, "fonts")]
    if WINDOWS:
        k.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        k.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"))
    else:
        k += ["/usr/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]
    return [x for x in k if os.path.isdir(x)]


def _dosyalar():
    for kl in _klasorler():
        for kok, _, adlar in os.walk(kl):
            for ad in adlar:
                if ad.lower().endswith((".ttf", ".otf", ".ttc")):
                    yield os.path.join(kok, ad)


def _imza():
    """Font klasorlerinin degisip degismedigini anlamak icin kisa imza."""
    parcalar = []
    for kl in _klasorler():
        try:
            parcalar.append(f"{kl}:{os.path.getmtime(kl):.0f}:{len(os.listdir(kl))}")
        except Exception:
            pass
    return "|".join(parcalar)


def _tara():
    from PIL import ImageFont
    sonuc = {}
    for yol in _dosyalar():
        try:
            aile, stil = ImageFont.truetype(yol, 10).getname()
        except Exception:
            continue
        if not aile:
            continue
        s = (stil or "Regular").strip().lower()
        tur = STANDART_STIL.get(s, "")
        if tur is None or tur == "":
            # Light, Semibold, Black gibi agirliklar ayri aile olarak listelenir
            temel = s.replace("italic", "").replace("oblique", "").strip()
            aile = f"{aile} {temel.title()}".strip() if temel else aile
            tur = "italik" if ("italic" in s or "oblique" in s) else "normal"
        sonuc.setdefault(aile, {})
        sonuc[aile].setdefault(tur, yol)
    return {a: v for a, v in sonuc.items() if "normal" in v or "kalin" in v}


def baslat():
    """Arka planda tarar (onbellek gecerliyse aninda yukler)."""
    def is_():
        global _aileler
        try:
            imza = _imza()
            if os.path.isfile(ONBELLEK):
                with open(ONBELLEK, encoding="utf-8") as f:
                    v = json.load(f)
                if v.get("imza") == imza and v.get("aileler"):
                    _aileler = v["aileler"]
                    _hazir.set()
                    return
            _aileler = _tara()
            try:
                with open(ONBELLEK, "w", encoding="utf-8") as f:
                    json.dump({"imza": imza, "aileler": _aileler}, f, ensure_ascii=False)
            except Exception:
                pass
        except Exception:
            _aileler = {}
        _hazir.set()
    threading.Thread(target=is_, daemon=True).start()


def hazir():
    return _hazir.is_set()


def aileler():
    """Siralanmis aile listesi: once sik kullanilanlar, sonra alfabetik tumu."""
    tumu = sorted(_aileler, key=lambda a: a.lower())
    ust = [a for a in ONERILEN if a in _aileler]
    return ust + ["──────────"] + [a for a in tumu if a not in ust] if ust else tumu


def yol(aile, kalin=False, italik=False):
    v = _aileler.get(aile)
    if not v:
        return None
    tur = ("kalin_italik" if italik else "kalin") if kalin else ("italik" if italik else "normal")
    return v.get(tur) or v.get("kalin" if kalin else "normal") or v.get("normal") or next(iter(v.values()))


def font(aile, kalin=False, italik=False):
    """fitz.Font dondurur (bulunamazsa None). Istenen kalinlik yoksa en yakini."""
    y = yol(aile, kalin, italik)
    if not y:
        return None
    if y not in _yuklu:
        try:
            _yuklu[y] = fitz.Font(fontfile=y)
        except Exception:
            return None
    return _yuklu[y]


def harfleri_var_mi(f, metin):
    return all(c in " \n\t" or f.has_glyph(ord(c)) for c in metin)
