# -*- coding: utf-8 -*-
"""
PDF PRO - Kurulum dosyasi (setup .exe) olusturucu  (yonetici paneli kullanir)

Tek bir PDF_PRO_Kurulum_X.exe uretir:  kurulum_stub.exe + PPAK paketi + iz
Paketin icinde:
  runtime/    bu bilgisayardaki Python (tkinter dahil) + PDF PRO'nun ihtiyac duydugu kutuphaneler
  app/        program dosyalari (kurulum sihirbazi app/kurulum/kurulum.pyw dahil)
  tesseract/  OCR motoru (bu bilgisayarda kuruluysa)
Karsi bilgisayarda internet, Python ya da KURULUM.bat gerekmez.
"""
import os
import re
import struct
import sys
import zlib

from . import guncelleme as GN

PROGRAM = GN.PROGRAM_KLASORU
STUB = os.path.join(PROGRAM, "kurulum", "kurulum_stub.exe")
IZ = b"PDFPROK1"

# Python klasorunden pakete alinmayanlar (gereksiz / buyuk)
LIB_HARIC = {"site-packages", "test", "tests", "idle_test", "__pycache__", "lib2to3", "turtledemo", "ensurepip",
             "venv", "pydoc_data"}
SIKISTIRMA_YOK = (".zip", ".png", ".jpg", ".jpeg", ".gz", ".whl", ".7z", ".ico")


def _ad(s):
    return re.sub(r"[-_.]+", "-", s).lower()


def python_klasoru():
    from . import sistem
    return os.path.dirname(sistem.pythonw_yolu())


def _gereksinimler():
    yol = os.path.join(PROGRAM, "requirements.txt")
    adlar = []
    with open(yol, encoding="utf-8") as f:
        for s in f:
            s = s.split("#")[0].strip()
            if not s:
                continue
            if ";" in s and "win32" in s and not sys.platform.startswith("win"):
                continue
            adlar.append(re.split(r"[<>=!~;\[ ]", s, 1)[0].strip())
    return adlar


def _req_ad(req):
    """'numpy>=1.2; extra == "x"' -> ('numpy', ekstra_mi)"""
    try:
        try:
            from packaging.requirements import Requirement
        except ImportError:
            from pip._vendor.packaging.requirements import Requirement
        r = Requirement(req)
        if r.marker is not None:
            try:
                if not r.marker.evaluate({"extra": ""}):
                    return None
            except Exception:
                return None
        return r.name
    except Exception:
        if "extra ==" in req:
            return None
        return re.split(r"[<>=!~;\[ (]", req, 1)[0].strip()


def kutuphane_dosyalari(ilerleme=None):
    """PDF PRO'nun kutuphaneleri ve bagimliliklari: [(tam_yol, 'runtime/Lib/site-packages/...')]"""
    from importlib import metadata
    dagitimlar = {_ad(d.metadata["Name"] or ""): d for d in metadata.distributions() if d.metadata["Name"]}
    kuyruk = [_ad(a) for a in _gereksinimler()]
    goruldu, eksik = set(), []
    while kuyruk:
        ad = kuyruk.pop()
        if ad in goruldu:
            continue
        goruldu.add(ad)
        d = dagitimlar.get(ad)
        if d is None:
            eksik.append(ad)
            continue
        for r in d.requires or []:
            n = _req_ad(r)
            if n:
                kuyruk.append(_ad(n))
    sonuc, gorulen_yol = [], set()
    for ad in sorted(goruldu):
        d = dagitimlar.get(ad)
        if d is None:
            continue
        for f in d.files or []:
            goreli = str(f).replace("\\", "/")
            if goreli.startswith("..") or "__pycache__" in goreli or goreli.endswith((".pyc", ".pyo")):
                continue
            tam = str(d.locate_file(f))
            if not os.path.isfile(tam) or tam in gorulen_yol:
                continue
            gorulen_yol.add(tam)
            sonuc.append((tam, "runtime/Lib/site-packages/" + goreli))
    return sonuc, [e for e in eksik if e not in ("pywin32",) or sys.platform.startswith("win")]


def python_dosyalari():
    """Python'un kendisi (Lib, DLLs, tcl, python.exe ...)."""
    kok = python_klasoru()
    if not os.path.isfile(os.path.join(kok, "Lib", "os.py")):
        raise GN.GuncellemeHatasi(f"Python klasörü beklenen yapıda değil:\n{kok}\n"
                                  "(python.org'dan kurulmuş standart Python gerekir.)")
    sonuc = []
    for ad in os.listdir(kok):
        tam = os.path.join(kok, ad)
        if os.path.isfile(tam) and ad.lower().endswith((".exe", ".dll", ".txt", ".pyd")):
            sonuc.append((tam, "runtime/" + ad))
    for alt in ("DLLs", "Lib", "tcl"):
        k = os.path.join(kok, alt)
        if not os.path.isdir(k):
            continue
        for d, klasorler, dosyalar in os.walk(k):
            if alt == "Lib":
                klasorler[:] = [x for x in klasorler if x not in LIB_HARIC and not (d == k and x == "site-packages")]
            klasorler[:] = [x for x in klasorler if x != "__pycache__"]
            for ad in dosyalar:
                if ad.endswith((".pyc", ".pyo")):
                    continue
                tam = os.path.join(d, ad)
                sonuc.append((tam, "runtime/" + os.path.relpath(tam, kok).replace(os.sep, "/")))
    # site-packages klasoru bos da olsa olsun (+ pywin32 icin .pth dosyalari kutuphane listesinden gelir)
    return sonuc


