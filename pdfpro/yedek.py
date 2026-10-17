# -*- coding: utf-8 -*-
"""
PDF PRO - Otomatik yedek
Bir dosyanin uzerine kaydetmeden once eski hali programin 'yedekler' klasorune kopyalanir.
Her dosya icin son 10 yedek tutulur; 'Yedekten Geri Yukle' ile istenen ana donulur.
"""
import datetime
import hashlib
import os
import re
import shutil

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEDEK_KLASORU = os.path.join(PROGRAM_KLASORU, "yedekler")
SAKLA = 10


def _klasor(yol):
    yol = os.path.normcase(os.path.abspath(yol))
    ad = os.path.splitext(os.path.basename(yol))[0]
    ad = re.sub(r"[^\w\-]+", "_", ad, flags=re.UNICODE)[:50] or "belge"
    return os.path.join(YEDEK_KLASORU, f"{ad}_{hashlib.md5(yol.encode('utf-8')).hexdigest()[:8]}")


def yedekle(yol, sakla=SAKLA):
    """Var olan dosyanin bir kopyasini alir. Dondurur: yedek yolu veya None."""
    if not yol or not os.path.isfile(yol):
        return None
    k = _klasor(yol)
    os.makedirs(k, exist_ok=True)
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = os.path.join(k, f"{zaman}.pdf")
    n = 2
    while os.path.exists(hedef):
        hedef = os.path.join(k, f"{zaman}_{n}.pdf")
        n += 1
    shutil.copy2(yol, hedef)
    with open(os.path.join(k, "kaynak.txt"), "w", encoding="utf-8") as f:
        f.write(os.path.abspath(yol))
    for eski in liste(yol)[sakla:]:
        try:
            os.remove(eski["yol"])
        except OSError:
            pass
    return hedef


def liste(yol):
    """Yeniden eskiye yedekler: [{'yol', 'zaman' (datetime), 'boyut'}]"""
    k = _klasor(yol)
    if not os.path.isdir(k):
        return []
    sonuc = []
    for ad in os.listdir(k):
        if not ad.lower().endswith(".pdf"):
            continue
        y = os.path.join(k, ad)
        try:
            z = datetime.datetime.strptime(ad[:15], "%Y%m%d_%H%M%S")
        except ValueError:
            z = datetime.datetime.fromtimestamp(os.path.getmtime(y))
        sonuc.append({"yol": y, "zaman": z, "boyut": os.path.getsize(y)})
    return sorted(sonuc, key=lambda s: (s["zaman"], s["yol"]), reverse=True)


def tum_yedekler():
    """Tum dosyalarin yedekleri: [{'kaynak', 'yedekler': [...]}]"""
    if not os.path.isdir(YEDEK_KLASORU):
        return []
    sonuc = []
    for ad in os.listdir(YEDEK_KLASORU):
        k = os.path.join(YEDEK_KLASORU, ad)
        kt = os.path.join(k, "kaynak.txt")
        if not os.path.isfile(kt):
            continue
        with open(kt, encoding="utf-8") as f:
            kaynak = f.read().strip()
        ys = liste(kaynak)
        if ys:
            sonuc.append({"kaynak": kaynak, "yedekler": ys})
    return sorted(sonuc, key=lambda s: s["yedekler"][0]["zaman"], reverse=True)
