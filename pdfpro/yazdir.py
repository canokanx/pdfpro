# -*- coding: utf-8 -*-
"""
PDF PRO - Yazdirma (baska bir PDF programina gerek yok)

Sayfalar PyMuPDF ile resme cizilir ve Windows yazicisina (GDI) dogrudan gonderilir.
Pencere: yazici secimi, yazici ozellikleri (kagit, cift yuz, renk...), sayfa araligi,
kopya sayisi, sayfaya sigdir / gercek boyut, renkli / siyah-beyaz, onizleme.
Komut satiri:  PDF_PRO.exe --yazdir "belge.pdf"  (Dosya Gezgini sag tik > Yazdir)
"""
import base64
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

WINDOWS = sys.platform.startswith("win")
EN_FAZLA_DPI = 300           # cizim cozunurlugu ust siniri (bellek / hiz)

# GetDeviceCaps sabitleri
HORZRES, VERTRES, LOGPIXELSX, LOGPIXELSY = 8, 10, 88, 90
PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY = 110, 111, 112, 113


class YazdirmaHatasi(Exception):
    pass


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    return fitz


# ------------------------------------------------------------------ yazicilar
def yazicilar():
    """(ad listesi, varsayilan ad)"""
    if not WINDOWS:
        return [], None
    try:
        import win32print
    except ImportError:
        raise YazdirmaHatasi("Yazdırma için gerekli 'pywin32' kütüphanesi eksik.\n"
                             "PDF PRO klasöründeki KURULUM.bat dosyasını bir kez çalıştırın.")
    adlar = []
    for bayrak in (win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,):
        try:
            for p in win32print.EnumPrinters(bayrak, None, 2):
                ad = p.get("pPrinterName") if isinstance(p, dict) else p[2]
                if ad and ad not in adlar:
                    adlar.append(ad)
        except Exception:
            pass
    try:
        varsayilan = win32print.GetDefaultPrinter()
    except Exception:
        varsayilan = adlar[0] if adlar else None
    if varsayilan and varsayilan not in adlar:
        adlar.insert(0, varsayilan)
    return adlar, varsayilan


def yazici_durumu(ad):
    if not (WINDOWS and ad):
        return ""
    try:
        import win32print
        h = win32print.OpenPrinter(ad)
        try:
            b = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
        d = b.get("Status", 0)
        is_ = b.get("cJobs", 0)
        if d & 0x00000080:
            m = "Çevrimdışı"
        elif d & 0x00000002:
            m = "Hata"
        elif d & 0x00000008:
            m = "Kağıt sıkıştı"
        elif d & 0x00000010:
            m = "Kağıt bitti"
        elif d & 0x00000001:
            m = "Duraklatıldı"
        elif d & 0x00000400:
            m = "Yazdırıyor"
        else:
            m = "Hazır"
        return m + (f" · kuyrukta {is_} iş" if is_ else "")
    except Exception:
        return ""


def ozellikler_penceresi(hwnd, ad, devmode=None):
    """Yazicinin kendi ayar penceresi (kagit boyutu, cift yuz, renk ...). Yeni DEVMODE ya da None."""
    import win32print
    import win32con
    h = win32print.OpenPrinter(ad)
    try:
        dm = devmode or win32print.GetPrinter(h, 2)["pDevMode"]
        if dm is None:
            raise YazdirmaHatasi("Bu yazıcının ayarları okunamadı.")
        r = win32print.DocumentProperties(hwnd, h, ad, dm, dm,
                                          win32con.DM_IN_PROMPT | win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER)
        return dm if r == 1 else None          # 1 = IDOK
    finally:
        win32print.ClosePrinter(h)


# ------------------------------------------------------------------ sayfa araligi
def aralik_coz(metin, n):
    """'1-3, 5, 8-' -> [0,1,2,4,7,...]  (1 tabanli metin, 0 tabanli liste). Hatali ise ValueError."""
    metin = (metin or "").replace(" ", "").replace(";", ",")
    if not metin:
        raise ValueError("Sayfa aralığı boş.")
    sonuc = []
    for parca in metin.split(","):
        if not parca:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)", parca)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else n
        elif parca.isdigit():
            a = b = int(parca)
        else:
            raise ValueError(f"Anlaşılmadı: {parca}")
        if a < 1 or b < 1 or a > n or b > n:
            raise ValueError(f"Sayfa {max(a, b) if max(a, b) > n else min(a, b)} yok (belgede {n} sayfa var).")
        adim = 1 if b >= a else -1
        sonuc.extend(range(a - 1, b - 1 + adim, adim))
    if not sonuc:
        raise ValueError("Sayfa aralığı boş.")
    return sonuc


