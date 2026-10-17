# -*- coding: utf-8 -*-
"""
PDF PRO - Windows Dosya Gezgini onizleme cizici.

onizleme.dll (Explorer'in kucuk resim / onizleme bolmesi eklentisi) bu modulu
PDF_PRO.exe --onizle <pdf> <cikti_klasoru> <piksel> <en_fazla_sayfa> <kucuk|genislik>
seklinde calistirir. Her sayfa cikti klasorune sNNNN.bin olarak yazilir:
  b"PPV1" + uint32 genislik + uint32 yukseklik + uint32 satir_boyu + RGB satirlari (satir_boyu 4'un kati)
En sonda bitti.txt:  "tamam <yazilan> <toplam>" | "sifreli" | "hata <mesaj>"
"""
import os
import struct
import sys


def _yaz_atomik(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "wb") as f:
        f.write(veri)
    os.replace(gecici, yol)


def _bitti(klasor, metin):
    try:
        _yaz_atomik(os.path.join(klasor, "bitti.txt"), metin.encode("utf-8"))
    except OSError:
        pass


def sayfa_verisi(sayfa, fitz, piksel, mod):
    r = sayfa.rect
    if r.width <= 0 or r.height <= 0:
        return None
    if mod == "kucuk":
        olcek = piksel / max(r.width, r.height)
    else:
        olcek = piksel / r.width
    olcek = max(0.02, min(olcek, 8.0))
    pix = sayfa.get_pixmap(matrix=fitz.Matrix(olcek, olcek), alpha=False, colorspace=fitz.csRGB)
    w, h, kaynak_satir = pix.width, pix.height, pix.stride
    satir = (w * 3 + 3) & ~3
    ham = pix.samples
    if kaynak_satir == satir:
        govde = bytes(ham)
    else:
        dolgu = b"\0" * (satir - w * 3)
        govde = b"".join(ham[y * kaynak_satir:y * kaynak_satir + w * 3] + dolgu for y in range(h))
    return b"PPV1" + struct.pack("<III", w, h, satir) + govde


def ciz(pdf, klasor, piksel=256, en_fazla=1, mod="kucuk"):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass
    try:
        belge = fitz.open(pdf)
    except Exception as e:
        _bitti(klasor, f"hata {e}")
        return 1
    if belge.needs_pass:
        _bitti(klasor, "sifreli")
        return 0
    toplam = belge.page_count
    yazilan = 0
    for i in range(min(toplam, max(1, en_fazla))):
        if os.path.isfile(os.path.join(klasor, "dur.txt")):
            break
        try:
            veri = sayfa_verisi(belge[i], fitz, piksel, mod)
        except Exception:
            veri = None
        if veri is None:
            continue
        yazilan += 1
        _yaz_atomik(os.path.join(klasor, "s%04d.bin" % yazilan), veri)
    _bitti(klasor, f"tamam {yazilan} {toplam}")
    return 0


def main(arglar):
    try:
        pdf, klasor = arglar[0], arglar[1]
        piksel = int(arglar[2]) if len(arglar) > 2 else 256
        en_fazla = int(arglar[3]) if len(arglar) > 3 else 1
        mod = arglar[4] if len(arglar) > 4 else "kucuk"
    except (IndexError, ValueError):
        return 2
    piksel = max(16, min(piksel, 2400))
    try:
        return ciz(pdf, klasor, piksel, en_fazla, mod)
    except Exception as e:
        _bitti(klasor, f"hata {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
