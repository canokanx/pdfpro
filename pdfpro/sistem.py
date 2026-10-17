# -*- coding: utf-8 -*-
"""
PDF PRO - Windows ile tumlesme
- "Birlikte ac" listesine ve sag tik menusune "PDF PRO ile ac" eklenir (yonetici izni gerekmez, HKCU).
- Ayarlar > Varsayilan uygulamalar'da PDF PRO secilebilir hale gelir.
- Tek pencere: program aciksa yeni acilan dosyalar mevcut pencerede yeni sekme olarak acilir.
"""
import json
import os
import socket
import sys
import time

WINDOWS = sys.platform.startswith("win")
PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGID = "PDFPRO.Belge"
UZANTILAR = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]
PORT = 47917


# ------------------------------------------------------------------ kayit
def pythonw_yolu():
    gercek = os.environ.get("PDFPRO_PYTHONW", "")
    if gercek and os.path.isfile(gercek):
        return gercek
    exe = sys.executable or ""
    klasor = os.path.dirname(exe)
    for ad in ("pythonw.exe", "pythonw3.exe"):
        y = os.path.join(klasor, ad)
        if os.path.isfile(y):
            return y
    return exe


BASLATICI = os.path.join(PROGRAM_KLASORU, "PDF_PRO.exe")


def komut_satiri():
    """PDF_PRO.exe (kendi simgesi ve 'PDF PRO' adiyla gorunur) varsa onu, yoksa pythonw'yu kullanir."""
    if os.path.isfile(BASLATICI):
        return f'"{BASLATICI}" "%1"'
    betik = os.path.join(PROGRAM_KLASORU, "PDF_PRO.pyw")
    return f'"{pythonw_yolu()}" "{betik}" "%1"'


def python_yolunu_yaz():
    """PDF_PRO.exe hangi Python'u calistiracagini bu dosyadan okur."""
    y = os.path.join(PROGRAM_KLASORU, "python_yolu.txt")
    pw = pythonw_yolu()
    try:
        if os.path.isfile(y):
            with open(y, encoding="utf-8-sig") as f:
                if f.read().strip() == pw:
                    return
        with open(y, "w", encoding="utf-8") as f:
            f.write(pw)
    except OSError:
        pass


def _yaz(winreg, yol, deger=None, ad=""):
    k = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, yol, 0, winreg.KEY_WRITE)
    try:
        if deger is not None:
            winreg.SetValueEx(k, ad, 0, winreg.REG_SZ, deger)
    finally:
        winreg.CloseKey(k)


def _oku(winreg, yol, ad=""):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol)
        try:
            return winreg.QueryValueEx(k, ad)[0]
        finally:
            winreg.CloseKey(k)
    except OSError:
        return None


KAYIT_SURUM = "3"


def _sil(winreg, yol):
    """Anahtari alt anahtarlariyla birlikte siler (yoksa sessiz gecer)."""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, yol, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    try:
        while True:
            try:
                alt = winreg.EnumKey(k, 0)
            except OSError:
                break
            _sil(winreg, yol + "\\" + alt)
    finally:
        winreg.CloseKey(k)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, yol)
    except OSError:
        pass


def kayitli_mi():
    if not WINDOWS:
        return True
    import winreg
    return (_oku(winreg, rf"Software\Classes\{PROGID}\shell\open\command") == komut_satiri()
            and _oku(winreg, rf"Software\Classes\{PROGID}", "PDFPRO_KayitSurum") == KAYIT_SURUM)


# ------------------------------------------------------------------ Dosya Gezgini onizlemesi
ONIZLEME_KUCUK = "{4F2266AF-4870-4AD7-B002-F50753535A14}"     # kucuk resim (simge yerine ilk sayfa)
ONIZLEME_BOLME = "{099B1E91-513E-4084-9351-358406A52166}"     # onizleme bolmesi (Alt+P)
SHELLEX_KUCUK = "{e357fccd-a995-4576-b01f-234630154e96}"
SHELLEX_BOLME = "{8895b1c6-b41f-4c1c-a562-0d564250836f}"
PREVHOST_APPID = "{6d2b5079-2f0b-48dd-ab7f-97cec514d30b}"