# ------------------------------------------------------------------ yerlesim (test edilebilir, GDI'siz)
def yerlesim(sayfa_pt, alan_px, kagit_px, ofset_px, dpi, sigdir=True, dondur_izin=True):
    """Bir sayfanin kagida nasil basilacagi.
    sayfa_pt: (gen, yuk) punto; alan_px: yazdirilabilir alan; kagit_px: fiziksel kagit; ofset_px: kenar ofseti
    Dondurur: (dondur_mu, cizim_olcegi (px/pt, sadece cizim), hedef_dikdortgen (sol, ust, sag, alt))"""
    pw, ph = sayfa_pt
    aw, ah = alan_px
    dondur = bool(dondur_izin and pw > 0 and ph > 0 and ((pw > ph) != (aw > ah)) and abs(pw - ph) > 1)
    if dondur:
        pw, ph = ph, pw
    if sigdir:
        olcek = min(aw / pw, ah / ph)
        w, h = pw * olcek, ph * olcek
        x, y = (aw - w) / 2, (ah - h) / 2
    else:
        olcek_x, olcek_y = dpi[0] / 72.0, dpi[1] / 72.0
        w, h = pw * olcek_x, ph * olcek_y
        # fiziksel kagidin ortasina
        x = (kagit_px[0] - w) / 2 - ofset_px[0]
        y = (kagit_px[1] - h) / 2 - ofset_px[1]
        olcek = olcek_x
    cizim = min(olcek, EN_FAZLA_DPI / 72.0)
    return dondur, cizim, (int(round(x)), int(round(y)), int(round(x + w)), int(round(y + h)))


def sayfa_resmi(sayfa, olcek, gri=False, dondur=False):
    """PIL resmi."""
    from PIL import Image
    fitz = _fitz()
    cs = fitz.csGRAY if gri else fitz.csRGB
    pix = sayfa.get_pixmap(matrix=fitz.Matrix(olcek, olcek), colorspace=cs, alpha=False, annots=True)
    mod = "L" if gri else "RGB"
    resim = Image.frombytes(mod, (pix.width, pix.height), pix.samples, "raw", mod, pix.stride)
    if dondur:
        resim = resim.rotate(90, expand=True)
    return resim


# ------------------------------------------------------------------ yazdirma (GDI)
def yazdir(pdf_yolu, yazici, sayfalar, kopya=1, harmanla=True, sigdir=True, gri=False, devmode=None,
           baslik="PDF PRO", ilerleme=None, iptal=None, _dc=None):
    """Belgeyi yaziciya gonderir. Dondurur: basilan sayfa sayisi. _dc: testler icin sahte cihaz."""
    il = ilerleme or (lambda *a: None)
    fitz = _fitz()
    belge = fitz.open(pdf_yolu)
    if belge.needs_pass:
        raise YazdirmaHatasi("Belge parolalı; önce PDF PRO'da parolasını kaldırın.")
    kopya = max(1, int(kopya))
    if harmanla:
        sira = [s for _ in range(kopya) for s in sayfalar]
    else:
        sira = [s for s in sayfalar for _ in range(kopya)]
    dc = _dc or _GdiCihaz(yazici, devmode)
    try:
        aw, ah = dc.olcu(HORZRES), dc.olcu(VERTRES)
        kagit = (dc.olcu(PHYSICALWIDTH) or aw, dc.olcu(PHYSICALHEIGHT) or ah)
        ofset = (dc.olcu(PHYSICALOFFSETX), dc.olcu(PHYSICALOFFSETY))
        dpi = (dc.olcu(LOGPIXELSX) or 300, dc.olcu(LOGPIXELSY) or 300)
        if aw <= 0 or ah <= 0:
            raise YazdirmaHatasi("Yazıcının kağıt ölçüsü okunamadı.")
        dc.basla(baslik)
        basilan = 0
        for k, i in enumerate(sira):
            if iptal and iptal():
                dc.iptal()
                return basilan
            il(k, len(sira), f"Yazdırılıyor: sayfa {i + 1} ({k + 1}/{len(sira)})")
            sayfa = belge[i]
            r = sayfa.rect
            dondur, olcek, hedef = yerlesim((r.width, r.height), (aw, ah), kagit, ofset, dpi, sigdir)
            resim = sayfa_resmi(sayfa, olcek, gri, dondur)
            dc.sayfa(resim, hedef)
            basilan += 1
        dc.bitir()
        il(len(sira), len(sira), "Yazıcıya gönderildi")
        return basilan
    except Exception:
        try:
            dc.iptal()
        except Exception:
            pass
        raise
    finally:
        dc.kapat()
        belge.close()


