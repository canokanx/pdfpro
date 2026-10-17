# -*- coding: utf-8 -*-
"""PDF PRO surum numarasi. Yonetici 'Yayinla' dediginde otomatik artirilir."""
SURUM = "4.0.4"


def surum_tuple(s):
    """'v4.0.12' -> (4, 0, 12)"""
    parcalar = []
    for p in str(s).strip().lstrip("vV").split("."):
        sayi = "".join(c for c in p if c.isdigit())
        parcalar.append(int(sayi) if sayi else 0)
    while len(parcalar) < 3:
        parcalar.append(0)
    return tuple(parcalar[:3])