def tesseract_dosyalari():
    from . import ocr as O
    t = O.tesseract_bul()
    if not t:
        return []
    kok = os.path.dirname(os.path.abspath(t))
    if os.path.normcase(kok).startswith(os.path.normcase(os.path.join(PROGRAM, "tesseract"))):
        return []          # zaten program klasorunde (app ile gelir)
    sonuc = []
    for d, klasorler, dosyalar in os.walk(kok):
        rel = os.path.relpath(d, kok).replace(os.sep, "/")
        for ad in dosyalar:
            if rel.startswith("tessdata") and ad.endswith(".traineddata"):
                continue     # dil dosyalari PDF PRO'nun kendi tessdata klasorunde
            if ad.lower().startswith("unins"):
                continue
            tam = os.path.join(d, ad)
            sonuc.append((tam, "tesseract/" + os.path.relpath(tam, kok).replace(os.sep, "/")))
    return sonuc


def program_dosyalari():
    return [(tam, "app/" + goreli) for goreli, tam in GN.paket_dosyalari().items()
            if not goreli.startswith("tesseract/")]


def olustur(hedef, ilerleme=None, iptal=None, tesseract_dahil=True):
    """Kurulum .exe dosyasini yazar. Dondurur: (hedef, boyut, notlar)"""
    il = ilerleme or (lambda *a: None)
    if not os.path.isfile(STUB):
        raise GN.GuncellemeHatasi("kurulum\\kurulum_stub.exe bulunamadı.")
    il(0, 100, "Dosyalar toplanıyor")
    notlar = []
    liste = program_dosyalari() + python_dosyalari()
    kut, eksik = kutuphane_dosyalari()
    if eksik:
        notlar.append("Bu bilgisayarda bulunmayan kütüphaneler pakete giremedi: " + ", ".join(eksik))
    liste += kut
    if tesseract_dahil:
        t = tesseract_dosyalari()
        if not t:
            notlar.append("Tesseract (OCR) bu bilgisayarda bulunamadı; kurulumda OCR olmayacak.")
        liste += t
    paket_yaz(hedef, liste, il, iptal)
    return hedef, os.path.getsize(hedef), notlar


def paket_yaz(hedef, liste, il=None, iptal=None):
    """stub + PPAK paketi + iz -> hedef .exe"""
    il = il or (lambda *a: None)
    toplam = sum(os.path.getsize(t) for t, _ in liste) or 1
    gecici = hedef + ".yaziliyor"
    islenen = 0
    with open(STUB, "rb") as f:
        stub = f.read()
    with open(gecici, "wb") as c:
        c.write(stub)
        basla = c.tell()
        c.write(b"PPAK1\0\0\0" + struct.pack("<I", len(liste)))
        for k, (tam, ad) in enumerate(liste):
            if iptal and iptal():
                c.close()
                os.remove(gecici)
                raise GN.GuncellemeHatasi("İptal edildi.")
            if k % 25 == 0:
                il(islenen * 100 // toplam, 100, f"Paketleniyor: {ad[:70]}")
            with open(tam, "rb") as f:
                veri = f.read()
            if ad.lower().endswith(SIKISTIRMA_YOK) or len(veri) < 64:
                yontem, s = 0, veri
            else:
                s = zlib.compress(veri, 6)
                yontem = 1
                if len(s) >= len(veri):
                    yontem, s = 0, veri
            ad_b = ad.encode("utf-8")
            c.write(struct.pack("<H", len(ad_b)) + ad_b + struct.pack("<QQB", len(veri), len(s), yontem))
            c.write(s)
            islenen += len(veri)
        c.write(IZ + struct.pack("<Q", basla))
    os.replace(gecici, hedef)


# ------------------------------------------------------------------ GitHub'a yukleme (sabit indirme linki)
KURULUM_ETIKETI = "kurulum"
KURULUM_ADI = "PDF_PRO_Kurulum.exe"


def indirme_linki(repo):
    return f"https://github.com/{repo}/releases/download/{KURULUM_ETIKETI}/{KURULUM_ADI}"


def github_yukle(repo, token, exe_yolu, surum, ilerleme=None):
    """'kurulum' etiketli (on surum olarak isaretli; otomatik guncellemeyi etkilemez) yayina yukler."""
    il = ilerleme or (lambda *a: None)
    api = f"{GN.API}/repos/{repo}"
    try:
        rel = GN.istek(f"{api}/releases/tags/{KURULUM_ETIKETI}", token=token)
    except GN.GuncellemeHatasi as e:
        if getattr(e, "kod", 0) != 404:
            raise
        rel = GN.istek(f"{api}/releases", token=token, veri={
            "tag_name": KURULUM_ETIKETI, "name": "PDF PRO Kurulum", "prerelease": True,
            "body": "PDF PRO kurulum dosyası. İndirip çalıştırın; program sonra kendini otomatik günceller."})
    GN.istek(f"{api}/releases/{rel['id']}", token=token, yontem="PATCH",
             veri={"body": f"PDF PRO {surum} kurulum dosyası. İndirip çalıştırın; program sonra kendini "
                           f"otomatik günceller.", "prerelease": True})
    for a in rel.get("assets", []):
        if a.get("name") == KURULUM_ADI:
            GN.istek(f"{api}/releases/assets/{a['id']}", token=token, yontem="DELETE")
    il(1, 2, "GitHub'a yükleniyor (birkaç dakika sürebilir)")
    yukle = rel["upload_url"].split("{")[0]
    with open(exe_yolu, "rb") as f:
        GN.istek(f"{yukle}?name={KURULUM_ADI}", veri=f.read(), token=token,
                 basliklar={"Content-Type": "application/vnd.microsoft.portable-executable"}, zaman=3600)
    return indirme_linki(repo)