class _GdiCihaz:
    def __init__(self, yazici, devmode=None):
        if not WINDOWS:
            raise YazdirmaHatasi("Yazdırma yalnızca Windows'ta.")
        import win32ui
        import win32gui
        self._acik = False
        self._belge = False
        try:
            if devmode is not None:
                h = win32gui.CreateDC("WINSPOOL", yazici, devmode)
                self.dc = win32ui.CreateDCFromHandle(h)
            else:
                self.dc = win32ui.CreateDC()
                self.dc.CreatePrinterDC(yazici)
        except Exception as e:
            raise YazdirmaHatasi(f"Yazıcıya bağlanılamadı: {yazici}\n{e}")
        self._acik = True

    def olcu(self, kod):
        return self.dc.GetDeviceCaps(kod)

    def basla(self, baslik):
        self.dc.StartDoc(baslik[:120] or "PDF PRO")
        self._belge = True

    def sayfa(self, resim, hedef):
        from PIL import ImageWin
        self.dc.StartPage()
        ImageWin.Dib(resim).draw(self.dc.GetHandleOutput(), hedef)
        self.dc.EndPage()

    def bitir(self):
        if self._belge:
            self.dc.EndDoc()
            self._belge = False

    def iptal(self):
        if self._belge:
            try:
                self.dc.AbortDoc()
            finally:
                self._belge = False

    def kapat(self):
        if self._acik:
            try:
                self.dc.DeleteDC()
            except Exception:
                pass
            self._acik = False


