# -*- coding: utf-8 -*-
"""Masaustune 'PDF PRO' kisayolu olusturur (KURULUM.bat cagirir)."""
import os
import sys

klasor = os.path.dirname(os.path.abspath(__file__))
pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.isfile(pyw):
    pyw = sys.executable
try:
    import win32com.client
    kabuk = win32com.client.Dispatch("WScript.Shell")
    masaustu = kabuk.SpecialFolders("Desktop")
    k = kabuk.CreateShortcut(os.path.join(masaustu, "PDF PRO.lnk"))
    exe = os.path.join(klasor, "PDF_PRO.exe")
    if os.path.isfile(exe):
        k.TargetPath = exe
        k.Arguments = ""
    else:
        k.TargetPath = pyw
        k.Arguments = '"' + os.path.join(klasor, "PDF_PRO.pyw") + '"'
    k.WorkingDirectory = klasor
    k.IconLocation = os.path.join(klasor, "simge.ico")
    k.Description = "PDF PRO"
    k.Save()
    print("OK")
except Exception as e:
    print("HATA", e)
# PDF'e sag tik > "Birlikte ac" listesine ve "PDF PRO ile ac" menusune ekle
try:
    sys.path.insert(0, klasor)
    from pdfpro import sistem
    sistem.kaydet()
    print("KAYIT OK")
except Exception as e:
    print("HATA", e)
    sys.exit(1)