def _onizleme_dll_hedefi():
    import hashlib
    kaynak = os.path.join(PROGRAM_KLASORU, "onizleme.dll")
    if not os.path.isfile(kaynak):
        return None
    with open(kaynak, "rb") as f:
        ozet = hashlib.md5(f.read()).hexdigest()[:10]
    hedef_klasor = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PDFPRO")
    return os.path.join(hedef_klasor, f"onizleme_{ozet}.dll")


def _onizleme_dll_kopyasi():
    """onizleme.dll Explorer tarafindan kilitlenir; guncellemeler takilmasin diye
    %LOCALAPPDATA%/PDFPRO altina icerigine gore adlandirilmis bir kopyasi kaydedilir."""
    import shutil
    kaynak = os.path.join(PROGRAM_KLASORU, "onizleme.dll")
    hedef = _onizleme_dll_hedefi()
    if not hedef:
        return None
    hedef_klasor = os.path.dirname(hedef)
    os.makedirs(hedef_klasor, exist_ok=True)
    if not os.path.isfile(hedef):
        shutil.copyfile(kaynak, hedef)
        for ad in os.listdir(hedef_klasor):        # eski kopyalar (kullanimda degilse) silinsin
            if ad.startswith("onizleme_") and ad.endswith(".dll") and ad != os.path.basename(hedef):
                try:
                    os.remove(os.path.join(hedef_klasor, ad))
                except OSError:
                    pass
    return hedef


def _onizleme_ilisikleri():
    c = r"Software\Classes"
    return [rf"{c}\.pdf", rf"{c}\{PROGID}", rf"{c}\SystemFileAssociations\.pdf", rf"{c}\Applications\PDF_PRO.exe"]


def onizleme_kayitli_mi():
    if not WINDOWS:
        return True
    import winreg
    beklenen = _onizleme_dll_hedefi()
    if not beklenen:
        return True               # bu kurulumda onizleme.dll yok
    dll = _oku(winreg, rf"Software\Classes\CLSID\{ONIZLEME_KUCUK}\InprocServer32")
    return (bool(dll) and os.path.normcase(dll) == os.path.normcase(beklenen) and os.path.isfile(dll)
            and _oku(winreg, rf"Software\Classes\CLSID\{ONIZLEME_BOLME}\InprocServer32") == dll
            and _oku(winreg, r"Software\IRONHULL\PDFPRO", "Program") == PROGRAM_KLASORU
            and _oku(winreg, rf"Software\Classes\{PROGID}\ShellEx\{SHELLEX_KUCUK}") == ONIZLEME_KUCUK)


def onizleme_kaydet():
    """Dosya Gezgini'nde PDF simgesi yerine ilk sayfa + onizleme bolmesinde sayfalar."""
    if not WINDOWS:
        return False
    import winreg
    dll = _onizleme_dll_kopyasi()
    if not dll:
        return False
    _yaz(winreg, r"Software\IRONHULL\PDFPRO", PROGRAM_KLASORU, "Program")
    c = r"Software\Classes\CLSID"
    _yaz(winreg, rf"{c}\{ONIZLEME_KUCUK}", "PDF PRO Küçük Resim")
    _yaz(winreg, rf"{c}\{ONIZLEME_KUCUK}\InprocServer32", dll)
    _yaz(winreg, rf"{c}\{ONIZLEME_KUCUK}\InprocServer32", "Apartment", "ThreadingModel")
    _yaz(winreg, rf"{c}\{ONIZLEME_BOLME}", "PDF PRO Önizleme")
    _yaz(winreg, rf"{c}\{ONIZLEME_BOLME}", "PDF PRO Önizleme", "DisplayName")
    _yaz(winreg, rf"{c}\{ONIZLEME_BOLME}", PREVHOST_APPID, "AppID")
    _yaz(winreg, rf"{c}\{ONIZLEME_BOLME}\InprocServer32", dll)
    _yaz(winreg, rf"{c}\{ONIZLEME_BOLME}\InprocServer32", "Apartment", "ThreadingModel")
    _yaz(winreg, r"Software\Microsoft\Windows\CurrentVersion\PreviewHandlers", "PDF PRO Önizleme", ONIZLEME_BOLME)
    for yol in _onizleme_ilisikleri():
        _yaz(winreg, rf"{yol}\ShellEx\{SHELLEX_KUCUK}", ONIZLEME_KUCUK)
        _yaz(winreg, rf"{yol}\ShellEx\{SHELLEX_BOLME}", ONIZLEME_BOLME)
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except Exception:
        pass
    return True


