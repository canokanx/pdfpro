# -*- coding: utf-8 -*-
"""PDF PRO - baslatici"""
import os
import sys

KLASOR = os.path.dirname(os.path.abspath(__file__))

# Dosya Gezgini onizleme eklentisi (onizleme.dll) sayfa resmi istiyor: pencere acmadan ciz ve cik
if len(sys.argv) > 1 and sys.argv[1] == "--onizle":
    os.environ.pop("PDFPRO_GOMULU", None)
    sys.path.insert(0, KLASOR)
    from pdfpro import onizleme
    sys.exit(onizleme.main(sys.argv[2:]))

# PDF_PRO.exe Python'u kendi icinde calistirdiysa (Gorev Yoneticisi'nde "PDF PRO" gorunsun diye):
# sys.executable gercek pythonw'yu gostersin (pip kurulumu vb. icin)
if os.environ.pop("PDFPRO_GOMULU", "") == "1":
    _gercek = os.environ.get("PDFPRO_PYTHONW", "")
    os.environ.pop("PYTHONHOME", None)
    if _gercek and os.path.isfile(_gercek):
        sys.executable = _gercek
        sys._base_executable = _gercek
    try:
        import tkinter
        tkinter.Tcl()          # Tcl/Tk bu sekilde de yuklenebiliyor mu?
        try:
            if not os.path.isfile(os.path.join(KLASOR, "gomulu_ok.txt")):
                with open(os.path.join(KLASOR, "gomulu_ok.txt"), "w") as _f:
                    _f.write("ok")
        except OSError:
            pass
    except Exception:
        # olmadi: klasik yolla (ayri pythonw sureci) yeniden baslat
        import subprocess
        ortam = dict(os.environ, PDFPRO_AYRI_SUREC="1")
        subprocess.Popen([_gercek or "pythonw", os.path.abspath(__file__)] + sys.argv[1:], env=ortam, cwd=KLASOR)
        sys.exit(0)
elif (sys.platform.startswith("win") and os.environ.get("PDFPRO_AYRI_SUREC") != "1"
      and os.path.isfile(os.path.join(KLASOR, "PDF_PRO.exe")) and __name__ == "__main__"):
    # eski kisayol / pythonw ile acildi: PDF_PRO.exe uzerinden ac ki her yerde "PDF PRO" adi ve simgesi gorunsun
    try:
        import subprocess
        subprocess.Popen([os.path.join(KLASOR, "PDF_PRO.exe")] + sys.argv[1:], cwd=KLASOR)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        pass
sys.path.insert(0, KLASOR)
os.chdir(KLASOR)

if sys.platform.startswith("win"):
    try:  # net (bulanik olmayan) yazi icin
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:  # gorev cubugunda Python degil PDF PRO simgesi gorunsun
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IRONHULL.PDFPRO")
    except Exception:
        pass

if __name__ == "__main__":
    # Dosya Gezgini: sag tik > Yazdir  ->  yalnizca yazdirma penceresi
    if len(sys.argv) > 2 and sys.argv[1] == "--yazdir":
        from pdfpro import yazdir as _yazdir
        sys.exit(_yazdir.tek_basina(os.path.abspath(sys.argv[2])))
    yollar = [os.path.abspath(a) for a in sys.argv[1:] if os.path.isfile(a)]
    # program zaten aciksa dosyalari o pencerede ac (yeni pencere acma)
    sok = False
    try:
        from pdfpro import sistem
        sok = sistem.tek_ornek(yollar)
    except Exception:
        sok = False
    if sok is None:
        sys.exit(0)
    # bekleyen otomatik guncellemeyi uygula (ya da cokmus guncellemeyi geri al)
    guncelleme_mesaji = None
    try:
        from pdfpro import guncelleme
        guncelleme_mesaji = guncelleme.acilista_calistir()
        if guncelleme_mesaji:
            os.environ["PDFPRO_GUNCELLEME_MESAJI"] = guncelleme_mesaji
            gerekli = guncelleme.bagimlilik_gerekli_mi()
            if gerekli:
                guncelleme.bagimliliklari_kur_bekle(gerekli)
    except Exception:
        pass
    for _ad in [m for m in sys.modules if m.startswith("pdfpro.")]:
        del sys.modules[_ad]          # guncellenen modullerin yeni hali yuklensin
    from pdfpro.arayuz import calistir
    calistir(yollar, sok or None)
