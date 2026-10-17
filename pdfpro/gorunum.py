# -*- coding: utf-8 -*-
"""
PDF PRO - Belge modeli, orta belge gorunumu ve soldaki sayfa kucuk resimleri
"""
import os
import sys
import tempfile
import tkinter as tk
from collections import OrderedDict

from .cekirdek import fitz, PdfProHata
from . import duzenle as Z

WINDOWS = sys.platform.startswith("win")
PT_PX = 96 / 72          # %100 = gercek boyut (96 dpi ekran)
SAYFA_ARASI = 14
GERI_AL_SINIRI = 20


# ================================================================== belge modeli
class Belge:
    """Acik bir PDF. Dosyadan bellege okunur; dosya kilitlenmez."""
    _sayac = 0

    def __init__(self, yol=None, doc=None, ad=None, sifre_sor=None):
        self.yol = yol
        if doc is None:
            doc = self._oku(yol, sifre_sor)
        self.doc = doc
        if ad:
            self.ad = ad
        elif yol:
            self.ad = os.path.basename(yol)
        else:
            Belge._sayac += 1
            self.ad = f"Yeni belge {Belge._sayac}"
        self.degisti = yol is None or not yol.lower().endswith(".pdf")
        if yol and not yol.lower().endswith(".pdf"):
            self.yol = None   # resimden acildi: farkli kaydet gerekecek
            self.ad = os.path.splitext(os.path.basename(yol))[0] + ".pdf"
        self.geri = []
        self.ileri = []
        self.nesneler = []     # sayfadaki tasinabilir imza / kaseler: {id, sayfa, ad, rect, png}
        self.surum = 0
        self.zoom = "genislik"
        self.secili = {0}
        self.aktif = 0
        self.kaydirma = (0.0, 0.0)

    @staticmethod
    def _oku(yol, sifre_sor=None):
        if not yol or not os.path.isfile(yol):
            raise PdfProHata(f"Dosya bulunamadı:\n{yol}")
        try:
            with open(yol, "rb") as f:
                veri = f.read()
            uz = os.path.splitext(yol)[1].lower().lstrip(".") or "pdf"
            doc = fitz.open(stream=veri, filetype=uz if uz != "pdf" else "pdf")
        except Exception as e:
            raise PdfProHata(f"Dosya açılamadı:\n{os.path.basename(yol)}\n\n{e}")
        if doc.needs_pass:
            deneme = 0
            while True:
                sifre = sifre_sor(os.path.basename(yol), deneme) if sifre_sor else None
                if sifre is None:
                    raise PdfProHata("Şifre girilmediği için dosya açılmadı.")
                if doc.authenticate(sifre):
                    break
                deneme += 1
        if not doc.is_pdf:
            pdfb = doc.convert_to_pdf()
            doc.close()
            doc = fitz.open("pdf", pdfb)
        if doc.page_count == 0:
            raise PdfProHata("Belgede sayfa yok.")
        return doc

    # -- geri al
    def _durum(self):
        return (self.doc.tobytes(garbage=0), [dict(n) for n in self.nesneler])

    def anlik(self):
        """Degisiklikten ONCE cagrilir. Bellek siniri: toplam ~600 MB (buyuk taramalarda daha az adim)."""
        self.geri.append(self._durum())
        while len(self.geri) > GERI_AL_SINIRI or (len(self.geri) > 2 and sum(len(g[0]) for g in self.geri) > 600 * 1024 * 1024):
            self.geri.pop(0)
        self.ileri.clear()

    def degisiklik(self):
        self.surum += 1
        self.degisti = True
        n = self.doc.page_count
        self.secili = {s for s in self.secili if s < n} or {min(self.aktif, n - 1)}
        self.aktif = min(self.aktif, n - 1)

    def geri_al(self):
        if not self.geri:
            return False
        self.ileri.append(self._durum())
        self.geri_yukle(self.geri.pop())
        return True

    def yinele(self):
        if not self.ileri:
            return False
        self.geri.append(self._durum())
        self.geri_yukle(self.ileri.pop())
        return True

    def nesneleri_esle(self):
        """Dosya tabanli islemlerden sonra resim numaralari degisebilir: tasinabilir imza/kaseleri
        sayfadaki konumlarindan yeniden bulur. Bulunamayanlar listeden cikar."""
        kalan = []
        kullanilan = set()
        for n in self.nesneler:
            try:
                page = self.doc[n["sayfa"]]
                hedef = fitz.Rect(n["rect"])
                bulunan = None
                for im in page.get_images(full=True):
                    if im[0] in kullanilan:
                        continue
                    r = Z.nesne_konumu(page, im[0])
                    if r is not None and abs(r.x0 - hedef.x0) < 0.8 and abs(r.y0 - hedef.y0) < 0.8 and \
                            abs(r.x1 - hedef.x1) < 0.8 and abs(r.y1 - hedef.y1) < 0.8:
                        bulunan = im[0]
                        break
                if bulunan:
                    n["xref"] = bulunan
                    kullanilan.add(bulunan)
                    kalan.append(n)
            except Exception:
                pass
        self.nesneler = kalan

    def geri_yukle(self, durum):
        bayt, nesneler = durum
        self.nesneler = [dict(n) for n in nesneler]
        self._degistir(bayt)

    def _degistir(self, bayt):
        eski = self.doc
        self.doc = fitz.open("pdf", bayt)
        try:
            eski.close()
        except Exception:
            pass
        self.degisiklik()

    def yeni_icerik(self, bayt):
        """Dosya tabanli bir islemin sonucunu belgeye uygular (geri alinabilir)."""
        self.anlik()
        self._degistir(bayt)
        if self.nesneler:
            self.nesneleri_esle()

    # -- dosya
    def gecici_kopya(self):
        """Dosya tabanli islemler icin belgenin guncel halini gecici dosyaya yazar."""
        yol = os.path.join(tempfile.gettempdir(), f"pdfpro_{id(self)}_{self.surum}.pdf")
        self.doc.save(yol, garbage=1)
        return yol

    def kaydet(self, yol=None):
        hedef = yol or self.yol
        if not hedef:
            raise PdfProHata("Kayıt yeri seçilmedi.")
        gecici = hedef + ".pdfpro_tmp"
        try:
            self.doc.save(gecici, garbage=3, deflate=True)
            os.replace(gecici, hedef)
        except PermissionError:
            try:
                os.remove(gecici)
            except Exception:
                pass
            raise PdfProHata("Dosya kaydedilemedi. Başka bir programda (Adobe, tarayıcı) açık olabilir.\n"
                             "Kapatıp tekrar deneyin veya 'Farklı Kaydet' kullanın.\n\n" + hedef)
        self.yol = hedef
        self.ad = os.path.basename(hedef)
        self.degisti = False
        return hedef

    def kapat(self):
        try:
            self.doc.close()
        except Exception:
            pass

    @property
    def baslik(self):
        return ("● " if self.degisti else "") + self.ad