def onizleme_kaldir():
    if not WINDOWS:
        return
    import winreg
    for yol in _onizleme_ilisikleri():
        _sil(winreg, rf"{yol}\ShellEx\{SHELLEX_KUCUK}")
        _sil(winreg, rf"{yol}\ShellEx\{SHELLEX_BOLME}")
    _sil(winreg, rf"Software\Classes\CLSID\{ONIZLEME_KUCUK}")
    _sil(winreg, rf"Software\Classes\CLSID\{ONIZLEME_BOLME}")
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\PreviewHandlers",
                           0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(k, ONIZLEME_BOLME)
        winreg.CloseKey(k)
    except OSError:
        pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def kaydet():
    """Windows'a PDF PRO'yu tanitir. Dondurur: True/False."""
    if not WINDOWS:
        return False
    import winreg
    python_yolunu_yaz()
    komut = komut_satiri()
    simge = os.path.join(PROGRAM_KLASORU, "simge.ico")
    if os.path.isfile(BASLATICI):
        simge = BASLATICI + ",0"
    c = r"Software\Classes"
    _yaz(winreg, rf"{c}\{PROGID}", "PDF Belgesi (PDF PRO)")
    _yaz(winreg, rf"{c}\{PROGID}", "PDF Belgesi", "FriendlyTypeName")
    _yaz(winreg, rf"{c}\{PROGID}\DefaultIcon", simge)
    _yaz(winreg, rf"{c}\{PROGID}\shell", "open")
    _yaz(winreg, rf"{c}\{PROGID}\shell\open", "PDF PRO ile aç")
    _yaz(winreg, rf"{c}\{PROGID}\shell\open", "PDF PRO", "FriendlyAppName")
    _yaz(winreg, rf"{c}\{PROGID}\shell\open", simge, "Icon")
    _yaz(winreg, rf"{c}\{PROGID}\shell\open\command", komut)
    # "Birlikte ac" listesinde gorunen ad ve simge
    _yaz(winreg, rf"{c}\{PROGID}\Application", "PDF PRO", "ApplicationName")
    _yaz(winreg, rf"{c}\{PROGID}\Application", simge, "ApplicationIcon")
    _yaz(winreg, rf"{c}\{PROGID}\Application", "IRONHULL", "ApplicationCompany")
    _yaz(winreg, rf"{c}\{PROGID}\Application", "PDF düzenleme, birleştirme, OCR, dönüştürme", "ApplicationDescription")
    _yaz(winreg, rf"{c}\{PROGID}", KAYIT_SURUM, "PDFPRO_KayitSurum")
    # Windows'un program adi onbellegi (eski / bos ad kalmasin)
    if os.path.isfile(BASLATICI):
        mui = r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
        _yaz(winreg, mui, "PDF PRO", BASLATICI + ".FriendlyAppName")
        _yaz(winreg, mui, "IRONHULL", BASLATICI + ".ApplicationCompany")
    _sil(winreg, rf"{c}\Applications\PDF_PRO.pyw")      # eski surumden kalan kayit
    # uygulama kaydi ("Birlikte ac > Baska uygulama sec" listesinde ad ve simge)
    uyg = rf"{c}\Applications\PDF_PRO.exe"
    _yaz(winreg, uyg, "PDF PRO", "FriendlyAppName")
    _yaz(winreg, uyg, "IRONHULL", "ApplicationCompany")
    _yaz(winreg, rf"{uyg}\DefaultIcon", simge)
    _yaz(winreg, rf"{uyg}\shell\open\command", komut)
    for uz in UZANTILAR:
        _yaz(winreg, rf"{c}\{uz}\OpenWithProgids", "", PROGID)
        _yaz(winreg, rf"{uyg}\SupportedTypes", "", uz)
        # sag tik menusunde dogrudan "PDF PRO ile ac"
        _yaz(winreg, rf"{c}\SystemFileAssociations\{uz}\shell\PDFPRO", "PDF PRO ile aç")
        _yaz(winreg, rf"{c}\SystemFileAssociations\{uz}\shell\PDFPRO", simge, "Icon")
        _yaz(winreg, rf"{c}\SystemFileAssociations\{uz}\shell\PDFPRO\command", komut)
    # Ayarlar > Varsayilan uygulamalar
    cap = r"Software\PDFPRO\Capabilities"
    _yaz(winreg, cap, "PDF PRO", "ApplicationName")
    _yaz(winreg, cap, "PDF düzenleme, birleştirme, OCR, dönüştürme, imza", "ApplicationDescription")
    _yaz(winreg, cap, simge, "ApplicationIcon")
    for uz in UZANTILAR:
        _yaz(winreg, rf"{cap}\FileAssociations", PROGID, uz)
    _yaz(winreg, r"Software\RegisteredApplications", cap, "PDF PRO")
    try:
        onizleme_kaydet()
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except Exception:
        pass
    try:  # simge onbellegini yenile (eski Python simgesi kalmasin)
        import subprocess
        subprocess.Popen(["ie4uinit.exe", "-show"], creationflags=0x08000000)
    except Exception:
        pass
    return True


