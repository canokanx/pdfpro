# -*- coding: utf-8 -*-
"""
PDF PRO - Cihaz ve Office baglantilari (Windows)
- Tarayicidan tara (WIA): Windows'un tarama penceresiyle sayfa sayfa tarar.
- E-posta ile gonder: Outlook (klasik) acikta yeni ileti + ek; Outlook yoksa .eml taslagi
  varsayilan e-posta programinda acilir.
"""
import os
import subprocess
import sys
import tempfile
from email.message import EmailMessage

from .cekirdek import PdfProHata

WINDOWS = sys.platform.startswith("win")
WIA_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
WIA_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"


def _com():
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        return win32com.client
    except Exception:
        raise PdfProHata("Bu özellik için Windows bileşeni (pywin32) gerekli.\n"
                         "KURULUM.bat'ı bir kez daha çalıştırın.")


def tara_sayfa(klasor, sira, renk="Renkli", cihaz=None):
    """Tek sayfa tarar; resim yolunu dondurur (vazgecilirse None). cihaz: onceki cagridan donen DeviceID."""
    if not WINDOWS:
        raise PdfProHata("Tarayıcıdan tarama sadece Windows'ta çalışır.")
    w = _com()
    try:
        dlg = w.Dispatch("WIA.CommonDialog")
    except Exception:
        raise PdfProHata("Windows tarama bileşeni (WIA) bulunamadı.")
    niyet = {"Renkli": 1, "Gri": 2, "Siyah-beyaz": 4}.get(renk, 1)
    try:
        img = dlg.ShowAcquireImage(1, niyet, 131072, WIA_JPEG, False, True, False)
    except Exception as e:
        metin = str(e)
        if "0x80210015" in metin or "-2145320939" in metin:
            raise PdfProHata("Bilgisayara bağlı bir tarayıcı bulunamadı.\n"
                             "Tarayıcının açık ve USB/ağ ile bağlı olduğundan emin olun.")
        if "0x80210064" in metin or "-2145320860" in metin or "cancel" in metin.lower():
            return None
        raise PdfProHata(f"Tarama yapılamadı:\n{metin}")
    if img is None:
        return None
    yol = os.path.join(klasor, f"tarama_{sira:03d}.jpg")
    if os.path.exists(yol):
        os.remove(yol)
    img.SaveFile(yol)
    return yol


def tarama_klasoru():
    return tempfile.mkdtemp(prefix="pdfpro_tarama_")


def windows_tarama_ac():
    """WIA calismazsa Windows Faks ve Tarama programini acar."""
    for kom in (["WFS.exe"], [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WFS.exe")]):
        try:
            subprocess.Popen(kom)
            return True
        except Exception:
            continue
    return False


# ------------------------------------------------------------------ e-posta
def _eml_taslak(dosyalar, konu, metin, alici=""):
    m = EmailMessage()
    m["Subject"] = konu
    if alici:
        m["To"] = alici
    m["X-Unsent"] = "1"
    m.set_content(metin or "")
    for d in dosyalar:
        with open(d, "rb") as f:
            m.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(d))
    yol = os.path.join(tempfile.gettempdir(), "PDF_PRO_eposta.eml")
    with open(yol, "wb") as f:
        f.write(bytes(m))
    return yol


def eposta_gonder(dosyalar, konu="", metin="", alici=""):
    """Outlook'ta yeni ileti acar (gondermez, kullanici kontrol edip Gonder'e basar).
    Dondurur: 'outlook' veya 'eml'."""
    dosyalar = [os.path.abspath(d) for d in dosyalar]
    if WINDOWS:
        try:
            w = _com()
            ol = w.Dispatch("Outlook.Application")
            m = ol.CreateItem(0)
            m.Subject = konu
            if alici:
                m.To = alici
            for d in dosyalar:
                m.Attachments.Add(d)
            m.Display(False)
            # imzayi korumak icin metni basa ekle
            if metin:
                try:
                    m.HTMLBody = "<p>" + metin.replace("\n", "<br>") + "</p>" + m.HTMLBody
                except Exception:
                    m.Body = metin + "\n\n" + m.Body
            return "outlook"
        except PdfProHata:
            raise
        except Exception:
            pass
    yol = _eml_taslak(dosyalar, konu, metin, alici)
    if WINDOWS:
        os.startfile(yol)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", yol])
    else:
        subprocess.Popen(["xdg-open", yol])
    return "eml"