# ================================================================== orta gorunum
class BelgeGorunumu(tk.Frame):
    """Sayfalari alt alta gosterir; yakinlastirma, kaydirma ve duzenleme modlari."""

    ZEMIN = "#DDE1EA"

    def __init__(self, ust, uygulama):
        super().__init__(ust, bg=self.ZEMIN)
        self.u = uygulama
        self.belge = None
        self.olcek = 1.0
        self.yerler = []              # [(x, y, w, h)]
        self.genislik = 0
        self.onbellek = OrderedDict()
        self.metin_onbellek = {}
        self.mod = "sec"
        self._ciz_zaman = None
        self._vurgu = None
        self._surukle = None
        self._duzenleyici = None
        self._hayalet = None
        self.secili_nesne = None
        self._nesne_foto = None

        self.tuval = tk.Canvas(self, bg=self.ZEMIN, highlightthickness=0, bd=0,
                               yscrollincrement=24, xscrollincrement=24)
        from tkinter import ttk
        self.dikey = ttk.Scrollbar(self, orient="vertical", command=self._ykaydir, style="Belge.Vertical.TScrollbar")
        self.yatay = ttk.Scrollbar(self, orient="horizontal", command=self._xkaydir, style="Belge.Horizontal.TScrollbar")
        self._nesil = 0                # cizim kuyrugu nesli (kaydirinca eski isler iptal)
        self._kuyruk_zaman = None
        self._gorunen = []
        self.tuval.configure(yscrollcommand=self._ykaydirildi, xscrollcommand=self.yatay.set)
        self.tuval.grid(row=0, column=0, sticky="nsew")
        self.dikey.grid(row=0, column=1, sticky="ns")
        self.yatay.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        t = self.tuval
        t.bind("<Configure>", lambda e: self._yeniden_yerlestir())
        t.bind("<MouseWheel>", self._teker)
        t.bind("<Control-MouseWheel>", self._ctrl_teker)
        t.bind("<Button-4>", lambda e: self._teker_linux(e, -1))
        t.bind("<Button-5>", lambda e: self._teker_linux(e, 1))
        t.bind("<ButtonPress-1>", self._bas)
        t.bind("<B1-Motion>", self._surukle_hareket)
        t.bind("<ButtonRelease-1>", self._birak)
        t.bind("<Motion>", self._hareket)
        t.bind("<Leave>", lambda e: self._vurgu_temizle())
        t.bind("<Double-Button-1>", self._cift_tik)
        t.bind("<Shift-MouseWheel>", lambda e: (t.xview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units"), "break")[1])
        t.bind("<ButtonPress-2>", lambda e: t.scan_mark(e.x, e.y))
        t.bind("<B2-Motion>", lambda e: (t.scan_dragto(e.x, e.y, gain=1), self._gecikmeli_ciz()))
        t.bind("<Up>", lambda e: self._ok_tusu(e, 0, -1) or self._kaydir_birim(-2))
        t.bind("<Down>", lambda e: self._ok_tusu(e, 0, 1) or self._kaydir_birim(2))
        t.bind("<Left>", lambda e: self._ok_tusu(e, -1, 0) or (t.xview_scroll(-2, "units"), "break")[1])
        t.bind("<Right>", lambda e: self._ok_tusu(e, 1, 0) or (t.xview_scroll(2, "units"), "break")[1])
        t.bind("<Delete>", lambda e: (self.u.nesne_sil(self.secili_nesne), "break")[1] if self.secili_nesne else None)
        t.bind("<space>", lambda e: (t.yview_scroll(1, "pages"), self._gecikmeli_ciz(), "break")[2])
        t.bind("<Shift-space>", lambda e: (t.yview_scroll(-1, "pages"), self._gecikmeli_ciz(), "break")[2])

    # ---------------------------------------------------------- belge
    def goster(self, belge):
        self._duzenleyici_kapat(uygula=True)
        self.belge = belge
        self.onbellek.clear()
        self.metin_onbellek.clear()
        self._yeniden_yerlestir(koru=False)
        if belge:
            self.after(10, lambda: self._kaydirma_yukle(belge))

    def _kaydirma_yukle(self, belge):
        if belge is self.belge:
            self.tuval.yview_moveto(belge.kaydirma[1])
            self.tuval.xview_moveto(belge.kaydirma[0])
            self.ciz()

    def kaydirma_kaydet(self):
        if self.belge:
            self.belge.kaydirma = (self.tuval.xview()[0], self.tuval.yview()[0])

    def yenile(self, koru=True):
        """Belge icerigi degistiginde."""
        self.onbellek.clear()
        self.metin_onbellek.clear()
        self._yeniden_yerlestir(koru=koru)

    # ---------------------------------------------------------- yerlesim
    def _olcek_hesapla(self):
        b = self.belge
        cw = max(self.tuval.winfo_width(), 200)
        ch = max(self.tuval.winfo_height(), 200)
        if b.zoom == "genislik":
            maxw = max(p.rect.width for p in b.doc) if b.doc.page_count < 400 else b.doc[0].rect.width
            return max(0.1, (cw - 40) / maxw)
        if b.zoom == "sayfa":
            r = b.doc[b.aktif].rect
            return max(0.1, min((cw - 40) / r.width, (ch - 2 * SAYFA_ARASI) / r.height))
        return float(b.zoom) * PT_PX

    def _yeniden_yerlestir(self, koru=True):
        t = self.tuval
        t.delete("all")
        self.yerler = []
        self._ys = []
        if not self.belge:
            t.configure(scrollregion=(0, 0, 1, 1))
            self.u.karsilama_goster(True)
            return
        self.u.karsilama_goster(False, otomatik=True)
        oran = self._gorunen_sayfa_orani() if koru else None
        self.olcek = self._olcek_hesapla()
        cw = max(t.winfo_width(), 200)
        rects = [p.rect for p in self.belge.doc]
        maxw = max(r.width for r in rects) * self.olcek
        self.genislik = max(cw, maxw + 40)
        y = SAYFA_ARASI
        for r in rects:
            w, h = r.width * self.olcek, r.height * self.olcek
            x = (self.genislik - w) / 2
            self.yerler.append((x, y, w, h))
            y += h + SAYFA_ARASI
        t.configure(scrollregion=(0, 0, self.genislik, y))
        self._ys = [yy for (_, yy, _, _) in self.yerler]
        for i, (x, y0, w, h) in enumerate(self.yerler):
            t.create_rectangle(x + 3, y0 + 3, x + w + 3, y0 + h + 3, fill="#B9C1CD", outline="", tags="golge")
            t.create_rectangle(x, y0, x + w, y0 + h, fill="white", outline="#C5CCD8", tags=("kagit", f"k{i}"))
        if oran is not None:
            i, kesir = oran
            if i < len(self.yerler):
                x, y0, w, h = self.yerler[i]
                self._yuksekligi_kaydir(y0 + h * kesir - SAYFA_ARASI)
        self.u.zoom_guncelle()
        self.ciz()
        self.arama_ciz()
        self.nesne_ciz()

    def _yuksekligi_kaydir(self, y):
        toplam = float(self.tuval.cget("scrollregion").split()[3] or 1)
        self.tuval.yview_moveto(max(0, y / toplam))

    def _gorunen_sayfa_orani(self):
        if not self.yerler:
            return None
        ust = self.tuval.canvasy(0)
        for i, (x, y, w, h) in enumerate(self.yerler):
            if y + h >= ust:
                return i, max(0.0, (ust - y + SAYFA_ARASI) / h)
        return None

    # ---------------------------------------------------------- cizim
    # Kaydirirken hic beklemeden onbellekteki sayfalar cizilir; eksik sayfalar once kucuk resimden
    # buyutulmus gecici gorunumle gosterilir, kaydirma durunca tek tek net hale getirilir.
    # Boylece kaydirma cubugu ve fare tekeri takilmaz.
    def _kaydir_birim(self, n):
        self.tuval.yview_scroll(n, "units")
        self._gecikmeli_ciz()
        return "break"

    def _ykaydir(self, *a):
        self.tuval.yview(*a)
        self.ciz(hizli=True)

    def _xkaydir(self, *a):
        self.tuval.xview(*a)

    def _ykaydirildi(self, a, b):
        self.dikey.set(a, b)
        self._gecikmeli_ciz()

    def _gecikmeli_ciz(self):
        if self._ciz_zaman:
            self.after_cancel(self._ciz_zaman)
        self._ciz_zaman = self.after(15, lambda: self.ciz(hizli=True))

    def _gorunen_sayfalar(self, pay=60):
        t = self.tuval
        ust, alt = t.canvasy(0) - pay, t.canvasy(t.winfo_height()) + pay
        # yerler y'ye gore sirali: ikili arama
        import bisect
        ys = self._ys
        i = max(0, bisect.bisect_right(ys, ust) - 1)
        sonuc = []
        while i < len(self.yerler):
            x, y, w, h = self.yerler[i]
            if y > alt:
                break
            if y + h >= ust:
                sonuc.append(i)
            i += 1
        return sonuc

    def ciz(self, hizli=False):
        """hizli=True: sadece hazir olanlari ciz, eksikleri sonra tamamla."""
        self._ciz_zaman = None
        if not self.belge or not self.yerler:
            return
        t = self.tuval
        gorunen = self._gorunen_sayfalar()
        self._nesil += 1
        eksik = []
        t.delete("sayfa")
        for i in gorunen:
            img = self._onbellekten(i)
            if img is None:
                if self.u.mesgul_render or hizli:
                    img = self._gecici_resim(i)
                    eksik.append(i)
                else:
                    img = self._sayfa_resmi(i)
            if img is None:
                continue
            x, y, w, h = self.yerler[i]
            t.create_image(x, y, image=img, anchor="nw", tags=("sayfa", f"s{i}"))
        for etiket in ("arama", "vurgu", "secim", "hayalet", "duzen", "stil"):
            t.tag_raise(etiket)
        self.nesne_ciz()
        if eksik and not self.u.mesgul_render:
            nesil = self._nesil
            if self._kuyruk_zaman:
                self.after_cancel(self._kuyruk_zaman)
            self._kuyruk_zaman = self.after(70, lambda: self._kuyruk_isle(eksik, nesil))
        elif eksik:
            self._kuyruk_zaman = self.after(400, lambda: self.ciz(hizli=True))
        self._aktif_guncelle(gorunen)

    def _kuyruk_isle(self, eksik, nesil):
        """Eksik sayfalari birer birer net ciz; kullanici kaydirirsa dur."""
        self._kuyruk_zaman = None
        if nesil != self._nesil or not self.belge:
            return
        if self.u.mesgul_render:
            self._kuyruk_zaman = self.after(400, lambda: self.ciz(hizli=True))
            return
        while eksik and self._onbellekten(eksik[0]) is not None:
            eksik.pop(0)
        if not eksik:
            return
        i = eksik.pop(0)
        img = self._sayfa_resmi(i)
        if img is not None and i < len(self.yerler):
            t = self.tuval
            t.delete(f"s{i}")
            x, y, w, h = self.yerler[i]
            t.create_image(x, y, image=img, anchor="nw", tags=("sayfa", f"s{i}"))
            for etiket in ("arama", "vurgu", "secim", "hayalet", "duzen", "stil"):
                t.tag_raise(etiket)
        if eksik:
            self._kuyruk_zaman = self.after(1, lambda: self._kuyruk_isle(eksik, nesil))

    def _aktif_guncelle(self, gorunen):
        t = self.tuval
        orta = (t.canvasy(0) + t.canvasy(t.winfo_height())) / 2
        aktif = None
        for i in gorunen:
            x, y, w, h = self.yerler[i]
            if y - SAYFA_ARASI <= orta <= y + h + SAYFA_ARASI:
                aktif = i
                break
        if aktif is None and gorunen:
            aktif = gorunen[0]
        if aktif is not None and aktif != self.belge.aktif:
            self.belge.aktif = aktif
            self.u.sayfa_degisti(kaydir_kucuk=True)

    def _onbellekten(self, i):
        anahtar = (i, self.belge.surum, round(self.olcek, 4))
        img = self.onbellek.get(anahtar)
        if img is not None:
            self.onbellek.move_to_end(anahtar)
        return img

    def _gecici_resim(self, i):
        """Net goruntu hazir olana kadar: kucuk resmi buyutup goster (aninda)."""
        kucuk = self.u.kucuk.onbellek.get((i, self.belge.surum))
        if kucuk is None:
            return None
        try:
            x, y, w, h = self.yerler[i]
            kat = max(1, int(round(w / max(1, kucuk.width()))))
            if kat > 12:
                return None
            anahtar = ("gecici", i, self.belge.surum, kat)
            img = self.onbellek.get(anahtar)
            if img is None:
                img = kucuk.zoom(kat, kat)
                self.onbellek[anahtar] = img
            return img
        except Exception:
            return None

    def _sayfa_resmi(self, i):
        img = self._onbellekten(i)
        if img is not None:
            return img
        anahtar = (i, self.belge.surum, round(self.olcek, 4))
        try:
            s = self.olcek
            p = self.belge.doc[i]
            # cok buyuk resimleri sinirla
            maks = 4500 / max(p.rect.width, p.rect.height)
            if s > maks:
                s = maks
            pix = p.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False, annots=True)
            img = tk.PhotoImage(data=pix.tobytes("ppm"))
        except Exception:
            return None
        self.onbellek[anahtar] = img
        while len(self.onbellek) > 30:
            self.onbellek.popitem(last=False)
        return img

    # ---------------------------------------------------------- tasinabilir imza / kase
    TUTAMAK = 5     # kose tutamagi yari boyu (piksel)

    def nesne_sec(self, nid):
        self.secili_nesne = nid
        self.nesne_ciz()
        if nid:
            self.tuval.focus_set()

    def _nesneler(self, i=None):
        b = self.belge
        if not b:
            return []
        return [n for n in b.nesneler if i is None or n["sayfa"] == i]

    def nesne_ciz(self):
        t = self.tuval
        t.delete("nesne")
        n = self.u._nesne(self.secili_nesne) if self.secili_nesne else None
        if not n or n["sayfa"] >= len(self.yerler):
            return
        x0, y0, x1, y1 = self.tuval_rect(n["sayfa"], n["rect"])
        t.create_rectangle(x0, y0, x1, y1, outline="#4F46E5", width=1.5, dash=(5, 3), tags="nesne")
        k = self.TUTAMAK
        for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            t.create_rectangle(cx - k, cy - k, cx + k, cy + k, fill="white", outline="#4F46E5", width=1.5, tags="nesne")
        t.tag_raise("nesne")

    def _nesne_vurusu(self, e):
        """Fare altinda: ('kose', nid, kose_no) | ('ic', nid) | None"""
        cx, cy = self.tuval.canvasx(e.x), self.tuval.canvasy(e.y)
        k = self.TUTAMAK + 3
        if self.secili_nesne:
            n = self.u._nesne(self.secili_nesne)
            if n and n["sayfa"] < len(self.yerler):
                x0, y0, x1, y1 = self.tuval_rect(n["sayfa"], n["rect"])
                for no, (kx, ky) in enumerate(((x0, y0), (x1, y0), (x0, y1), (x1, y1))):
                    if abs(cx - kx) <= k and abs(cy - ky) <= k:
                        return ("kose", n["id"], no)
        for n in reversed(self._nesneler()):
            if n["sayfa"] >= len(self.yerler):
                continue
            x0, y0, x1, y1 = self.tuval_rect(n["sayfa"], n["rect"])
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return ("ic", n["id"])
        return None

    def _ok_tusu(self, e, dx, dy):
        """Secili imza/kase varsa yon tuslariyla 1 pt (Shift ile 10 pt) kaydir."""
        if not self.secili_nesne or self.mod != "sec":
            return None
        n = self.u._nesne(self.secili_nesne)
        if not n:
            return None
        adim = 10 if (e.state & 0x0001) else 1
        r = fitz.Rect(n["rect"]) + (dx * adim, dy * adim, dx * adim, dy * adim)
        self.u.nesne_guncelle(n["id"], r, "İmza / kaşe ince ayar")
        return "break"

    def _nesne_surukle(self, e):
        _, tur, nid, ek, cx0, cy0, r0 = self._surukle
        n = self.u._nesne(nid)
        if not n:
            return
        s = self.olcek
        dx, dy = (self.tuval.canvasx(e.x) - cx0) / s, (self.tuval.canvasy(e.y) - cy0) / s
        r = fitz.Rect(r0)
        if tur == "tasi":
            r = r + (dx, dy, dx, dy)
        else:
            oran = r0.height / max(r0.width, 0.1)
            # karsi kose sabit, oran korunur
            sabit = {0: (r0.x1, r0.y1), 1: (r0.x0, r0.y1), 2: (r0.x1, r0.y0), 3: (r0.x0, r0.y0)}[ek]
            hareketli = {0: (r0.x0, r0.y0), 1: (r0.x1, r0.y0), 2: (r0.x0, r0.y1), 3: (r0.x1, r0.y1)}[ek]
            yeni_x = hareketli[0] + dx
            gen = max(8.0, abs(yeni_x - sabit[0]))
            yuk = gen * oran
            x0 = sabit[0] - gen if ek in (0, 2) else sabit[0]
            y0 = sabit[1] - yuk if ek in (0, 1) else sabit[1]
            r = fitz.Rect(x0, y0, x0 + gen, y0 + yuk)
        self._surukle = self._surukle[:6] + (r0,)
        self._nesne_yeni = r
        t = self.tuval
        t.delete("nesne_hayalet")
        a = self.tuval_rect(n["sayfa"], r)
        if self._nesne_foto is not None and tur == "tasi":
            t.create_image(a[0], a[1], image=self._nesne_foto, anchor="nw", tags="nesne_hayalet")
        t.create_rectangle(*a, outline="#E8590C", width=2, dash=(5, 3), tags="nesne_hayalet")
        t.tag_raise("nesne_hayalet")

    def _nesne_foto_hazirla(self, n):
        try:
            from PIL import Image, ImageTk
            import io
            x0, y0, x1, y1 = self.tuval_rect(n["sayfa"], n["rect"])
            im = Image.open(io.BytesIO(n["png"])).convert("RGBA").resize((max(1, int(x1 - x0)), max(1, int(y1 - y0))))
            im.putalpha(im.split()[3].point(lambda v: int(v * 0.65)))
            self._nesne_foto = ImageTk.PhotoImage(im)
        except Exception:
            self._nesne_foto = None

    # ---------------------------------------------------------- arama vurgulari
    def arama_ciz(self, sonuclar=None, aktif=None):
        if sonuclar is not None:
            self._arama_durum = (sonuclar, aktif)
        sonuclar, aktif = getattr(self, "_arama_durum", ([], -1))
        t = self.tuval
        t.delete("arama")
        if not self.yerler:
            return
        for k, (i, r) in enumerate(sonuclar):
            if i >= len(self.yerler):
                continue
            x0, y0, x1, y1 = self.tuval_rect(i, (r.x0, r.y0, r.x1, r.y1))
            if k == aktif:
                t.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, outline="#E8590C", width=2, tags="arama")
            else:
                t.create_rectangle(x0, y0, x1, y1, outline="#E6B800", fill="#FFE94D", stipple="gray25", tags="arama")
        t.tag_raise("arama")

    def alana_git(self, i, r):
        """Sayfadaki bir alani ekranin ortasina getir."""
        if not self.yerler or i >= len(self.yerler):
            return
        x0, y0, x1, y1 = self.tuval_rect(i, (r.x0, r.y0, r.x1, r.y1))
        t = self.tuval
        bolge = [float(v) for v in t.cget("scrollregion").split()]
        H, W = bolge[3] or 1, bolge[2] or 1
        ch, cw = t.winfo_height(), t.winfo_width()
        t.yview_moveto(max(0, ((y0 + y1) / 2 - ch / 2) / H))
        if W > cw:
            t.xview_moveto(max(0, ((x0 + x1) / 2 - cw / 2) / W))
        self.ciz()

    # ---------------------------------------------------------- gezinme / zoom
    def sayfaya_git(self, i):
        if not self.belge or not (0 <= i < len(self.yerler)):
            return
        self.belge.aktif = i
        self._yuksekligi_kaydir(self.yerler[i][1] - SAYFA_ARASI / 2)
        self.ciz()
        self.u.sayfa_degisti(kaydir_kucuk=True)

    def zoom_ayarla(self, deger):
        if not self.belge:
            return
        if isinstance(deger, (int, float)):
            deger = max(0.1, min(4.0, float(deger)))
        self.belge.zoom = deger
        self._yeniden_yerlestir()

    def zoom_adim(self, yon):
        if not self.belge:
            return
        su_an = self.olcek / PT_PX
        adimlar = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
        if yon > 0:
            yeni = next((a for a in adimlar if a > su_an + 0.01), 4.0)
        else:
            yeni = next((a for a in reversed(adimlar) if a < su_an - 0.01), 0.25)
        self.zoom_ayarla(yeni)

    def _teker(self, e):
        if e.state & 0x0004:
            return self._ctrl_teker(e)
        self.tuval.yview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units")
        self._gecikmeli_ciz()
        return "break"

    def _teker_linux(self, e, yon):
        if e.state & 0x0004:
            self.zoom_adim(-yon)
            return
        self.tuval.yview_scroll(yon * 3, "units")
        self._gecikmeli_ciz()

    def _ctrl_teker(self, e):
        self.zoom_adim(1 if e.delta > 0 else -1)
        return "break"

    # ---------------------------------------------------------- koordinat
    def nokta(self, e):
        """Olay -> (sayfa_no, pdf_x, pdf_y) ya da None"""
        cx, cy = self.tuval.canvasx(e.x), self.tuval.canvasy(e.y)
        for i, (x, y, w, h) in enumerate(self.yerler):
            if x <= cx <= x + w and y <= cy <= y + h:
                return i, (cx - x) / self.olcek, (cy - y) / self.olcek
        return None

    def tuval_rect(self, i, r):
        x, y, w, h = self.yerler[i]
        s = self.olcek
        return x + r[0] * s, y + r[1] * s, x + r[2] * s, y + r[3] * s

    # ---------------------------------------------------------- modlar
    IMLECLER = {"sec": "arrow", "kaydir": "fleur", "yazi_duzelt": "xterm", "yazi_ekle": "xterm",
                "beyaz_kutu": "crosshair", "imza": "crosshair", "resim_yazi": "crosshair",
                "vurgula": "crosshair", "karart": "crosshair", "kirp": "crosshair", "damga": "crosshair",
                "sekil_dikdortgen": "crosshair", "sekil_elips": "crosshair", "sekil_cizgi": "crosshair",
                "sekil_ok": "crosshair", "not": "hand2", "set": "crosshair", "metin_kutusu": "crosshair",
                "form_metin": "crosshair", "form_onay": "crosshair", "form_liste": "crosshair"}
    SURUKLE_MODLARI = {"beyaz_kutu", "imza", "resim_yazi", "vurgula", "karart", "kirp",
                       "sekil_dikdortgen", "sekil_elips", "sekil_cizgi", "sekil_ok",
                       "metin_kutusu", "form_metin", "form_onay", "form_liste"}
    MOD_RENKLERI = {"beyaz_kutu": "#C0392B", "karart": "#000000", "vurgula": "#E6B800", "kirp": "#2E9E6B",
                    "resim_yazi": "#E8590C", "metin_kutusu": "#4F46E5", "form_metin": "#7048E8",
                    "form_onay": "#7048E8", "form_liste": "#7048E8"}

    def mod_ayarla(self, mod):
        self._duzenleyici_kapat(uygula=True)
        self._vurgu_temizle()
        self.tuval.delete("hayalet")
        self.mod = mod
        self.tuval.configure(cursor=self.IMLECLER.get(mod, "arrow"))

    def _metin_verisi(self, i):
        k = (i, self.belge.surum)
        if k not in self.metin_onbellek:
            self.metin_onbellek = {kk: v for kk, v in self.metin_onbellek.items() if kk[1] == self.belge.surum}
            self.metin_onbellek[k] = Z.metin_verisi(self.belge.doc[i])
        return self.metin_onbellek[k]

    def _vurgu_temizle(self):
        self.tuval.delete("vurgu")
        self._vurgu = None

    def _hareket(self, e):
        if not self.belge or self.u.mesgul:
            return
        if self.mod == "sec" and not self._surukle:
            v = self._nesne_vurusu(e) if self.belge.nesneler else None
            if v and v[0] == "kose":
                if WINDOWS:
                    self.tuval.configure(cursor="size_nw_se" if v[2] in (0, 3) else "size_ne_sw")
                else:
                    self.tuval.configure(cursor="sizing")
            elif v:
                self.tuval.configure(cursor="fleur")
            else:
                self.tuval.configure(cursor="arrow")
            return
        if self.mod == "yazi_duzelt" and not self._duzenleyici:
            n = self.nokta(e)
            satir = None
            if n and self.belge.doc[n[0]].rotation == 0:   # donuk sayfada vurgu yok; tiklayinca duzelir
                i, px, py = n
                satir = Z.satir_bul(self.belge.doc[i], px, py, veri=self._metin_verisi(i))
            key = (n[0], satir["bbox"]) if (n and satir) else None
            if key != self._vurgu:
                self._vurgu_temizle()
                if key:
                    self._vurgu = key
                    x0, y0, x1, y1 = self.tuval_rect(n[0], satir["bbox"])
                    renk = "#2E9E6B" if satir.get("gorunmez") else "#E8590C"   # yesil: resimdeki yazi
                    self.tuval.create_rectangle(x0 - 3, y0 - 2, x1 + 3, y1 + 2, outline=renk,
                                                dash=(4, 3), width=1.5, tags="vurgu")
            self.tuval.configure(cursor="xterm" if key else "crosshair")
        elif self.mod == "imza" and self.u.imza_ayar:
            self._hayalet_ciz(e)
        elif self.mod == "damga" and self.u.damga_ayar:
            self.tuval.delete("hayalet")
            cx, cy = self.tuval.canvasx(e.x), self.tuval.canvasy(e.y)
            w, h = self.u.damga_ayar.get("boyut_pt", (120, 40))
            w, h = w * self.olcek, h * self.olcek
            self.tuval.create_rectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
                                        outline="#C0392B", width=2, dash=(4, 2), tags="hayalet")
            self.tuval.create_text(cx, cy, text=self.u.damga_ayar["metin"], fill="#C0392B",
                                   font=("Arial", max(6, int(12 * self.olcek)), "bold"), tags="hayalet")

    def _hayalet_ciz(self, e):
        self.tuval.delete("hayalet")
        n = self.nokta(e)
        if not n:
            return
        gen_pt = self.u.imza_ayar["genislik_mm"] * 72 / 25.4
        oran = self.u.imza_ayar["oran"]
        w, h = gen_pt * self.olcek, gen_pt * oran * self.olcek
        cx, cy = self.tuval.canvasx(e.x), self.tuval.canvasy(e.y)
        img = self.u.imza_ayar.get("tk_onizleme")
        if img is None or self.u.imza_ayar.get("tk_olcek") != round(self.olcek, 3):
            img = self.u.imza_onizleme_resmi(int(w), int(h))
            self.u.imza_ayar["tk_onizleme"] = img
            self.u.imza_ayar["tk_olcek"] = round(self.olcek, 3)
        if img is not None:
            self.tuval.create_image(cx, cy, image=img, tags="hayalet")
        self.tuval.create_rectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
                                    outline="#4F46E5", dash=(4, 2), tags="hayalet")

    def _bas(self, e):
        self.tuval.focus_set()
        if not self.belge:
            return
        if self._duzenleyici:
            self._duzenleyici_kapat(uygula=True)
            return
        n = self.nokta(e)
        cx, cy = self.tuval.canvasx(e.x), self.tuval.canvasy(e.y)
        if self.mod in ("sec", "kaydir"):
            if self.mod == "sec":
                v = self._nesne_vurusu(e)
                if v:
                    nid = v[1]
                    self.nesne_sec(nid)
                    nn = self.u._nesne(nid)
                    tur = "tasi" if v[0] == "ic" else "boyut"
                    if tur == "tasi":
                        self._nesne_foto_hazirla(nn)
                    self._nesne_yeni = None
                    self._surukle = ("nesne", tur, nid, v[2] if v[0] == "kose" else None, cx, cy, fitz.Rect(nn["rect"]))
                    return
                if self.secili_nesne:
                    self.nesne_sec(None)
            if self.mod == "sec" and n and self.u.form_alani_tikla(*n):
                return
            self.tuval.scan_mark(e.x, e.y)
            self._surukle = ("kaydir",)
            if self.mod == "sec":
                self.tuval.configure(cursor="fleur")
        elif self.mod in self.SURUKLE_MODLARI and n:
            self._surukle = ("kutu", n[0], cx, cy, n[1], n[2])
        elif self.mod == "yazi_duzelt" and n:
            self._yazi_duzelt_baslat(*n)
        elif self.mod == "yazi_ekle" and n:
            self._yazi_ekle_baslat(*n)
        elif self.mod == "damga" and n:
            self.u.damga_bas(*n)
        elif self.mod == "set" and n:
            self.u.set_bas(*n)
        elif self.mod == "not" and n:
            self.u.not_bas(*n)

    def _surukle_hareket(self, e):
        if not self._surukle:
            return
        if self._surukle[0] == "nesne":
            self._nesne_surukle(e)
            return
        if self._surukle[0] == "kaydir":
            self.tuval.scan_dragto(e.x, e.y, gain=1)
            self._gecikmeli_ciz()
        elif self._surukle[0] == "kutu":
            _, i, x0, y0, _, _ = self._surukle
            x, y, w, h = self.yerler[i]
            cx = min(max(self.tuval.canvasx(e.x), x), x + w)
            cy = min(max(self.tuval.canvasy(e.y), y), y + h)
            self.tuval.delete("secim")
            self.tuval.delete("hayalet")
            renk = self.MOD_RENKLERI.get(self.mod, "#4F46E5")
            if self.mod in ("sekil_cizgi", "sekil_ok"):
                self.tuval.create_line(x0, y0, cx, cy, fill="#C0392B", width=2,
                                       arrow="last" if self.mod == "sekil_ok" else None, tags="secim")
            elif self.mod == "sekil_elips":
                self.tuval.create_oval(x0, y0, cx, cy, outline="#C0392B", width=2, tags="secim")
            else:
                dolgu = {"beyaz_kutu": "white", "karart": "black"}.get(self.mod, "")
                stip = "gray50" if self.mod in ("karart", "vurgula") else ""
                if self.mod == "vurgula":
                    dolgu = "#FFE94D"
                self.tuval.create_rectangle(x0, y0, cx, cy, outline=renk, width=2, dash=(5, 3),
                                            fill=dolgu, stipple=stip, tags="secim")

    def _birak(self, e):
        s = self._surukle
        self._surukle = None
        if not s:
            return
        if s[0] == "nesne":
            self.tuval.delete("nesne_hayalet")
            self._nesne_foto = None
            r = getattr(self, "_nesne_yeni", None)
            if r is not None and fitz.Rect(r) != fitz.Rect(s[6]):
                self.u.nesne_guncelle(s[2], r, "İmza / kaşe taşıma" if s[1] == "tasi" else "İmza / kaşe boyutlandırma")
            return
        if s[0] == "kaydir":
            if self.mod == "sec":
                self.tuval.configure(cursor="arrow")
            return
        self.tuval.delete("secim")
        _, i, cx0, cy0, px0, py0 = s
        x, y, w, h = self.yerler[i]
        cx1 = min(max(self.tuval.canvasx(e.x), x), x + w)
        cy1 = min(max(self.tuval.canvasy(e.y), y), y + h)
        px1, py1 = (cx1 - x) / self.olcek, (cy1 - y) / self.olcek
        rect = fitz.Rect(min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))
        if self.mod == "imza":
            if rect.width < 5 or rect.height < 5:
                rect = None   # tek tik: varsayilan genislik, tiklanan yer merkez
            self.u.imza_yerlestir(i, rect, (px0, py0))
            return
        if self.mod in ("sekil_cizgi", "sekil_ok"):
            if abs(px1 - px0) + abs(py1 - py0) > 3:
                self.u.alan_secildi(self.mod, i, rect, (px0, py0), (px1, py1))
            return
        if self.mod == "form_onay" and (rect.width < 5 or rect.height < 5):
            rect = fitz.Rect(px0 - 6, py0 - 6, px0 + 6, py0 + 6)       # tek tik: 12 pt kutu
        if self.mod == "metin_kutusu" and (rect.width < 10 or rect.height < 8):
            rect = fitz.Rect(px0, py0, px0 + 180, py0 + 50)
        if rect.width > 2 and rect.height > 2:
            self.u.alan_secildi(self.mod, i, rect, (px0, py0), (px1, py1))

    def _cift_tik(self, e):
        if self.mod == "sec" and self.belge:
            n = self.nokta(e)
            if n:
                self.u.mod_sec("yazi_duzelt")
                self._yazi_duzelt_baslat(*n)

    # ---------------------------------------------------------- yazi duzenleyici
    def _tk_font(self, ayar, boyut):
        aile = ayar.get("aile")
        if not aile or aile.startswith("Otomatik") or aile.startswith("─"):
            serif = ayar.get("serif", False)
            if WINDOWS:
                aile = "Times New Roman" if serif else "Arial"
            else:
                aile = "DejaVu Serif" if serif else "DejaVu Sans"
        agirlik = "bold" if ayar.get("kalin") else "normal"
        egik = "italic" if ayar.get("italik") else "roman"
        return (aile, -max(6, int(round(boyut * self.olcek))), agirlik, egik)

    def _yazi_duzelt_baslat(self, i, px, py):
        sayfa = self.belge.doc[i]
        if sayfa.rotation:
            # once sayfayi duzle (gorunum ayni kalir), sonra tekrar ara
            self.belge.anlik()
            Z.sayfa_hazirla(sayfa)
            self.belge.degisiklik()
            self.yenile()
        satir = Z.satir_bul(self.belge.doc[i], px, py, veri=self._metin_verisi(i))
        if not satir or satir.get("gorunmez"):
            # resim / tarama uzerindeki yazi: OCR ile oku, dokuyu koruyarak duzelt
            self.u.resimde_yazi_bul(i, px, py, yedek=satir)
            return
        self._vurgu_temizle()
        stil = {"aile": "Otomatik (orijinal)", "boyut": satir["boyut"], "kalin": satir["kalin"],
                "italik": satir["italik"], "serif": satir["serif"], "renk": satir["renk"], "hiza": "sol"}
        self._duzenleyici_ac("duzelt", i, satir, satir["bbox"], satir["metin"], stil)

    def resim_duzenleyici_ac(self, i, bilgi):
        """Resimden OCR ile okunan yazi icin duzenleyici."""
        self._vurgu_temizle()
        stil = {"aile": "Otomatik (orijinal)", "boyut": bilgi["boyut"], "kalin": bilgi["kalin"],
                "italik": False, "serif": False, "renk": bilgi["renk"], "hiza": "sol"}
        self._duzenleyici_ac("resim", i, bilgi, bilgi["kutu"], bilgi["metin"], stil)
        x0, y0, x1, y1 = self.tuval_rect(i, bilgi["kutu"])
        self.tuval.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, outline="#2E9E6B", width=2,
                                    dash=(4, 2), tags="duzen")

    def _yazi_ekle_baslat(self, i, px, py):
        ayar = self.u.yazi_ayar()
        stil = {"aile": ayar.get("aile") or "Otomatik (orijinal)", "boyut": ayar["boyut"], "kalin": ayar["kalin"],
                "italik": False, "serif": ayar["serif"], "renk": ayar["renk"], "hiza": "sol"}
        b = ayar["boyut"]
        self._duzenleyici_ac("ekle", i, (px, py + b * 0.1), (px, py - b * 0.8, px + 150, py + b * 0.3), "", stil)

    def _duzenleyici_ac(self, tur, i, bilgi, bbox, metin, stil):
        """tur: 'duzelt' (PDF yazisi) | 'resim' (resimdeki yazi) | 'ekle' (yeni yazi)"""
        x0, y0, x1, y1 = self.tuval_rect(i, bbox)
        self._stil = dict(stil)
        self._stil_ilk = dict(stil)
        coklu = "\n" in metin
        if tur == "resim" and abs(bilgi.get("yon_aci", 0)) in (90, 270):
            # yan yazilmis yazi: duzenleyiciyi yatay ac, kutunun yanina koy
            x0, y0, x1, y1 = x0, y0, max(x1, x0 + 220), y0 + (x1 - x0)
        renk = "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in self._stil["renk"])
        font = self._tk_font(self._stil, self._stil["boyut"])
        ortak = dict(font=font, relief="solid", bd=1, fg=renk, bg="#FFFBEA", insertbackground="#C0392B",
                     highlightthickness=2, highlightcolor="#E8590C", highlightbackground="#E8590C")
        satir_px = (bilgi.get("satir_araligi") if isinstance(bilgi, dict) else None) or self._stil["boyut"] * 1.2
        satir_px *= self.olcek
        if not coklu:
            var = tk.StringVar(value=metin)
            giris = tk.Entry(self.tuval, textvariable=var, **ortak)
            en_az = max(x1 - x0 + 40, 180)
            pencere = self.tuval.create_window(x0 - 4, y0 - 4, window=giris, anchor="nw", width=en_az,
                                               height=max(y1 - y0, abs(font[1]) * 1.3) + 10, tags="duzen")
            self._genislik_izle(giris, var, pencere, en_az)
            giris.icursor("end")
            ipucu = "Enter = uygula · Esc = vazgeç · Üstteki çubuktan yazı tipi / boyut / renk değiştirilebilir"
        else:
            giris = tk.Text(self.tuval, wrap="none", undo=True, padx=2, pady=0, spacing1=0, spacing3=0, **ortak)
            giris.insert("1.0", metin)
            giris.configure(spacing2=max(0, int(satir_px - abs(font[1]) * 1.17)))
            sag = bilgi.get("sag_sinir", 0) if isinstance(bilgi, dict) else 0
            sag_px = (sag - bbox[0]) * self.olcek + 30 if sag else 0
            pencere = self.tuval.create_window(x0 - 4, y0 - 4, window=giris, anchor="nw",
                                               width=max(x1 - x0 + 60, 220, sag_px),
                                               height=(y1 - y0) + satir_px * 0.6 + 14, tags="duzen")
            giris.mark_set("insert", "end-1c")
            var = _MetinOkuyucu(giris)
            ipucu = "Enter = uygula · Shift+Enter = yeni satır · Esc = vazgeç"

        def enter(e):
            if isinstance(giris, tk.Text) and (e.state & 0x0001):
                return None
            self._duzenleyici_kapat(uygula=True)
            return "break"
        giris.focus_set()
        self._duzenleyici = (tur, giris, i, bilgi, var)
        giris.bind("<Return>", enter)
        giris.bind("<KP_Enter>", enter)
        giris.bind("<Escape>", lambda e: (self._duzenleyici_kapat(uygula=False), "break")[1])
        self._stil_cubugu(x0, y0, giris)
        self.u.durum_yaz(ipucu)

    def _stil_cubugu(self, x0, y0, giris):
        """Duzenleyicinin ustunde: yazi tipi, boyut, kalin, renk, hizalama, uygula/vazgec."""
        from tkinter import ttk, colorchooser
        from . import fontlar
        st = self._stil
        f = tk.Frame(self.tuval, bg="#312E81", padx=4, pady=3)
        aileler = ["Otomatik (orijinal)"] + (fontlar.aileler() if fontlar.hazir() else fontlar.ONERILEN)
        aile = ttk.Combobox(f, values=aileler, width=22, state="readonly", font=("Segoe UI" if WINDOWS else "DejaVu Sans", 9))
        aile.set(st["aile"] if st["aile"] in aileler else "Otomatik (orijinal)")
        aile.pack(side="left", padx=(0, 4))
        boyut = tk.StringVar(value=f"{st['boyut']:.1f}".rstrip("0").rstrip("."))
        sp = ttk.Spinbox(f, from_=4, to=144, increment=0.5, width=5, textvariable=boyut)
        sp.pack(side="left", padx=2)
        kalin = tk.BooleanVar(value=st["kalin"])
        kb = tk.Checkbutton(f, text="K", variable=kalin, bg="#312E81", fg="white", selectcolor="#4338CA",
                            font=("Arial", 9, "bold"), activebackground="#312E81", activeforeground="white")
        kb.pack(side="left", padx=2)
        renk_btn = tk.Label(f, text="  ", bg="#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in st["renk"]),
                            relief="solid", bd=1, width=3, cursor="hand2")
        renk_btn.pack(side="left", padx=4)
        hiza = tk.StringVar(value=st["hiza"])
        for deger, simge in (("sol", "⇤"), ("orta", "⇔"), ("sag", "⇥")):
            tk.Radiobutton(f, text=simge, value=deger, variable=hiza, indicatoron=False, width=2,
                           bg="#4338CA", fg="white", selectcolor="#4F46E5", font=("Arial", 9),
                           activebackground="#6366F1", bd=0).pack(side="left", padx=1)
        tk.Button(f, text="✔", bg="#10B981", fg="white", bd=0, padx=8, font=("Arial", 9, "bold"),
                  command=lambda: self._duzenleyici_kapat(True)).pack(side="left", padx=(6, 2))
        tk.Button(f, text="✖", bg="#E11D48", fg="white", bd=0, padx=8, font=("Arial", 9, "bold"),
                  command=lambda: self._duzenleyici_kapat(False)).pack(side="left")

        def guncelle(*_):
            try:
                b = float(str(boyut.get()).replace(",", "."))
            except ValueError:
                b = st["boyut"]
            st.update(aile=aile.get() if not aile.get().startswith("─") else st["aile"],
                      boyut=max(3.0, min(144.0, b)), kalin=kalin.get(), hiza=hiza.get())
            try:
                giris.configure(font=self._tk_font(st, st["boyut"]))
            except tk.TclError:
                pass

        def renk_sec(e=None):
            ilk = "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in st["renk"])
            r = colorchooser.askcolor(color=ilk, parent=self, title="Yazı rengi")
            if r and r[1]:
                st["renk"] = tuple(v / 255 for v in r[0])
                renk_btn.config(bg=r[1])
                try:
                    giris.configure(fg=r[1])
                except tk.TclError:
                    pass
            giris.focus_set()
        renk_btn.bind("<Button-1>", renk_sec)
        aile.bind("<<ComboboxSelected>>", lambda e: (guncelle(), giris.focus_set()))
        boyut.trace_add("write", guncelle)
        kalin.trace_add("write", guncelle)
        hiza.trace_add("write", guncelle)
        self.tuval.create_window(x0 - 4, y0 - 8, window=f, anchor="sw", tags="stil")

    def _genislik_izle(self, giris, var, pencere, en_az):
        """Yazdikca kutuyu buyutur."""
        import tkinter.font as tkfont

        def ayarla(*_):
            try:
                f = tkfont.Font(font=giris.cget("font"))
                self.tuval.itemconfigure(pencere, width=max(en_az, f.measure(var.get() + "WW") + 12))
            except tk.TclError:
                pass
        var.trace_add("write", ayarla)
        ayarla()

    def _secilen_font(self, st):
        """Stil cubugunda secilen aile -> fitz.Font (Otomatik ise None)."""
        from . import fontlar
        aile = st.get("aile") or ""
        if aile.startswith("Otomatik") or aile.startswith("─"):
            return None
        return fontlar.font(aile, st.get("kalin", False), st.get("italik", False))

    def _duzenleyici_kapat(self, uygula=True):
        d = self._duzenleyici
        if not d:
            return
        self._duzenleyici = None
        tur, giris, i, bilgi, var = d
        metin = var.get()
        st = getattr(self, "_stil", {}) or {}
        ilk = getattr(self, "_stil_ilk", {}) or {}
        self.tuval.delete("duzen")
        self.tuval.delete("stil")
        try:
            giris.destroy()
        except Exception:
            pass
        if not uygula:
            self.u.durum_yaz("Vazgeçildi.")
            return
        font = self._secilen_font(st)
        boyut = st.get("boyut") if abs(st.get("boyut", 0) - ilk.get("boyut", 0)) > 0.01 else None
        renk = st.get("renk") if st.get("renk") != ilk.get("renk") else None
        kalin = st.get("kalin") if st.get("kalin") != ilk.get("kalin") else None
        hiza = st.get("hiza", "sol")
        stil_degisti = any(v is not None for v in (font, boyut, renk, kalin)) or hiza != "sol"
        if tur == "duzelt":
            if metin == bilgi["metin"] and not stil_degisti:
                return
            if font is None and kalin is not None:
                font = Z.font_sec(self.belge.doc[i], bilgi, metin, kalin)
            self.u.duzenle_islem("Yazı düzeltme", lambda doc: Z.satir_degistir(
                doc[i], bilgi, metin, boyut=boyut, renk=renk, kalin=kalin, font=font, hiza=hiza), i)
        elif tur == "resim":
            if metin == bilgi["metin"] and not stil_degisti:
                return
            from . import resim_yazi as R
            if font is None and kalin is not None:
                font = Z.font_al(False, kalin, False)
            self.u.duzenle_islem("Resimdeki yazıyı düzeltme", lambda doc: R.degistir(
                doc[i], bilgi, metin, font=font, boyut=boyut, renk=renk, hiza=hiza), i)
        else:
            if not metin.strip():
                return
            px, py = bilgi
            b = st.get("boyut", 11)
            rk = st.get("renk", (0, 0, 0))
            f = font or Z.font_al(st.get("serif", False), st.get("kalin", False), False)
            self.u.yazi_ayar_kaydet(st)

            def ekle(doc):
                Z.sayfa_hazirla(doc[i])
                for k, satir in enumerate(metin.split("\n")):
                    Z._yaz(doc[i], px, py + k * b * 1.25, satir, b, rk, font=f)
            self.u.duzenle_islem("Yazı ekleme", ekle, i)


