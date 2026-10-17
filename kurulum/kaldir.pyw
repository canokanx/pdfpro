# -*- coding: utf-8 -*-
"""PDF PRO'yu kaldirir: kisayollar, Windows kayitlari ve program klasoru silinir.
Kisisel yonetici ayarlari (%APPDATA%\\PDFPRO) silinmez."""
import ctypes
import os
import subprocess
import sys

HEDEF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KALDIR_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PDF PRO"
UZANTILAR = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]


def _yazilabilir(k):
    try:
        t = os.path.join(k, ".kaldir_deneme")
        with open(t, "w") as f:
            f.write("x")
        os.remove(t)
        return True
    except OSError:
        return False


def _sil_agac(winreg, kok, yol):
    try:
        k = winreg.OpenKey(kok, yol, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    while True:
        try:
            alt = winreg.EnumKey(k, 0)
        except OSError:
            break
        _sil_agac(winreg, kok, yol + "\\" + alt)
    winreg.CloseKey(k)
    try:
        winreg.DeleteKey(kok, yol)
    except OSError:
        pass


def _deger_sil(winreg, kok, yol, ad):
    try:
        k = winreg.OpenKey(kok, yol, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(k, ad)
        winreg.CloseKey(k)
    except OSError:
        pass


def _ozel_klasor(csidl):
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return buf.value


def kaldir():
    import winreg
    import shutil
    # kisayollar (kullanici + tum kullanicilar)
    for csidl in (0x0010, 0x0019):
        try:
            os.remove(os.path.join(_ozel_klasor(csidl), "PDF PRO.lnk"))
        except OSError:
            pass
    for csidl in (0x0002, 0x0017):
        shutil.rmtree(os.path.join(_ozel_klasor(csidl), "PDF PRO"), ignore_errors=True)
    # Programlar ve Ozellikler
    for kok in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        _sil_agac(winreg, kok, KALDIR_ANAHTARI)
    # "PDF PRO ile ac" / "Birlikte ac" kayitlari (bu kullanici)
    hk = winreg.HKEY_CURRENT_USER
    c = r"Software\Classes"
    for yol in (rf"{c}\PDFPRO.Belge", rf"{c}\Applications\PDF_PRO.exe", rf"{c}\Applications\PDF_PRO.pyw", r"Software\PDFPRO"):
        _sil_agac(winreg, hk, yol)
    for uz in UZANTILAR:
        _sil_agac(winreg, hk, rf"{c}\SystemFileAssociations\{uz}\shell\PDFPRO")
        _deger_sil(winreg, hk, rf"{c}\{uz}\OpenWithProgids", "PDFPRO.Belge")
    _deger_sil(winreg, hk, r"Software\RegisteredApplications", "PDF PRO")
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass
    # program klasoru: bu surec kapandiktan sonra silinsin
    komut = f'ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{HEDEF}"'
    subprocess.Popen(["cmd", "/c", komut], creationflags=0x08000000 | 0x00000008, cwd=os.environ.get("TEMP", "C:\\"))


def main():
    import tkinter as tk
    from tkinter import messagebox
    k = tk.Tk()
    k.withdraw()
    if "--onayli" not in sys.argv:
        if not messagebox.askyesno("PDF PRO'yu Kaldır",
                                   "PDF PRO bu bilgisayardan kaldırılsın mı?\n\n"
                                   "Kısayollar, 'PDF PRO ile aç' kayıtları ve program klasörü silinecek.\n"
                                   "PDF belgeleriniz silinmez."):
            return
    if not _yazilabilir(HEDEF) and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                            f'"{os.path.abspath(__file__)}" --onayli', HEDEF, 1)
        return
    try:
        kaldir()
    except Exception as e:
        messagebox.showerror("PDF PRO'yu Kaldır", f"Kaldırma tamamlanamadı:\n{e}")
        return
    messagebox.showinfo("PDF PRO'yu Kaldır", "PDF PRO kaldırıldı.\n\nCan Okan AKTAŞ İyi Çalışmalar Diler.")


if __name__ == "__main__":
    main()