# ------------------------------------------------------------------ pencere
class YazdirPenceresi(tk.Toplevel):
    MAVI = "#2563EB"

    def __init__(self, ust, pdf_yolu, baslik="PDF PRO", gecerli=0, font="Segoe UI", bitince=None):
        super().__init__(ust)
        self.pdf = pdf_yolu
        self.belge_adi = baslik
        self.font = font
        self.bitince = bitince
        self.devmode = None
        self.calisiyor = False
        self._iptal = False
        self._onizleme_resmi = None
        fitz = _fitz()
        with fitz.open(pdf_yolu) as d:
            self.n = d.page_count
        self.gecerli = max(0, min(gecerli, self.n - 1))
        self.title("Yazdır")
        self.configure(bg="white")
        self.resizable(False, False)
        try:
            self.transient(ust)
        except tk.TclError:
            pass
        self._arayuz()
        self.protocol("WM_DELETE_WINDOW", self.kapat)
        self.bind("<Escape>", lambda e: self.kapat())
        self.bind("<Return>", lambda e: self.yazdir())
        self.update_idletasks()
        try:
            if ust.winfo_viewable():
                x = ust.winfo_rootx() + (ust.winfo_width() - self.winfo_width()) // 2
                y = ust.winfo_rooty() + (ust.winfo_height() - self.winfo_height()) // 3
            else:
                x = (self.winfo_screenwidth() - self.winfo_width()) // 2
                y = (self.winfo_screenheight() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass
        self.after(50, self._onizle)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()

    # --- arayuz
    def _arayuz(self):
        F = self.font
        bant = tk.Frame(self, bg=self.MAVI)
        bant.pack(fill="x")
        tk.Label(bant, text="🖨  Yazdır", bg=self.MAVI, fg="white", font=(F, 13, "bold")).pack(side="left", padx=16, pady=9)
        ad = self.belge_adi if len(self.belge_adi) < 50 else self.belge_adi[:47] + "…"
        tk.Label(bant, text=f"{ad}  ·  {self.n} sayfa", bg=self.MAVI, fg="#DBEAFE", font=(F, 9)).pack(side="right", padx=16)

        govde = tk.Frame(self, bg="white")
        govde.pack(fill="both", expand=True, padx=16, pady=12)
        sol = tk.Frame(govde, bg="white")
        sol.pack(side="left", fill="y")
        sag = tk.Frame(govde, bg="white")
        sag.pack(side="left", fill="y", padx=(18, 0))

        def etiket(ust, metin):
            tk.Label(ust, text=metin, bg="white", fg="#374151", font=(F, 9, "bold")).pack(anchor="w", pady=(8, 2))

        etiket(sol, "Yazıcı")
        satir = tk.Frame(sol, bg="white")
        satir.pack(fill="x")
        adlar, varsayilan = yazicilar()
        self.yazici = tk.StringVar(value=varsayilan or (adlar[0] if adlar else ""))
        self.yazici_kutu = ttk.Combobox(satir, textvariable=self.yazici, values=adlar, state="readonly", width=34)
        self.yazici_kutu.pack(side="left")
        self.yazici_kutu.bind("<<ComboboxSelected>>", lambda e: self._yazici_degisti())
        ttk.Button(satir, text="Özellikler…", command=self._ozellikler).pack(side="left", padx=(6, 0))
        self.durum = tk.Label(sol, text="", bg="white", fg="#6B7280", font=(F, 8))
        self.durum.pack(anchor="w")
        if not adlar:
            self.durum.config(text="Bilgisayarda yazıcı bulunamadı." if WINDOWS else "Yazdırma yalnızca Windows'ta.",
                              fg="#DC2626")
        else:
            self._yazici_degisti()

        etiket(sol, "Sayfalar")
        self.secim = tk.StringVar(value="tum")
        self.aralik = tk.StringVar(value=f"1-{self.n}" if self.n > 1 else "1")
        for deger, metin in (("tum", f"Tümü ({self.n} sayfa)"), ("gecerli", f"Geçerli sayfa ({self.gecerli + 1})")):
            tk.Radiobutton(sol, text=metin, value=deger, variable=self.secim, bg="white", activebackground="white", highlightthickness=0, bd=0,
                           font=(F, 9), command=self._onizle).pack(anchor="w")
        a = tk.Frame(sol, bg="white")
        a.pack(anchor="w")
        tk.Radiobutton(a, text="Aralık:", value="aralik", variable=self.secim, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9), command=self._onizle).pack(side="left")
        g = ttk.Entry(a, textvariable=self.aralik, width=16)
        g.pack(side="left")
        g.bind("<FocusIn>", lambda e: (self.secim.set("aralik"), self._onizle()))
        g.bind("<KeyRelease>", lambda e: self._onizle())
        tk.Label(a, text="örn. 1-3, 5", bg="white", fg="#9CA3AF", font=(F, 8)).pack(side="left", padx=6)

        etiket(sol, "Kopya")
        k = tk.Frame(sol, bg="white")
        k.pack(anchor="w")
        self.kopya = tk.StringVar(value="1")
        ttk.Spinbox(k, from_=1, to=999, textvariable=self.kopya, width=5).pack(side="left")
        self.harmanla = tk.BooleanVar(value=True)
        tk.Checkbutton(k, text="Harmanla (1-2-3, 1-2-3)", variable=self.harmanla, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9)).pack(side="left", padx=10)

        etiket(sol, "Boyut")
        self.sigdir = tk.BooleanVar(value=True)
        b = tk.Frame(sol, bg="white")
        b.pack(anchor="w")
        tk.Radiobutton(b, text="Sayfaya sığdır", value=True, variable=self.sigdir, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9)).pack(side="left")
        tk.Radiobutton(b, text="Gerçek boyut", value=False, variable=self.sigdir, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9)).pack(side="left", padx=10)

        etiket(sol, "Renk")
        self.gri = tk.BooleanVar(value=False)
        r = tk.Frame(sol, bg="white")
        r.pack(anchor="w")
        tk.Radiobutton(r, text="Renkli", value=False, variable=self.gri, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9), command=self._onizle).pack(side="left")
        tk.Radiobutton(r, text="Siyah-beyaz", value=True, variable=self.gri, bg="white", activebackground="white", highlightthickness=0, bd=0,
                       font=(F, 9), command=self._onizle).pack(side="left", padx=10)

        # onizleme
        self.tuval = tk.Canvas(sag, width=200, height=260, bg="#F3F4F6", highlightthickness=1,
                               highlightbackground="#E5E7EB")
        self.tuval.pack()
        self.onizleme_etiket = tk.Label(sag, text="", bg="white", fg="#6B7280", font=(F, 8))
        self.onizleme_etiket.pack(pady=(4, 0))

        alt = tk.Frame(self, bg="#F9FAFB")
        alt.pack(fill="x", side="bottom")
        tk.Frame(self, bg="#E5E7EB", height=1).pack(fill="x", side="bottom")
        self.ilerleme = ttk.Progressbar(alt, length=200, mode="determinate")
        self.ilerleme_etiket = tk.Label(alt, text="", bg="#F9FAFB", fg="#6B7280", font=(F, 8))
        self.ilerleme_etiket.pack(side="left", padx=16, pady=12)
        self.yazdir_dugme = tk.Button(alt, text="  Yazdır  ", bg=self.MAVI, fg="white", activebackground="#1D4ED8",
                                      activeforeground="white", bd=0, font=(F, 10, "bold"), padx=14, pady=6,
                                      cursor="hand2", command=self.yazdir)
        self.yazdir_dugme.pack(side="right", padx=(6, 16), pady=10)
        self.iptal_dugme = tk.Button(alt, text="Vazgeç", bg="#E5E7EB", fg="#111827", activebackground="#D1D5DB",
                                     bd=0, font=(F, 10), padx=14, pady=6, cursor="hand2", command=self.kapat)
        self.iptal_dugme.pack(side="right", pady=10)
        if not adlar:
            self.yazdir_dugme.config(state="disabled", bg="#9CA3AF")

    def _yazici_degisti(self):
        self.devmode = None
        self.durum.config(text=yazici_durumu(self.yazici.get()), fg="#6B7280")

    def _ozellikler(self):
        if not (WINDOWS and self.yazici.get()):
            return
        try:
            hwnd = int(self.wm_frame(), 16)
        except Exception:
            hwnd = 0
        try:
            dm = ozellikler_penceresi(hwnd, self.yazici.get(), self.devmode)
        except Exception as e:
            messagebox.showerror("Yazdır", f"Yazıcı ayarları açılamadı:\n{e}", parent=self)
            return
        if dm is not None:
            self.devmode = dm
            try:  # yazici penceresinde kopya secildiyse buraya al (iki kez carpilmasin)
                if getattr(dm, "Copies", 1) > 1:
                    self.kopya.set(str(dm.Copies))
                    dm.Copies = 1
            except Exception:
                pass
            self.durum.config(text="Yazıcı ayarları değiştirildi.", fg="#059669")

    def secili_sayfalar(self):
        s = self.secim.get()
        if s == "tum":
            return list(range(self.n))
        if s == "gecerli":
            return [self.gecerli]
        return aralik_coz(self.aralik.get(), self.n)

    def _onizle(self):
        try:
            sayfalar = self.secili_sayfalar()
            hata = None
        except ValueError as e:
            sayfalar, hata = [], str(e)
        t = self.tuval
        t.delete("all")
        if hata:
            t.create_text(100, 130, text=hata, width=180, fill="#DC2626", font=(self.font, 9))
            self.onizleme_etiket.config(text="")
            return
        i = sayfalar[0]
        try:
            fitz = _fitz()
            with fitz.open(self.pdf) as d:
                r = d[i].rect
                olcek = min(180 / r.width, 240 / r.height)
                cs = fitz.csGRAY if self.gri.get() else fitz.csRGB
                pix = d[i].get_pixmap(matrix=fitz.Matrix(olcek, olcek), colorspace=cs, alpha=False)
                self._onizleme_resmi = tk.PhotoImage(master=self, data=base64.b64encode(pix.tobytes("png")).decode())
            x, y = 100 - pix.width // 2, 130 - pix.height // 2
            t.create_rectangle(x + 2, y + 2, x + pix.width + 2, y + pix.height + 2, fill="#D1D5DB", outline="")
            t.create_image(x, y, image=self._onizleme_resmi, anchor="nw")
        except Exception:
            pass
        toplam = len(sayfalar)
        self.onizleme_etiket.config(text=f"Sayfa {i + 1}" + (f"  ·  toplam {toplam} sayfa yazdırılacak" if toplam > 1 else ""))

    # --- yazdirma
    def yazdir(self):
        if self.calisiyor:
            return
        if not self.yazici.get():
            messagebox.showwarning("Yazdır", "Yazıcı seçilmedi.", parent=self)
            return
        try:
            sayfalar = self.secili_sayfalar()
        except ValueError as e:
            messagebox.showwarning("Yazdır", str(e), parent=self)
            return
        try:
            kopya = max(1, min(999, int(self.kopya.get())))
        except ValueError:
            messagebox.showwarning("Yazdır", "Kopya sayısı geçersiz.", parent=self)
            return
        self.calisiyor = True
        self._iptal = False
        self.yazdir_dugme.config(state="disabled", bg="#9CA3AF")
        self.iptal_dugme.config(text="Durdur")
        self.ilerleme.pack(side="left", padx=(0, 8), before=self.ilerleme_etiket)
        self.ilerleme.config(value=0, maximum=max(1, len(sayfalar) * kopya))
        ayar = dict(yazici=self.yazici.get(), sayfalar=sayfalar, kopya=kopya, harmanla=self.harmanla.get(),
                    sigdir=bool(self.sigdir.get()), gri=bool(self.gri.get()), devmode=self.devmode,
                    baslik=self.belge_adi)
        sonuc = {}

        def ilerle(i, n, metin):
            self.after(0, lambda: (self.ilerleme.config(value=i, maximum=max(1, n)),
                                   self.ilerleme_etiket.config(text=metin)) if self.winfo_exists() else None)

        def is_():
            try:
                sonuc["adet"] = yazdir(self.pdf, ilerleme=ilerle, iptal=lambda: self._iptal, **ayar)
            except Exception as e:
                sonuc["hata"] = e
            self.after(0, lambda: self._bitti(sonuc))

        threading.Thread(target=is_, daemon=True).start()

    def _bitti(self, sonuc):
        self.calisiyor = False
        if not self.winfo_exists():
            return
        if "hata" in sonuc:
            e = sonuc["hata"]
            if not isinstance(e, YazdirmaHatasi):
                try:
                    from .arayuz import hata_kaydet
                    import traceback
                    hata_kaydet("".join(traceback.format_exception(type(e), e, e.__traceback__)))
                except Exception:
                    pass
            self.yazdir_dugme.config(state="normal", bg=self.MAVI)
            self.iptal_dugme.config(text="Vazgeç")
            self.ilerleme.pack_forget()
            self.ilerleme_etiket.config(text="")
            messagebox.showerror("Yazdır", f"Yazdırılamadı:\n{e}", parent=self)
            return
        mesaj = "Yazdırma durduruldu." if self._iptal else f"Yazıcıya gönderildi ({sonuc.get('adet', 0)} sayfa)."
        if self.bitince:
            try:
                self.bitince(mesaj, not self._iptal)
            except Exception:
                pass
        self._kapat_gercek()

    def kapat(self):
        if self.calisiyor:
            self._iptal = True
            self.iptal_dugme.config(text="Durduruluyor…")
            return
        self._kapat_gercek()

    def _kapat_gercek(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ------------------------------------------------------------------ komut satiri (sag tik > Yazdir)
def tek_basina(yol, font="Segoe UI"):
    kok = tk.Tk()
    kok.withdraw()
    try:
        simge = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simge.ico")
        if WINDOWS and os.path.isfile(simge):
            kok.iconbitmap(default=simge)
    except Exception:
        pass
    try:
        p = YazdirPenceresi(kok, yol, os.path.basename(yol), font=font)
    except Exception as e:
        messagebox.showerror("PDF PRO", f"Belge açılamadı:\n{e}")
        kok.destroy()
        return 1
    p.bind("<Destroy>", lambda e: kok.after(10, kok.destroy) if e.widget is p else None)
    kok.mainloop()
    return 0
