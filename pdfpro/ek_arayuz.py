# -*- coding: utf-8 -*-
"""
PDF PRO - Ek islemler (ana pencereye karisim sinifi olarak eklenir)
Tarama, e-posta, yedekler, not / metin kutusu, form olusturma, karsilastirma, QR, onarim,
yeni donusturmeler, yapay zeka, is akislari, belge paketi, imza + kase setleri.
"""
import copy
import os
import re
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from .cekirdek import fitz, PdfProHata, BilesenEksik, benzersiz_yol
from . import cekirdek as C
from . import araclar as AR
from . import donustur as D
from . import duzenle as Z
from . import diyaloglar as DG
from . import yedek as YD
from . import yapay_zeka as YZ
from . import otomasyon as OT
from . import cihaz as CH
from . import fontlar

try:
    from tkinterdnd2 import DND_FILES
except Exception:
    DND_FILES = None


def _A():
    from . import arayuz
    return arayuz


PPT_TUR = [("PowerPoint", "*.pptx *.ppt *.ppsx *.pps *.odp"), ("Tüm dosyalar", "*.*")]
HTML_TUR = [("Web sayfası", "*.html *.htm *.mht *.mhtml"), ("Tüm dosyalar", "*.*")]
HER_TUR = [("PDF, resim, Office", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.docx *.doc *.xlsx *.xls *.pptx *.ppt *.html *.htm"),
           ("Tüm dosyalar", "*.*")]
KONUMLAR = ["Sağ alt", "Orta alt", "Sol alt", "Sağ üst", "Orta üst", "Sol üst", "Orta"]


def _drop_yollari(w, veri):
    try:
        return [os.path.normpath(y) for y in w.tk.splitlist(veri)]
    except Exception:
        return [veri]


class _Pencere(tk.Toplevel):
    """Grab'li, ortalanan basit pencere."""

    def __init__(self, ust, baslik, boyut="640x520"):
        super().__init__(ust)
        A = _A()
        self.title(baslik)
        self.configure(bg=A.R_KART)
        self.transient(ust)
        self.geometry(boyut)
        self._gen = int(boyut.split("x")[0])
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        try:
            w, h = (int(x) for x in boyut.split("x"))
            x = ust.winfo_rootx() + (ust.winfo_width() - w) // 2
            y = ust.winfo_rooty() + (ust.winfo_height() - h) // 3
            self.geometry(f"{boyut}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def baslik(self, metin, alt=None):
        A = _A()
        renk = DG.baslik_rengi(self.master)
        bant = tk.Frame(self, bg=renk)
        bant.pack(fill="x")
        tk.Label(bant, text=metin, bg=renk, fg="white", font=(A.FONT, 13, "bold")).pack(anchor="w", padx=16, pady=(10, 9))
        if alt:
            tk.Label(self, text=alt, bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 9), justify="left",
                     wraplength=getattr(self, '_gen', 640) - 40).pack(anchor="w", padx=16, pady=(8, 6))


class EkIslemler:
    # ================================================================== bilesen eksikse
    def _bilesen_hatasi(self, e):
        if isinstance(e, BilesenEksik):
            if messagebox.askyesno("PDF PRO", f"{e.ad} kurulu değil.\nŞimdi internetten kurulsun mu? (1-2 dakika)"):
                self.bilesen_kur([e.paket], e.ad)
            return True
        return False

    def calistir_bilesenli(self, baslik, fonk, bitince=None, iptal_edilebilir=False):
        """calistir() gibi; BilesenEksik hatasinda kurulum teklif eder."""
        def sarmal(il, ip):
            try:
                return ("ok", fonk(il, ip))
            except BilesenEksik as e:
                return ("bilesen", e)

        def bitti(r):
            if r[0] == "bilesen":
                self._bilesen_hatasi(r[1])
            elif bitince:
                bitince(r[1])
        self.calistir(baslik, sarmal, bitti, iptal_edilebilir)

    # ================================================================== DOSYA: tara, e-posta, yedek
    def tara(self):
        A = _A()
        d = DG.Diyalog(self, "📠 Tarayıcıdan Tara",
                       "Windows'un tarama penceresi açılır. Her sayfadan sonra 'başka sayfa?' diye sorulur; "
                       "bitince tüm sayfalar tek PDF olarak açılır.", dugme="Taramaya Başla")
        renk = ttk.Combobox(d.govde, values=["Renkli", "Gri", "Siyah-beyaz"], state="readonly", width=14)
        renk.set(self.ayar.get("tara_renk", "Gri"))
        d.satir("Renk:", renk, "Gri = belge için ideal, küçük dosya")
        ocr = tk.BooleanVar(value=self.ayar.get("tara_ocr", True))
        d.tam_satir(ttk.Checkbutton(d.govde, text="Bitince aranabilir yap (OCR)", variable=ocr, style="Kart.TCheckbutton"))
        d.topla = lambda: {"renk": renk.get(), "ocr": ocr.get()}
        s = d.ac()
        if not s:
            return
        self.ayar.update(tara_renk=s["renk"], tara_ocr=s["ocr"])
        klasor = CH.tarama_klasoru()
        sayfalar = []
        while True:
            try:
                self.durum_yaz(f"📠 Taranıyor… (sayfa {len(sayfalar) + 1})")
                y = CH.tara_sayfa(klasor, len(sayfalar) + 1, s["renk"])
            except PdfProHata as e:
                if messagebox.askyesno("PDF PRO", f"{e}\n\nWindows Faks ve Tarama programı açılsın mı?\n"
                                                  "(Orada tarayıp kaydettiğiniz resmi PDF PRO'ya sürükleyebilirsiniz.)"):
                    CH.windows_tarama_ac()
                break
            if not y:
                break
            sayfalar.append(y)
            if not messagebox.askyesno("PDF PRO", f"{len(sayfalar)}. sayfa tarandı.\n\nBaşka sayfa taransın mı?\n"
                                                  "(Sonraki sayfayı tarayıcıya koyup Evet'e basın)"):
                break
        if not sayfalar:
            self.durum_yaz("Tarama yapılmadı.")
            return
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_tarama.pdf")
        ad = f"Tarama_{__import__('datetime').datetime.now():%Y%m%d_%H%M}.pdf"

        def is_(il, ip):
            D.resim_to_pdf(sayfalar, gecici, "A4 otomatik", 0, il)
            if s["ocr"]:
                from . import ocr as O
                if O.ocr_durumu()[0]:
                    c = gecici[:-4] + "_ocr.pdf"
                    O.aranabilir_pdf(gecici, c, "tur+eng", 300, True, il, ip)
                    os.replace(c, gecici)
            return gecici

        def bitti(r):
            self._gecici_belge(r, ad)
            self.durum_yaz(f"✔ {len(sayfalar)} sayfa tarandı. Kaydetmek için Ctrl+S.", basari=True)
        self.calistir("Tarama PDF'e çevriliyor", is_, bitti)

    def eposta(self):
        A = _A()
        b = self._belge_gerekli()
        if not b:
            return
        d = DG.Diyalog(self, "📧 E-posta ile Gönder",
                       "Outlook'ta yeni bir ileti açılır, PDF ekli olur. Kontrol edip 'Gönder'e siz basarsınız.",
                       dugme="İletiyi Hazırla")
        konu = ttk.Entry(d.govde, width=40)
        konu.insert(0, os.path.splitext(b.ad)[0])
        d.satir("Konu:", konu)
        alici = ttk.Entry(d.govde, width=40)
        alici.insert(0, self.ayar.get("eposta_alici", ""))
        d.satir("Alıcı:", alici, "boş bırakabilirsiniz")
        sik = tk.BooleanVar(value=True)
        d.tam_satir(ttk.Checkbutton(d.govde, text="10 MB'tan büyükse önce sıkıştır", variable=sik, style="Kart.TCheckbutton"))
        d.topla = lambda: {"konu": konu.get().strip(), "alici": alici.get().strip(), "sik": sik.get()}
        s = d.ac()
        if not s:
            return
        self.ayar["eposta_alici"] = s["alici"]
        klasor = os.path.join(tempfile.gettempdir(), "pdfpro_eposta")
        os.makedirs(klasor, exist_ok=True)
        ad = b.ad if b.ad.lower().endswith(".pdf") else b.ad + ".pdf"
        hedef = os.path.join(klasor, ad)

        try:
            with open(hedef, "wb") as f:
                f.write(b.doc.tobytes(garbage=3, deflate=True))
        except Exception as e:
            messagebox.showerror("PDF PRO", f"Ek hazırlanamadı:\n{e}")
            return

        def gonder(yol):
            try:
                tur = CH.eposta_gonder([yol], s["konu"], "", s["alici"])
                self.durum_yaz("✔ E-posta hazırlandı (Outlook)." if tur == "outlook"
                               else "✔ E-posta taslağı varsayılan posta programında açıldı.", basari=True)
            except PdfProHata as e:
                messagebox.showerror("PDF PRO", str(e))

        if s["sik"] and os.path.getsize(hedef) > 10 * 1024 * 1024:
            kucuk = hedef[:-4] + "_k.pdf"

            def bitti(r):
                os.replace(r[0], hedef)
                gonder(hedef)
            self.calistir("Sıkıştırılıyor", lambda il, ip: C.sikistir(hedef, kucuk, "orta", 10 * 1024, False, il, ip), bitti, True)
        else:
            gonder(hedef)

    def yedekler(self):
        A = _A()
        b = self.belge
        p = _Pencere(self, "Yedekler", "640x460")
        tum = YD.tum_yedekler()
        if b and b.yol:
            tum.sort(key=lambda t: os.path.normcase(t["kaynak"]) != os.path.normcase(b.yol))
        p.baslik("🕘 Yedekler", "Bir dosyanın üzerine kaydettiğinizde eski hali otomatik saklanır (dosya başına son 10). "
                              "Seçip açabilir ya da dosyayı o haline geri döndürebilirsiniz.")
        if not tum:
            tk.Label(p, text="Henüz yedek yok.", bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 11)).pack(pady=40)
            return
        ust = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0))
        ust.pack(fill="x")
        dosya = ttk.Combobox(ust, state="readonly", width=70,
                             values=[os.path.basename(t["kaynak"]) + "   —   " + os.path.dirname(t["kaynak"]) for t in tum])
        dosya.current(0)
        dosya.pack(fill="x")
        liste = tk.Listbox(p, font=(A.FONT, 10), activestyle="none", selectbackground=A.R_VURGU, height=12)
        liste.pack(fill="both", expand=True, padx=16, pady=8)

        def doldur(e=None):
            liste.delete(0, "end")
            for y in tum[dosya.current()]["yedekler"]:
                liste.insert("end", f"  {y['zaman']:%d.%m.%Y  %H:%M:%S}     {A.boyut_yaz(y['boyut'])}")
            if liste.size():
                liste.selection_set(0)
        dosya.bind("<<ComboboxSelected>>", doldur)
        doldur()

        def secili():
            s = liste.curselection()
            return tum[dosya.current()]["yedekler"][s[0]] if s else None

        def ac():
            y = secili()
            if y:
                g = os.path.join(tempfile.gettempdir(), "pdfpro_yedek_ac.pdf")
                import shutil
                shutil.copyfile(y["yol"], g)
                ad = os.path.splitext(os.path.basename(tum[dosya.current()]["kaynak"]))[0]
                p.destroy()
                self._gecici_belge(g, f"{ad}_yedek_{y['zaman']:%H%M}.pdf")

        def geri():
            y = secili()
            if not y:
                return
            kaynak = tum[dosya.current()]["kaynak"]
            if not messagebox.askyesno("PDF PRO", f"{os.path.basename(kaynak)}\n\n{y['zaman']:%d.%m.%Y %H:%M} "
                                                  "tarihli hale geri döndürülsün mü?\n(Şimdiki hali de yedeklenir.)", parent=p):
                return
            import shutil
            acik = next((x for x in self.belgeler if x.yol and os.path.normcase(x.yol) == os.path.normcase(kaynak)), None)
            if acik is not None and acik.degisti:
                if not messagebox.askyesno("PDF PRO", "Bu dosya açık ve kaydedilmemiş değişiklikleri var. Yine de devam edilsin mi?", parent=p):
                    return
            try:
                if acik is not None:
                    acik.kapat()
                    self.belgeler.remove(acik)
                YD.yedekle(kaynak)
                shutil.copyfile(y["yol"], kaynak)
            except Exception as e:
                messagebox.showerror("PDF PRO", f"Geri yüklenemedi:\n{e}", parent=p)
                return
            p.destroy()
            if acik is not None:
                self.belge = None
            self.ac([kaynak])
            self.durum_yaz("✔ Yedekten geri yüklendi.", basari=True)

        alt = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0, 16, 14))
        alt.pack(fill="x")
        ttk.Button(alt, text="Kapat", style="Ikincil.TButton", command=p.destroy).pack(side="right")
        ttk.Button(alt, text="↩ Dosyayı Bu Hale Döndür", style="Ikincil.TButton", command=geri).pack(side="right", padx=6)
        ttk.Button(alt, text="📄 Yeni Sekmede Aç", style="Ana.TButton", command=ac).pack(side="right")
        ttk.Button(alt, text="📁 Yedek Klasörü", style="Ikincil.TButton",
                   command=lambda: A.dosya_ac(YD.YEDEK_KLASORU)).pack(side="left")
        liste.bind("<Double-Button-1>", lambda e: ac())

    def yedek_al(self, yol):
        """Kaydetmeden once cagrilir (ayar kapali degilse)."""
        if not self.ayar.get("otomatik_yedek", True):
            return
        try:
            YD.yedekle(yol)
        except Exception:
            pass

    # ================================================================== ISARETLE: not, metin kutusu
    def _metin_sor(self, baslik, aciklama, varsayilan="", satir=5):
        A = _A()
        d = DG.Diyalog(self, baslik, aciklama, dugme="Tamam", genislik=460)
        t = tk.Text(d.govde, width=50, height=satir, font=(A.FONT, 10), wrap="word", relief="solid", bd=1)
        t.insert("1.0", varsayilan)
        d.tam_satir(t)
        t.focus_set()
        d.topla = lambda: {"metin": t.get("1.0", "end-1c").strip()}
        s = d.ac()
        return s["metin"] if s and s["metin"] else None

    def not_bas(self, i, px, py):
        m = self._metin_sor("💬 Not Ekle", "Sayfada küçük bir not simgesi görünür; üzerine gelince / tıklayınca not okunur.")
        if not m:
            return
        yazar = self.ayar.get("not_yazar") or os.environ.get("USERNAME") or "PDF PRO"
        self.duzenle_islem("Not", lambda d: AR.not_ekle(d[i], (px, py), m, yazar), i)

    def _ek_alan_secildi(self, mod, i, rect):
        if mod == "metin_kutusu":
            m = self._metin_sor("🗨 Metin Kutusu", "Yazı kutuya sığdırılır. Boyut / renk / yazı tipi: Giriş sekmesindeki yazı ayarı.")
            if not m:
                return
            ayar = self.yazi_ayar()
            font = fontlar.font(ayar.get("aile"), ayar["kalin"]) if ayar.get("aile") else None
            if font is not None and not fontlar.harfleri_var_mi(font, m):
                font = None
            self.duzenle_islem("Metin kutusu", lambda d: AR.metin_kutusu(d[i], rect, m, ayar["boyut"], ayar["renk"], font), i)
            return
        tur = {"form_metin": "metin", "form_onay": "onay", "form_liste": "liste"}[mod]
        d = DG.Diyalog(self, "📋 Form Alanı", "Alan adı, doldururken görünen etikettir.", dugme="Ekle")
        ad = ttk.Entry(d.govde, width=30)
        kelimeler = self.belge.doc[i].get_text("words")
        ad.insert(0, AR._etiket_bul(kelimeler, rect, sag_once=(tur == "onay")) or {"metin": "Metin", "onay": "Onay", "liste": "Liste"}[tur])
        d.satir("Alan adı:", ad)
        sec = None
        if tur == "liste":
            sec = ttk.Entry(d.govde, width=30)
            sec.insert(0, self.ayar.get("form_secenekler", "Evet; Hayır"))
            d.satir("Seçenekler:", sec, "noktalı virgülle ayırın")
        d.topla = lambda: {"ad": ad.get().strip(),
                           "sec": [x.strip() for x in sec.get().split(";") if x.strip()] if sec else None}
        s = d.ac()
        if not s:
            return
        if sec:
            self.ayar["form_secenekler"] = "; ".join(s["sec"] or [])
        self._form_onbellek = {}
        self.duzenle_islem("Form alanı", lambda doc: AR.form_alani_ekle(doc[i], rect, tur, s["ad"], s["sec"]), i)

    def form_otomatik(self):
        b = self._belge_gerekli()
        if not b:
            return
        sonuc = {}
        self._form_onbellek = {}
        if self.duzenle_islem("Form alanlarını algılama", lambda d: sonuc.update(n=AR.form_otomatik_algila(d))):
            n = sonuc.get("n", 0)
            if n:
                self.durum_yaz(f"✔ {n} form alanı eklendi. Tıklayarak doldurabilirsiniz · Geri almak için Ctrl+Z", basari=True)
            else:
                b.geri_al()
                self.icerik_degisti()
                messagebox.showinfo("PDF PRO", "Boş form çizgisi / kutusu bulunamadı.\n"
                                               "Form sekmesindeki Metin Alanı / Onay Kutusu ile elle ekleyebilirsiniz.")

    def form_kilitle(self):
        b = self._belge_gerekli()
        if not b:
            return
        if not messagebox.askyesno("PDF PRO", "Form alanları ve notlar sayfaya kalıcı olarak işlensin mi?\n"
                                              "(Değerler görünür kalır ama artık değiştirilemez.)"):
            return
        self._form_onbellek = {}
        self.duzenle_islem("Formu düzleştirme", lambda d: d.bake())

    # ================================================================== ARACLAR
    def karsilastir(self):
        b = self._belge_gerekli()
        if not b:
            return
        y = filedialog.askopenfilename(title="Karşılaştırılacak (YENİ) PDF'i seçin", filetypes=_A().PDF_TUR,
                                       initialdir=os.path.dirname(b.yol) if b.yol else self.ayar.get("son_klasor"))
        if not y:
            return
        k = self.kaynak_dosya()
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_karsilastirma.pdf")

        def bitti(r):
            _, sil, ekl, fark = r
            self._gecici_belge(gecici, "Karşılaştırma.pdf")
            if sil + ekl == 0:
                messagebox.showinfo("PDF PRO", "İki belgenin yazıları AYNI. Fark bulunmadı.")
            self.durum_yaz(f"✔ Karşılaştırma: {fark} sayfada fark · silinen {sil} / eklenen {ekl} kelime  "
                           "(solda kırmızı = eski, sağda yeşil = yeni)", basari=True)
        self.calistir("Karşılaştırılıyor", lambda il, ip: AR.karsilastir(k, y, gecici, il), bitti)

    def qr_oku(self):
        b = self._belge_gerekli()
        if not b:
            return
        doc_bayt = b.doc.tobytes()

        def is_(il, ip):
            d = fitz.open("pdf", doc_bayt)
            return AR.qr_oku(d, ilerleme=il)

        def bitti(sonuc):
            A = _A()
            if not sonuc:
                messagebox.showinfo("PDF PRO", "Belgede okunabilen QR kod / barkod bulunamadı.")
                return
            p = _Pencere(self, "QR / Barkod", "640x380")
            p.baslik(f"▦ {len(sonuc)} kod okundu")
            kap = tk.Frame(p, bg=A.R_KART)
            kap.pack(fill="both", expand=True, padx=16, pady=6)
            for r in sonuc:
                f = tk.Frame(kap, bg="#F3F6FA", padx=8, pady=6)
                f.pack(fill="x", pady=3)
                tk.Label(f, text=f"Sayfa {r['sayfa'] + 1} · {r['tur']}", bg="#F3F6FA", fg=A.R_SOLUK,
                         font=(A.FONT, 8)).pack(anchor="w")
                e = tk.Entry(f, font=(A.FONT, 10), relief="flat", bg="#F3F6FA")
                e.insert(0, r["metin"])
                e.config(state="readonly", readonlybackground="#F3F6FA")
                e.pack(side="left", fill="x", expand=True)
                if re.match(r"https?://", r["metin"]):
                    ttk.Button(f, text="🌐 Aç", style="Ikincil.TButton",
                               command=lambda m=r["metin"]: webbrowser.open(m)).pack(side="right", padx=2)
                ttk.Button(f, text="📋", width=3, style="Ikincil.TButton",
                           command=lambda m=r["metin"]: (self.clipboard_clear(), self.clipboard_append(m))).pack(side="right")
                if r.get("rect") is not None:
                    ttk.Button(f, text="Göster", style="Ikincil.TButton",
                               command=lambda s_=r["sayfa"], rc=r["rect"]: self.gorunum.alana_git(s_, rc)).pack(side="right", padx=2)
            ttk.Button(p, text="Kapat", style="Ikincil.TButton", command=p.destroy).pack(pady=10)
        self.calistir_bilesenli("QR / barkod okunuyor", is_, bitti)

    def onar(self):
        y = filedialog.askopenfilename(title="Onarılacak (bozuk) PDF'i seçin", filetypes=_A().PDF_TUR,
                                       initialdir=self.ayar.get("son_klasor"))
        if not y:
            return
        c = benzersiz_yol(os.path.splitext(y)[0] + "_onarilmis.pdf")

        def bitti(r):
            yol, n, rapor = r
            self.sonuc_goster(f"{n} sayfa kurtarıldı.", yol, uyari="\n".join(rapor) if rapor else None)
        self.calistir("PDF onarılıyor", lambda il, ip: D.onar(y, c, il), bitti)

    def bilgileri_temizle(self):
        b = self._belge_gerekli()
        if not b:
            return
        if not messagebox.askyesno("PDF PRO", "Yazar, oluşturan program, başlık, tarih gibi gizli belge bilgileri ve "
                                              "notlar/yorumlar dışındaki ekli dosyalar silinsin mi?"):
            return

        def f(d):
            d.set_metadata({})
            try:
                d.del_xml_metadata()
            except Exception:
                pass
            for ad in list(d.embfile_names()):
                d.embfile_del(ad)
        self.duzenle_islem("Belge bilgilerini temizleme", f)

    # ================================================================== DONUSTUR (yeni)
    def pptx_e(self):
        if not self._belge_gerekli():
            return
        if not messagebox.askyesno("PDF PRO", "Her sayfa bir slayt olur; yazılar düzenlenebilir kutular halinde gelir.\n"
                                              "Devam edilsin mi?"):
            return
        k, c = self.kaynak_dosya(), self.cikti_yolu("sunum", ".pptx")
        self.calistir_bilesenli("PowerPoint'e çevriliyor", lambda il, ip: D.pdf_to_pptx(k, c, True, il, ip),
                                lambda r: self.sonuc_goster("PowerPoint dosyası hazır.", c), True)

    def markdown_e(self):
        if not self._belge_gerekli():
            return
        k, c = self.kaynak_dosya(), self.cikti_yolu("metin", ".md")
        self.calistir("Markdown'a çevriliyor", lambda il, ip: D.pdf_to_markdown(k, c, il),
                      lambda r: self.sonuc_goster("Markdown (.md) dosyası hazır.\nBaşlıklar, listeler ve tablolar korunur.", c))

    def pdfa_yap(self):
        if not self._belge_gerekli():
            return
        k, c = self.kaynak_dosya(), self.cikti_yolu("PDFA")
        self.calistir("PDF/A'ya çevriliyor", lambda il, ip: D.pdf_a(k, c, il),
                      lambda r: self.sonuc_goster("PDF/A (uzun süreli arşiv) kopyası kaydedildi.", r[0],
                                                  uyari="\n".join(r[1]) if r[1] else None))

    def pptden_pdf(self):
        self._dosyadan_pdf(PPT_TUR, D.pptx_to_pdf, "PowerPoint")

    def htmlden_pdf(self):
        d = DG.Diyalog(self, "🌐 HTML / Web Sayfasından PDF",
                       "Bir web adresi yazın ya da bilgisayardaki .html dosyasını seçin. (Edge veya Chrome kullanılır)",
                       dugme="PDF Yap")
        v = tk.StringVar()
        d.dosya_alani("Adres / dosya:", v, HTML_TUR)
        d.topla = lambda: {"k": v.get().strip()} if v.get().strip() else (_ for _ in ()).throw(ValueError("Adres veya dosya girin."))
        s = d.ac()
        if not s:
            return
        k = s["k"]
        if not os.path.isfile(k) and not re.match(r"^[a-z]+://", k, re.I):
            k = "https://" + k
        ad = (os.path.splitext(os.path.basename(k))[0] if os.path.isfile(k)
              else re.sub(r"[^\w.-]+", "_", re.sub(r"^[a-z]+://(www\.)?", "", k, flags=re.I))[:60]) or "sayfa"
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_html.pdf")
        self.calistir("Web sayfası PDF yapılıyor", lambda il, ip: D.html_to_pdf(k, gecici, il),
                      lambda r: (self._gecici_belge(gecici, ad + ".pdf"),
                                 self.durum_yaz("✔ PDF yapıldı. Kaydetmek için Ctrl+S.", basari=True)))

    def _dosyadan_pdf(self, turler, fonk, ad):
        ys = filedialog.askopenfilenames(title=f"{ad} dosyalarını seçin", filetypes=turler,
                                         initialdir=self.ayar.get("son_klasor"))
        if not ys:
            return
        self.ayar["son_klasor"] = os.path.dirname(ys[0])
        hedefler = [benzersiz_yol(os.path.splitext(y)[0] + ".pdf") for y in ys]

        def is_(il, ip):
            tamam, hatalar = [], []
            for i, (y, h) in enumerate(zip(ys, hedefler)):
                if ip():
                    break
                il(i, len(ys), os.path.basename(y))
                try:
                    fonk(y, h)
                    tamam.append(h)
                except Exception as e:
                    hatalar.append(f"{os.path.basename(y)}: {e}")
            return tamam, hatalar

        def bitti(r):
            tamam, hatalar = r
            if tamam:
                self.ac(tamam[:5])
            if hatalar:
                messagebox.showwarning("PDF PRO", "Dönüştürülemeyenler:\n\n" + "\n".join(hatalar))
            self.durum_yaz(f"✔ {len(tamam)} dosya PDF yapıldı (aynı klasöre kaydedildi).", basari=True)
        self.calistir(f"{ad} → PDF", is_, bitti, iptal_edilebilir=True)

    # ================================================================== YAPAY ZEKA
    def yz_ayarlar(self):
        A = _A()
        ay = self.ayar.setdefault("yz", {})
        d = DG.Diyalog(self, "🤖 Yapay Zeka Ayarları",
                       "Özetleme, çeviri ve belgeye soru sormak için bir yapay zeka anahtarı gerekir. "
                       "Google Gemini ve Groq anahtarları ÜCRETSİZ alınabilir. Anahtar yalnızca bu bilgisayarda saklanır.",
                       dugme="Kaydet", genislik=520)
        sag = ttk.Combobox(d.govde, values=list(YZ.SAGLAYICILAR), state="readonly", width=30)
        sag.set(ay.get("saglayici", "Google Gemini"))
        d.satir("Sağlayıcı:", sag)
        anahtarlar = dict(ay.get("anahtarlar", {}))
        modeller = dict(ay.get("modeller", {}))
        anahtar = ttk.Entry(d.govde, width=44, show="•")
        d.satir("Anahtar (API key):", anahtar)
        goster = tk.BooleanVar(value=False)
        d.tam_satir(ttk.Checkbutton(d.govde, text="Anahtarı göster", variable=goster, style="Kart.TCheckbutton",
                                    command=lambda: anahtar.config(show="" if goster.get() else "•")))
        model = ttk.Entry(d.govde, width=44)
        d.satir("Model:", model, "Boş bırakırsanız önerilen model kullanılır")
        adres = ttk.Entry(d.govde, width=44)
        adres.insert(0, ay.get("ozel_adres", ""))
        d.satir("Özel adres:", adres, "Sadece 'Özel' için (ör. FreeLLMAPI: http://localhost:8000/v1)")
        bag = tk.Label(d.govde, text="", bg=A.R_KART, fg=A.R_VURGU, font=(A.FONT, 9, "underline"), cursor="hand2")
        d.tam_satir(bag)
        durum = tk.Label(d.govde, text="", bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 9), wraplength=460, justify="left")
        onceki = {"ad": None}

        def sakla():
            if onceki["ad"]:
                anahtarlar[onceki["ad"]] = anahtar.get().strip()
                modeller[onceki["ad"]] = model.get().strip()

        def degisti(e=None):
            sakla()
            a = sag.get()
            onceki["ad"] = a
            anahtar.delete(0, "end")
            anahtar.insert(0, anahtarlar.get(a, ""))
            model.delete(0, "end")
            model.insert(0, modeller.get(a, "") or YZ.SAGLAYICILAR[a]["model"])
            u = YZ.SAGLAYICILAR[a]["anahtar_adresi"]
            bag.config(text=f"🔑 Ücretsiz anahtar al: {u}" if u else "")
            bag.bind("<Button-1>", lambda ev: webbrowser.open(u) if u else None)
        sag.bind("<<ComboboxSelected>>", degisti)
        degisti()

        def topla_():
            sakla()
            return {"saglayici": sag.get(), "anahtarlar": anahtarlar, "modeller": modeller,
                    "ozel_adres": adres.get().strip()}

        def test():
            yeni = topla_()
            durum.config(text="⏳ Deneniyor…", fg=A.R_SOLUK)
            d.update_idletasks()

            def is_():
                try:
                    YZ.baglanti_testi(yeni)
                    m = ("✔ Bağlantı başarılı.", A.R_BASARI)
                except Exception as e:
                    m = ("✖ " + str(e), A.R_TEHLIKE)
                d.after(0, lambda: durum.config(text=m[0], fg=m[1]) if durum.winfo_exists() else None)
            threading.Thread(target=is_, daemon=True).start()
        ttk.Button(d.govde, text="Bağlantıyı Dene", style="Ikincil.TButton", command=test).grid(row=d._satir, column=0, sticky="w", pady=6)
        durum.grid(row=d._satir, column=1, sticky="w")
        d._satir += 1
        d.topla = topla_
        s = d.ac()
        if s:
            self.ayar["yz"] = s
            _A().ayar_yaz(self.ayar)
            self.durum_yaz("✔ Yapay zeka ayarları kaydedildi.", basari=True)
        return s

    def _yz_hazir(self, cevrimdisi_olur=False):
        if YZ.hazir_mi(self.ayar.get("yz")):
            return True
        if cevrimdisi_olur:
            c = messagebox.askyesnocancel("PDF PRO", "Yapay zeka anahtarı girilmemiş.\n\n"
                                                     "Evet = şimdi anahtar gir (ücretsiz)\n"
                                                     "Hayır = internetsiz basit özet (önemli cümleler) çıkar")
            if c is None:
                return None
            if not c:
                return False
        else:
            if not messagebox.askyesno("PDF PRO", "Bu özellik için yapay zeka anahtarı gerekiyor (ücretsiz alınabilir).\n"
                                                  "Ayarlar açılsın mı?"):
                return None
        return True if (self.yz_ayarlar() and YZ.hazir_mi(self.ayar.get("yz"))) else None

    def _belge_metni_al(self, il, ip):
        b = self.belge
        anahtar = (id(b), b.surum)
        if getattr(self, "_yz_metin", (None,))[0] == anahtar:
            return self._yz_metin[1]
        bayt = b.doc.tobytes()
        m = YZ.belge_metni(fitz.open("pdf", bayt), ilerleme=il, iptal=ip)
        self._yz_metin = (anahtar, m)
        return m

    def ozetle(self):
        b = self._belge_gerekli()
        if not b:
            return
        hazir = self._yz_hazir(cevrimdisi_olur=True)
        if hazir is None:
            return
        ayar = self.ayar.get("yz")

        def is_(il, ip):
            metin = self._belge_metni_al(il, ip)
            if len(re.sub(r"--- Sayfa \d+ ---|\s", "", metin)) < 20:
                raise PdfProHata("Belgede okunabilir yazı bulunamadı.\nTaranmış belgeyse önce Araçlar → OCR uygulayın.")
            if hazir:
                return YZ.ozetle(ayar, metin, "orta", il, ip), True
            return YZ.cevrimdisi_ozet(metin), False

        def bitti(r):
            ozet, yz = r
            baslik = "🤖 Yapay zeka özeti" if yz else "📄 Basit özet (internetsiz – önemli cümleler)"
            self._metin_goster(f"{baslik} — {b.ad}", ozet, b.ad)
        self.calistir("Özetleniyor", is_, bitti, iptal_edilebilir=True)

    def _metin_goster(self, baslik, metin, ad):
        A = _A()
        p = _Pencere(self, baslik, "720x560")
        p.baslik(baslik)
        t = scrolledtext.ScrolledText(p, wrap="word", font=(A.FONT, 10), relief="flat", padx=12, pady=10)
        t.pack(fill="both", expand=True, padx=12)
        t.insert("1.0", metin)
        alt = ttk.Frame(p, style="Kart.TFrame", padding=10)
        alt.pack(fill="x")

        def kaydet():
            y = filedialog.asksaveasfilename(parent=p, defaultextension=".txt", initialfile=os.path.splitext(ad)[0] + "_ozet.txt",
                                             filetypes=[("Metin", "*.txt"), ("Word", "*.docx")])
            if not y:
                return
            m = t.get("1.0", "end-1c")
            if y.lower().endswith(".docx"):
                import docx
                dd = docx.Document()
                for s in m.split("\n"):
                    dd.add_paragraph(s)
                dd.save(y)
            else:
                with open(y, "w", encoding="utf-8-sig") as f:
                    f.write(m)
            self.durum_yaz(f"✔ Kaydedildi: {y}", basari=True)
        ttk.Button(alt, text="Kapat", style="Ikincil.TButton", command=p.destroy).pack(side="right")
        ttk.Button(alt, text="💾 Kaydet", style="Ikincil.TButton", command=kaydet).pack(side="right", padx=6)
        ttk.Button(alt, text="📋 Kopyala", style="Ana.TButton",
                   command=lambda: (self.clipboard_clear(), self.clipboard_append(t.get("1.0", "end-1c")))).pack(side="right")

    def belgeye_sor(self):
        A = _A()
        b = self._belge_gerekli()
        if not b:
            return
        if not self._yz_hazir():
            return
        ayar = self.ayar.get("yz")
        p = _Pencere(self, "Belgeye Sor", "720x560")
        p.baslik("💬 Belgeye Sor", f"{b.ad} hakkında soru yazın. Ör: 'Geminin IMO numarası ne?', "
                                  "'Son geçerlilik tarihi hangisi?', 'Toplam tutar ne kadar?'")
        t = scrolledtext.ScrolledText(p, wrap="word", font=(A.FONT, 10), relief="flat", padx=12, pady=10, state="disabled")
        t.pack(fill="both", expand=True, padx=12)
        t.tag_configure("soru", foreground=A.R_VURGU, font=(A.FONT, 10, "bold"), spacing1=8)
        t.tag_configure("cevap", spacing3=6)
        alt = ttk.Frame(p, style="Kart.TFrame", padding=10)
        alt.pack(fill="x")
        e = ttk.Entry(alt, font=(A.FONT, 11))
        e.pack(side="left", fill="x", expand=True)
        dugme = ttk.Button(alt, text="Sor", style="Ana.TButton")
        dugme.pack(side="left", padx=6)

        def yaz(metin, etiket):
            t.config(state="normal")
            t.insert("end", metin + "\n", etiket)
            t.see("end")
            t.config(state="disabled")

        def sor_(ev=None):
            soru = e.get().strip()
            if not soru or str(dugme["state"]) == "disabled":
                return
            e.delete(0, "end")
            yaz("❓ " + soru, "soru")
            dugme.config(state="disabled")

            def is_():
                try:
                    metin = self._belge_metni_al(lambda *a: None, lambda: False)
                    c = YZ.belgeye_sor(ayar, metin, soru)
                except Exception as ex:
                    c = "✖ " + str(ex)

                def goster():
                    if p.winfo_exists():
                        yaz(c, "cevap")
                        dugme.config(state="normal")
                p.after(0, goster)
            threading.Thread(target=is_, daemon=True).start()
        dugme.config(command=sor_)
        e.bind("<Return>", sor_)
        e.focus_set()

    def cevir(self):
        b = self._belge_gerekli()
        if not b:
            return
        if not self._yz_hazir():
            return
        d = DG.Diyalog(self, "🌍 PDF Çevir",
                       "Yazılar sayfadaki yerlerinde çevrilir; tablo, logo, imza ve resimler aynen kalır. "
                       "Sonuç yeni sekmede açılır (asıl belge değişmez).", dugme="Çevir")
        dil = ttk.Combobox(d.govde, values=YZ.DILLER, width=20)
        dil.set(self.ayar.get("ceviri_dil", "İngilizce"))
        d.satir("Hedef dil:", dil)
        d.topla = lambda: {"dil": dil.get().strip() or "İngilizce"}
        s = d.ac()
        if not s:
            return
        self.ayar["ceviri_dil"] = s["dil"]
        k = self.kaynak_dosya()
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_ceviri.pdf")
        ayar = self.ayar.get("yz")

        def bitti(r):
            _, n, taranmis = r
            ad = os.path.splitext(b.ad)[0] + f"_{s['dil']}.pdf"
            self._gecici_belge(gecici, ad)
            ek = f" · {taranmis} taranmış sayfa OCR ile çevrildi" if taranmis else ""
            self.durum_yaz(f"✔ Çeviri hazır ({n} yazı bloğu{ek}). Kaydetmek için Ctrl+S.", basari=True)
        self.calistir("Çevriliyor", lambda il, ip: YZ.pdf_cevir(ayar, k, gecici, s["dil"], il, ip), bitti, True)

    # ================================================================== IMZA + KASE SETLERI
    def _setler(self):
        return self.ayar.setdefault("imza_setleri", {})

    def imza_setleri(self):
        A = _A()
        setler = copy.deepcopy(self._setler())
        p = _Pencere(self, "İmza + Kaşe Setleri", "620x470")
        p.baslik("🖋 İmza + Kaşe Setleri",
                 "Sık kullandığınız imza + kaşe ikilisini bir kez kaydedin; tek tıkla ikisini birden koyun. "
                 "Sayfada her biri ayrı ayrı taşınıp boyutlandırılabilir.")
        ust = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0))
        ust.pack(fill="x")
        kutu = ttk.Combobox(ust, state="readonly", width=34)
        kutu.pack(side="left")

        def yeni():
            ad = simpledialog.askstring("PDF PRO", "Set adı (ör. 'Can – imza + şirket kaşesi'):", parent=p)
            if ad and ad.strip():
                setler.setdefault(ad.strip(), {"ogeler": []})
                yenile(ad.strip())

        def sil_set():
            a = kutu.get()
            if a and messagebox.askyesno("PDF PRO", f"'{a}' seti silinsin mi?", parent=p):
                setler.pop(a, None)
                yenile()
        ttk.Button(ust, text="➕ Yeni Set", style="Ikincil.TButton", command=yeni).pack(side="left", padx=6)
        ttk.Button(ust, text="🗑", width=3, style="Ikincil.TButton", command=sil_set).pack(side="left")
        orta = tk.Frame(p, bg=A.R_KART)
        orta.pack(fill="both", expand=True, padx=16, pady=8)
        fotolar = []

        def ogeleri_ciz():
            for w in orta.winfo_children():
                w.destroy()
            fotolar.clear()
            a = kutu.get()
            if not a:
                tk.Label(orta, text="Henüz set yok. 'Yeni Set' ile başlayın.", bg=A.R_KART, fg=A.R_SOLUK).pack(pady=30)
                return
            for k, o in enumerate(setler[a]["ogeler"]):
                f = tk.Frame(orta, bg="#F3F6FA", padx=8, pady=6)
                f.pack(fill="x", pady=3)
                try:
                    from PIL import Image, ImageTk
                    im = Image.open(o["yol"])
                    im.thumbnail((90, 50))
                    ph = ImageTk.PhotoImage(im)
                    fotolar.append(ph)
                    tk.Label(f, image=ph, bg="white").pack(side="left")
                except Exception:
                    tk.Label(f, text="(resim yok)", bg="#F3F6FA", fg=A.R_TEHLIKE).pack(side="left")
                tk.Label(f, text=os.path.basename(o["yol"]), bg="#F3F6FA", font=(A.FONT, 9)).pack(side="left", padx=8)
                ttk.Button(f, text="🗑", width=3, style="Ikincil.TButton",
                           command=lambda k=k: (setler[a]["ogeler"].pop(k), ogeleri_ciz())).pack(side="right")
                v = tk.StringVar(value=str(o.get("genislik_mm", 40)))
                sp = ttk.Spinbox(f, from_=10, to=150, width=5, textvariable=v)
                sp.pack(side="right")
                v.trace_add("write", lambda *_, o=o, v=v: o.update(genislik_mm=float(v.get())) if v.get().replace(".", "").isdigit() else None)
                tk.Label(f, text="genişlik mm", bg="#F3F6FA", fg=A.R_SOLUK, font=(A.FONT, 8)).pack(side="right", padx=4)
            ttk.Button(orta, text="➕ Resim Ekle (imza / kaşe)", style="Ikincil.TButton",
                       command=lambda: ekle(a)).pack(anchor="w", pady=6)

        def ekle(a):
            ys = filedialog.askopenfilenames(parent=p, title="İmza / kaşe resmi", filetypes=DG.RESIM_TUR)
            for y in ys:
                setler[a]["ogeler"].append({"yol": os.path.normpath(y), "genislik_mm": 40, "beyazi_sil": True})
            ogeleri_ciz()

        def yenile(sec=None):
            kutu.config(values=list(setler))
            if sec:
                kutu.set(sec)
            elif setler:
                kutu.set(list(setler)[0])
            else:
                kutu.set("")
            ogeleri_ciz()
        kutu.bind("<<ComboboxSelected>>", lambda e: ogeleri_ciz())
        yenile(self.ayar.get("son_set") if self.ayar.get("son_set") in setler else None)

        def kaydet():
            self.ayar["imza_setleri"] = setler
            _A().ayar_yaz(self.ayar)

        def koy():
            kaydet()
            a = kutu.get()
            if not a or not setler[a]["ogeler"]:
                messagebox.showinfo("PDF PRO", "Sete en az bir resim ekleyin.", parent=p)
                return
            p.destroy()
            self.set_baslat(a)
        alt = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0, 16, 14))
        alt.pack(fill="x")
        ttk.Button(alt, text="Kapat", style="Ikincil.TButton", command=lambda: (kaydet(), p.destroy())).pack(side="right")
        ttk.Button(alt, text="Sayfaya Koy →", style="Ana.TButton", command=koy).pack(side="right", padx=6)
        p.protocol("WM_DELETE_WINDOW", lambda: (kaydet(), p.destroy()))

    def set_baslat(self, ad=None):
        if not self._belge_gerekli():
            return
        setler = self._setler()
        if not ad:
            if not setler:
                self.imza_setleri()
                return
            ad = self.ayar.get("son_set") if self.ayar.get("son_set") in setler else list(setler)[0]
        try:
            ogeler = OT.set_hazirla(setler[ad])
        except PdfProHata as e:
            messagebox.showerror("PDF PRO", str(e))
            return
        self.ayar["son_set"] = ad
        self.mod_sec("sec")
        self.set_ayar = {"ad": ad, "ogeler": ogeler}
        self.mod = "set"
        self.gorunum.mod_ayarla("set")
        self._mod_renkleri()
        self.durum_yaz(f"🖋 '{ad}': Sayfada koymak istediğiniz yere tıklayın (imza + kaşe yan yana gelir). Esc = vazgeç")

    def set_bas(self, i, px, py):
        a = getattr(self, "set_ayar", None)
        if not a:
            return
        b = self.belge
        page_rect = b.doc[i].rect
        rectler = OT.set_rectleri(page_rect, a["ogeler"], "Orta")
        toplam = fitz.Rect(rectler[0])
        for r in rectler[1:]:
            toplam |= r
        dx, dy = px - (toplam.x0 + toplam.x1) / 2, py - (toplam.y0 + toplam.y1) / 2
        rectler = [r + (dx, dy, dx, dy) for r in rectler]
        ilk = {}

        def f(doc):
            for o, r in zip(a["ogeler"], rectler):
                xref = Z.nesne_ekle(doc[i], r, o["png"])
                if xref:
                    nid = self._yeni_nesne_id()
                    b.nesneler.append({"id": nid, "sayfa": i, "xref": xref, "rect": tuple(r), "png": o["png"]})
                    ilk.setdefault("id", nid)
        self.duzenle_islem("İmza + kaşe seti", f, i)
        self.set_ayar = None
        self.mod_sec("sec")
        if ilk.get("id"):
            self.gorunum.nesne_sec(ilk["id"])
            self.durum_yaz("✔ Set yerleştirildi. Her parçayı ayrı ayrı sürükleyip köşesinden boyutlandırabilirsiniz.", basari=True)

    # ================================================================== IS AKISLARI / TOPLU ISLEM
    def _akislar(self):
        if "akislar" not in self.ayar:
            self.ayar["akislar"] = copy.deepcopy(OT.HAZIR_AKISLAR)
        return self.ayar["akislar"]

    def _adim_ayar_diyalog(self, tur, ayar):
        """Adim ayarlarini duzenler; yeni ayar ya da None."""
        ad = OT.ADIMLAR[tur][0]
        a = dict(OT.ADIMLAR[tur][1], **(ayar or {}))
        if not a:
            return {}
        d = DG.Diyalog(self, f"⚙ {ad}", None, dugme="Tamam")
        al = {}
        for k, v in a.items():
            if k == "seviye":
                w = ttk.Combobox(d.govde, values=["hafif", "orta", "guclu", "en_kucuk", "asiri"], state="readonly", width=14)
                w.set(v)
                d.satir("Seviye:", w)
            elif k == "konum":
                w = ttk.Combobox(d.govde, values=KONUMLAR, state="readonly", width=14)
                w.set(v)
                d.satir("Konum:", w)
            elif k == "renk":
                w = ttk.Combobox(d.govde, values=list(OT.DAMGA_RENK), state="readonly", width=14)
                w.set(v)
                d.satir("Renk:", w)
            elif k == "metin" and tur == "damga":
                w = ttk.Combobox(d.govde, values=AR.HAZIR_DAMGALAR, width=24)
                w.set(v)
                d.satir("Yazı:", w)
            elif k == "set":
                w = ttk.Combobox(d.govde, values=list(self._setler()), state="readonly", width=24)
                w.set(v or (list(self._setler()) or [""])[0])
                d.satir("Set:", w, "İmza / İmza Setleri'nden oluşturulur")
            elif k == "yol":
                w = tk.StringVar(value=v)
                d.dosya_alani("Antet dosyası:", w, DG.PDF_RESIM_TUR)
            elif isinstance(v, bool):
                w = tk.BooleanVar(value=v)
                d.tam_satir(ttk.Checkbutton(d.govde, text={"tarih": "Altına tarih yaz"}.get(k, k), variable=w, style="Kart.TCheckbutton"))
            else:
                w = ttk.Entry(d.govde, width=26, show="•" if k == "sifre" else "")
                w.insert(0, str(v))
                etiket = {"metin": "Yazı:", "opaklik": "Saydamlık (0-1):", "hedef_mb": "En fazla MB (0 = sınırsız):",
                          "bicim": "Biçim:", "sayfalar": "Sayfalar:", "dil": "OCR dili:", "sifre": "Şifre:"}.get(k, k + ":")
                ipucu = {"sayfalar": "tümü · ilk · son · 1-3,5", "bicim": "{n} = sayfa, {N} = toplam"}.get(k)
                d.satir(etiket, w, ipucu)
            al[k] = (w, type(v))

        def topla():
            sonuc = {}
            for k, (w, tip) in al.items():
                deger = w.get()
                if tip in (int, float):
                    try:
                        deger = float(str(deger).replace(",", "."))
                    except ValueError:
                        raise ValueError(f"{k}: sayı girin")
                sonuc[k] = deger
            if tur == "sifre" and not sonuc.get("sifre"):
                raise ValueError("Şifre boş olamaz.")
            return sonuc
        d.topla = topla
        return d.ac()

    def is_akislari(self):
        A = _A()
        akislar = copy.deepcopy(self._akislar())
        p = _Pencere(self, "İş Akışları / Toplu İşlem", "900x600")
        p.baslik("⚙ İş Akışları / Toplu İşlem",
                 "Sık yaptığınız işlemleri sırayla kaydedin (ör. OCR → damga → sıkıştır). Sonra tek tıkla açık belgeye, "
                 "seçtiğiniz dosyalara ya da bir klasördeki TÜM PDF'lere uygulayın.")
        govde = tk.Frame(p, bg=A.R_KART)
        govde.pack(fill="both", expand=True, padx=16)
        sol = tk.Frame(govde, bg=A.R_KART)
        sol.pack(side="left", fill="y")
        tk.Label(sol, text="İş akışları", bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 9)).pack(anchor="w")
        lst = tk.Listbox(sol, width=30, font=(A.FONT, 10), activestyle="none", selectbackground=A.R_VURGU, exportselection=False)
        lst.pack(fill="y", expand=True)
        sd = tk.Frame(sol, bg=A.R_KART)
        sd.pack(fill="x", pady=4)
        sag = tk.Frame(govde, bg=A.R_KART)
        sag.pack(side="left", fill="both", expand=True, padx=(12, 0))
        tk.Label(sag, text="Adımlar (sırayla uygulanır)", bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 9)).pack(anchor="w")
        adim_lst = tk.Listbox(sag, font=(A.FONT, 10), activestyle="none", selectbackground=A.R_VURGU, exportselection=False)
        adim_lst.pack(fill="both", expand=True)
        ad_ = tk.Frame(sag, bg=A.R_KART)
        ad_.pack(fill="x", pady=4)
        tur_kutu = ttk.Combobox(ad_, state="readonly", width=22, values=[v[0] for v in OT.ADIMLAR.values()])
        tur_kutu.current(0)
        tur_kutu.pack(side="left")
        turler = list(OT.ADIMLAR)

        def akis():
            s = lst.curselection()
            return akislar[s[0]] if s else None

        def lst_ciz(sec=0):
            lst.delete(0, "end")
            for a in akislar:
                lst.insert("end", "  " + a["ad"])
            if akislar:
                sec = max(0, min(sec, len(akislar) - 1))
                lst.selection_set(sec)
            adim_ciz()

        def adim_ciz(sec=None):
            adim_lst.delete(0, "end")
            a = akis()
            if a:
                for k, ad in enumerate(a["adimlar"]):
                    adim_lst.insert("end", f"  {k + 1}. {OT.adim_ozeti(ad)}")
                if sec is not None and a["adimlar"]:
                    adim_lst.selection_set(max(0, min(sec, len(a["adimlar"]) - 1)))
        lst.bind("<<ListboxSelect>>", lambda e: adim_ciz())

        def yeni_akis():
            ad = simpledialog.askstring("PDF PRO", "İş akışının adı:", parent=p)
            if ad and ad.strip():
                akislar.append({"ad": ad.strip(), "adimlar": []})
                lst_ciz(len(akislar) - 1)

        def sil_akis():
            s = lst.curselection()
            if s and messagebox.askyesno("PDF PRO", f"'{akislar[s[0]]['ad']}' silinsin mi?", parent=p):
                akislar.pop(s[0])
                lst_ciz(s[0])

        def adlandir():
            a = akis()
            if a:
                ad = simpledialog.askstring("PDF PRO", "Yeni ad:", initialvalue=a["ad"], parent=p)
                if ad and ad.strip():
                    a["ad"] = ad.strip()
                    lst_ciz(lst.curselection()[0])

        def adim_ekle():
            a = akis()
            if not a:
                messagebox.showinfo("PDF PRO", "Önce soldan bir iş akışı seçin ya da yeni oluşturun.", parent=p)
                return
            tur = turler[tur_kutu.current()]
            ayar = self._adim_ayar_diyalog(tur, None)
            if ayar is None:
                return
            a["adimlar"].append({"tur": tur, "ayar": ayar})
            adim_ciz(len(a["adimlar"]) - 1)

        def adim_duzenle(e=None):
            a, s = akis(), adim_lst.curselection()
            if a and s:
                ad = a["adimlar"][s[0]]
                yeni = self._adim_ayar_diyalog(ad["tur"], ad.get("ayar"))
                if yeni is not None:
                    ad["ayar"] = yeni
                    adim_ciz(s[0])

        def adim_sil():
            a, s = akis(), adim_lst.curselection()
            if a and s:
                a["adimlar"].pop(s[0])
                adim_ciz(s[0])

        def adim_tasi(yon):
            a, s = akis(), adim_lst.curselection()
            if a and s and 0 <= s[0] + yon < len(a["adimlar"]):
                k = s[0]
                a["adimlar"][k], a["adimlar"][k + yon] = a["adimlar"][k + yon], a["adimlar"][k]
                adim_ciz(k + yon)
        adim_lst.bind("<Double-Button-1>", adim_duzenle)
        for t, c in (("➕ Yeni", yeni_akis), ("✎ Ad", adlandir), ("🗑", sil_akis)):
            ttk.Button(sd, text=t, style="Ikincil.TButton", command=c).pack(side="left", padx=(0, 3))
        for t, c in (("➕ Adım Ekle", adim_ekle), ("⚙ Ayar", adim_duzenle), ("▲", lambda: adim_tasi(-1)),
                     ("▼", lambda: adim_tasi(1)), ("🗑", adim_sil)):
            ttk.Button(ad_, text=t, style="Ikincil.TButton", command=c).pack(side="left", padx=(4, 0))
        # calistirma
        cal = tk.LabelFrame(p, text=" Çalıştır ", bg=A.R_KART, fg=A.R_BASLIK, font=(A.FONT, 9, "bold"), padx=10, pady=6)
        cal.pack(fill="x", padx=16, pady=8)
        hedef = tk.StringVar(value="belge" if self.belge else "dosyalar")
        for t, v in (("Açık belgeye", "belge"), ("Dosya seç…", "dosyalar"), ("Klasördeki tüm PDF'ler…", "klasor")):
            ttk.Radiobutton(cal, text=t, value=v, variable=hedef, style="Kart.TRadiobutton").grid(row=0, column=["belge", "dosyalar", "klasor"].index(v), sticky="w", padx=(0, 12))
        tk.Label(cal, text="Çıktı adı:", bg=A.R_KART, font=(A.FONT, 9)).grid(row=1, column=0, sticky="w", pady=(6, 0))
        sablon = ttk.Entry(cal, width=30)
        sablon.insert(0, self.ayar.get("akis_sablon", "{ad}_islenmis"))
        sablon.grid(row=1, column=1, sticky="w", pady=(6, 0))
        tk.Label(cal, text="{ad} {tarih} {sayac}", bg=A.R_KART, fg=A.R_SOLUK, font=(A.FONT, 8)).grid(row=1, column=2, sticky="w")
        ustune = tk.BooleanVar(value=False)
        ttk.Checkbutton(cal, text="Dosyaların üzerine yaz (yedek alınır)", variable=ustune, style="Kart.TCheckbutton").grid(row=2, column=0, columnspan=2, sticky="w")
        alt_kl = tk.BooleanVar(value=False)
        ttk.Checkbutton(cal, text="Alt klasörler dahil", variable=alt_kl, style="Kart.TCheckbutton").grid(row=2, column=2, sticky="w")

        def kaydet():
            self.ayar["akislar"] = akislar
            self.ayar["akis_sablon"] = sablon.get().strip() or "{ad}_islenmis"
            _A().ayar_yaz(self.ayar)

        def calistir_():
            a = akis()
            if not a or not a["adimlar"]:
                messagebox.showinfo("PDF PRO", "Seçili iş akışında adım yok.", parent=p)
                return
            kaydet()
            adimlar = copy.deepcopy(a["adimlar"])
            setler = copy.deepcopy(self._setler())
            h = hedef.get()
            if h == "belge":
                if not self.belge:
                    messagebox.showinfo("PDF PRO", "Açık belge yok.", parent=p)
                    return
                p.destroy()
                self.nesneleri_unut()
                self.dosya_islem(a["ad"], lambda k, c, il, ip: OT.akisi_uygula(adimlar, k, c, setler, il, ip), arka_plan=True,
                                 bitince=lambda r: messagebox.showinfo("PDF PRO", "Notlar:\n" + "\n".join(r[1])) if r and r[1] else None)
                return
            if h == "dosyalar":
                ys = filedialog.askopenfilenames(parent=p, title="İşlenecek PDF'ler", filetypes=_A().PDF_TUR,
                                                 initialdir=self.ayar.get("son_klasor"))
                kaynaklar = list(ys)
            else:
                k = filedialog.askdirectory(parent=p, title="PDF'lerin bulunduğu klasör", initialdir=self.ayar.get("son_klasor"))
                kaynaklar = [k] if k else []
            dosyalar = OT.dosyalari_topla(kaynaklar, alt_kl.get())
            if not dosyalar:
                if kaynaklar:
                    messagebox.showinfo("PDF PRO", "PDF dosyası bulunamadı.", parent=p)
                return
            if ustune.get() and not messagebox.askyesno("PDF PRO", f"{len(dosyalar)} dosyanın ÜZERİNE yazılacak "
                                                                   "(eski halleri Yedekler'e alınır). Devam?", parent=p):
                return
            self.ayar["son_klasor"] = os.path.dirname(dosyalar[0])
            sb = sablon.get().strip() or "{ad}_islenmis"
            p.destroy()

            def bitti(r):
                tamam, hatalar, notlar = r
                uyari = "\n".join((hatalar + notlar)[:15]) if (hatalar or notlar) else None
                self.sonuc_goster(f"{len(tamam)} / {len(dosyalar)} dosya işlendi.", None,
                                  klasor=tamam[0] if tamam else None, uyari=uyari)
            self.calistir(f"{a['ad']}", lambda il, ip: OT.toplu_isle(adimlar, dosyalar, None, sb, ustune.get(), setler, il, ip),
                          bitti, iptal_edilebilir=True)

        alt = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0, 16, 14))
        alt.pack(fill="x")
        ttk.Button(alt, text="Kapat", style="Ikincil.TButton", command=lambda: (kaydet(), p.destroy())).pack(side="right")
        ttk.Button(alt, text="▶ Çalıştır", style="Ana.TButton", command=calistir_).pack(side="right", padx=6)
        p.protocol("WM_DELETE_WINDOW", lambda: (kaydet(), p.destroy()))
        lst_ciz()

    # ================================================================== BELGE PAKETI
    def _paketler(self):
        if "paketler" not in self.ayar:
            self.ayar["paketler"] = copy.deepcopy(OT.HAZIR_PAKETLER)
        return self.ayar["paketler"]

    def belge_paketi(self):
        A = _A()
        paketler = copy.deepcopy(self._paketler())
        p = _Pencere(self, "Belge Paketi", "900x640")
        p.baslik("📦 Belge Paketi",
                 "Her satıra ilgili dosyayı sürükleyin ya da 'Ekle' ile seçin (PDF, resim, Word, Excel). Paket sırasıyla tek "
                 "PDF olur; her bölüm yer imi (bookmark) olarak eklenir. Boş satırlar atlanır.")
        ust = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0))
        ust.pack(fill="x")
        ttk.Label(ust, text="Paket türü:", style="Kart.TLabel").grid(row=0, column=0, sticky="w")
        tur = ttk.Combobox(ust, state="readonly", width=30, values=[x["ad"] for x in paketler])
        tur.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(ust, text="Dosya adı:", style="Kart.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        sablon = ttk.Entry(ust, width=32)
        sablon.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(ust, text="Gemi / kişi adı:", style="Kart.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))
        isim = ttk.Entry(ust, width=22)
        isim.insert(0, self.ayar.get("paket_isim", ""))
        isim.grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(ust, text="En fazla MB:", style="Kart.TLabel").grid(row=1, column=2, sticky="w", padx=(10, 0))
        hedef_mb = ttk.Spinbox(ust, from_=0, to=100, width=6)
        hedef_mb.grid(row=1, column=3, sticky="w", padx=6)
        ttk.Label(ust, text="{GEMI} {AD} = yukarıdaki ad · {tarih}", style="Soluk.TLabel").grid(row=2, column=1, columnspan=3, sticky="w", padx=6)
        kap = tk.Frame(p, bg=A.R_KART)
        kap.pack(fill="both", expand=True, padx=16, pady=6)
        tuval = tk.Canvas(kap, bg=A.R_KART, highlightthickness=0)
        sb = ttk.Scrollbar(kap, orient="vertical", command=tuval.yview)
        ic = tk.Frame(tuval, bg=A.R_KART)
        ic.bind("<Configure>", lambda e: tuval.configure(scrollregion=tuval.bbox("all")))
        pencere_id = tuval.create_window(0, 0, window=ic, anchor="nw")
        tuval.bind("<Configure>", lambda e: tuval.itemconfigure(pencere_id, width=e.width))
        tuval.configure(yscrollcommand=sb.set)
        tuval.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        dosyalar = {}     # yuva index -> [yollar]
        durum = {"paket": None}

        def paket():
            return paketler[tur.current()] if tur.current() >= 0 else None

        def satirlari_ciz():
            for w in ic.winfo_children():
                w.destroy()
            pk = paket()
            if not pk:
                return
            for k, ad in enumerate(pk["yuvalar"]):
                ds = dosyalar.setdefault(k, [])
                f = tk.Frame(ic, bg="#F3F6FA" if ds else "#FAFBFC", padx=8, pady=5,
                             highlightthickness=1, highlightbackground="#DDE3EB")
                f.pack(fill="x", pady=2)
                tk.Label(f, text=f"{k + 1}.", bg=f["bg"], fg=A.R_SOLUK, width=3).pack(side="left")
                tk.Label(f, text=ad, bg=f["bg"], font=(A.FONT, 10, "bold" if ds else "normal"), anchor="w", width=30).pack(side="left")
                bilgi = (", ".join(os.path.basename(x) for x in ds))[:60] if ds else "— sürükleyin veya Ekle —"
                tk.Label(f, text=bilgi, bg=f["bg"], fg=A.R_YAZI if ds else A.R_SOLUK, font=(A.FONT, 9), anchor="w").pack(side="left", fill="x", expand=True)
                ttk.Button(f, text="✖", width=3, style="Ikincil.TButton", command=lambda k=k: (dosyalar.__setitem__(k, []), satirlari_ciz())).pack(side="right")
                ttk.Button(f, text="Ekle", style="Ikincil.TButton", command=lambda k=k: ekle(k)).pack(side="right", padx=3)
                if DND_FILES:
                    for w in [f] + list(f.winfo_children()):
                        try:
                            w.drop_target_register(DND_FILES)
                            w.dnd_bind("<<Drop>>", lambda e, k=k: (dosyalar.setdefault(k, []).extend(
                                [y for y in _drop_yollari(p, e.data) if os.path.isfile(y)]), satirlari_ciz()))
                        except Exception:
                            pass
            ttk.Button(ic, text="➕ Satır ekle", style="Ikincil.TButton", command=satir_ekle).pack(anchor="w", pady=6)

        def ekle(k):
            ys = filedialog.askopenfilenames(parent=p, title=paket()["yuvalar"][k], filetypes=HER_TUR,
                                             initialdir=self.ayar.get("son_klasor"))
            if ys:
                self.ayar["son_klasor"] = os.path.dirname(ys[0])
                dosyalar.setdefault(k, []).extend(os.path.normpath(y) for y in ys)
                satirlari_ciz()

        def satir_ekle():
            ad = simpledialog.askstring("PDF PRO", "Belge adı (ör. 'Crew List'):", parent=p)
            if ad and ad.strip():
                paket()["yuvalar"].append(ad.strip())
                satirlari_ciz()

        def tur_degisti(e=None):
            pk = paket()
            dosyalar.clear()
            sablon.delete(0, "end")
            sablon.insert(0, pk.get("sablon", "{GEMI}_{tarih}"))
            hedef_mb.set(pk.get("hedef_mb", 0))
            satirlari_ciz()
        tur.bind("<<ComboboxSelected>>", tur_degisti)

        def yeni_tur():
            ad = simpledialog.askstring("PDF PRO", "Yeni paket türünün adı:", parent=p)
            if not ad or not ad.strip():
                return
            satirlar = simpledialog.askstring("PDF PRO", "Belgeleri sırasıyla, virgülle ayırarak yazın:\n"
                                                         "(ör. Crew List, Ship Particulars, ISPS)", parent=p)
            if not satirlar:
                return
            paketler.append({"ad": ad.strip(), "sablon": "{GEMI}_" + re.sub(r"\W+", "_", ad.strip().upper()) + "_{tarih}",
                             "hedef_mb": 10, "yuvalar": [x.strip() for x in satirlar.split(",") if x.strip()]})
            tur.config(values=[x["ad"] for x in paketler])
            tur.current(len(paketler) - 1)
            tur_degisti()

        def sil_tur():
            if tur.current() >= 0 and len(paketler) > 1 and messagebox.askyesno("PDF PRO", f"'{tur.get()}' silinsin mi?", parent=p):
                paketler.pop(tur.current())
                tur.config(values=[x["ad"] for x in paketler])
                tur.current(0)
                tur_degisti()
        ttk.Button(ust, text="➕", width=3, style="Ikincil.TButton", command=yeni_tur).grid(row=0, column=4, padx=2)
        ttk.Button(ust, text="🗑", width=3, style="Ikincil.TButton", command=sil_tur).grid(row=0, column=5)
        ayrac = tk.BooleanVar(value=False)

        def kaydet():
            pk = paket()
            if pk:
                pk["sablon"] = sablon.get().strip()
                try:
                    pk["hedef_mb"] = float(hedef_mb.get() or 0)
                except ValueError:
                    pass
            self.ayar["paketler"] = paketler
            self.ayar["paket_isim"] = isim.get().strip()
            _A().ayar_yaz(self.ayar)

        def olustur():
            kaydet()
            pk = paket()
            yuvalar = [{"ad": ad, "dosyalar": dosyalar.get(k, [])} for k, ad in enumerate(pk["yuvalar"])]
            if not any(y["dosyalar"] for y in yuvalar):
                messagebox.showinfo("PDF PRO", "Pakete en az bir dosya ekleyin.", parent=p)
                return
            nm = isim.get().strip() or "BELGE"
            ad = OT.ad_uret(sablon.get().strip() or "{GEMI}_{tarih}", None, 1, {"GEMI": nm, "AD": nm, "gemi": nm, "ad": nm})
            ilk = next(d_ for y in yuvalar for d_ in y["dosyalar"])
            y = filedialog.asksaveasfilename(parent=p, title="Paketi kaydet", initialdir=os.path.dirname(ilk),
                                             initialfile=ad, defaultextension=".pdf", filetypes=_A().PDF_TUR)
            if not y:
                return
            try:
                mb = float(hedef_mb.get() or 0)
            except ValueError:
                mb = 0
            p.destroy()

            def bitti(r):
                c, n, eksik = r
                self.sonuc_goster(f"Paket hazır: {n} sayfa · {_A().boyut_yaz(os.path.getsize(c))}", c,
                                  uyari=("Eklenmeyen (boş) bölümler: " + ", ".join(eksik)) if eksik else None)
            self.calistir("Paket oluşturuluyor", lambda il, ip: OT.paket_olustur(yuvalar, os.path.normpath(y), mb, ayrac.get(), True, il, ip),
                          bitti, iptal_edilebilir=True)

        alt = ttk.Frame(p, style="Kart.TFrame", padding=(16, 0, 16, 14))
        alt.pack(fill="x")
        ttk.Checkbutton(alt, text="Bölümler arasına başlık sayfası koy", variable=ayrac, style="Kart.TCheckbutton").pack(side="left")
        ttk.Button(alt, text="Kapat", style="Ikincil.TButton", command=lambda: (kaydet(), p.destroy())).pack(side="right")
        ttk.Button(alt, text="📦 Paketi Oluştur", style="Ana.TButton", command=olustur).pack(side="right", padx=6)
        p.protocol("WM_DELETE_WINDOW", lambda: (kaydet(), p.destroy()))
        tur.current(0)
        tur_degisti()