def kisayol_guncelle():
    """Masaustu kisayolu PDF_PRO.exe'yi gostersin (simge ve ad dogru gorunsun)."""
    if not (WINDOWS and os.path.isfile(BASLATICI)):
        return
    try:
        import win32com.client
        kabuk = win32com.client.Dispatch("WScript.Shell")
        yol = os.path.join(kabuk.SpecialFolders("Desktop"), "PDF PRO.lnk")
        if not os.path.isfile(yol):
            return
        k = kabuk.CreateShortcut(yol)
        if os.path.normcase(k.TargetPath) == os.path.normcase(BASLATICI):
            return
        k.TargetPath = BASLATICI
        k.Arguments = ""
        k.WorkingDirectory = PROGRAM_KLASORU
        k.IconLocation = BASLATICI + ",0"
        k.Save()
    except Exception:
        pass


def gerekiyorsa_kaydet():
    kisayol_guncelle()
    try:
        if WINDOWS and not os.path.isfile(os.path.join(PROGRAM_KLASORU, "onizleme_kapali.txt")) \
                and not onizleme_kayitli_mi():
            onizleme_kaydet()
    except Exception:
        pass
    if os.path.isfile(os.path.join(PROGRAM_KLASORU, "windows_kayit_kapali.txt")):
        return          # kurulumda "PDF PRO ile ac" istenmedi
    try:
        if WINDOWS:
            python_yolunu_yaz()
        if WINDOWS and not kayitli_mi():
            kaydet()
    except Exception:
        pass


def varsayilan_ayarlari_ac():
    """Windows varsayilan uygulama ayarlarini PDF PRO sayfasinda acar."""
    if not WINDOWS:
        return
    for adres in ("ms-settings:defaultapps?registeredAppUser=PDF%20PRO", "ms-settings:defaultapps"):
        try:
            os.startfile(adres)
            return
        except Exception:
            continue


# ------------------------------------------------------------------ tek pencere
def tek_ornek(yollar):
    """Dondurur: dinleme soketi (bu ilk pencere), None (dosyalar acik pencereye gonderildi, cik)
    veya False (tek pencere calismadi, normal ac)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", PORT))
        s.listen(5)
        return s
    except OSError:
        s.close()
    for _ in range(12):
        if gonder(yollar):
            return None
        time.sleep(0.4)
    return False


def gonder(yollar):
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=2) as c:
            c.sendall((json.dumps({"pdfpro": 1, "ac": list(yollar)}) + "\n").encode("utf-8"))
            return c.recv(16).startswith(b"OK")
    except OSError:
        return False


def dinle(sok, geri_cagir):
    """Arka planda gelen 'ac' isteklerini geri_cagir(yollar) ile iletir."""
    import threading

    def dongu():
        while True:
            try:
                c, _ = sok.accept()
            except OSError:
                return
            try:
                c.settimeout(3)
                veri = b""
                while not veri.endswith(b"\n") and len(veri) < 1_000_000:
                    p = c.recv(65536)
                    if not p:
                        break
                    veri += p
                m = json.loads(veri.decode("utf-8"))
                if m.get("pdfpro") == 1:
                    geri_cagir([y for y in m.get("ac", []) if isinstance(y, str)])
                    c.sendall(b"OK")
            except Exception:
                pass
            finally:
                try:
                    c.close()
                except Exception:
                    pass
    threading.Thread(target=dongu, daemon=True).start()