class _MetinOkuyucu:
    """tk.Text icin StringVar benzeri get()."""

    def __init__(self, w):
        self.w = w
        self._son = w.get("1.0", "end-1c")

    def get(self):
        try:
            self._son = self.w.get("1.0", "end-1c")
        except tk.TclError:
            pass
        return self._son


# ================================================================== kucuk resimler
class KucukResimler(tk.Frame):
    GEN = 118
    ZEMIN = "#F6F7FB"

    def __init__(self, ust, uygulama):
        super().__init__(ust, bg=self.ZEMIN)
        self.u = uygulama
        self.belge = None
        self.yerler = []
        self.onbellek = {}
        self._zaman = None
        self._surukle = None
        self.tuval = tk.Canvas(self, bg=self.ZEMIN, highlightthickness=0, width=self.GEN + 44, yscrollincrement=20)
        from tkinter import ttk
        sb = ttk.Scrollbar(self, orient="vertical", command=self._kaydir, style="Belge.Vertical.TScrollbar")
        self.tuval.configure(yscrollcommand=lambda a, b: (sb.set(a, b), self._gecikmeli()))
        self.tuval.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        t = self.tuval
        t.bind("<Configure>", lambda e: self.yerlestir())
        t.bind("<MouseWheel>", lambda e: (t.yview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units"), self._gecikmeli()))
        t.bind("<Button-4>", lambda e: (t.yview_scroll(-3, "units"), self._gecikmeli()))
        t.bind("<Button-5>", lambda e: (t.yview_scroll(3, "units"), self._gecikmeli()))
        t.bind("<ButtonPress-1>", self._bas)
        t.bind("<B1-Motion>", self._hareket)
        t.bind("<ButtonRelease-1>", self._birak)
        t.bind("<Button-3>", self._sag_tik)
        t.bind("<Delete>", lambda e: self.u.sayfa_sil())

    def _kaydir(self, *a):
        self.tuval.yview(*a)
        self._gecikmeli()

    def goster(self, belge):
        self.belge = belge
        self.onbellek.clear()
        self.yerlestir()

    def yenile(self):
        self.onbellek = {k: v for k, v in self.onbellek.items() if k[1] == (self.belge.surum if self.belge else -1)}
        self.yerlestir()

    def yerlestir(self):
        t = self.tuval
        t.delete("all")
        self.yerler = []
        self._ys = []
        if not self.belge:
            t.configure(scrollregion=(0, 0, 1, 1))
            return
        cw = max(t.winfo_width(), self.GEN + 40)
        y = 12
        for p in self.belge.doc:
            r = p.rect
            olc = self.GEN / max(r.width, r.height * 0.75)
            w, h = r.width * olc, r.height * olc
            x = (cw - w) / 2
            self.yerler.append((x, y, w, h))
            y += h + 34
        t.configure(scrollregion=(0, 0, cw, y))
        self.cerceve_ciz()
        self._gecikmeli()

    def cerceve_ciz(self):
        t = self.tuval
        t.delete("cerceve")
        if not self.belge:
            return
        for i, (x, y, w, h) in enumerate(self.yerler):
            secili = i in self.belge.secili
            aktif = i == self.belge.aktif
            if secili:
                t.create_rectangle(x - 7, y - 7, x + w + 7, y + h + 24, fill="#E0E7FF",
                                   outline="#4F46E5", width=2, tags="cerceve")
            t.create_rectangle(x, y, x + w, y + h, fill="white", outline="#9AA5B4" if not aktif else "#4F46E5",
                               width=1 if not aktif else 2, tags=("cerceve", "kutu"))
            t.create_text(x + w / 2, y + h + 11, text=str(i + 1), fill="#4338CA" if (secili or aktif) else "#6B7685",
                          font=("Segoe UI" if WINDOWS else "DejaVu Sans", 9, "bold" if aktif else "normal"), tags="cerceve")
        t.tag_lower("cerceve")
        t.tag_raise("resim")

    def _gecikmeli(self):
        if self._zaman:
            self.after_cancel(self._zaman)
        self._zaman = self.after(60, self.ciz)

    def ciz(self):
        self._zaman = None
        if not self.belge:
            return
        if self.u.mesgul_render:
            self._zaman = self.after(400, self.ciz)
            return
        t = self.tuval
        ust, alt = t.canvasy(0), t.canvasy(t.winfo_height())
        t.delete("resim")
        for i, (x, y, w, h) in enumerate(self.yerler):
            if y + h < ust - 20 or y > alt + 20:
                continue
            k = (i, self.belge.surum)
            img = self.onbellek.get(k)
            if img is None:
                try:
                    p = self.belge.doc[i]
                    s = w / p.rect.width
                    pix = p.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False, annots=True)
                    img = tk.PhotoImage(data=pix.tobytes("ppm"))
                    self.onbellek[k] = img
                except Exception:
                    continue
            t.create_image(x, y, image=img, anchor="nw", tags=("resim", f"r{i}"))
        t.tag_raise("resim")

    def aktif_gorunur_yap(self):
        if not self.belge or self.belge.aktif >= len(self.yerler):
            return
        x, y, w, h = self.yerler[self.belge.aktif]
        t = self.tuval
        ust, alt = t.canvasy(0), t.canvasy(t.winfo_height())
        if y < ust or y + h > alt:
            toplam = float(t.cget("scrollregion").split()[3] or 1)
            t.yview_moveto(max(0, (y - 20) / toplam))
            self._gecikmeli()

    def _indeks(self, e):
        cy = self.tuval.canvasy(e.y)
        cx = self.tuval.canvasx(e.x)
        for i, (x, y, w, h) in enumerate(self.yerler):
            if y - 8 <= cy <= y + h + 26 and x - 10 <= cx <= x + w + 10:
                return i
        return None

    def _bas(self, e):
        self.tuval.focus_set()
        i = self._indeks(e)
        if i is None or not self.belge:
            return
        b = self.belge
        if e.state & 0x0004:            # Ctrl
            if i in b.secili and len(b.secili) > 1:
                b.secili.discard(i)
            else:
                b.secili.add(i)
        elif e.state & 0x0001:          # Shift
            a = b.aktif
            b.secili = set(range(min(a, i), max(a, i) + 1))
        else:
            if i not in b.secili:
                b.secili = {i}
            self._surukle = (i, e.y, False)
        self.cerceve_ciz()
        self.u.gorunum.sayfaya_git(i)

    def _hareket(self, e):
        if not self._surukle:
            return
        i, y0, basladi = self._surukle
        if not basladi and abs(e.y - y0) < 8:
            return
        self._surukle = (i, y0, True)
        self.tuval.configure(cursor="sb_v_double_arrow")
        hedef = self._hedef(e)
        self.tuval.delete("cizgi")
        if hedef is not None:
            if hedef < len(self.yerler):
                x, y, w, h = self.yerler[hedef]
                yy = y - 17
            else:
                x, y, w, h = self.yerler[-1]
                yy = y + h + 17
            self.tuval.create_line(10, yy, self.tuval.winfo_width() - 10, yy, fill="#E8590C", width=3, tags="cizgi")
        # kenara gelince kaydir
        if e.y < 20:
            self.tuval.yview_scroll(-1, "units")
        elif e.y > self.tuval.winfo_height() - 20:
            self.tuval.yview_scroll(1, "units")

    def _hedef(self, e):
        cy = self.tuval.canvasy(e.y)
        for i, (x, y, w, h) in enumerate(self.yerler):
            if cy < y + h / 2:
                return i
        return len(self.yerler)

    def _birak(self, e):
        s = self._surukle
        self._surukle = None
        self.tuval.delete("cizgi")
        self.tuval.configure(cursor="arrow")
        if not s or not s[2] or not self.belge:
            if s and not s[2] and self.belge:
                self.belge.secili = {s[0]}
                self.cerceve_ciz()
            return
        hedef = self._hedef(e)
        self.u.sayfa_tasi(sorted(self.belge.secili), hedef)

    def _sag_tik(self, e):
        i = self._indeks(e)
        if i is None or not self.belge:
            return
        if i not in self.belge.secili:
            self.belge.secili = {i}
            self.belge.aktif = i
            self.cerceve_ciz()
        self.u.sayfa_menusu(e.x_root, e.y_root)
